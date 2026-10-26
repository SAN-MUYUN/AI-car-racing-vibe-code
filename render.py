"""Dependency-free SVG rendering of tracks, cars and sensor rays.

Everything is written as plain SVG text so it renders crisply in a browser,
file explorer, or directly on GitHub -- no matplotlib or numpy required.

Two things can be produced:

* :func:`render_track_svg` -- a static picture of a track (optionally with a
  car and its sensor rays drawn on top).
* :func:`render_lap_svg` -- an animated lap: the car moves along a recorded
  trajectory using native SVG ``<animateMotion>`` (press play in any browser).
"""

from __future__ import annotations

import math

from env.track import Track

Point = tuple[float, float]

_PAD = 30.0  # padding around the track, in world units


def _viewbox(track: Track) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = track.bounds()
    w = (max_x - min_x) + 2 * _PAD
    h = (max_y - min_y) + 2 * _PAD
    return min_x - _PAD, min_y - _PAD, w, h


def _path_d(points: list[Point], close: bool = True) -> str:
    d = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    if close:
        d += " Z"
    return d


def _car_polygon(x: float, y: float, heading: float, size: float = 7.0) -> str:
    """A small triangle pointing in the heading direction."""
    tip = (x + math.cos(heading) * size * 1.6, y + math.sin(heading) * size * 1.6)
    left = (
        x + math.cos(heading + 2.5) * size,
        y + math.sin(heading + 2.5) * size,
    )
    right = (
        x + math.cos(heading - 2.5) * size,
        y + math.sin(heading - 2.5) * size,
    )
    pts = " ".join(f"{px:.2f},{py:.2f}" for px, py in (tip, left, right))
    return f'<polygon points="{pts}" fill="#e63946" stroke="#7a1521" stroke-width="1"/>'


def _track_body(track: Track) -> str:
    """The shared track drawing (asphalt band, edges, centerline, start line)."""
    outer_d = _path_d(track.outer)
    inner_d = _path_d(track.inner)
    center_d = _path_d(track.center)

    # Asphalt = outer filled, inner punched out via even-odd fill rule.
    asphalt = (
        f'<path d="{outer_d} {inner_d}" fill="#44474d" '
        f'fill-rule="evenodd" stroke="none"/>'
    )
    outer_edge = f'<path d="{outer_d}" fill="none" stroke="#f1f1f1" stroke-width="1.5"/>'
    inner_edge = f'<path d="{inner_d}" fill="none" stroke="#f1f1f1" stroke-width="1.5"/>'
    centerline = (
        f'<path d="{center_d}" fill="none" stroke="#ffd166" '
        f'stroke-width="1" stroke-dasharray="6 6" opacity="0.8"/>'
    )

    (ix, iy), (ox, oy) = track.start_line()
    start_line = (
        f'<line x1="{ix:.2f}" y1="{iy:.2f}" x2="{ox:.2f}" y2="{oy:.2f}" '
        f'stroke="#06d6a0" stroke-width="4"/>'
    )
    return "\n  ".join([asphalt, outer_edge, inner_edge, centerline, start_line])


def render_track_svg(
    track: Track,
    car: tuple[float, float, float] | None = None,
    rays: list[Point] | None = None,
    title: str | None = None,
) -> str:
    """Render a static track. ``car`` is ``(x, y, heading)``; ``rays`` is a list
    of ray *endpoints* drawn from the car position."""
    vb_x, vb_y, vb_w, vb_h = _viewbox(track)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}" '
        f'width="700" font-family="sans-serif">',
        f'<rect x="{vb_x:.2f}" y="{vb_y:.2f}" width="{vb_w:.2f}" '
        f'height="{vb_h:.2f}" fill="#1a1d23"/>',
        _track_body(track),
    ]

    if car is not None:
        cx, cy, heading = car[0], car[1], car[2]   # tolerate extra fields (slip)
        if rays:
            for rx, ry in rays:
                parts.append(
                    f'<line x1="{cx:.2f}" y1="{cy:.2f}" x2="{rx:.2f}" y2="{ry:.2f}" '
                    f'stroke="#4cc9f0" stroke-width="0.8" opacity="0.7"/>'
                )
        parts.append(_car_polygon(cx, cy, heading))

    if title:
        parts.append(
            f'<text x="{vb_x + 8:.2f}" y="{vb_y + 20:.2f}" fill="#f1f1f1" '
            f'font-size="14">{title}</text>'
        )

    parts.append("</svg>")
    return "\n  ".join(parts)


def render_lap_svg(
    track: Track,
    trajectory: list,
    lap_time: float | None = None,
    duration_s: float = 8.0,
    max_frames: int = 240,
    slip_threshold: float = 1e-3,
) -> str:
    """Render an animated lap that shows the car's *true heading*.

    ``trajectory`` is a list of ``(x, y, heading[, slip])`` samples. Instead of
    ``<animateMotion rotate="auto">`` (which forces the sprite to face its path
    and so hides any slide), the car's ``transform`` (translate + rotate) is
    keyframe-animated directly from the recorded heading. When the car slides,
    its heading differs from its direction of travel, so you can actually *see*
    it pointing one way while sliding another -- and it flashes while slipping.
    """
    vb_x, vb_y, vb_w, vb_h = _viewbox(track)

    # Normalize samples to (x, y, heading, slip) and downsample to max_frames.
    samples = []
    for s in trajectory:
        if len(s) >= 4:
            x, y, h, slip = s[0], s[1], s[2], s[3]
        else:
            x, y, h = s[0], s[1], s[2]
            slip = 0.0
        samples.append((x, y, h, slip))
    if len(samples) > max_frames:
        step = len(samples) / max_frames
        samples = [samples[int(i * step)] for i in range(max_frames)]
    n = len(samples)
    if n < 2:
        samples = samples * 2
        n = 2

    # Build keyframe streams. We animate position and heading separately using
    # two nested groups (an SVG <animateTransform> carries a single transform
    # type), sharing the same keyTimes so they stay in sync.
    times = ";".join(f"{i/(n-1):.4f}" for i in range(n))
    translates = ";".join(f"{x:.2f} {y:.2f}" for x, y, _, _ in samples)
    rotates = ";".join(f"{math.degrees(h):.1f}" for _, _, h, _ in samples)
    # flash to a bright colour while slipping, normal red otherwise
    fills = ";".join(
        "#ffd166" if slip > slip_threshold else "#e63946" for _, _, _, slip in samples
    )

    title = "Lap replay"
    if lap_time is not None:
        title += f"  -  {lap_time:.2f}s"
    title += "   (car flashes yellow while sliding)"

    dur = f"{duration_s:.1f}s"
    anim = (
        f'dur="{dur}" repeatCount="indefinite" calcMode="discrete" '
        f'keyTimes="{times}"'
    )
    # car drawn at the origin, pointing +x; outer g translates, inner g rotates.
    car_shape = (
        '<polygon points="11,0 -6,5 -6,-5" fill="#e63946" '
        'stroke="#7a1521" stroke-width="1">'
        f'<animate attributeName="fill" {anim} values="{fills}"/>'
        '</polygon>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x:.2f} {vb_y:.2f} {vb_w:.2f} {vb_h:.2f}" '
        f'width="700" font-family="sans-serif">\n'
        f'  <rect x="{vb_x:.2f}" y="{vb_y:.2f}" width="{vb_w:.2f}" '
        f'height="{vb_h:.2f}" fill="#1a1d23"/>\n'
        f'  {_track_body(track)}\n'
        f'  <g>\n'
        f'    <animateTransform attributeName="transform" type="translate" '
        f'{anim} values="{translates}"/>\n'
        f'    <g>\n'
        f'      <animateTransform attributeName="transform" type="rotate" '
        f'{anim} values="{rotates}"/>\n'
        f'      {car_shape}\n'
        f'    </g>\n'
        f'  </g>\n'
        f'  <text x="{vb_x + 8:.2f}" y="{vb_y + 20:.2f}" fill="#f1f1f1" '
        f'font-size="13">{title}</text>\n'
        f'</svg>\n'
    )


def save_svg(svg: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
