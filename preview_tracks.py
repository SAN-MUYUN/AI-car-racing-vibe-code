"""Generate random tracks and save them as SVG previews.

Run:
    python preview_tracks.py                      # a mix of difficulties
    python preview_tracks.py --difficulty hard    # only hard tracks
    python preview_tracks.py --difficulty insane --seeds 1 2 3

Outputs:  previews/track_<difficulty>_<seed>.svg
"""

from __future__ import annotations

import argparse
import os

from env.track import generate_track
from render import render_track_svg, save_svg


def main() -> None:
    parser = argparse.ArgumentParser(description="Render random track previews.")
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard", "insane", "all"],
        default="all",
        help="which difficulty to preview (default: a mix of all)",
    )
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=[1, 7, 42, 123],
        help="track seeds to render",
    )
    args = parser.parse_args()

    os.makedirs("previews", exist_ok=True)
    difficulties = (
        ["easy", "medium", "hard", "insane"]
        if args.difficulty == "all"
        else [args.difficulty]
    )

    for diff in difficulties:
        for seed in args.seeds:
            track = generate_track(seed=seed, difficulty=diff)
            svg = render_track_svg(
                track,
                title=f"{diff.upper()}  seed={seed}  len={track.length():.0f}",
            )
            path = os.path.join("previews", f"track_{diff}_{seed}.svg")
            save_svg(svg, path)
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
