# AI Car Racing

Write Python to drive a car around a randomly generated race track, and see how
fast your code can complete a lap.

- **Random tracks** — every track is a unique, guaranteed-valid closed loop.
- **Pure Python** — zero dependencies. No numpy, no matplotlib, no game engine.
- **Your code drives** — you write a small `Policy` class; the game calls it
  every tick with what the car "sees" and uses the controls you return.
- **Visual output** — tracks and laps are rendered to SVG (open in any browser
  or view directly on GitHub).

## Quick start

```bash
# Race the bundled example driver on a specific track:
python main.py policies/example_policy.py --seed 42

# Crank up the track complexity:
python main.py policies/example_policy.py --seed 42 --difficulty hard

# Random track each run (omit --seed):
python main.py policies/example_policy.py --difficulty insane
```

### Difficulty

`--difficulty` controls how complicated the circuit is:

| Level | Generator | Feel |
|---|---|---|
| `easy` (default) | radial | smooth, gentle oval-ish loop |
| `medium` | circuit | real-circuit shape, a few proper corners |
| `hard` | circuit | more corners, sharper bends, longer |
| `insane` | circuit | long, technical, tight (but drivable) corners |

Same `--seed` + same `--difficulty` always produces the same track.

This prints the lap time and writes two SVGs to `output/`:

- `race_<seed>.svg` — a still of the final frame, with the car and its sensor rays.
- `replay_<seed>.svg` — an animated replay of the whole lap (open in a browser).

To preview some tracks without racing:

```bash
python preview_tracks.py      # writes previews/track_<seed>.svg
```

## Write your own driver

Create a file with a `Policy` class that has an `act(observation)` method
returning `steer` and `throttle`, each in the range `[-1, 1]`:

```python
class Policy:
    def act(self, observation):
        # observation = {
        #   "rays":     [d0, d1, ...], # distances to the track edge, left->right,
        #                              # normalized 0..1 (1 = clear, 0 = wall at nose)
        #   "speed":    float,         # 0..1 (fraction of max speed)
        #   "on_track": bool,
        #   "slipping": bool,          # True if the car is currently sliding
        #   "slip":     float,         # how badly it's sliding, ~0..1 (0 = gripping)
        # }
        return {"steer": 0.0, "throttle": 1.0}
```

Then race it:

```bash
python main.py policies/my_policy.py --seed 42
```

See `policies/example_policy.py` for a working hand-coded driver (steers toward
the most open sensor and brakes for corners) that laps every track.

## How it works

| Piece | File | What it does |
|---|---|---|
| Track generator | `env/track.py` | Random closed loop via polar radius + sine harmonics. |
| Car physics | `env/car.py` | Kinematic bicycle model (position, heading, speed). |
| Geometry | `env/geometry.py` | Ray-casting sensors, on-track test, lap-line crossing. |
| Environment | `env/race_env.py` | Gym-style `reset()` / `step()`, observations, lap timing. |
| Policy loader | `runner/loader.py` | Loads + validates your `.py` file. |
| Runner | `runner/runner.py` | Game loop with error isolation + per-step time budget. |
| Renderer | `render.py` | Dependency-free SVG (track, car, rays, animated replay). |
| CLI | `main.py` | Ties it together; prints the lap time, writes SVGs. |

### Tracks
There are two generators (`env/track.py`):

- **`easy` (radial)** — the centerline is `radius(angle)` around a center: a base
  radius plus a few random sine waves. Because radius is single-valued in the
  angle, the loop can never self-intersect — simple and always valid, but it
  can't make hairpins or straights.

- **`medium` / `hard` / `insane` (circuit)** — scatter random points, take their
  convex hull, spread them out, then **displace the hull edges** inward/outward
  to create concave bends, hairpins and variety, and finally **smooth** it with
  a Catmull-Rom spline. Each candidate is **validated** (no self-intersection,
  and no corner tighter than the car can physically turn) and **regenerated** if
  it fails. This produces complicated, real-circuit-style tracks with sharp
  corners while staying drivable.

Either way, the centerline is offset by half the track width to produce the
edges. Same `--seed` + `--difficulty` → same track, so lap times are comparable.

### What the car "sees"
Each tick the policy gets a fan of distance sensors (default 7, spread 90°)
measuring how far the track edge is in each direction, the current speed, and
whether it's currently sliding (`slipping` / `slip`). That's the full
observation — the rest is up to your code.

### Grip and sliding
The car isn't on rails. Tyres can only provide so much sideways force, so
turning hard at speed exceeds grip and the car **slides wide** (understeer).
The lateral acceleration a corner demands grows with speed *squared*
(`~ v² / radius`), so a corner that's easy slowly becomes impossible fast. A
corner of radius `R` can be taken cleanly up to about `sqrt(grip * R)`; go faster
and you slip.

The practical consequence: **you have to brake before corners.** Flooring the
throttle everywhere will slide you off the track on the tighter circuits — so
managing speed is a real skill a driver (or a trained policy) has to learn. The
slide is recoverable: lift off / slow down and grip returns. The observation's
`slipping` / `slip` fields tell your code when it's happening, so it can react.

**Seeing the slide:** in the animated replay (`output/replay_*.svg`) the car is
drawn at its true *heading*, so when it slides you can see it pointing one way
while travelling another, and it **flashes yellow** while slipping. A cautious
driver that brakes for corners (like the bundled example) won't slide much — to
watch a dramatic slide, race a flat-out "full throttle, no braking" policy on a
`hard` or `insane` track and it will drift wide and spin off.

## Status

Working end to end:

- [x] Random closed-loop track generator (radial + **circuit** generators)
- [x] **Difficulty levels** (`easy` / `medium` / `hard` / `insane`) with
      validate-and-retry so every circuit is drivable
- [x] Car physics with a **grip limit** — the car slides if it corners too fast
- [x] Sensor rays + gym-style environment (observation includes `slipping`/`slip`)
- [x] Policy loader + runner (run a user's `.py` file, with error isolation)
- [x] Lap timing + start/finish detection (step cap scales with track length)
- [x] SVG rendering: still frame + animated replay
- [x] Working example policy that laps the harder tracks

### Ideas for next
- Multiple cars on one track (ghost race / overlaid replay).
- Multiple-seed averaging for fairer scoring / a leaderboard.
- A training harness so a policy can *learn* to brake for corners and go faster.
- Richer physics (separate front/rear grip, drift), walls you can graze.

## A note on running untrusted code
The runner imports and executes your policy file directly. That is fine for a
local, single-user tool. It is **not** a security sandbox — don't run policy
files from strangers with this as-is.
