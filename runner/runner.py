"""Run a policy against the race environment.

The game owns the loop; the policy only answers "given this observation, what
controls?". Each call to the policy is isolated (errors end the run cleanly) and
time-budgeted (a slow/hanging policy aborts the lap instead of freezing).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from env.race_env import EnvConfig, RaceEnv
from runner.loader import PolicyError, validate_action


@dataclass
class RaceResult:
    finished: bool                 # did the car complete a lap?
    lap_time: float | None
    reason: str                    # "lap_complete" | "off_track" | "timeout" | "error"
    steps: int
    total_reward: float
    trajectory: list              # [(x, y, heading), ...] for replay
    error: str | None = None


def run_policy(
    policy,
    seed: int | None = None,
    difficulty: str = "easy",
    env_config: EnvConfig | None = None,
    per_step_budget_s: float = 0.25,
) -> tuple[RaceResult, RaceEnv]:
    """Drive ``policy`` around a track and return the result + the env (for render)."""
    env = RaceEnv(seed=seed, difficulty=difficulty, env_config=env_config)
    obs = env.reset()
    total_reward = 0.0
    done = False
    info: dict = {}

    while not done:
        # --- call the policy with isolation + a time budget ----------------
        t0 = time.perf_counter()
        try:
            raw = policy.act(obs)
            action = validate_action(raw)
        except PolicyError as exc:
            return (
                RaceResult(
                    finished=False, lap_time=None, reason="error",
                    steps=env.state.steps, total_reward=total_reward,
                    trajectory=env.state.trajectory, error=str(exc),
                ),
                env,
            )
        except Exception as exc:  # noqa: BLE001 - any bug in user code
            return (
                RaceResult(
                    finished=False, lap_time=None, reason="error",
                    steps=env.state.steps, total_reward=total_reward,
                    trajectory=env.state.trajectory,
                    error=f"Your act() raised: {type(exc).__name__}: {exc}",
                ),
                env,
            )

        elapsed = time.perf_counter() - t0
        if elapsed > per_step_budget_s:
            return (
                RaceResult(
                    finished=False, lap_time=None, reason="error",
                    steps=env.state.steps, total_reward=total_reward,
                    trajectory=env.state.trajectory,
                    error=f"act() too slow: {elapsed*1000:.0f}ms "
                          f"(budget {per_step_budget_s*1000:.0f}ms).",
                ),
                env,
            )

        obs, reward, done, info = env.step(action)
        total_reward += reward

    reason = info.get("reason", "timeout")
    return (
        RaceResult(
            finished=(reason == "lap_complete"),
            lap_time=info.get("lap_time"),
            reason=reason,
            steps=env.state.steps,
            total_reward=total_reward,
            trajectory=env.state.trajectory,
        ),
        env,
    )
