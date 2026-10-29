"""F10 display contracts use the real contact core, without native rendering claims."""

import unittest
from pathlib import Path
from lupa.lua51 import LuaRuntime

import test_sensors
import test_bootstrap
from test_contact_core import PLUGIN

SOURCE = (PLUGIN / "f10-contacts.lua").read_text("utf-8")
MARKS = """
marks={};ever={};created={};removed={};removeFailure=false
world.event.S_EVENT_MARK_ADDED=25
world.getMarkPanels=function()return {{idx=200000000}}end
trigger=trigger or {};trigger.action=trigger.action or {}
trigger.action.markToCoalition=function(id,text,p,side,readonly)
  assert(not ever[id] and side==2 and readonly)
  ever[id]=true;marks[id]={x=p.x,y=p.y,z=p.z,text=text};created[#created+1]=id
end
trigger.action.removeMark=function(id)
  if removeFailure then error('map unavailable')end
  marks[id]=nil;removed[#removed+1]=id
end
"""


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.rt = LuaRuntime()
        self.rt.execute((PLUGIN / "core.lua").read_text("utf-8"))
        self.rt.execute(SOURCE)
        self.rt.execute("""
        now=0;serial=100;marks={};ever={};ids={};removed={};removeFailure=false
        s=RealisticCAS.new({enabled=true,ttl=15,clock=function()return now end,setVisible=function()return true end})
        assert(s:register(1,1));assert(s:register(2,1));assert(s:register(22,1))
        mapOptions={groups={{name='front',id=1,coalition=1},{name='support',id=2,coalition=1}},
          readContact=function(id,side)return s:getContact(id,side)end,
          allocateMarkId=function()serial=serial+1;return serial end,
          setMark=function(id,side,p,text)
            assert(side==2 and not ever[id]);ever[id]=true
            ids[#ids+1]=id;marks[id]={x=p.x,y=p.y,z=p.z,text=text}
          end,
          removeMark=function(id)
            if removeFailure then return false end
            marks[id]=nil;removed[#removed+1]=id
          end}
        layer=RealisticCAS.newF10Contacts(mapOptions)
        """)

    def test_reveal_renew_expire_and_rediscover_have_fresh_ids(self):
        self.rt.execute("""
        layer:tick();assert(next(marks)==nil)
        assert(s:observe(22,2,{x=999,y=0,z=0}));layer:tick();assert(next(marks)==nil)
        assert(not s:observe(1,1,{x=1,y=0,z=0}))
        assert(s:observe(1,2,{x=10,y=0,z=20}));layer:tick();assert(marks[101].x==10)
        now=5;layer:tick();assert(#ids==1 and s:getContact(1,2).expiresAt==15)
        assert(s:observe(1,2,{x=70,y=0,z=80}));layer:tick()
        assert(not marks[101] and marks[102].x==70 and removed[1]==101)
        now=20;s:tick();layer:tick();assert(next(marks)==nil)
        now=21;assert(s:observe(1,2,{x=90,y=0,z=100}));layer:tick()
        assert(marks[103].x==90 and #ids==3)
        assert(layer:stop() and next(marks)==nil and s:isRevealed(1,2))
        """)

    def test_stationary_renewal_avoids_native_churn_and_keeps_real_expiry(self):
        self.rt.execute("""
        assert(s:observe(1,2,{x=10,y=0,z=20}));layer:tick()
        now=5;assert(s:observe(1,2,{x=10,y=0,z=20}));layer:tick();assert(#ids==1)
        now=19;s:tick();layer:tick();assert(marks[101])
        now=20;s:tick();layer:tick();assert(next(marks)==nil)
        """)

    def test_round_robin_budget_and_cleanup_retry(self):
        self.rt.execute("""
        assert(s:observe(1,2,{x=10,y=0,z=20}));assert(s:observe(2,2,{x=30,y=0,z=40}))
        assert(layer:tick(1)==1 and #ids==1);assert(layer:tick(1)==1 and #ids==2)
        removeFailure=true
        now=5;assert(s:observe(1,2,{x=70,y=0,z=80}));layer:tick()
        assert(marks[101] and marks[103]) -- failed removal remains owned for retry
        assert(not layer:stop())
        removeFailure=false;assert(layer:stop() and next(marks)==nil)
        local reads=layer:diagnostics().reads;layer:tick();assert(layer:diagnostics().reads==reads)
        """)

    def test_labels_include_only_observed_types_and_refresh_at_the_same_position(self):
        self.rt.execute("""
        assert(s:observe(1,2,{x=10,y=0,z=20},'visual','T-72B'));layer:tick()
        assert(marks[101].text=='Frontline contact: T-72B\\nDiscovered at 00:00:00')
        now=1;assert(s:observe(1,2,{x=10,y=0,z=20},'ir','T-72B'));layer:tick()
        assert(#ids==1)
        assert(s:observe(1,2,{x=10,y=0,z=20},'ir','BMP-2'));layer:tick()
        assert(#ids==2 and not marks[101])
        assert(marks[102].text=='Frontline contact: BMP-2, T-72B\\nDiscovered at 00:00:00')
        local contact=s:getContact(1,2);contact.observedTypes[1]='UNSEEN SECRET UNIT'
        layer:tick();assert(#ids==2 and not marks[102].text:find('SECRET'))
        now=16;s:tick();layer:tick();assert(next(marks)==nil)
        assert(s:observe(1,2,{x=10,y=0,z=20},'fire','Ural-375'));layer:tick()
        assert(marks[103].text=='Frontline contact: Ural-375\\nDiscovered at 00:00:16')
        """)

    def test_large_allowlist_is_processed_in_bounded_round_robin_batches(self):
        self.rt.execute("""
        local groups,visits={},{}
        for i=1,1000 do groups[i]={name='front'..i,id=i,coalition=1}end
        local map=RealisticCAS.newF10Contacts({groups=groups,
          readContact=function(id)visits[#visits+1]=id end,
          allocateMarkId=function()error('no contact should be rendered')end,
          setMark=function()error('no contact should be rendered')end,removeMark=function()end})
        assert(map:tick(17)==17 and #visits==17)
        assert(map:tick(17)==17 and #visits==34 and visits[18]==18)
        assert(map:stop())
        """)

    def test_discovery_clock_is_stable_until_expiry_and_rediscovery(self):
        self.rt.execute("""
        assert(layer:stop());mapOptions.timeOffset=13*3600
        layer=RealisticCAS.newF10Contacts(mapOptions)
        now=5;assert(s:observe(1,2,{x=10,y=0,z=20},'visual','T-72B'))
        now=8;layer:tick()
        assert(marks[101].text:find('Discovered at 13:00:05',1,true))
        now=9;assert(s:observe(1,2,{x=10,y=0,z=20},'ir','T-72B'));layer:tick()
        assert(#ids==1 and s:getContact(1,2).discoveredAt==5)
        assert(s:getContact(1,2).observedAt==9)
        now=25;s:tick();layer:tick();assert(next(marks)==nil)
        now=26;assert(s:observe(1,2,{x=10,y=0,z=20},'visual','T-72B'));layer:tick()
        assert(marks[102].text:find('Discovered at 13:00:26',1,true))
        """)

    def test_clock_wraps_at_midnight_and_rejects_invalid_offsets(self):
        self.rt.execute("""
        assert(layer:stop());mapOptions.timeOffset=86397
        layer=RealisticCAS.newF10Contacts(mapOptions)
        now=5;assert(s:observe(1,2,{x=10,y=0,z=20}));layer:tick()
        assert(marks[101].text:find('Discovered at 00:00:02',1,true))
        for _,bad in ipairs({false,'13:00',0/0,math.huge})do
          mapOptions.timeOffset=bad
          assert(not pcall(RealisticCAS.newF10Contacts,mapOptions))
        end
        """)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        test_sensors.BridgeTests.setUp(self)
        self.rt.execute(SOURCE)
        self.rt.execute(MARKS)

    def test_foreign_mark_ids_restart_and_cleanup(self):
        self.rt.execute("""
        local options={groups={{name='red',id=1,coalition=1}}}
        local display=RealisticCAS.startF10Contacts(fog,options)
        assert(fog:observe('red',2,{x=10,y=0,z=20}));run(2)
        assert(created[1]==200000001)
        for h in pairs(handlers)do h:onEvent({id=25,idx=200000090})end
        assert(fog:observe('red',2,{x=70,y=0,z=80}));run(4)
        assert(created[2]==200000091 and not marks[created[1]])
        assert(display:stop() and next(marks)==nil)
        display=RealisticCAS.startF10Contacts(fog,options);run(4)
        assert(created[3]>created[2])
        removeFailure=true;assert(not display:stop())
        removeFailure=false;assert(display:stop() and fog:stop());run(5)
        assert(next(marks)==nil and next(handlers)==nil and #pending==0)
        """)

    def test_native_marker_receives_the_observed_type_label(self):
        self.rt.execute("""
        local display=RealisticCAS.startF10Contacts(fog,{groups={{name='red',id=1,coalition=1}}})
        assert(fog:observe('red',2,{x=10,y=0,z=20},'visual','T-72B'));run(2)
        assert(marks[created[1]].text=='Frontline contact: T-72B\\nDiscovered at 00:00:00')
        assert(display:stop())
        """)

    def test_native_marker_uses_mission_clock_not_elapsed_runtime(self):
        self.rt.execute("""
        timer.getAbsTime=function()return 13*3600+now end
        local display=RealisticCAS.startF10Contacts(fog,{groups={{name='red',id=1,coalition=1}}})
        assert(fog:observe('red',2,{x=10,y=0,z=20},'visual','T-72B'));run(2)
        assert(marks[created[1]].text:find('Discovered at 13:00:00',1,true))
        assert(display:stop())
        """)

    def test_destroyed_group_loses_its_marker_and_no_longer_has_a_contact(self):
        self.rt.execute("""
        local display=RealisticCAS.startF10Contacts(fog,{groups={{name='red',id=1,coalition=1}}})
        assert(fog:observe('red',2,{x=10,y=0,z=20},'visual','T-72B'));run(2)
        assert(next(marks))
        target.life=0;run(4)
        assert(next(marks)==nil and not fog.service:isRegistered(1))
        assert(fog.service:getDiagnostics().scheduled==0)
        assert(not fog:observe('red',2,{x=10,y=0,z=20}))
        assert(display:stop())
        """)

    def test_surviving_units_keep_the_group_contact(self):
        self.rt.execute("""
        local survivor=unit('survivor',red,'BMP-2',6000,0)
        local display=RealisticCAS.startF10Contacts(fog,{groups={{name='red',id=1,coalition=1}}})
        assert(fog:observe('red',2,{x=10,y=0,z=20},'visual','T-72B'));run(2)
        target.life=0;run(4)
        assert(next(marks) and fog.service:isRegistered(1))
        survivor.exists=false;run(4)
        assert(next(marks)==nil and not fog.service:isRegistered(1))
        assert(display:stop())
        """)

    def test_unavailable_liveness_query_does_not_erase_a_contact(self):
        self.rt.execute("""
        local display=RealisticCAS.startF10Contacts(fog,{groups={{name='red',id=1,coalition=1}}})
        assert(fog:observe('red',2,{x=10,y=0,z=20}));run(2)
        local getUnits=red.getUnits
        red.getUnits=function()error('temporary native failure')end
        run(4);assert(next(marks) and fog.service:isRegistered(1))
        red.getUnits=getUnits;assert(display:stop())
        """)


class BootstrapMapTests(unittest.TestCase):
    def setUp(self):
        test_bootstrap.BootstrapTests.setUp(self)
        self.rt.execute(SOURCE)
        self.rt.execute(MARKS)

    def test_real_detection_drives_map_and_mission_end_cleans_it(self):
        self.rt.execute("""
        cfg.f10FrontlineContacts=true;cfg.frontlineMapGroups={{name='red',id=1,coalition=1}}
        local m=assert(RealisticCAS.startMission(cfg))
        assert(next(marks)==nil);run(180)
        assert(next(marks)~=nil and m.fog.service:isRevealed(1,2))
        assert(m:stop());run(5)
        assert(next(marks)==nil and next(handlers)==nil and #pending==0)
        """)

    def test_foreign_frontline_group_is_rejected_before_fog_mutation(self):
        self.rt.execute("""
        cfg.f10FrontlineContacts=true;cfg.frontlineMapGroups={{name='foreign',id=90,coalition=1}}
        local count=#commands
        assert(not pcall(RealisticCAS.startMission,cfg))
        assert(#commands==count and not RealisticCAS.mission)
        """)
