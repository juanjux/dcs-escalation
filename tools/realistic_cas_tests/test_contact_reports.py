"""Contact lifecycle notices use snapshots and coalition addressing, not native UI proof."""

import unittest

import test_bootstrap
from test_contact_core import CORE, CORE_FIXTURE
from lupa.lua51 import LuaRuntime


class ContactSnapshotTests(unittest.TestCase):
    def test_observed_types_are_copied_and_reset_after_expiry(self):
        rt = LuaRuntime()
        rt.execute(CORE)
        rt.execute(CORE_FIXTURE)
        rt.execute("""
        assert(s:register('red',1))
        assert(not s:observe('red',1,p,'visual','SECRET'))
        assert(not s:observe('red',2,p,'visual',{}))
        assert(s:observe('red',2,p,'visual','T-72B'))
        assert(s:observe('red',2,p,'ir','BMP-2'))
        local c=s:getContact('red',2)
        assert(table.concat(c.observedTypes,',')=='BMP-2,T-72B')
        c.observedTypes[1]='MUTATED';c.lastPosition.x=999;c.discoveredAt=999
        assert(s:getContact('red',2).lastPosition.x==10)
        assert(s:getContact('red',2).observedTypes[1]=='BMP-2')
        assert(s:getContact('red',2).discoveredAt==0)
        now=11;assert(s:fire('red',p,'Ural-375'))
        assert(RealisticCAS.contactDescription(s:getContact('red',2))=='Ural-375')
        assert(s:getContact('red',1)==nil)
        """)


class ContactReportTests(unittest.TestCase):
    def setUp(self):
        test_bootstrap.BootstrapTests.setUp(self)
        self.rt.execute("""
        messages={}
        trigger={action={outTextForCoalition=function(side,text,seconds)
          messages[#messages+1]={side=side,text=text,seconds=seconds}
        end}}
        coord={LOtoLL=function(p)return p.x/1000,p.z/1000 end,
          LLtoMGRS=function()return {UTMZone='38T',MGRSDigraph='KM',Easting=12345,Northing=67890}end}
        cfg.registry.observers={};cfg.contactReports=true;cfg.contactReportSeconds=25
        cfg.ttl=30
        p={x=1000,y=0,z=2000}
        """)

    def test_known_ground_groups_stay_visible_without_discovery_or_expiry_reports(self):
        self.rt.execute("""
        cfg.registry.groups={};cfg.registry.targets={}
        cfg.registry.knownGroundGroups={{name='red',coalition=1}}
        local m=assert(RealisticCAS.startMission(cfg))
        assert(not red.hidden and not m.fog.service:isRegistered(1))
        assert(not m.fog:observe('red',2,p,'visual:scout','SA-18'))
        emit(world.event.S_EVENT_SHOT,red)
        run(100)
        assert(not red.hidden and #messages==0)
        assert(m:stop())
        """)

    def test_discovery_renewal_expiry_and_rediscovery(self):
        self.rt.execute("""
        local m=assert(RealisticCAS.startMission(cfg));assert(#messages==0)
        assert(m.fog:observe('red',2,p,'visual:scout','T-72B'))
        assert(#messages==1 and messages[1].side==2 and messages[1].seconds==25)
        assert(messages[1].text:find('Enemy contact discovered: T%-72B'))
        assert(messages[1].text:find('N 01 00.000 E 02 00.000',1,true))
        assert(m.fog:observe('red',2,p,'ir:scout','BMP-2'));assert(#messages==1)
        -- Forget reports keep the old position even if the real target moves.
        target.point.x=90000
        now=m.fog.service:getContact(1,2).expiresAt;m.fog.service:tick()
        assert(#messages==2 and messages[2].text:find('Enemy contact forgotten:',1,true))
        assert(messages[2].text:find('BMP%-2, T%-72B') and messages[2].text:find('N 01 00.000',1,true))
        assert(m.fog:observe('red',2,p,'visual:scout','Ural-375'))
        assert(#messages==3 and messages[3].text:find('Ural%-375') and not messages[3].text:find('T%-72B'))
        assert(m:stop());assert(#messages==3)
        """)

    def test_firing_self_reveal_is_reported_once(self):
        self.rt.execute("""
        local m=assert(RealisticCAS.startMission(cfg))
        function target:getName()return 'target'end
        for h in pairs(handlers)do h:onEvent({id=world.event.S_EVENT_SHOT,initiator=target})end
        assert(#messages==1 and messages[1].side==2)
        assert(messages[1].text:find('revealed by firing: T%-72B'))
        for h in pairs(handlers)do h:onEvent({id=world.event.S_EVENT_SHOOTING_START,initiator=target})end
        assert(#messages==1 and m.fog.service:isRevealed(1,2))
        assert(m:stop())
        """)

    def test_destroyed_contacts_do_not_report_forgotten_even_before_cleanup_runs(self):
        self.rt.execute("""
        local m=assert(RealisticCAS.startMission(cfg))
        assert(m.fog:observe('red',2,p,'visual','T-72B'));assert(#messages==1)
        target.life=0
        now=m.fog.service:getContact(1,2).expiresAt;m.fog.service:tick()
        assert(#messages==1)
        assert(m:stop())
        """)

    def test_destroyed_contact_is_removed_without_f10_or_contact_reports(self):
        self.rt.execute("""
        cfg.contactReports=false
        local m=assert(RealisticCAS.startMission(cfg))
        assert(m.fog:observe('red',2,p,'visual','T-72B'))
        target.life=0;run(4)
        assert(not m.fog.service:isRegistered(1) and #messages==0)
        assert(m.fog.service:getDiagnostics().scheduled==0)
        assert(m:stop())
        """)

    def test_disabled_reports_do_not_change_discovery_or_expiry(self):
        self.rt.execute("""
        cfg.contactReports=false
        local m=assert(RealisticCAS.startMission(cfg))
        assert(m.fog:observe('red',2,p,'visual','T-72B') and not red.hidden)
        now=m.fog.service:getContact(1,2).expiresAt;m.fog.service:tick()
        assert(red.hidden and #messages==0)
        assert(m:stop())
        """)

    def test_blue_enemy_reports_go_only_to_red(self):
        self.rt.execute("""
        blue.category=Group.Category.GROUND
        cfg.registry.groups={{name='blue',originalInvisible=false}}
        cfg.registry.targets={}
        local m=assert(RealisticCAS.startMission(cfg))
        assert(m.fog:observe('blue',1,p,'visual','M-1 Abrams'))
        assert(#messages==1 and messages[1].side==1 and messages[1].text:find('M%-1 Abrams'))
        assert(m:stop())
        """)

    def test_hide_retries_do_not_repeat_forgotten_reports(self):
        self.rt.execute("""
        local m=assert(RealisticCAS.startMission(cfg))
        assert(m.fog:observe('red',2,p,'visual','T-72B'))
        red.fail=true;now=m.fog.service:getContact(1,2).expiresAt
        m.fog.service:tick();assert(#messages==2 and not m.fog.service:isRevealed(1,2))
        now=now+5;m.fog.service:tick();assert(#messages==2)
        red.fail=false;now=now+5;m.fog.service:tick();assert(red.hidden and #messages==2)
        assert(m:stop())
        """)

    def test_report_failure_does_not_break_contact_state(self):
        self.rt.execute("""
        local m=assert(RealisticCAS.startMission(cfg))
        trigger.action.outTextForCoalition=function()error('display unavailable')end
        assert(m.fog:observe('red',2,p,'visual','T-72B'))
        assert(m.fog.service:isRevealed(1,2))
        now=m.fog.service:getContact(1,2).expiresAt;m.fog.service:tick()
        assert(red.hidden and not m.fog.service:isRevealed(1,2))
        local logged=false
        for _,line in ipairs(logs)do if line:find('CONTACT_REPORT_ERROR',1,true)then logged=true end end
        assert(logged and m:stop())
        """)

    def test_invalid_settings_fail_before_visibility_changes(self):
        self.rt.execute("""
        local count=#commands
        for _,bad in ipairs({'yes',0})do
          cfg.contactReports=bad;assert(not pcall(RealisticCAS.startMission,cfg))
        end
        cfg.contactReports=true
        for _,bad in ipairs({false,0,301,1.5,0/0})do
          cfg.contactReportSeconds=bad;assert(not pcall(RealisticCAS.startMission,cfg))
        end
        assert(#commands==count and not RealisticCAS.mission)
        """)
