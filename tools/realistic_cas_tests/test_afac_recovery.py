"""Bounded recovery geometry; native AI steering still needs DCS probes."""

import unittest

from lupa.lua51 import LuaRuntime
from test_contact_core import PLUGIN


class AfacRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.execute("RealisticCAS={AFACSearch={}}")
        self.lua.execute((PLUGIN / "afac-safety.lua").read_text("utf-8"))
        self.lua.execute("""
A=RealisticCAS.AFACSafety
input={source={x=-20000,y=2000,z=0},destination={x=20000,z=0,altitude=2000},
  speed=60,slots=2,footprint=1000,clearance=150,height=function()return 0 end,
  threats={{point={x=0,y=0,z=0},radius=7000,ceiling=4000}}}
function validate(plan)
  local expanded={}
  for _,t in ipairs(input.threats)do
    expanded[#expanded+1]={point=t.point,radius=t.radius+input.footprint,ceiling=t.ceiling}
  end
  local last=input.source
  for i,p in ipairs(plan.path)do
    assert(A.leg(last,p,input.source.y,expanded,i==1))
    last=p
  end
  assert(A.leg(last,input.destination,input.source.y,expanded,#plan.path==0))
end
""")

    def test_recovery_routes_around_a_known_circle(self):
        self.lua.execute("""
local plan=A.recovery(input)
assert(plan.mode=='return' and #plan.path>0 and #plan.path<=2)
validate(plan)
""")

    def test_unknown_ceiling_requires_standoff_even_at_high_altitude(self):
        self.lua.execute("""
input.threats[1].ceiling=nil;input.source.y=10000
local plan=A.recovery(input);assert(#plan.path>0);validate(plan)
""")

    def test_candidate_generation_does_not_omit_other_threats_on_a_detour(self):
        self.lua.execute("""
input.candidateThreats={input.threats[1]}
input.threats[2]={point={x=0,y=0,z=-12000},radius=7000,ceiling=4000}
local plan=A.recovery(input);assert(plan.mode=='return');validate(plan)
""")

    def test_dense_known_network_uses_a_bounded_hold_without_dropping_rings(self):
        self.lua.execute("""
input.threats={}
for i=1,65 do input.threats[i]={point={x=100000+i,y=0,z=0},radius=7000,ceiling=4000}end
assert(A.recovery(input).mode=='hold')
""")

    def test_verified_overflight_preserves_a_direct_route(self):
        self.lua.execute("""
input.source.y=5000;input.destination.altitude=5000
local plan=A.recovery(input);assert(plan.mode=='return' and #plan.path==0)
""")

    def test_emergency_exit_is_outward_and_is_not_limited_to_the_work_zone(self):
        self.lua.execute("""
input.source.x=-1000
local plan=A.escape(input)
assert(plan.escape and plan.point.x< -9000 and math.abs(plan.point.z)<1)
assert(plan.altitude==input.source.y)
input.destination={x=-40000,z=0,altitude=2000}
local recovery=A.recovery(input)
assert(recovery.mode=='return' and recovery.escape and #recovery.path>=1)
assert(recovery.path[1].x< -9000 and math.abs(recovery.path[1].z)<1)
validate(recovery)
""")

    def test_landing_inside_a_known_ring_holds_outside_instead_of_entering(self):
        self.lua.execute("""
input.destination={x=0,z=0,landing=true}
local plan=A.recovery(input)
assert(plan.mode=='hold' and plan.point.x==input.source.x)
""")

    def test_insufficient_prefix_slots_fail_closed(self):
        self.lua.execute("""
input.slots=0
local plan=A.recovery(input);assert(plan.mode=='hold')
""")

    def test_terrain_can_block_an_otherwise_safe_detour(self):
        self.lua.execute("""
input.height=function(p)return math.abs(p.z)>500 and 5000 or 0 end
local plan=A.recovery(input);assert(plan.mode=='blocked')
""")

    def test_long_direct_landing_keeps_a_cruise_leg(self):
        self.lua.execute("""
input.threats={};input.destination={x=110000,z=0,landing=true}
local plan=A.recovery(input)
assert(plan.mode=='return' and #plan.path==1 and plan.altitude==2000)
assert(math.abs(A.distance(plan.path[1],input.destination)-10800)<0.01)
""")

    def test_native_low_level_radio_destination_uses_its_planned_clearance(self):
        self.lua.execute("""
input.threats={};input.source.y=500
input.destination={x=20000,z=0,altitude=60.95999804928006,radioAltitude=60.95999804928006}
local plan=A.recovery(input)
assert(plan.mode=='return' and #plan.path==0)
local route={{x=20000,y=0,alt=60.95999804928006,alt_type='RADIO',type='Turning Point'}}
assert(A.recoverySafe(input,route,1,1,false))
-- The exception belongs to the native RADIO leg, not invented diversion points.
input.destination.radioAltitude=nil
assert(A.recovery(input).mode=='hold')
route[1].alt_type='BARO';assert(not A.recoverySafe(input,route,1,1,false))
""")

    def test_radio_recovery_follows_terrain_but_keeps_baro_and_threat_checks(self):
        self.lua.execute("""
input.source={x=0,y=500,z=0};input.threats={}
input.destination={x=20000,z=0,altitude=61,radioAltitude=61}
input.height=function(p)return p.x>9000 and p.x<11000 and 200 or 0 end
assert(A.recovery(input).mode=='return')
local route={{x=20000,y=0,alt=61,alt_type='RADIO',type='Turning Point'}}
assert(A.recoverySafe(input,route,1,1,false))
route[1].alt_type='BARO';assert(not A.recoverySafe(input,route,1,1,false))
route[1].alt_type='RADIO'
input.height=function()return 0 end
input.threats={{point={x=20000,y=0,z=0},radius=7000,ceiling=4000}}
assert(A.recovery(input).mode~='return')
assert(not A.recoverySafe(input,route,1,1,false))
""")

    def test_radio_recovery_cannot_use_high_endpoint_terrain_to_ignore_a_threat(self):
        self.lua.execute("""
input.source={x=0,y=3000,z=0}
input.destination={x=20000,z=0,altitude=2700,radioAltitude=700}
input.height=function(p)return p.x>18000 and 2000 or 0 end
input.threats={{point={x=10000,y=0,z=0},radius=5000,ceiling=1000}}
local route={{x=20000,y=0,alt=700,alt_type='RADIO',type='Turning Point'}}
assert(not A.recoverySafe(input,route,1,1,false))
local plan=A.recovery(input)
assert(plan.mode~='return' or #plan.path>0)
-- Any invented BARO diversion still needs the normal terrain clearance.
input.source.y=500;input.destination.altitude=61;input.destination.radioAltitude=61
input.height=function(p)return math.abs(p.z)>100 and 600 or 0 end
assert(A.recovery(input).mode~='return')
""")

    def test_safe_overflight_cannot_descend_into_a_radio_threat_using_escape(self):
        self.lua.execute("""
input.source={x=0,y=3000,z=0}
input.destination={x=20000,z=0,altitude=61,radioAltitude=61}
input.threats={{point={x=0,y=0,z=0},radius=5000,ceiling=1000}}
local route={{x=20000,y=0,alt=61,alt_type='RADIO',type='Turning Point'}}
assert(not A.recoverySafe(input,route,1,1,false))
local plan=A.recovery(input)
assert(plan.mode~='return' or #plan.path>0)
""")
