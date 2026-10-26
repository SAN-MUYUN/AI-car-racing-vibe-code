"""Small 2D geometry helpers used by the environment.

Pure standard library -- no numpy.
"""

from __future__ import annotations

import math

Point = tuple[float, float]
Segment = tuple[Point, Point]


def segments_from_loop(points: list[Point]) -> list[Segment]:
    """Turn a closed polyline into a list of edge segments (last joins first)."""
    n = len(points)
    return [(points[i], points[(i + 1) % n]) for i in range(n)]


def ray_segment_intersection(
    ox: float, oy: float, dx: float, dy: float, seg: Segment
) -> float | None:
    """Distance from ray origin to its intersection with a segment, or None.

    Ray:      P = (ox, oy) + t * (dx, dy),  t >= 0
    Segment:  from a to b
    Returns the ray parameter ``t`` (== distance if (dx,dy) is unit length).
    """
    (ax, ay), (bx, by) = seg
    ex, ey = bx - ax, by - ay           # segment direction

    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None                     # parallel

    # Solve  origin + t*d = a + u*e
    wx, wy = ax - ox, ay - oy
    t = (wx * ey - wy * ex) / denom     # along the ray
    u = (wx * dy - wy * dx) / denom     # along the segment

    if t >= 0.0 and 0.0 <= u <= 1.0:
        return t
    return None


def ray_cast(
    ox: float, oy: float, angle: float, segments: list[Segment], max_dist: float
) -> float:
    """Cast a ray and return the distance to the nearest segment hit (<= max_dist)."""
    dx, dy = math.cos(angle), math.sin(angle)
    best = max_dist
    for seg in segments:
        t = ray_segment_intersection(ox, oy, dx, dy, seg)
        if t is not None and t < best:
            best = t
    return best


def point_in_polygon(px: float, py: float, poly: list[Point]) -> bool:
    """Even-odd ray-casting point-in-polygon test."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py):
            x_cross = (xj - xi) * (py - yi) / (yj - yi + 1e-18) + xi
            if px < x_cross:
                inside = not inside
        j = i
    return inside


def dist_point_to_segment(px: float, py: float, a: Point, b: Point) -> float:
    """Shortest distance from point (px,py) to segment a-b."""
    ax, ay = a
    bx, by = b
    ex, ey = bx - ax, by - ay
    len_sq = ex * ex + ey * ey
    if len_sq < 1e-18:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * ex + (py - ay) * ey) / len_sq
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * ex, ay + t * ey
    return math.hypot(px - cx, py - cy)


def dist_to_polyline(px: float, py: float, loop: list[Point]) -> float:
    """Shortest distance from a point to a closed polyline (the centerline)."""
    best = float("inf")
    n = len(loop)
    for i in range(n):
        d = dist_point_to_segment(px, py, loop[i], loop[(i + 1) % n])
        if d < best:
            best = d
    return best


def on_track_centerline(px: float, py: float, center: list[Point], half_width: float) -> bool:
    """True if the point is within ``half_width`` of the centerline.

    This is an exact test for a constant-width ribbon track and -- unlike a
    point-in-polygon test -- has no degeneracies at axis-aligned coordinates.
    """
    return dist_to_polyline(px, py, center) <= half_width


def segments_cross(p1: Point, p2: Point, p3: Point, p4: Point) -> bool:
    """True if segment p1-p2 intersects segment p3-p4."""
    def ccw(a: Point, b: Point, c: Point) -> bool:
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    return (ccw(p1, p3, p4) != ccw(p2, p3, p4)) and (
        ccw(p1, p2, p3) != ccw(p1, p2, p4)
    )


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])
