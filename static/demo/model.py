"""Authored LIF teaching model, Euler dt=0.1 ms (demo notes pp.1-4)."""
import json

DT = 0.1
DEFAULTS = {"I": 0.0, "tau": 20.0}


def initial(params):
    return {"V": -65.0, "time": 0.0, "spikes": 0, "refractory": 0.0, "rate": 0.0, **DEFAULTS, **params}


def advance(s):
    s["time"] += DT
    if s["refractory"] > 0:
        s["refractory"] = max(0.0, s["refractory"] - DT)
        s["V"] = -65.0
    else:
        s["V"] += (-(s["V"] + 65.0) + 10.0 * s["I"]) / s["tau"] * DT
        if s["V"] >= -50.0:
            s["spikes"] += 1
            s["V"] = -65.0
            s["refractory"] = 2.0
    s["rate"] = s["spikes"] / (s["time"] / 1000.0)


def run(params, steps):
    """State after `steps` timesteps from rest; the browser model must match it."""
    s = initial(params)
    for _ in range(steps):
        advance(s)
    return s


def simulate(I=0.0, tau=20.0, duration=1000.0):
    return run({"I": I, "tau": tau}, round(duration / DT))


if __name__ == "__main__":
    print(json.dumps({"metrics": {f"spikes_{current}nA": simulate(current)["spikes"] for current in (0, 1, 2, 3)}, "notes": "Authored demo model. 1000 ms, Euler dt=0.1 ms, tau=20 ms, R=10 Mohm, rest/reset=-65 mV, threshold=-50 mV, refractory=2 ms. No biological fit claimed."}))
