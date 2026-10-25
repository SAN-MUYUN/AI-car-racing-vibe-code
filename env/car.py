"""Simple 2D car physics (kinematic bicycle model).

The car has a position, a heading (the direction it faces) and a forward speed.
Each tick it receives two controls in the range ``[-1, 1]``:

* ``steer``    -- turn left/right.
* ``throttle`` -- accelerate forward / brake-reverse.

This is deliberately a *kinematic* model (no tyre slip, no drift): it is easy to
reason about and plenty for an ML-driving playground. Complexity can be added
later without changing the control interface.

Pure standard library -- no numpy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CarConfig:
    max_speed: float = 60.0          # world units / second
    accel: float = 45.0              # acceleration at full throttle (u/s^2)
    brake_decel: float = 70.0        # deceleration when reversing throttle
    drag: float = 2.0                # passive slow-down per second (fraction)
    max_steer: float = math.radians(35.0)   # max steering angle per tick input
    wheelbase: float = 8.0           # distance between axles (turn sharpness)


@dataclass
class CarState:
    x: float
    y: float
    heading: float          # radians; 0 = +x axis
    speed: float = 0.0      # forward speed (can be slightly negative)


class Car:
    """Kinematic bicycle-model car."""

    def __init__(self, config: CarConfig | None = None) -> None:
        self.config = config or CarConfig()
        self.state = CarState(0.0, 0.0, 0.0, 0.0)

    def reset(self, x: float, y: float, heading: float) -> None:
        self.state = CarState(x, y, heading, 0.0)

    def step(self, steer: float, throttle: float, dt: float) -> None:
        """Advance the car by ``dt`` seconds given clamped controls."""
        cfg = self.config
        s = self.state

        steer = _clamp(steer, -1.0, 1.0)
        throttle = _clamp(throttle, -1.0, 1.0)

        # --- longitudinal: throttle accelerates, drag slows -----------------
        if throttle >= 0.0:
            s.speed += cfg.accel * throttle * dt
        else:
            s.speed += cfg.brake_decel * throttle * dt   # throttle<0 -> brake
        s.speed -= s.speed * cfg.drag * dt               # passive drag
        s.speed = _clamp(s.speed, -cfg.max_speed * 0.3, cfg.max_speed)

        # --- lateral: bicycle-model heading change --------------------------
        steer_angle = steer * cfg.max_steer
        if abs(steer_angle) > 1e-6:
            # angular velocity = v / wheelbase * tan(steer_angle)
            s.heading += (s.speed / cfg.wheelbase) * math.tan(steer_angle) * dt
            s.heading = _wrap_angle(s.heading)

        # --- integrate position ---------------------------------------------
        s.x += math.cos(s.heading) * s.speed * dt
        s.y += math.sin(s.heading) * s.speed * dt

    @property
    def pose(self) -> tuple[float, float, float]:
        return self.state.x, self.state.y, self.state.heading


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _wrap_angle(a: float) -> float:
    """Wrap angle into (-pi, pi]."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi
