"""Segment-based circuit generator (Silverstone-style layouts).

Unlike the smooth-blob generators in ``track.py``, this builds a track from a
*sequence of features* -- straights, corners, chicanes and fast sweepers -- laid
end to end. That gives distinct corner types (slow hairpins, quick flicks, fast
sweepers) connected by real straights, which is what makes a layout feel like a
proper racing circuit rather than a rounded loop.

Loop closure
------------
A random feature sequence won't naturally end where it started. We close it in
two stages:

1. **Heading closure (exact, by construction):** the signed corner angles are
   normalized so they sum to exactly +/-360 degrees. Integrating heading then
   returns to the start heading automatically, with no kink at the line.

2. **Position closure (iterative nudge):** after laying out the turtle, the
   endpoint generally misses the start by some ``(dx, dy)``. We treat the
   segment lengths (and, if needed, corner radii) as adjustable and take a few
   Gauss-Newton steps -- using a finite-difference Jacobian -- to drive that gap
   to ~0. Corrections are spread across straights first so the designed corner
   character is preserved.

Finally the closed centerline is validated (no self-intersection, no corner
tighter than the car can drive) and regenerated on failure.

Pure standard library -- no numpy.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

Point = tuple[float, float]


# --------------------------------------------------------------------------- #
# Feature vocabulary
# --------------------------------------------------------------------------- #
# A segment is one of:
#   ("straight", length)
#   ("arc", signed_angle_radians, radius)
# Chicanes/sweepers are just arcs with particular angle/radius choices; we build
# them as pairs/singletons of arcs so they share the same integration code.
Segment = tuple


@dataclass
class CircuitStyle:
    """Tunables for how technical / complex the generated circuit is."""
    n_corners: int                 # number of corners around the lap
    straight_min: float            # shortest straight (world units)
    straight_max: float            # longest straight
    corner_radius_min: float       # tightest corner radius allowed
    corner_radius_max: float       # most open corner radius
    chicane_chance: float          # probability a "corner slot" becomes a chicane
    sweeper_chance: float          # probability a slot becomes a fast sweeper


STYLES: dict[str, CircuitStyle] = {
    "medium": CircuitStyle(
        n_corners=7, straight_min=70.0, straight_max=180.0,
        corner_radius_min=28.0, corner_radius_max=90.0,
        chicane_chance=0.15, sweeper_chance=0.25,
    ),
    "hard": CircuitStyle(
        n_corners=10, straight_min=55.0, straight_max=220.0,
        corner_radius_min=20.0, corner_radius_max=80.0,
        chicane_chance=0.25, sweeper_chance=0.30,
    ),
    "insane": CircuitStyle(
        n_corners=13, straight_min=45.0, straight_max=260.0,
        corner_radius_min=16.0, corner_radius_max=70.0,
        chicane_chance=0.35, sweeper_chance=0.30,
    ),
}


# --------------------------------------------------------------------------- #
# Step 1: design a feature sequence whose corner angles sum to +/-360 deg
# --------------------------------------------------------------------------- #
def _design_sequence(rng: random.Random, style: CircuitStyle) -> list[Segment]:
    """Build a randomized straight/arc sequence with total turning = +/-360 deg."""
    direction = rng.choice((1.0, -1.0))        # overall lap direction (CW/CCW)

    # Decide each corner's "slot" type and a raw turn angle, then normalize the
    # arc angles so their signed sum is exactly direction*2*pi.
    corner_specs: list[tuple[str, float, float]] = []   # (kind, raw_angle, radius)
    for _ in range(style.n_corners):
        roll = rng.random()
        radius = rng.uniform(style.corner_radius_min, style.corner_radius_max)
        if roll < style.chicane_chance:
            # chicane: a quick pair, net ~0 turning (handled specially below)
            corner_specs.append(("chicane", 0.0, style.corner_radius_min * 1.3))
        elif roll < style.chicane_chance + style.sweeper_chance:
            # fast sweeper: gentle angle, big radius
            ang = rng.uniform(math.radians(25), math.radians(70))
            corner_specs.append(("sweeper", ang, max(radius, style.corner_radius_max * 0.8)))
        else:
            # normal corner: anything from a bend to a hairpin
            ang = rng.uniform(math.radians(40), math.radians(170))
            corner_specs.append(("corner", ang, radius))

    # Assign a sign to each turning corner, biased toward `direction`, then
    # normalize so the signed angles sum to exactly direction * 2*pi.
    turning = [c for c in corner_specs if c[0] != "chicane"]
    signs = []
    for _ in turning:
        # ~75% follow the lap direction, 25% go against (adds S-sections)
        signs.append(direction if rng.random() < 0.75 else -direction)
    raw_signed = [s * c[1] for s, c in zip(signs, turning)]
    current_sum = sum(raw_signed)
    target = direction * 2.0 * math.pi
    # scale the signed angles uniformly so they sum to the target
    if abs(current_sum) < 1e-6:
        # degenerate: force all to follow direction
        raw_signed = [direction * c[1] for c in turning]
        current_sum = sum(raw_signed)
    scale = target / current_sum
    scaled = [a * scale for a in raw_signed]

    # Build the actual segment list: straight, feature, straight, feature, ...
    segments: list[Segment] = []
    ti = 0                                     # index into turning/scaled
    for kind, _, radius in corner_specs:
        # a straight before each feature
        segments.append(("straight", rng.uniform(style.straight_min, style.straight_max)))
        if kind == "chicane":
            # left-right flick that nets ~0 turning
            flick = rng.uniform(math.radians(18), math.radians(32))
            segments.append(("arc", direction * flick, radius))
            segments.append(("arc", -direction * flick, radius))
        else:
            angle = scaled[ti]
            ti += 1
            segments.append(("arc", angle, radius))
    # one final straight to vary the start/finish placement
    segments.append(("straight", rng.uniform(style.straight_min, style.straight_max)))
    return segments


# --------------------------------------------------------------------------- #
# Step 2: integrate the turtle -> endpoint, and sample points
# --------------------------------------------------------------------------- #
def _straight_lengths(segments: list[Segment]) -> list[int]:
    """Indices of straight segments (the 'free' parameters we nudge first)."""
    return [i for i, s in enumerate(segments) if s[0] == "straight"]


def _sign(v: float) -> float:
    return 1.0 if v >= 0 else -1.0


def _sample_points(segments: list[Segment], samples_per_unit: float = 0.25) -> list[Point]:
    """Sample the centerline polyline from the segment list, starting at origin.

    ``samples_per_unit`` controls resolution along straights and arcs. A value of
    0 yields just the segment endpoints (fast, used for closure math).
    """
    pts: list[Point] = [(0.0, 0.0)]
    x = y = h = 0.0
    for seg in segments:
        if seg[0] == "straight":
            length = seg[1]
            n = max(1, int(length * samples_per_unit)) if samples_per_unit else 1
            for k in range(1, n + 1):
                t = length * k / n
                pts.append((x + math.cos(h) * t, y + math.sin(h) * t))
            x += math.cos(h) * length
            y += math.sin(h) * length
        else:
            _, angle, radius = seg
            if abs(angle) < 1e-9:
                continue
            arclen = abs(angle) * radius
            n = max(1, int(arclen * samples_per_unit)) if samples_per_unit else 1
            s = _sign(angle)
            # arc centre, to the left (angle>0) or right (angle<0) of heading
            cx = x - math.sin(h) * radius * s
            cy = y + math.cos(h) * radius * s
            for k in range(1, n + 1):
                a = angle * k / n
                px = cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a)
                py = cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)
                pts.append((px, py))
            # advance exact end pose
            ex = cx + (x - cx) * math.cos(angle) - (y - cy) * math.sin(angle)
            ey = cy + (x - cx) * math.sin(angle) + (y - cy) * math.cos(angle)
            x, y, h = ex, ey, h + angle
    return pts


# --------------------------------------------------------------------------- #
# Step 3: close the position gap with a few Gauss-Newton nudges
# --------------------------------------------------------------------------- #
def _closure_error(segments: list[Segment]) -> tuple[float, float]:
    pts = _sample_points(segments, samples_per_unit=0.0)
    ex, ey = pts[-1]
    return ex, ey                              # want this to be (0, 0)


def _close_loop(segments: list[Segment], iters: int = 40) -> list[Segment] | None:
    """Adjust straight lengths (then radii) to drive the endpoint back to (0,0).

    Returns the closed segment list, or None if it could not converge.
    """
    segs = [list(s) for s in segments]
    free = _straight_lengths(segments)         # tweak straights first (free lengths)
    if not free:
        return None

    def endpoint(sl):
        return _closure_error([tuple(s) for s in sl])

    for _ in range(iters):
        ex, ey = endpoint(segs)
        err = math.hypot(ex, ey)
        if err < 0.5:
            return [tuple(s) for s in segs]

        # finite-difference Jacobian: d(ex,ey)/d(length_i) for each free straight
        eps = 1.0
        J = []                                 # 2 x len(free)
        base = (ex, ey)
        cols = []
        for idx in free:
            segs[idx][1] += eps
            ex2, ey2 = endpoint(segs)
            segs[idx][1] -= eps
            cols.append(((ex2 - base[0]) / eps, (ey2 - base[1]) / eps))
        # Solve least-squares  J * d = -base   (minimum-norm via normal equations)
        # Build 2x2 (J J^T) since we have 2 residuals and many params; use the
        # pseudo-inverse form d = J^T (J J^T)^-1 (-base).
        a = sum(c[0] * c[0] for c in cols)     # J J^T [0][0]
        b = sum(c[0] * c[1] for c in cols)     # [0][1] = [1][0]
        d = sum(c[1] * c[1] for c in cols)     # [1][1]
        det = a * d - b * b
        if abs(det) < 1e-9:
            break
        rx, ry = -base[0], -base[1]
        # (J J^T)^-1 * r
        m0 = (d * rx - b * ry) / det
        m1 = (-b * rx + a * ry) / det
        # step on each straight, damped, and keep lengths positive
        step = 0.7
        for col, idx in zip(cols, free):
            delta = (col[0] * m0 + col[1] * m1) * step
            segs[idx][1] = max(15.0, segs[idx][1] + delta)

    ex, ey = endpoint(segs)
    if math.hypot(ex, ey) < 1.5:
        return [tuple(s) for s in segs]
    return None


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _self_intersects(pts: list[Point]) -> bool:
    from env.geometry import polyline_self_intersects
    return polyline_self_intersects(pts)


def _min_turn_radius(pts: list[Point], step: int) -> float:
    from env.geometry import min_turn_radius
    return min_turn_radius(pts, step=step)


# --------------------------------------------------------------------------- #
# Public: generate a closed segment-based centerline
# --------------------------------------------------------------------------- #
def generate_circuit_centerline(
    seed: int,
    style_name: str = "hard",
    min_drivable_radius: float = 13.0,
    samples_per_unit: float = 0.3,
    max_attempts: int = 300,
) -> tuple[list[Point], int]:
    """Return (closed centerline points, seed) for a segment-based circuit.

    Raises RuntimeError if no valid layout is found within ``max_attempts``.
    """
    style = STYLES[style_name]
    for attempt in range(max_attempts):
        rng = random.Random((seed * 1_000_003) + attempt)
        segments = _design_sequence(rng, style)
        closed = _close_loop(segments)
        if closed is None:
            continue
        pts = _sample_points(closed, samples_per_unit=samples_per_unit)
        if len(pts) < 9:
            continue
        # The heading closes exactly (angles sum to 2*pi); only a small position
        # gap remains. Distribute that residual gap smoothly over all points so
        # the polyline closes exactly with no notch at the start/finish line.
        pts = pts[:-1]                         # drop the near-duplicate end point
        n = len(pts)
        gap_x = pts[-1][0] + (pts[-1][0] - pts[-2][0]) - pts[0][0]
        gap_y = pts[-1][1] + (pts[-1][1] - pts[-2][1]) - pts[0][1]
        pts = [
            (p[0] - gap_x * i / n, p[1] - gap_y * i / n)
            for i, p in enumerate(pts)
        ]
        if len(pts) < 8:
            continue
        if _self_intersects(pts):
            continue
        window = max(2, int(len(pts) / 60))
        if _min_turn_radius(pts, window) < min_drivable_radius:
            continue
        return pts, seed
    raise RuntimeError(
        f"could not generate a valid '{style_name}' circuit for seed {seed} "
        f"in {max_attempts} attempts; try a different seed."
    )
