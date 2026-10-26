"""Example policy: a simple but capable hand-coded driver.

Strategy
--------
The observation gives a fan of distance sensors ("rays"), from the car's far
left to its far right, each normalized to 0..1 (1 = nothing within sensor range,
0 = wall right at the nose). We:

1. Steer by a *weighted average* of all ray directions (each ray pulls toward
   itself in proportion to how open it is) -- smoother and more robust than just
   chasing the single most-open ray.
2. Brake for corners: slow down when the road ahead is short, and brake harder
   the sharper we need to turn. This lets the car survive tight corners on the
   harder, circuit-style tracks.

Copy this file, change `act`, and race your own driver:

    python main.py policies/my_policy.py --seed 42 --difficulty hard
"""


class Policy:
    def act(self, observation: dict) -> dict:
        rays = observation["rays"]            # left -> right, values 0..1
        speed = observation["speed"]          # 0..1
        n = len(rays)
        mid = (n - 1) / 2.0

        # --- steering: weighted average of ray directions ------------------
        # each ray i sits at offset (i - mid); weight it by openness^2 so the
        # clearest directions dominate but nearby rays still contribute.
        num = 0.0
        den = 0.0
        for i, r in enumerate(rays):
            w = r * r
            num += (i - mid) * w
            den += w
        steer = (num / den) / mid if den > 0 and mid > 0 else 0.0
        steer = max(-1.0, min(1.0, steer))

        # --- throttle: ease off for corners --------------------------------
        forward_clear = rays[int(round(mid))]     # ray pointing straight ahead
        if forward_clear > 0.6:
            throttle = 1.0
        elif forward_clear > 0.35:
            throttle = 0.55
        else:
            throttle = 0.2                        # tight corner: slow right down

        # brake more if we're going fast and must turn hard
        if speed > 0.45 and abs(steer) > 0.4:
            throttle = min(throttle, 0.15)

        return {"steer": steer, "throttle": throttle}
