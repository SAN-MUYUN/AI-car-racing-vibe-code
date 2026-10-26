"""Random race-track (closed loop) generation.

Two generators are provided:

* :func:`generate_radial_track` -- the simple, always-valid generator. The
  centerline is ``radius(angle)`` around a center (a base radius plus a few
  random sine waves). Because radius is single-valued in the angle, the loop can
  never self-intersect -- but it also can never make a hairpin, a straight or a
  non-convex bend. Used as the ``easy`` difficulty / safe fallback.

* :func:`generate_circuit_track` -- a proper circuit generator. It scatters
  random points, takes their convex hull, spreads them out, displaces the hull
  edges inward/outward (this creates concave bends, hairpins and variety), then
  smooths everything with a Catmull-Rom spline. The result is validated
  (no self-intersection, no undrivably sharp corner) and regenerated on failure.
  This is what produces complicated, real-circuit-style tracks with sharp
  corners.

:func:`generate_track` is the public entry point and dispatches on ``difficulty``.

Pure standard library -- no numpy, no external dependencies.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from env.geometry import (
    catmull_rom_closed,
    convex_hull,
    distance,
    min_turn_radius,
    polyline_self_intersects,
)

Point = tuple[float, float]


@dataclass
class Track:
    """A generated closed-loop track.

    All polylines are lists of ``(x, y)`` points and are *closed* (the last
    point connects back to the first).
    """

    center: list[Point]      # centerline
    inner: list[Point]       # inner edge
    outer: list[Point]       # outer edge
    width: float             # track width (distance between inner and outer)
    seed: int                # seed used to generate this track
    difficulty: str = "easy"

    @property
    def start(self) -> Point:
        """Start/finish position = first centerline point."""
        return self.center[0]

    def start_line(self) -> tuple[Point, Point]:
        """The start/finish line as (inner_edge_point, outer_edge_point)."""
        return self.inner[0], self.outer[0]

    def length(self) -> float:
        """Approximate centerline length (world units)."""
        n = len(self.center)
        return sum(
            distance(self.center[i], self.center[(i + 1) % n]) for i in range(n)
        )

    def bounds(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box (min_x, min_y, max_x, max_y) of the edges."""
        xs = [p[0] for p in self.outer] + [p[0] for p in self.inner]
        ys = [p[1] for p in self.outer] + [p[1] for p in self.inner]
        return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------- #
# Difficulty presets
# --------------------------------------------------------------------------- #
@dataclass
class Difficulty:
    n_points: int            # number of control points (more = more corners)
    spread: float            # bounding box half-size for scattering points
    displacement: float      # how far hull edges are pushed (bend severity)
    min_turn_radius: float   # reject tracks with any corner tighter than this
    min_seg_len: float       # minimum spacing between control points (straights)
    samples_per_seg: int     # spline resolution


# NOTE: the car's minimum turning radius is ~11.4 world units (see car.py).
# The centerline's tightest corner must stay comfortably above that so the car
# can actually follow the corner while staying within the track width. Harder
# difficulties allow *tighter* (but still drivable) corners -> smaller radius.
DIFFICULTIES: dict[str, Difficulty] = {
    # 'easy' is handled by the radial generator; not listed here.
    "medium": Difficulty(
        n_points=9, spread=150.0, displacement=42.0,
        min_turn_radius=26.0, min_seg_len=65.0, samples_per_seg=16,
    ),
    "hard": Difficulty(
        n_points=12, spread=180.0, displacement=60.0,
        min_turn_radius=20.0, min_seg_len=52.0, samples_per_seg=18,
    ),
    "insane": Difficulty(
        n_points=16, spread=210.0, displacement=78.0,
        min_turn_radius=16.0, min_seg_len=44.0, samples_per_seg=20,
    ),
}


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _normalize(dx: float, dy: float) -> Point:
    length = math.hypot(dx, dy)
    if length == 0.0:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def _build_edges(center: list[Point], track_width: float) -> tuple[list[Point], list[Point]]:
    """Offset a centerline by half-width along its local normal to get edges."""
    inner: list[Point] = []
    outer: list[Point] = []
    n = len(center)
    half = track_width / 2.0
    for i in range(n):
        prev_pt = center[(i - 1) % n]
        next_pt = center[(i + 1) % n]
        tx, ty = _normalize(next_pt[0] - prev_pt[0], next_pt[1] - prev_pt[1])
        nx, ny = -ty, tx                                  # left-hand normal
        cx, cy = center[i]
        inner.append((cx - nx * half, cy - ny * half))
        outer.append((cx + nx * half, cy + ny * half))
    return inner, outer


# --------------------------------------------------------------------------- #
# Generator 1: radial (simple, always valid)  -- difficulty "easy"
# --------------------------------------------------------------------------- #
def generate_radial_track(
    seed: int | None = None,
    n_points: int = 240,
    base_radius: float = 120.0,
    track_width: float = 18.0,
    n_waves: int = 3,
    max_wobble: float = 0.35,
) -> Track:
    """Simple, guaranteed-valid loop: centerline = radius(angle) + sine waves."""
    if seed is None:
        seed = random.randrange(2**31)
    rng = random.Random(seed)

    amps = [rng.uniform(0.05, 0.20) * base_radius for _ in range(n_waves)]
    total = sum(amps) or 1.0
    scale = (max_wobble * base_radius) / total
    amps = [a * scale for a in amps]
    phases = [rng.uniform(0.0, 2.0 * math.pi) for _ in range(n_waves)]

    center: list[Point] = []
    for i in range(n_points):
        theta = 2.0 * math.pi * i / n_points
        r = base_radius
        for k in range(n_waves):
            freq = k + 1
            r += amps[k] * math.sin(freq * theta + phases[k])
        center.append((r * math.cos(theta), r * math.sin(theta)))

    inner, outer = _build_edges(center, track_width)
    return Track(center, inner, outer, track_width, seed, difficulty="easy")


# --------------------------------------------------------------------------- #
# Generator 2: convex-hull + spline (complicated circuits)
# --------------------------------------------------------------------------- #
def _spread_points(points: list[Point], min_dist: float, iters: int = 80) -> list[Point]:
    """Push clustered points apart so corners aren't bunched together.

    A simple relaxation: on each pass, any two points closer than ``min_dist``
    are nudged away from each other. Keeps control points well-separated so the
    smoothed track has room for straights between corners.
    """
    pts = [list(p) for p in points]
    n = len(pts)
    for _ in range(iters):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                dx = pts[j][0] - pts[i][0]
                dy = pts[j][1] - pts[i][1]
                d = math.hypot(dx, dy)
                if 1e-9 < d < min_dist:
                    push = (min_dist - d) / 2.0
                    ux, uy = dx / d, dy / d
                    pts[i][0] -= ux * push
                    pts[i][1] -= uy * push
                    pts[j][0] += ux * push
                    pts[j][1] += uy * push
                    moved = True
        if not moved:
            break
    return [(p[0], p[1]) for p in pts]


def _displace_hull(hull: list[Point], rng: random.Random, max_disp: float) -> list[Point]:
    """Insert a displaced midpoint on each hull edge to break convexity.

    This is what creates concave sections, hairpins and sharp corners: each edge
    of the convex hull gets a new midpoint pushed perpendicular to the edge by a
    random (signed) amount, turning a boring convex polygon into a wiggly loop.
    """
    out: list[Point] = []
    n = len(hull)
    for i in range(n):
        a = hull[i]
        b = hull[(i + 1) % n]
        out.append(a)
        mx, my = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        ex, ey = b[0] - a[0], b[1] - a[1]
        nx, ny = _normalize(-ey, ex)                      # edge normal
        disp = rng.uniform(-max_disp, max_disp)
        out.append((mx + nx * disp, my + ny * disp))
    return out


def _generate_circuit_once(
    rng: random.Random, diff: Difficulty, track_width: float
) -> list[Point] | None:
    """One attempt at a circuit centerline. Returns None if invalid."""
    # 1. scatter random points
    raw = [
        (rng.uniform(-diff.spread, diff.spread), rng.uniform(-diff.spread, diff.spread))
        for _ in range(diff.n_points)
    ]
    # 2. convex hull -> non-self-intersecting base loop
    hull = convex_hull(raw)
    if len(hull) < 4:
        return None
    # 3. spread hull points apart (creates room -> straights)
    hull = _spread_points(hull, diff.min_seg_len)
    # 4. displace edges -> concavity, hairpins, variety
    control = _displace_hull(hull, rng, diff.displacement)
    # 5. smooth with a closed Catmull-Rom spline
    center = catmull_rom_closed(control, samples_per_seg=diff.samples_per_seg)

    # 6. validate: no self-intersection
    if polyline_self_intersects(center):
        return None
    # 7. validate: no corner tighter than the car can follow. Measure the
    #    tightest turning radius over a window scaled to the spline resolution.
    window = max(2, diff.samples_per_seg // 2)
    if min_turn_radius(center, step=window) < diff.min_turn_radius:
        return None
    return center


def generate_circuit_track(
    seed: int | None = None,
    difficulty: str = "hard",
    track_width: float = 20.0,
    max_attempts: int = 400,
) -> Track:
    """Generate a complicated circuit-style track (validate-and-retry).

    Raises:
        RuntimeError: if no valid track is found within ``max_attempts`` (rare;
            bump attempts or ease the difficulty if it happens).
    """
    if difficulty not in DIFFICULTIES:
        raise ValueError(
            f"unknown difficulty {difficulty!r}; "
            f"choose from {sorted(DIFFICULTIES)} or 'easy'"
        )
    diff = DIFFICULTIES[difficulty]

    if seed is None:
        seed = random.randrange(2**31)

    # Each attempt uses a derived sub-seed so a given `seed` is reproducible but
    # we can still retry deterministically until a valid track appears.
    for attempt in range(max_attempts):
        rng = random.Random((seed * 1_000_003) + attempt)
        center = _generate_circuit_once(rng, diff, track_width)
        if center is not None:
            inner, outer = _build_edges(center, track_width)
            return Track(center, inner, outer, track_width, seed, difficulty)

    raise RuntimeError(
        f"could not generate a valid '{difficulty}' track for seed {seed} "
        f"in {max_attempts} attempts; try a different seed or lower difficulty."
    )


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def generate_track(
    seed: int | None = None,
    difficulty: str = "easy",
    track_width: float | None = None,
) -> Track:
    """Generate a track at the requested difficulty.

    ``difficulty='easy'`` uses the simple radial generator; ``'medium'``,
    ``'hard'`` and ``'insane'`` use the circuit generator with increasingly
    many, sharper corners.
    """
    if difficulty == "easy":
        return generate_radial_track(
            seed=seed, track_width=track_width if track_width is not None else 18.0
        )
    return generate_circuit_track(
        seed=seed,
        difficulty=difficulty,
        track_width=track_width if track_width is not None else 20.0,
    )
