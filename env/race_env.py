"""The race environment: a small gym-style simulator.

Usage::

    env = RaceEnv(seed=42)
    obs = env.reset()
    done = False
    while not done:
        action = {"steer": 0.0, "throttle": 1.0}
        obs, reward, done, info = env.step(action)

Observation (the thing a policy "sees"), a plain dict::

    {
        "rays":  [d0, d1, ...],   # distances to track edge, normalized 0..1
        "speed": float,           # normalized 0..1 (fraction of max speed)
        "on_track": bool,
    }

Pure standard library -- no numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from env.car import Car, CarConfig
from env.geometry import (
    Point,
    on_track_centerline,
    ray_cast,
    segments_cross,
    segments_from_loop,
)
from env.track import Track, generate_track


@dataclass
class EnvConfig:
    dt: float = 0.05                       # seconds per simulation step
    max_steps: int = 4000                  # hard cap (prevents infinite laps)
    n_rays: int = 7                        # sensor beams
    ray_spread: float = math.radians(90.0) # total fan angle, centered on heading
    ray_max_dist: float = 150.0            # max sensor range (world units)
    off_track_grace: float = 0.5           # seconds allowed off-track before reset


@dataclass
class EnvState:
    steps: int = 0
    time: float = 0.0
    lap_count: int = 0
    lap_time: float | None = None
    off_track_time: float = 0.0
    prev_pose: tuple[float, float, float] = (0.0, 0.0, 0.0)
    trajectory: list[tuple[float, float, float]] = field(default_factory=list)


class RaceEnv:
    def __init__(
        self,
        seed: int | None = None,
        env_config: EnvConfig | None = None,
        car_config: CarConfig | None = None,
    ) -> None:
        self.cfg = env_config or EnvConfig()
        self.track: Track = generate_track(seed=seed)
        self.car = Car(car_config)
        self.state = EnvState()

        # Precompute edge segments for fast ray-casting / collision.
        self._inner_segs = segments_from_loop(self.track.inner)
        self._outer_segs = segments_from_loop(self.track.outer)
        self._edge_segs = self._inner_segs + self._outer_segs
        self._half_width = self.track.width / 2.0

    # ------------------------------------------------------------------ reset
    def reset(self) -> dict:
        start = self.track.start
        nxt = self.track.center[1]
        heading = math.atan2(nxt[1] - start[1], nxt[0] - start[0])
        self.car.reset(start[0], start[1], heading)
        self.state = EnvState(prev_pose=self.car.pose)
        self.state.trajectory.append(self.car.pose)
        return self._observe()

    # ------------------------------------------------------------------- step
    def step(self, action: dict) -> tuple[dict, float, bool, dict]:
        steer = float(action.get("steer", 0.0))
        throttle = float(action.get("throttle", 0.0))

        prev_pose = self.car.pose
        self.car.step(steer, throttle, self.cfg.dt)
        self.state.steps += 1
        self.state.time += self.cfg.dt
        self.state.trajectory.append(self.car.pose)

        x, y, _ = self.car.pose
        is_on = on_track_centerline(x, y, self.track.center, self._half_width)

        reward = self.car.state.speed * self.cfg.dt   # reward forward progress
        done = False
        info: dict = {}

        # --- off-track handling --------------------------------------------
        if not is_on:
            self.state.off_track_time += self.cfg.dt
            reward -= 1.0
            if self.state.off_track_time >= self.cfg.off_track_grace:
                done = True
                info["reason"] = "off_track"
        else:
            self.state.off_track_time = 0.0

        # --- lap detection: did we cross the start/finish line forward? -----
        if self._crossed_start_line(prev_pose, self.car.pose):
            # Ignore the very first steps so we don't count the start itself.
            if self.state.time > 1.0:
                self.state.lap_count += 1
                self.state.lap_time = self.state.time
                reward += 100.0
                done = True
                info["reason"] = "lap_complete"
                info["lap_time"] = self.state.lap_time

        # --- step cap -------------------------------------------------------
        if self.state.steps >= self.cfg.max_steps and not done:
            done = True
            info["reason"] = "timeout"

        self.state.prev_pose = self.car.pose
        obs = self._observe()
        info["time"] = self.state.time
        return obs, reward, done, info

    # ---------------------------------------------------------------- observe
    def _observe(self) -> dict:
        x, y, heading = self.car.pose
        rays: list[float] = []
        ray_endpoints: list[Point] = []
        n = self.cfg.n_rays
        spread = self.cfg.ray_spread
        for i in range(n):
            # fan the rays evenly across the spread, centered on heading
            frac = 0.0 if n == 1 else (i / (n - 1) - 0.5)
            angle = heading + frac * spread
            dist = ray_cast(x, y, angle, self._edge_segs, self.cfg.ray_max_dist)
            rays.append(dist / self.cfg.ray_max_dist)     # normalize 0..1
            ray_endpoints.append(
                (x + math.cos(angle) * dist, y + math.sin(angle) * dist)
            )

        self._last_ray_endpoints = ray_endpoints
        return {
            "rays": rays,
            "speed": self.car.state.speed / self.car.config.max_speed,
            "on_track": on_track_centerline(x, y, self.track.center, self._half_width),
        }

    @property
    def ray_endpoints(self) -> list[Point]:
        return getattr(self, "_last_ray_endpoints", [])

    # ------------------------------------------------------- lap-line crossing
    def _crossed_start_line(
        self, prev: tuple[float, float, float], curr: tuple[float, float, float]
    ) -> bool:
        inner_pt, outer_pt = self.track.start_line()
        p1 = (prev[0], prev[1])
        p2 = (curr[0], curr[1])
        return segments_cross(p1, p2, inner_pt, outer_pt)
