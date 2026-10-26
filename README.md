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

# Multi-lap race (reports each lap, the best lap, and the total):
python main.py policies/example_policy.py --seed 42 --laps 3
```

### Laps

`--laps N` runs an N-lap race (default 1). The car drives continuously; each
time it crosses the start/finish line a lap split is recorded. Output shows every
lap time, marks the fastest, and (for multi-lap races) the total:

```
laps       : 3
result     : RACE COMPLETE (3 laps)
  lap 1    : 39.90s
  lap 2    : 39.60s  <- best
  lap 3    : 39.65s
  total    : 119.15s
```

If the car goes off track partway, it reports how many laps it managed
(e.g. `did not finish (off_track) after 1/3 laps`).

### Difficulty

`--difficulty` controls how complicated the circuit is:

| Level | Generator | Feel |
|---|---|---|
| `easy` (default) | radial | smooth, gentle oval-ish loop |
| `medium` | smooth circuit | real-circuit shape, a few proper corners |
| `hard` | smooth circuit | more corners, sharper bends, longer |
| `insane` | smooth circuit | long, technical, tight (but drivable) corners |
| `circuit` (= `circuit-hard`) | **segment-based** | **Silverstone-style**: real straights, hairpins, chicanes and fast sweepers |
| `circuit-medium` / `circuit-insane` | segment-based | easier / harder segment circuits |

Same `--seed` + same `--difficulty` always produces the same track.

The **`circuit-*`** styles use a different, more authentic generator (see below):
instead of smoothing a random blob, they assemble the lap from a sequence of
features — straights, corners, chicanes, sweepers — so you get long full-throttle
straights leading into heavy braking zones and slow hairpins, the way a real
circuit flows. Try:

```bash
python main.py policies/example_policy.py --seed 42 --difficulty circuit
python main.py policies/example_policy.py --seed 7 --difficulty circuit-insane --laps 3
```

This prints the lap time and writes two SVGs to `output/`:

- `race_<seed>.svg` — a still of the final frame, with the car and its sensor rays.
- `replay_<seed>.svg` — an animated replay of the whole lap (open in a browser).

### Replay playback speed

By default the replay is a quick **fixed ~8-second clip** regardless of the real
lap time — easy to glance at, but it doesn't reflect actual pace (a 44 s lap and
a 74 s lap both finish the clip in 8 s, so the slow one looks just as fast).

Add **`--realtime`** to make the clip length proportional to the real lap time,
so a faster run visibly plays as a shorter, snappier clip and you can compare
pace across replays:

```bash
python main.py policies/example_policy.py --seed 7 --difficulty circuit-insane --realtime
```

`--replay-scale N` sets real seconds per clip second (default `5`; higher =
shorter clips). Clip length is clamped to a watchable 2–40 s.

Playback stays smooth at any length: the number of animation frames scales with
the clip duration (targeting ~30 fps), and the car's position and heading are
linearly interpolated between frames — so a longer real-time clip glides rather
than stutters.

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
There are three generators (`env/track.py`, `env/circuit.py`):

- **`easy` (radial)** — the centerline is `radius(angle)` around a center: a base
  radius plus a few random sine waves. Because radius is single-valued in the
  angle, the loop can never self-intersect — simple and always valid, but it
  can't make hairpins or straights.

- **`medium` / `hard` / `insane` (smooth circuit)** — scatter random points, take
  their convex hull, spread them out, then **displace the hull edges** to create
  concave bends and variety, and **smooth** with a Catmull-Rom spline. Validated
  (no self-intersection, no undrivable corner) and regenerated on failure. More
  complex than radial, but the smoothing gives fairly uniform curvature.

- **`circuit-*` (segment-based, Silverstone-style)** — the authentic one. The lap
  is assembled from a random sequence of *features* — straights, corners,
  chicanes, fast sweepers — laid end to end, so you get distinct corner types
  (slow hairpins, quick flicks, long sweepers) joined by real straights. The
  loop is closed in two stages: the signed corner angles are normalized to sum
  to exactly ±360° (so the heading closes by construction), then the straight
  lengths are **nudged by a small Gauss-Newton solver** (finite-difference
  Jacobian) to drive the end position back to the start. Same validation +
  retry. This is what makes a layout flow like a real racing circuit.

In every case the centerline is offset by half the track width to produce the
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

- [x] Three track generators: radial, smooth-circuit, and a **segment-based
      Silverstone-style** generator (straights, hairpins, chicanes, sweepers)
- [x] **Difficulty / style levels** (`easy` / `medium` / `hard` / `insane` /
      `circuit-*`) with validate-and-retry so every track is drivable
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
