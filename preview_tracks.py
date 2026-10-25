"""Generate a handful of random tracks and save them as SVG previews.

Run:  python preview_tracks.py
Outputs:  previews/track_<seed>.svg
"""

from __future__ import annotations

import os

from env.track import generate_track
from render import render_track_svg, save_svg


def main() -> None:
    os.makedirs("previews", exist_ok=True)
    seeds = [1, 7, 42, 123]
    for seed in seeds:
        track = generate_track(seed=seed)
        svg = render_track_svg(track, title=f"Random track  (seed={seed})")
        path = os.path.join("previews", f"track_{seed}.svg")
        save_svg(svg, path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
