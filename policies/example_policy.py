"""Example policy: a simple but effective hand-coded driver.

Strategy
--------
The observation gives a fan of distance sensors ("rays"), from the car's far
left to its far right, each normalized to 0..1 (1 = nothing within sensor range,
0 = wall right at the nose). We:

1. Steer toward whichever ray sees the most open space (usually the direction
   the track continues).
2. Slow down when the road straight ahead is short (a tight corner is coming),
   and accelerate when it is clear.

Copy this file, change `act`, and race your own driver:

    python main.py policies/my_policy.py --seed 42
"""


class Policy:
    def act(self, observation: dict) -> dict:
        rays = observation["rays"]            # left -> right, values 0..1
        speed = observation["speed"]          # 0..1
        n = len(rays)
        mid = n // 2

        # --- steering: aim at the most open direction ----------------------
        best_i = max(range(n), key=lambda i: rays[i])
        # map ray index to a steer command in [-1, 1]
        # index < mid is to the left, > mid is to the right
        steer = (best_i - mid) / max(1, mid)

        # --- throttle: go fast when it's clear ahead, ease off for corners --
        forward_clear = rays[mid]             # the ray pointing straight ahead
        if forward_clear > 0.6:
            throttle = 1.0
        elif forward_clear > 0.3:
            throttle = 0.6
        else:
            throttle = 0.25                   # tight corner: slow down

        # gentle extra braking if we're fast and need to turn hard
        if speed > 0.6 and abs(steer) > 0.5:
            throttle = min(throttle, 0.3)

        return {"steer": steer, "throttle": throttle}
