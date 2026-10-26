"""Random race-track (closed loop) generation.

The track is defined as a *centerline* given in polar form: for each angle
``theta`` around a center point we compute a radius ``r(theta)``. Because the
radius is a single-valued function of the angle, the resulting closed curve can
never intersect itself -- which guarantees a valid, drivable loop every time.

``r(theta)`` is a base radius plus a few low-frequency sine waves with random
amplitudes and phases. Low frequencies + bounded total amplitude keep the bends
smooth and drivable (no kinks, no pinch points).

Pure standard library -- no numpy, no external dependencies.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


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

    @property
    def start(self) -> Point:
        """Start/finish position = first centerline point."""
        return self.center[0]

    def start_line(self) -> tuple[Point, Point]:
        """The start/finish line as (inner_edge_point, outer_edge_point)."""
        return self.inner[0], self.outer[0]

    def bounds(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box (min_x, min_y, max_x, max_y) of the edges."""
        xs = [p[0] for p in self.outer] + [p[0] for p in self.inner]
        ys = [p[1] for p in self.outer] + [p[1] for p in self.inner]
        return min(xs), min(ys), max(xs), max(ys)


def _normalize(dx: float, dy: float) -> Point:
    length = math.hypot(dx, dy)
    if length == 0.0:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def generate_track(
    seed: int | None = None,
    n_points: int = 240,
    base_radius: float = 120.0,
    track_width: float = 18.0,
    n_waves: int = 3,
    max_wobble: float = 0.35,
) -> Track:
    """Generate a random closed-loop track.

    Args:
        seed: RNG seed. ``None`` picks a random seed (recorded on the result).
        n_points: number of samples around the loop (resolution).
        base_radius: average radius of the centerline.
        track_width: distance between the inner and outer edges.
        n_waves: how many sine harmonics shape the loop (more = wigglier).
        max_wobble: cap on total wobble as a fraction of ``base_radius``.
            Values above ~0.45 risk very tight turns, so we keep it bounded.

    Returns:
        A :class:`Track` with centerline, inner edge and outer edge.
    """
    if seed is None:
        seed = random.randrange(2**31)
    rng = random.Random(seed)

    # --- random, bounded sine harmonics -------------------------------------
    amps = [rng.uniform(0.05, 0.20) * base_radius for _ in range(n_waves)]
    total = sum(amps) or 1.0
    scale = (max_wobble * base_radius) / total          # cap the total wobble
    amps = [a * scale for a in amps]
    phases = [rng.uniform(0.0, 2.0 * math.pi) for _ in range(n_waves)]

    # --- centerline in polar form -------------------------------------------
    center: list[Point] = []
    for i in range(n_points):
        theta = 2.0 * math.pi * i / n_points
        r = base_radius
        for k in range(n_waves):
            freq = k + 1                                # 1, 2, 3, ... (low freq)
            r += amps[k] * math.sin(freq * theta + phases[k])
        center.append((r * math.cos(theta), r * math.sin(theta)))

    # --- offset to inner/outer edges along the local normal -----------------
    inner: list[Point] = []
    outer: list[Point] = []
    n = len(center)
    half = track_width / 2.0
    for i in range(n):
        prev_pt = center[(i - 1) % n]
        next_pt = center[(i + 1) % n]
        tx, ty = _normalize(next_pt[0] - prev_pt[0], next_pt[1] - prev_pt[1])
        # left-hand normal of the tangent
        nx, ny = -ty, tx
        cx, cy = center[i]
        inner.append((cx - nx * half, cy - ny * half))
        outer.append((cx + nx * half, cy + ny * half))

    return Track(
        center=center,
        inner=inner,
        outer=outer,
        width=track_width,
        seed=seed,
    )
