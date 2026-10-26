"""Run a policy against the race environment.

The game owns the loop; the policy only answers "given this observation, what
controls?". Each call to the policy is isolated (errors end the run cleanly) and
time-budgeted (a slow/hanging policy aborts the lap instead of freezing).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from env.race_env import EnvConfig, RaceEnv
from runner.loader import PolicyError, validate_action


@dataclass
class RaceResult:
    finished: bool                 # did the car complete the full race (all laps)?
    lap_time: float | None         # last completed lap's time (back-compat)
    reason: str                    # "race_complete" | "off_track" | "timeout" | "error"
    steps: int
    total_reward: float
    trajectory: list               # [(x, y, heading, slip), ...] for replay
    lap_times: list = field(default_factory=list)   # each completed lap's split (s)
    laps_completed: int = 0
    laps_requested: int = 1
    total_time: float | None = None                 # time for all requested laps
    error: str | None = None

    @property
    def best_lap(self) -> float | None:
        return min(self.lap_times) if self.lap_times else None


def _fail(env, reason, total_reward, error=None) -> RaceResult:
    """Build a RaceResult for a run that ended without finishing the race."""
    return RaceResult(
        finished=False,
        lap_time=env.state.lap_time,
        reason=reason,
        steps=env.state.steps,
        total_reward=total_reward,
        trajectory=env.state.trajectory,
        lap_times=list(env.state.lap_times),
        laps_completed=env.state.lap_count,
        laps_requested=env.laps,
        error=error,
    )


def run_policy(
    policy,
    seed: int | None = None,
    difficulty: str = "easy",
    laps: int = 1,
    env_config: EnvConfig | None = None,
    per_step_budget_s: float = 0.25,
) -> tuple[RaceResult, RaceEnv]:
    """Drive ``policy`` for ``laps`` laps and return the result + env (for render)."""
    env = RaceEnv(seed=seed, difficulty=difficulty, laps=laps, env_config=env_config)
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
            return _fail(env, "error", total_reward, error=str(exc)), env
        except Exception as exc:  # noqa: BLE001 - any bug in user code
            return (
                _fail(env, "error", total_reward,
                      error=f"Your act() raised: {type(exc).__name__}: {exc}"),
                env,
            )

        elapsed = time.perf_counter() - t0
        if elapsed > per_step_budget_s:
            return (
                _fail(env, "error", total_reward,
                      error=f"act() too slow: {elapsed*1000:.0f}ms "
                            f"(budget {per_step_budget_s*1000:.0f}ms)."),
                env,
            )

        obs, reward, done, info = env.step(action)
        total_reward += reward

    reason = info.get("reason", "timeout")
    return (
        RaceResult(
            finished=(reason == "race_complete"),
            lap_time=env.state.lap_time,
            reason=reason,
            steps=env.state.steps,
            total_reward=total_reward,
            trajectory=env.state.trajectory,
            lap_times=list(env.state.lap_times),
            laps_completed=env.state.lap_count,
            laps_requested=env.laps,
            total_time=info.get("total_time"),
        ),
        env,
    )
