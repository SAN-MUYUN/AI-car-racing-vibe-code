"""AI Car Racing -- command-line entry point.

Run a policy file around a randomly generated track and report the lap time.
A static image (car + sensor rays at the final frame) and an animated replay
are written to ``output/`` as SVG.

Examples
--------
    python main.py policies/example_policy.py
    python main.py policies/example_policy.py --seed 42
"""

from __future__ import annotations

import argparse
import os

from render import render_lap_svg, render_track_svg, save_svg
from runner.loader import PolicyError, load_policy
from runner.runner import run_policy


def main() -> int:
    parser = argparse.ArgumentParser(description="Race a Python policy around a track.")
    parser.add_argument("policy", help="path to your policy .py file")
    parser.add_argument("--seed", type=int, default=None,
                        help="track seed (same seed = same track)")
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard", "insane",
                 "circuit", "circuit-medium", "circuit-hard", "circuit-insane"],
        default="easy",
        help="track type (default: easy). medium/hard/insane = smooth circuit; "
             "circuit[-medium/-hard/-insane] = segment-based Silverstone-style "
             "circuit (straights, hairpins, chicanes, sweepers).")
    parser.add_argument("--laps", type=int, default=1,
                        help="number of laps to complete (default: 1)")
    parser.add_argument("--realtime", action="store_true",
                        help="make the replay play at speed-accurate pace "
                             "(clip length proportional to real lap time) instead "
                             "of the default fixed ~8s clip.")
    parser.add_argument("--replay-scale", type=float, default=5.0,
                        help="with --realtime, real seconds per clip second "
                             "(default 5; higher = shorter clips).")
    parser.add_argument("--outdir", default="output", help="where to write SVGs")
    args = parser.parse_args()

    # --- load the user's policy ----------------------------------------------
    try:
        policy = load_policy(args.policy)
    except PolicyError as exc:
        print(f"[policy error]\n{exc}")
        return 1

    # --- race ----------------------------------------------------------------
    result, env = run_policy(
        policy, seed=args.seed, difficulty=args.difficulty, laps=args.laps
    )

    # --- report --------------------------------------------------------------
    print(f"track seed : {env.track.seed}")
    print(f"laps       : {result.laps_requested}")
    if result.reason == "error":
        print(f"result     : ERROR\n{result.error}")
    elif result.finished:
        lap_word = "lap" if result.laps_completed == 1 else "laps"
        print(f"result     : RACE COMPLETE ({result.laps_completed} {lap_word})")
    else:
        print(f"result     : did not finish ({result.reason}) "
              f"after {result.laps_completed}/{result.laps_requested} laps")

    # per-lap splits (best lap marked)
    if result.lap_times:
        best = result.best_lap
        for i, t in enumerate(result.lap_times, start=1):
            mark = "  <- best" if t == best else ""
            print(f"  lap {i}    : {t:.2f}s{mark}")
        if result.laps_requested > 1 and result.total_time is not None:
            print(f"  total    : {result.total_time:.2f}s")

    print(f"steps      : {result.steps}")
    print(f"reward     : {result.total_reward:.1f}")

    # --- render --------------------------------------------------------------
    os.makedirs(args.outdir, exist_ok=True)

    tag = f"{env.track.difficulty}_{env.track.seed}"
    final_pose = result.trajectory[-1] if result.trajectory else None
    still = render_track_svg(
        env.track,
        car=final_pose,
        rays=env.ray_endpoints,
        title=f"{env.track.difficulty}  seed={env.track.seed}  "
              + (
                  f"best={result.best_lap:.2f}s ({result.laps_completed}/{result.laps_requested} laps)"
                  if result.best_lap else result.reason
              ),
    )
    still_path = os.path.join(args.outdir, f"race_{tag}.svg")
    save_svg(still, still_path)
    print(f"wrote      : {still_path}")

    if result.trajectory and len(result.trajectory) > 2:
        anim = render_lap_svg(
            env.track,
            result.trajectory,
            lap_time=result.lap_time,
            realtime=args.realtime,
            real_time_s=env.state.time,
            realtime_scale=args.replay_scale,
        )
        anim_path = os.path.join(args.outdir, f"replay_{tag}.svg")
        save_svg(anim, anim_path)
        mode = "real-time pace" if args.realtime else "fixed 8s clip"
        print(f"wrote      : {anim_path}  ({mode})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
