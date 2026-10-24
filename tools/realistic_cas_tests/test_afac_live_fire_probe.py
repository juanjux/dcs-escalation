"""Read-only live-fire diagnostics; actual weapon behaviour needs native DCS."""

from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime


class AfacLiveFireProbeTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.execute("""
now=0;logs={};mutations=0;pending={};handlers={}
timer={getTime=function()return now end,scheduleFunction=function(fn,_,at)pending[at]=fn end}
env={info=function(text)logs[#logs+1]=text end}
world={event={S_EVENT_SHOT=1,S_EVENT_SHOOTING_START=2,S_EVENT_SHOOTING_END=3,S_EVENT_HIT=4},
  addEventHandler=function(h)handlers[#handlers+1]=h end}
land={getHeight=function()return 0 end}
function aircraft()
  local u={point={x=9000,y=1000,z=0},life=100}
  function u:isExist()return true end
  function u:getName()return self==blue and 'blue' or 'red' end
  function u:getPoint()return self.point end
  function u:getLife()return self.life end
  function u:getLife0()return 100 end
  function u:inAir()return true end
  function u:getController()mutations=mutations+1;error('read-only diagnostic')end
  return u
end
blue=aircraft();red=aircraft();red.point={x=0,y=0,z=0}
Unit={getByName=function(name)return name=='blue' and blue or name=='red' and red or nil end}
Group={getByName=function()return {getID=function()return 123 end}end}
service={known=false,reason='unknown',
  isRevealed=function(self,_,side)assert(side==2);return self.known end,
  getContact=function(self)return {reason=self.reason}end,
  observe=function()mutations=mutations+1;error('diagnostics must not observe')end,
  fire=function()mutations=mutations+1;error('diagnostics must not reveal')end}
RealisticCAS={mission={fog={service=service}}}
LIVE_CONFIG={aircraft={{name='blue',group='blue-group',side=2,case=3}},
  threats={{name='red',groupName='red-group',coalition=1,radius=7000,ceiling=4000,known=false}}}
function contains(part)
  for _,line in ipairs(logs)do if line:find(part,1,true)then return true end end
  return false
end
function tick(at)now=at;return pending[1](nil,now)end
""")
        self.lua.execute(
            Path(__file__).with_name("afac_live_fire_probe.lua").read_text("utf-8")
        )

    def test_knowledge_exposure_and_escape_are_observed_without_mutating_the_game(self):
        self.lua.execute("""
tick(1);assert(contains('known=false'))
service.known=true;service.reason='fire';blue.point.x=6000
tick(2);assert(contains('KNOWN_DANGER|t=2|case=3') and contains('reason=fire'))
tick(3);assert(contains('sampledKnownExposure=1'))
blue.point.x=9000;tick(4)
assert(contains('ESCAPED|t=4|case=3') and contains('elapsed=2'))
assert(mutations==0 and #handlers==1)
""")

    def test_fire_bursts_and_hits_include_health_and_return_phase(self):
        self.lua.execute("""
service.known=true;service.reason='fire';RealisticCAS.afacReturn={['blue-group']='BINGO'}
handlers[1]:onEvent({id=1,initiator=red})
handlers[1]:onEvent({id=2,initiator=red})
blue.life=40
handlers[1]:onEvent({id=4,initiator=red,target=blue})
tick(1)
assert(contains('FIRST_FIRE') and contains('phase=return|health=0.4'))
assert(contains('shots=1|bursts=1|firing=true|hits=1'))
handlers[1]:onEvent({id=3,initiator=red});tick(2)
assert(contains('firing=false|hits=1') and mutations==0)
""")

    def test_verified_overflight_and_unknown_ceiling_are_distinguished(self):
        self.lua.execute("""
service.known=true;blue.point={x=1000,y=4500,z=0}
tick(1);assert(contains('insideModel=false|insideBuffer=false'))
LIVE_CONFIG.threats[1].ceiling=nil;tick(2)
assert(contains('ceiling=nil|insideModel=true|insideBuffer=true'))
assert(mutations==0)
""")

    def test_malformed_events_and_unavailable_native_objects_do_not_raise(self):
        self.lua.execute("""
handlers[1]:onEvent({});handlers[1]:onEvent({id=1,initiator={}})
handlers[1]:onEvent({id=4,target={}})
function red:getPoint()error('native unit gone')end
function blue:getLife()error('native unit gone')end
tick(1);assert(contains('health=-1') and mutations==0)
""")
