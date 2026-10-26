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
<<<<<<< HEAD
=======


def convex_hull(points: list[Point]) -> list[Point]:
    """Andrew's monotone-chain convex hull. Returns the hull in CCW order."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def polyline_self_intersects(loop: list[Point]) -> bool:
    """True if any two non-adjacent edges of a closed polyline cross.

    Used to reject invalid generated tracks before they are used.
    """
    n = len(loop)
    segs = [(loop[i], loop[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        a1, a2 = segs[i]
        # compare with later segments, skipping neighbours (which share a point)
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue  # first and last segments are adjacent on a loop
            b1, b2 = segs[j]
            if segments_cross(a1, a2, b1, b2):
                return True
    return False


def catmull_rom_closed(points: list[Point], samples_per_seg: int = 12) -> list[Point]:
    """Smooth a closed loop of control points with a Catmull-Rom spline.

    Produces a dense, smooth closed polyline passing through every control
    point. ``samples_per_seg`` controls resolution (higher = smoother).
    """
    n = len(points)
    if n < 3:
        return list(points)

    out: list[Point] = []
    for i in range(n):
        p0 = points[(i - 1) % n]
        p1 = points[i]
        p2 = points[(i + 1) % n]
        p3 = points[(i + 2) % n]
        for s in range(samples_per_seg):
            t = s / samples_per_seg
            t2 = t * t
            t3 = t2 * t
            # standard Catmull-Rom basis (tension 0.5)
            x = 0.5 * (
                (2 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            out.append((x, y))
    return out


def min_corner_angle(loop: list[Point], step: int = 1) -> float:
    """Smallest turn angle (radians) between consecutive segments of a loop.

    A small value means a very sharp kink. Used to reject undrivable tracks.
    Returns pi (straight everywhere) for degenerate input.
    """
    n = len(loop)
    if n < 3:
        return math.pi
    sharpest = math.pi
    for i in range(n):
        a = loop[(i - step) % n]
        b = loop[i]
        c = loop[(i + step) % n]
        v1x, v1y = b[0] - a[0], b[1] - a[1]
        v2x, v2y = c[0] - b[0], c[1] - b[1]
        n1 = math.hypot(v1x, v1y)
        n2 = math.hypot(v2x, v2y)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        dot = (v1x * v2x + v1y * v2y) / (n1 * n2)
        dot = max(-1.0, min(1.0, dot))
        turn = math.acos(dot)              # 0 = straight, pi = U-turn
        interior = math.pi - turn          # interior angle at the vertex
        if interior < sharpest:
            sharpest = interior
    return sharpest


def min_turn_radius(loop: list[Point], step: int = 3) -> float:
    """Smallest turning radius along a closed loop (world units).

    Estimated as the circumradius of each triangle of points spaced ``step``
    apart. A small value means a very tight corner. Used to reject tracks the
    car physically cannot follow (corners tighter than its turning circle).
    """
    n = len(loop)
    if n < 3:
        return float("inf")
    best = float("inf")
    for i in range(n):
        a = loop[(i - step) % n]
        b = loop[i]
        c = loop[(i + step) % n]
        ab = math.hypot(b[0] - a[0], b[1] - a[1])
        bc = math.hypot(c[0] - b[0], c[1] - b[1])
        ca = math.hypot(a[0] - c[0], a[1] - c[1])
        area = abs(
            (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        ) / 2.0
        if area < 1e-6:
            continue                       # (near-)collinear: ~straight, huge R
        r = (ab * bc * ca) / (4.0 * area)
        if r < best:
            best = r
    return best
>>>>>>> 525c6c7a47049dbe4fdad4e6e1e8b4a4a8533d29
