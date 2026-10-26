"""2D car physics with a tyre-grip limit.

The car has a position, a heading (the direction it *points*) and a velocity
*vector* (the direction it is actually *moving*). Each tick it receives two
controls in the range ``[-1, 1]``:

* ``steer``    -- turn the heading left/right.
* ``throttle`` -- accelerate forward / brake-reverse.

Grip model (why the car can slide)
-----------------------------------
Steering rotates the *heading*. The velocity vector is then rotated toward the
heading -- but tyres can only provide so much sideways ("lateral") force, i.e. a
limited lateral acceleration ``grip``. Turning hard at speed demands lateral
acceleration ``~ v^2 / R`` (speed squared over turn radius); if that exceeds
``grip`` the velocity can only be bent as far as grip allows, so the car keeps
some of its old momentum and **slides wide** (understeer). The excess is reported
as ``slip``.

Because the demand grows with v^2, a corner that is easy slowly becomes
impossible fast -- so speed management (braking before corners) is the skill a
driver has to learn. The slide is recoverable: lift off / slow down and grip
returns.

This replaces the previous pure-kinematic model (which always went exactly where
it pointed, so sharp high-speed flicks were "free"). The control interface is
unchanged.

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
    drag: float = 0.8                # passive slow-down per second (fraction)
    max_steer: float = math.radians(35.0)   # max steering angle per tick input
    wheelbase: float = 8.0           # distance between axles (turn sharpness)
    grip: float = 70.0               # max lateral acceleration (u/s^2) before sliding
                                     # (v_max for a corner of radius R is sqrt(grip*R);
                                     #  tuned so easy corners never slide but tight
                                     #  medium/hard/insane corners need braking)


@dataclass
class CarState:
    x: float
    y: float
    heading: float          # radians; direction the car points. 0 = +x axis
    speed: float = 0.0      # forward speed along the velocity vector
    vx: float = 0.0         # velocity vector (direction the car actually moves)
    vy: float = 0.0
    slip: float = 0.0       # how far the velocity lagged the heading this tick (rad)


class Car:
    """Car with grip-limited cornering (can understeer / slide)."""

    def __init__(self, config: CarConfig | None = None) -> None:
        self.config = config or CarConfig()
        self.state = CarState(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def reset(self, x: float, y: float, heading: float) -> None:
        self.state = CarState(x, y, heading, 0.0, 0.0, 0.0, 0.0)

    def step(self, steer: float, throttle: float, dt: float) -> None:
        """Advance the car by ``dt`` seconds given clamped controls."""
        cfg = self.config
        s = self.state

        steer = _clamp(steer, -1.0, 1.0)
        throttle = _clamp(throttle, -1.0, 1.0)

        # --- longitudinal: throttle/brake act along the current heading -----
        if throttle >= 0.0:
            s.speed += cfg.accel * throttle * dt
        else:
            s.speed += cfg.brake_decel * throttle * dt   # throttle<0 -> brake
        s.speed -= s.speed * cfg.drag * dt               # passive drag
        s.speed = _clamp(s.speed, -cfg.max_speed * 0.3, cfg.max_speed)

        # --- rotate the heading from steering (where the car points) --------
        steer_angle = steer * cfg.max_steer
        if abs(steer_angle) > 1e-6 and abs(s.speed) > 1e-6:
            yaw_rate = (s.speed / cfg.wheelbase) * math.tan(steer_angle)
            s.heading = _wrap_angle(s.heading + yaw_rate * dt)

        # --- resync the velocity vector toward the heading, within grip -----
        # Current velocity vector: rebuild it from the previous one but target
        # the heading. The amount we can rotate the velocity is limited by how
        # much lateral acceleration the tyres can supply (the grip budget).
        speed = abs(s.speed)
        target = s.heading if s.speed >= 0 else _wrap_angle(s.heading + math.pi)

        # direction the car is currently moving (fall back to heading at rest)
        if speed < 1e-6:
            vel_dir = target
        else:
            vel_dir = math.atan2(s.vy, s.vx)

        # angle we would need to turn the velocity to line up with the heading
        delta = _wrap_angle(target - vel_dir)

        # max angle the velocity can rotate this tick given grip:
        #   lateral accel a_lat = v * omega  ->  omega_max = grip / v
        #   max_turn = omega_max * dt
        if speed < 1e-6:
            allowed = abs(delta)                 # at rest, no grip demand
        else:
            allowed = (cfg.grip / speed) * dt

        if abs(delta) <= allowed:
            new_dir = target                     # grip handles it: no slide
            s.slip = 0.0
        else:
            # exceeded grip: only bend velocity as far as grip allows -> slide
            new_dir = _wrap_angle(vel_dir + math.copysign(allowed, delta))
            s.slip = abs(delta) - allowed        # leftover = how much we slid

        s.vx = math.cos(new_dir) * speed
        s.vy = math.sin(new_dir) * speed

        # --- integrate position along the (possibly sliding) velocity -------
        s.x += s.vx * dt
        s.y += s.vy * dt

    @property
    def pose(self) -> tuple[float, float, float]:
        return self.state.x, self.state.y, self.state.heading

    @property
    def is_slipping(self) -> bool:
        return self.state.slip > 1e-3


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _wrap_angle(a: float) -> float:
    """Wrap angle into (-pi, pi]."""
    return (a + math.pi) % (2.0 * math.pi) - math.pi
