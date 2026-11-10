"""Coalition ground-intelligence contracts, not native DCS detection simulation."""

import unittest

from lupa.lua51 import LuaRuntime

from test_contact_core import CORE, ADAPTER, ADAPTER_FIXTURE, PLUGIN

FIXTURE = """
units={};shares={};nextUnit=0
Unit={getByName=function(name)return units[name]end}
function unit(name,g)
  nextUnit=nextUnit+1
  local u={name=name,id=nextUnit,g=g,exists=true,life=100}
  function u:getID()return self.id end
  function u:getName()return self.name end
  function u:isExist()return self.exists end
  function u:getLife()return self.life end
  function u:getCoalition()return self.g.side end
  function u:getGroup()return self.g end
  function u:getPoint()error('intel must not poll target positions')end
  u.controller={knowTarget=function(_,enemy,typed,distance)
    if u.fail then error('receiver controller failed')end
    assert(typed and distance)
    shares[#shares+1]={receiver=name,target=enemy.name}
  end}
  function u:getController()return self.controller end
  units[name]=u;g.units=g.units or {};g.units[#g.units+1]=u;return u
end
red=group('red',1);blue=group('blue',2,2)
target=unit('target',red);neighbour=unit('neighbour',red)
b1=unit('blue1',blue);b2=unit('blue2',blue)
r1=unit('red1',red)
observers={{name='blue1',category='ground',coalition=2},
 {name='blue2',category='ground',coalition=2},{name='red1',category='ground',coalition=1}}
targets={{name='target',groupName='red',coalition=1},
 {name='neighbour',groupName='red',coalition=1},
 {name='blue1',groupName='blue',coalition=2}}
fog=RealisticCAS.start({enabled=true,ttl=10,targets={
 {name='red',originalInvisible=false},{name='blue',originalInvisible=false}},
 onObservation=function(name,side,contact)intel:observe(name,side,contact)end})
function build(budget)
  intel=RealisticCAS.newGroundIntel(fog,observers,targets,{budget=budget or 128,refreshSeconds=2})
end
function observe(name,side)
  local u=units[name]
  return fog:observe(u.g.name,side,{x=1,y=2,z=3},'visual:test',nil,name)
end
build()
"""


class GroundIntelTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        for source in (
            CORE,
            ADAPTER_FIXTURE,
            ADAPTER,
            (PLUGIN / "ground-intel.lua").read_text("utf-8"),
            FIXTURE,
        ):
            self.rt.execute(source)

    def check(self, script):
        self.rt.execute(script)

    def test_shared_with_whole_opposing_ground_force_not_unseen_neighbours(self):
        self.check("""
        assert(observe('target',2));assert(#shares==0)
        assert(intel:tick()==2 and #shares==2)
        assert(shares[1].receiver=='blue1' and shares[2].receiver=='blue2')
        for _,share in ipairs(shares)do assert(share.target=='target')end
        assert(observe('blue1',1));intel:tick()
        assert(#shares==3 and shares[3].receiver=='red1' and shares[3].target=='blue1')
        assert(#commands==4) -- Only hide/reveal commands; no task, ROE or AI changes.
        """)

    def test_air_neutral_and_unregistered_receivers_do_not_receive_contacts(self):
        self.check("""
        observers[#observers+1]={name='blue1',category='ground',coalition=2}
        observers[#observers+1]={name='plane',category='air',coalition=2}
        observers[#observers+1]={name='neutral',category='ground',coalition=0}
        unit('plane',group('air',3,2,0));unit('neutral',group('neutral',4,0))
        unit('outside',blue)
        build();assert(observe('target',2));intel:tick()
        assert(#shares==2)
        """)

    def test_pending_expiry_and_failed_hide_do_not_deliver_stale_information(self):
        self.check("""
        build(1);observe('target',2);intel:tick();assert(#shares==1)
        red.fail=true;now=10;fog.service:tick()
        assert(not red.hidden) -- Native hide failed, logical intel still expired.
        intel:tick();assert(#shares==1 and intel:getDiagnostics().queued==0)
        red.fail=false;now=15;fog.service:tick();assert(red.hidden)
        now=16;observe('target',2);intel:tick();intel:tick();assert(#shares==3)
        """)

    def test_no_autonomous_refresh_or_position_polling(self):
        self.check("""
        observe('target',2);intel:tick();assert(#shares==2)
        for i=1,9 do now=i;intel:tick()end
        assert(#shares==2 and fog:getContact(1,2).observedAt==0)
        now=10;intel:tick();assert(#shares==2)
        now=11;observe('target',2);intel:tick();assert(#shares==4)
        """)

    def test_renewal_coalescing_budget_and_fairness(self):
        self.check("""
        build(1);observe('target',2);observe('neighbour',2)
        for i=1,1000 do observe('target',2)end
        assert(intel:getDiagnostics().queued==2)
        for i=1,4 do
          assert(intel:tick()==1);assert(#shares==i)
          observe('target',2)
        end
        assert(shares[1].target=='target' and shares[2].target=='neighbour')
        assert(shares[3].receiver=='blue2' and shares[4].receiver=='blue2')
        assert(intel:getDiagnostics().queued==0)
        """)

    def test_dead_missing_changed_coalition_and_failed_receivers(self):
        self.check("""
        b1.fail=true;observe('target',2);intel:tick()
        assert(#shares==1 and shares[1].receiver=='blue2')
        assert(intel:getDiagnostics().errors==1)
        now=3;b1.fail=false;b1.life=0;b2.g=group('captured',5,1)
        observe('target',2);intel:tick();assert(#shares==1)
        """)

    def test_reused_target_name_and_destroyed_target_are_not_shared(self):
        self.check("""
        observe('target',2);unit('target',red);intel:tick();assert(#shares==0)
        now=3;observe('target',2);units.target.life=0;intel:tick();assert(#shares==0)
        """)

    def test_target_that_changes_coalition_is_not_shared(self):
        self.check("""
        observe('target',2);red.side=0;intel:tick();assert(#shares==0)
        """)

    def test_rediscovery_does_not_deliver_an_old_wave_or_wait_for_cooldown(self):
        self.check("""
        build(1);observe('target',2);intel:tick();assert(#shares==1)
        now=11;observe('target',2)
        assert(intel:tick()==1 and #shares==1) -- Discard the previous contact wave.
        assert(intel:tick()==1 and #shares==2 and shares[2].receiver=='blue1')
        intel:tick();assert(#shares==3 and shares[3].receiver=='blue2')
        """)

    def test_large_wave_is_bounded_and_eventually_reaches_every_receiver(self):
        self.check("""
        for i=1,1000 do
          local name='receiver'..i;unit(name,blue)
          observers[#observers+1]={name=name,category='ground',coalition=2}
        end
        build(37);observe('target',2)
        for i=1,28 do
          local before=#shares;assert(intel:tick()<=37 and #shares-before<=37)
        end
        assert(#shares==1002 and intel:getDiagnostics().queued==0)
        """)

    def test_late_receiver_and_observation_validation_and_stop(self):
        self.check("""
        units.blue2=nil;observe('target',2);intel:tick();assert(#shares==1)
        b2=unit('blue2',blue);now=3;observe('target',2);intel:tick();assert(#shares==3)
        assert(not observe('target',1))
        assert(not intel:observe('outside',2,fog:getContact(1,2)))
        assert(not intel:observe('target',0,fog:getContact(1,2)))
        now=6;observe('target',2);intel:stop();assert(intel:tick()==0 and #shares==3)
        assert(intel:getDiagnostics().queued==0)
        """)

    def test_firing_reveal_uses_the_same_sharing_path(self):
        self.check("""
        local initiator=target
        function initiator:getPoint()return {x=1,y=2,z=3}end
        for h in pairs(handlers)do h:onEvent({id=world.event.S_EVENT_SHOT,initiator=initiator})end
        assert(not red.hidden);intel:tick();assert(#shares==2)
        """)


if __name__ == "__main__":
    unittest.main()
