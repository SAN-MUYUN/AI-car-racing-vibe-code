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
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "insane"],
                        default="easy",
                        help="track complexity (default: easy). "
                             "medium/hard/insane use the circuit generator.")
    parser.add_argument("--outdir", default="output", help="where to write SVGs")
    args = parser.parse_args()

    # --- load the user's policy ----------------------------------------------
    try:
        policy = load_policy(args.policy)
    except PolicyError as exc:
        print(f"[policy error]\n{exc}")
        return 1

    # --- race ----------------------------------------------------------------
    result, env = run_policy(policy, seed=args.seed, difficulty=args.difficulty)

    # --- report --------------------------------------------------------------
    print(f"track seed : {env.track.seed}")
    if result.reason == "error":
        print(f"result     : ERROR\n{result.error}")
    elif result.finished:
        print(f"result     : LAP COMPLETE")
        print(f"lap time   : {result.lap_time:.2f}s")
    else:
        print(f"result     : did not finish ({result.reason})")
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
              + (f"lap={result.lap_time:.2f}s" if result.lap_time else result.reason),
    )
    still_path = os.path.join(args.outdir, f"race_{tag}.svg")
    save_svg(still, still_path)
    print(f"wrote      : {still_path}")

    if result.trajectory and len(result.trajectory) > 2:
        anim = render_lap_svg(env.track, result.trajectory, lap_time=result.lap_time)
        anim_path = os.path.join(args.outdir, f"replay_{tag}.svg")
        save_svg(anim, anim_path)
        print(f"wrote      : {anim_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
