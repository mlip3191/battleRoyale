"""Prototype (#332): compare venomous fights in swarm mode with the one-by-one engine.

Run from backend/:  PYTHONPATH=. python scripts/venom_parity.py
Forces each mode the way scripts/validate_swarm.py does (swarm: SWARM_THRESHOLD 1 and a zero work
budget; one by one: a threshold nobody reaches). Seed sheets, 300 runs, king cobras v legionaries.
Reads win share and draw share. Nothing here uses the network.
"""

import time

from app.models.matchup import FighterRequest, Matchup
from app.simulation import benchmark as bm
from app.simulation import constants as c
from app.simulation.engine import run

sh = bm.seed_sheets()


def fr(e, n):
    return FighterRequest(entity=e, raw=e, count=n)


def go(a, na, b, nb, mode, runs):
    m = Matchup(fighters=[fr(a, na), fr(b, nb)], raw_text="x", terrain="open_field")
    s = [sh.get(f) for f in m.fighters]
    sv = (c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET)
    try:
        if mode == "swarm":
            c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET = 1, 0.0
        else:
            c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET = 10**9, float("inf")
        t = time.perf_counter()
        r = run(m, s, runs=runs, explain=False)
        dt = time.perf_counter() - t
    finally:
        c.SWARM_THRESHOLD, c.SWARM_WORK_BUDGET = sv
    return r.win_prob[0], r.draw_prob, dt


for a, na, b, nb in [
    ("king-cobra", 50, "roman-legionary", 50),
    ("king-cobra", 100, "roman-legionary", 50),
    ("king-cobra", 201, "roman-legionary", 50),
    ("king-cobra", 60, "african-elephant", 1),
    ("king-cobra", 100, "gorilla", 20),
]:
    try:
        o = go(a, na, b, nb, "one", 300) if na <= 199 else (float("nan"), float("nan"), 0.0)
    except Exception as e:
        o = ("err", str(e)[:40], 0)
    w = go(a, na, b, nb, "swarm", 300)
    print(
        f"{na} {a} v {nb} {b}: one by one {o[0]:.3f} draw {o[1]:.3f} ({o[2]:.1f}s)"
        f" | swarm {w[0]:.3f} draw {w[1]:.3f} ({w[2]:.1f}s)",
        flush=True,
    )
