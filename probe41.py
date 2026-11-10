import sys; sys.path.insert(0,'.')
from app.simulation import constants as c
from app.simulation.engine import _foregone,_starts,_templates,run_once
from app.simulation.rng import run_rng
from tests.property.sim_helpers import make_sheet, matchup_of
def mk(end, n):
    tank = make_sheet("tank", body="machine", weapons=["ramming"], mass_kg=3, endurance_s=end, attack_force_n=0, spread=0.0)
    boulder = make_sheet("boulder", body="inert", weapons=["none"], mass_kg=1_000_000, attack_force_n=0, attacks_per_s=0, top_speed_mps=0, spread=0.0)
    return tank, boulder
for end in (600, 599.95, 570, 580):
    t,b = mk(end,1); m = matchup_of(5,5)
    rng=run_rng(1,0); sides=_templates(m,[t,b],rng,(1.0,1.0))
    f=_foregone(sides,_starts(sides))
    o=run_once(sides,m.terrain,run_rng(1,0),record_events=True)
    print("indiv",end,f,o.winner,o.survivors,o.duration_s)
for end in (570,590,599):
    t,b = mk(end,1); m = matchup_of(250,250)
    sides=_templates(m,[t,b],run_rng(1,0),(1.0,1.0))
    o=run_once(sides,m.terrain,run_rng(1,0),record_events=True)
    print("swarm",end,o.winner,o.survivors,o.duration_s)
