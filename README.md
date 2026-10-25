# AI Car Racing

Write Python to drive a car around a randomly generated race track, and see how
fast your code can complete a lap.

- **Random tracks** — every track is a unique, guaranteed-valid closed loop.
- **Pure Python** — zero dependencies. No numpy, no matplotlib, no game engine.
- **Your code drives** — you write a small `Policy` class; the game calls it
  every tick with what the car "sees" and uses the controls you return.
- **Visual output** — tracks and laps are rendered to SVG (open in any browser
  or view directly on GitHub).

## Status

Work in progress. Currently implemented:

- [x] Random closed-loop **track generator** (`env/track.py`)
- [x] Dependency-free **SVG renderer** (`render.py`)
- [ ] Car physics
- [ ] Sensor rays + gym-style environment
- [ ] Policy loader + runner (run a user's `.py` file)
- [ ] Lap timing + animated replay

## Try it

```bash
python preview_tracks.py      # writes previews/track_<seed>.svg
```

Then open the generated files in `previews/` to see a few random tracks.

## How tracks are generated

Each track centerline is defined in polar form: for every angle `theta` around
a center, the radius is a base radius plus a few random low-frequency sine
waves. Because the radius is a single-valued function of the angle, the loop can
never cross itself — so every generated track is valid and drivable. The
centerline is then offset by half the track width to produce the inner and outer
edges.
