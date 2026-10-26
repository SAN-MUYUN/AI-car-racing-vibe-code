"""Load and validate a user-supplied policy file.

The user writes a file that defines a class named ``Policy`` with an
``act(self, observation) -> dict`` method. We import that file as a module,
instantiate the class, and sanity-check the interface before the race starts so
problems surface as friendly messages instead of mid-race crashes.

NOTE on security: this imports and executes arbitrary Python. That is fine for a
local, single-user tool (you are running your own code). It is NOT a sandbox --
do not run untrusted files from strangers with this as-is.
"""

from __future__ import annotations

import importlib.util
import os


class PolicyError(Exception):
    """Raised when a policy file does not satisfy the contract."""


def load_policy(path: str):
    """Load a ``Policy`` instance from a .py file at ``path``."""
    if not os.path.isfile(path):
        raise PolicyError(f"Policy file not found: {path}")

    spec = importlib.util.spec_from_file_location("user_policy", path)
    if spec is None or spec.loader is None:
        raise PolicyError(f"Could not load Python module from: {path}")

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)      # executes the user's file
    except Exception as exc:                  # noqa: BLE001 - surface any error
        raise PolicyError(f"Error while importing your policy file: {exc}") from exc

    if not hasattr(module, "Policy"):
        raise PolicyError(
            "Your file must define a class named `Policy`.\n"
            "Example:\n"
            "    class Policy:\n"
            "        def act(self, observation):\n"
            "            return {'steer': 0.0, 'throttle': 1.0}"
        )

    try:
        policy = module.Policy()
    except Exception as exc:                  # noqa: BLE001
        raise PolicyError(f"Could not create Policy(): {exc}") from exc

    act = getattr(policy, "act", None)
    if not callable(act):
        raise PolicyError("`Policy` must have a callable `act(self, observation)` method.")

    return policy


def validate_action(action: object) -> dict:
    """Validate and normalize the dict returned by ``act``."""
    if not isinstance(action, dict):
        raise PolicyError(
            f"act() must return a dict like {{'steer': 0.0, 'throttle': 1.0}}, "
            f"got {type(action).__name__}."
        )
    out = {}
    for key in ("steer", "throttle"):
        val = action.get(key, 0.0)
        try:
            out[key] = float(val)
        except (TypeError, ValueError) as exc:
            raise PolicyError(f"act() returned a non-numeric '{key}': {val!r}.") from exc
    return out
