"""Exercise production Lua against native API doubles, not invented enemy tracks."""

from typing import Any

import pytest

from .test_imac import ROOT, config, metadata


def runtime() -> Any:
    lua = pytest.importorskip("lupa.lua51").LuaRuntime(unpack_returned_tuples=True)
    cfg = config()
    cfg["sensors"] = [
        {"name": "CAP-unit", "group": "CAP", "side": 2, "air": True},
        {"name": "AWACS-unit", "group": "AWACS", "side": 2, "air": True},
    ]
    lua.globals().cfg = lua.table_from(cfg, recursive=True)
    lua.execute("""
        now=0;logs={};messages={};scheduled={};units={};groups={};statics={};handlers={};menus={}
        Controller={Detection={VISUAL=1,OPTIC=2,RADAR=4,IRST=8,RWR=16,DLINK=32}}
        Object={Category={UNIT=1,WEAPON=2}}
        Unit={Category={AIRPLANE=0,HELICOPTER=1,GROUND_UNIT=2},getByName=function(n)return units[n]end}
        Group={getByName=function(n)return groups[n]end}
        StaticObject={getByName=function(n)return statics[n]end}
        env={info=function(s)logs[#logs+1]=s end,warning=function(s)logs[#logs+1]=s end}
        trigger={action={outTextForCoalition=function(side,s,t)messages[#messages+1]={side=side,text=s}end,
          outText=function(s,t)messages[#messages+1]={text=s}end}}
        land={getHeight=function(p)return 0 end}
        timer={getTime=function()return now end,scheduleFunction=function(fn,a,t)scheduled[#scheduled+1]=fn end}
        world={event={S_EVENT_MISSION_END=99},addEventHandler=function(h)handlers[#handlers+1]=h end,
          removeEventHandler=function(h)removedHandler=h end}
        missionCommands={
          addSubMenuForCoalition=function(side,name)return {side=side,name=name}end,
            addCommandForCoalition=function(side,name,path,fn)menus[#menus+1]={side=side,name=name,path=path,fn=fn}end,
          addSubMenuForGroup=function(id,name)return {id=id,name=name}end,
          addCommandForGroup=function(id,name,path,fn)menus[#menus+1]={id=id,name=name,fn=fn}end,
          removeItemForCoalition=function()end,removeItemForGroup=function()end
        }
        function add(name,side,x,air,attributes)
          local g={name=name,side=side,id=#handlers+100,units={},pushes={},rtbs={}}
          local u={name=name..'-unit',side=side,x=x,alt=6000,air=air,life=100,fuel=.95,
            velocity={x=0,y=0,z=0},radar=true,attributes=attributes or {},category=0,
            detections={},objectCategory=1,positionReads=0,active=true}
          local c={}
          function u:isExist()return self.life>0 end
          function u:isActive()return self.active end
          function u:getLife()return self.life end
          function u:getLife0()return 100 end
          function u:getFuel()return self.fuel end
          function u:getPlayerName()return self.player end
          function u:inAir()return self.air end
          function u:getRadar()return self.radar end
          function u:getAmmo()return {{count=4,desc={missileCategory=1}}}end
          function u:getCoalition()return self.side end
          function u:getCategory()return self.objectCategory end
          function u:getDesc()return {category=self.category,attributes=self.attributes}end
          function u:getGroup()return g end
          function u:getID()return self.name end
          function u:getPoint()
            self.positionReads=self.positionReads+1
            assert(not self.poison,'unobserved hostile position was read')
            if self.positionError then error('position error')end
            if self.invalidPoint then return {x=0/0,y=self.alt,z=0}end
            return {x=self.x,y=self.alt,z=0}
          end
          function u:getVelocity()assert(not self.poison,'hostile velocity was read');return self.velocity end
          function u:getController()return c end
          function c:getDetectedTargets(...)
            for _,kind in ipairs({...})do assert(kind~=16 and kind~=32,'bearing-only or task datalink intelligence')end
            local out={};for key,t in pairs(u.detections)do
              out[key]={object=t,visible=t.visible==true,type=t.knownType~=false,distance=t.distanceKnown~=false}
            end;return out
          end
          function c:isTargetDetected(t,...)
            if t.visible then return t.detected~=false,true,t.knownType~=false,t.distanceKnown~=false end
            return t.detected~=false,false,t.knownType~=false,t.distanceKnown~=false,t.seen or now,
              {x=t.observedX or t.x,y=t.alt,z=0},t.observedVelocity or {x=-250,y=0,z=0}
          end
          function c:pushTask(t)g.pushes[#g.pushes+1]=t end
          function c:popTask()error('must not pop another owner task')end
          function c:setTask(t)g.rtbs[#g.rtbs+1]=t end
          function c:setOption()error('must not change AI fuel, ROE or reaction options')end
          function g:isExist()return u.life>0 end
          function g:getUnits()return self.units end
          function g:getName()return self.name end
          function g:getCoalition()return self.side end
          function g:getController()return c end
          function g:getID()return self.name end
          g.units={u};units[u.name]=u;groups[name]=g
          return u
        end
        cap=add('CAP',2,0,true,{Fighters=true})
        awacs=add('AWACS',2,-100000,true,{AWACS=true})
        bandit=add('BOMBER',1,120000,true,{Bombers=true});bandit.poison=true
        function addStatic(name,side)
          local u={life=100}
          function u:isExist()return self.life>0 end
          function u:getLife()return self.life end
          function u:getCoalition()return side end
          statics[name]=u;return u
        end
        function tick(t)now=t;scheduled[1](nil,t)end
    """)
    for name in ("geometry.lua", "commander.lua", "imac-dcs.lua"):
        lua.execute((ROOT / name).read_text(encoding="utf-8"))
    return lua


def start(lua: Any) -> None:
    lua.execute("EscalationIMAC.start(cfg);EscalationIMAC.reached('CAP',2)")


def test_native_detection_uses_last_observed_position_not_live_enemy_position() -> None:
    lua = runtime()
    lua.execute("bandit.x=999999;bandit.observedX=120000;awacs.detections={bandit}")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    assert lua.eval("groups.CAP.pushes[1].params.task.id") == "AttackGroup"
    assert lua.eval("bandit.positionReads") == 0
    assert lua.eval("#groups.CAP.rtbs") == 0


def test_current_native_detection_returns_four_flags_without_memory_vectors() -> None:
    lua = runtime()
    lua.execute("""
        bandit.visible=true;bandit.poison=false;bandit.velocity={x=-250,y=0,z=0}
        awacs.detections={bandit}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    assert lua.eval("bandit.positionReads") > 0
    lua.execute("awacs.detections={};bandit.poison=true;tick(20);tick(40)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order==nil") is True


def test_existing_inactive_patrol_is_not_commanded_until_activation() -> None:
    lua = runtime()
    lua.execute("cap.active=false;awacs.detections={bandit}")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("cap:isExist() and cap:inAir()") is True
    assert lua.eval("#groups.CAP.pushes") == 0
    lua.execute("cap.active=true;tick(15)")
    assert lua.eval("#groups.CAP.pushes") == 1


def test_existing_inactive_awacs_does_not_grant_authority() -> None:
    lua = runtime()
    lua.execute("awacs.active=false;cap.detections={bandit}")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("bandit.positionReads") == 0


def test_existing_inactive_sensor_does_not_supply_contacts() -> None:
    lua = runtime()
    lua.execute("""
        cap.active=false;cap.detections={bandit};cfg.flights[1].mode='support'
        bandit.attributes={Fighters=true};bandit.observedX=-50000
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.AWACS.pushes") == 0
    assert lua.eval("bandit.positionReads") == 0


def test_existing_inactive_hostile_does_not_become_a_contact() -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit};bandit.active=false;bandit.visible=true")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("bandit.positionReads") == 0


@pytest.mark.parametrize("active,expected", [(True, 0), (False, 1)])
def test_inactive_sam_does_not_leave_an_active_threat_ring(
    active: bool, expected: int
) -> None:
    lua = runtime()
    lua.execute("""
        sam=add('SAM',1,60000,false);sam.alt=0;awacs.detections={bandit}
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=10000}}
    """)
    lua.globals().sam.active = active
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == expected


def test_inactive_dead_does_not_make_a_strike_wait_for_nonexistent_support() -> None:
    lua = runtime()
    for index, flight in enumerate(
        [metadata("STRIKE", "strike"), metadata("DEAD", "dead")], 3
    ):
        lua.globals().cfg.flights[index] = lua.table_from(flight, recursive=True)
    lua.execute("""
        strike=add('STRIKE',2,0,true);strike.velocity={x=220,y=0,z=0}
        dead=add('DEAD',2,10000,true);dead.active=false
        sam=add('SAM',1,20000,false);sam.alt=0
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000}}
    """)
    start(lua)
    lua.execute("EscalationIMAC.reached('STRIKE',2);tick(5)")
    assert lua.eval("EscalationIMAC.instance.states.STRIKE.finished") is True
    assert lua.eval("#groups.STRIKE.rtbs") == 1
    assert lua.eval("#groups.DEAD.pushes") == 0


@pytest.mark.parametrize(
    "change",
    [
        "bandit.distanceKnown=false",
        "bandit.detected=false",
        "bandit.category=2",
        "bandit.objectCategory=2",
        "bandit.side=2",
        "bandit.side=0",
    ],
)
def test_current_detection_requires_hostile_aircraft_and_native_range(
    change: str,
) -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit};bandit.visible=true;" + change)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("bandit.positionReads") == 0


def test_current_detection_with_invalid_position_is_not_shared() -> None:
    lua = runtime()
    lua.execute("""
        awacs.detections={bandit};bandit.visible=true;bandit.poison=false
        bandit.invalidPoint=true
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0


def test_native_detection_table_need_not_be_a_dense_array() -> None:
    lua = runtime()
    lua.execute("awacs.detections={[3]=bandit}")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    assert lua.eval("bandit.positionReads") == 0


def test_current_unknown_type_does_not_leak_bomber_classification() -> None:
    lua = runtime()
    lua.execute("""
        awacs.detections={bandit};bandit.visible=true;bandit.poison=false
        bandit.knownType=false;bandit.velocity={x=-250,y=0,z=0}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0


def test_current_awacs_contact_is_shared_for_protection_and_evasion() -> None:
    lua = runtime()
    lua.execute("""
        awacs.detections={bandit};bandit.visible=true;bandit.poison=false
        bandit.attributes={Fighters=true};bandit.x=-50000
        bandit.velocity={x=-250,y=0,z=0}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("groups.CAP.pushes[1].params.task.id") == "AttackGroup"
    assert lua.eval("groups.AWACS.pushes[1].params.task.id") == "Orbit"


@pytest.mark.parametrize(
    "change",
    [
        "bandit.distanceKnown=false",
        "bandit.detected=false",
        "bandit.seen=-100",
        "bandit.seen=1000",
        "bandit.category=2",
        "bandit.objectCategory=2",
        "bandit.side=0",
        "bandit.side=2",
        "awacs.air=false;cap.detections={bandit}",
        "awacs.radar=false",
        "awacs.life=0",
        "cfg.options.blue=false",
    ],
)
def test_unknown_or_unavailable_intelligence_does_not_create_an_intercept(
    change: str,
) -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit};" + change)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("bandit.positionReads") == 0


def test_unknown_type_does_not_leak_bomber_classification() -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit};bandit.knownType=false")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0


def test_assigned_interceptor_cannot_renew_task_created_detection() -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit}")
    start(lua)
    lua.execute("tick(5);awacs.detections={};cap.detections={bandit};tick(20);tick(40)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order==nil") is True
    assert lua.eval("#groups.CAP.pushes") == 1


def test_powered_command_centre_fuses_other_radars_without_an_awacs() -> None:
    lua = runtime()
    lua.execute("""
        awacs.radar=false;cap.detections={bandit}
        cc=addStatic('CC object',2);power=addStatic('POWER object',2)
        cfg.commandCenters={{name='CC object',key='CC',side=2,power={'POWER object'}}}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    lua.execute("power.life=0;tick(15)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order==nil") is True
    assert lua.eval("#groups.CAP.rtbs") == 0


def test_isolated_command_centre_needs_no_iads_membership_or_radio_link() -> None:
    lua = runtime()
    lua.execute("""
        awacs.life=0;cap.detections={bandit};cc=addStatic('ISOLATED CC object',2)
        cfg.commandCenters={{name='ISOLATED CC object',key='ISOLATED CC',side=2,power={}}}
        dcsRetribution={iadsHasWorkingPower=function()return nil end,
          iadsHasWorkingConnection=function()error('radio topology must not gate IMAC')end}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    assert "ISOLATED CC (standalone)" in lua.eval("EscalationIMAC.status(2)")
    lua.execute("cc.life=0;tick(15)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order==nil") is True
    assert "authority: unavailable" in lua.eval("EscalationIMAC.status(2)")


def test_command_centre_and_two_fixed_stations_survive_partial_building_losses() -> (
    None
):
    lua = runtime()
    lua.execute("""
        awacs.life=0;cap.detections={bandit}
        cc=addStatic('CC object',2);cc.life=0
        ccSecond=addStatic('CC SECOND object',2)
        p1=addStatic('P1 object',2);p1.life=0
        p1Second=addStatic('P1 SECOND object',2)
        p2=addStatic('P2 object',2);p2.life=0
        third=addStatic('P3 object',2)
        cfg.commandCenters={{name='CC object',key='CC',side=2,
          members={'CC object','CC SECOND object'},requiresPower=true,
          power={'P1 object','P1 SECOND object','P2 object'}}}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    lua.execute("p1Second.life=0;tick(15)")
    assert lua.eval("third.life") == 100
    assert "authority: unavailable" in lua.eval("EscalationIMAC.status(2)")
    lua.execute("p2.life=100;tick(25)")
    assert "authority: available" in lua.eval("EscalationIMAC.status(2)")
    lua.execute("ccSecond.life=0;tick(35)")
    assert "authority: unavailable" in lua.eval("EscalationIMAC.status(2)")


@pytest.mark.parametrize("requires_power,expected", [(True, False), (False, True)])
def test_empty_advanced_grid_is_not_independent_standalone_authority(
    requires_power: bool, expected: bool
) -> None:
    lua = runtime()
    lua.execute("""
        awacs.life=0;cap.detections={bandit};cc=addStatic('CC object',2)
        cfg.commandCenters={{name='CC object',key='CC',side=2,power={}}}
    """)
    lua.globals().cfg.commandCenters[1].requiresPower = requires_power
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == int(expected)


@pytest.mark.parametrize(
    "physical,answer,expected",
    [
        (False, True, True),
        (True, False, False),
        (False, None, False),
        (True, None, True),
    ],
)
def test_iads_power_answer_overrides_only_the_supply_fallback(
    physical: bool, answer: bool | None, expected: bool
) -> None:
    lua = runtime()
    lua.execute("""
        awacs.life=0;cap.detections={bandit}
        cc=addStatic('CC object',2);power=addStatic('POWER object',2)
        cfg.commandCenters={{name='CC object',key='CC',side=2,
          requiresPower=true,power={'POWER object'}}}
        dcsRetribution={iadsHasWorkingPower=function()return powerAnswer end}
    """)
    lua.globals().power.life = 100 if physical else 0
    lua.globals().powerAnswer = answer
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == int(expected)


@pytest.mark.parametrize("side,life", [(2, 0), (1, 100)])
def test_iads_power_cannot_revive_a_dead_or_enemy_command_centre(
    side: int, life: int
) -> None:
    lua = runtime()
    lua.execute("""
        awacs.life=0;cap.detections={bandit}
        cfg.commandCenters={{name='CC object',key='CC',side=2,power={}}}
        dcsRetribution={iadsHasWorkingPower=function()return true end}
    """)
    lua.globals().addStatic("CC object", side).life = life
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0


def test_isolated_command_centre_does_not_supply_undetected_contacts() -> None:
    lua = runtime()
    lua.execute("""
        awacs.life=0;cc=addStatic('ISOLATED CC object',2)
        cfg.commandCenters={{name='ISOLATED CC object',key='ISOLATED CC',side=2,power={}}}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("bandit.positionReads") == 0
    assert "authority: available" in lua.eval("EscalationIMAC.status(2)")


@pytest.mark.parametrize(
    "blue,red", [(True, True), (True, False), (False, True), (False, False)]
)
def test_side_switches_are_independent(blue: bool, red: bool) -> None:
    lua = runtime()
    for index, flight in enumerate(
        [metadata("RED_CAP", "cap", 1), metadata("RED_AWACS", "support", 1)], 3
    ):
        flight["awacs"] = flight["group"] == "RED_AWACS"
        lua.globals().cfg.flights[index] = lua.table_from(flight, recursive=True)
    lua.globals().cfg.options.blue = blue
    lua.globals().cfg.options.red = red
    lua.execute("""
        redCap=add('RED_CAP',1,0,true,{Fighters=true})
        redEye=add('RED_AWACS',1,-100000,true,{AWACS=true})
        blueBomber=add('BLUE_BOMBER',2,120000,true,{Bombers=true});blueBomber.poison=true
        awacs.detections={bandit};redEye.detections={blueBomber}
        cfg.sensors[#cfg.sensors+1]={name='RED_AWACS-unit',group='RED_AWACS',side=1,air=true}
    """)
    start(lua)
    lua.execute("EscalationIMAC.reached('RED_CAP',2);tick(5)")
    assert lua.eval("#groups.CAP.pushes") == int(blue)
    assert lua.eval("#groups.RED_CAP.pushes") == int(red)


def test_debug_is_silent_by_default() -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit};cfg.options.reports=false")
    start(lua)
    lua.execute("tick(5);tick(65)")
    assert lua.eval("#messages") == 0
    assert lua.eval("table.concat(logs,';'):find('IMAC|DEBUG|',1,true)==nil") is True


def test_debug_reports_source_orders_and_rejection_reasons_without_normal_reports() -> (
    None
):
    lua = runtime()
    lua.execute(
        "cfg.options.debug=true;cfg.options.reports=false;cfg.options.red=false;"
        "awacs.detections={bandit}"
    )
    start(lua)
    lua.execute("tick(5);tick(15)")
    log = lua.eval("table.concat(logs,';')")
    assert "IMAC|DEBUG|" in log
    assert "AWACS AWACS" in log
    assert "intercept; target group=" in log
    assert "fuel=" in log and "remaining=" in log
    assert lua.eval("#messages") > 0
    assert lua.eval("#messages") <= 4
    assert lua.eval("messages[1].side") == 2
    lua.execute(
        "awacs.detections={};tick(50);bandit.observedX=200000;awacs.detections={bandit};tick(90)"
    )
    assert "contact beyond patrol leash" in lua.eval("table.concat(logs,';')")
    assert lua.eval("bandit.positionReads") == 0


def test_debug_suppresses_disabled_sides_and_limits_screen_messages() -> None:
    lua = runtime()
    lua.execute("""
        cfg.options.debug=true;cfg.options.red=false;cfg.options.reports=false
        awacs.detections={bandit}
    """)
    start(lua)
    lua.execute("tick(5);tick(15);tick(25);tick(35);tick(45);tick(55)")
    assert lua.eval("#messages") <= 4
    assert lua.eval("table.concat(logs,';'):find('side=1|',1,true)==nil") is True
    lua.execute("tick(65)")
    assert lua.eval("#messages") <= 8


@pytest.mark.parametrize(
    "change,reason",
    [("cap.air=false", "not airborne"), ("cap.active=false", "flight unavailable")],
)
def test_inactive_debug_stays_in_the_log_without_using_screen_message_budget(
    change: str, reason: str
) -> None:
    lua = runtime()
    lua.execute("cfg.options.debug=true;cfg.options.reports=false;" + change)
    start(lua)
    lua.execute("tick(5);tick(65)")
    assert "availability|" + reason in lua.eval("table.concat(logs,';')")
    lua.globals().quietReason = reason
    assert lua.eval(
        "(function() for _,m in ipairs(messages) do "
        "if m.text:find(quietReason,1,true) then return false end end return true end)()"
    )
    lua.execute("cap.air=true;cap.active=true;cap.fuel=.1;tick(75)")
    assert "fuel at BINGO reserve" in lua.eval("messages[#messages].text")
    assert lua.eval("#groups.CAP.pushes") == 0


@pytest.mark.parametrize(
    "change",
    [
        "cc.life=0",
        "power.life=0",
        "dcsRetribution={iadsHasWorkingPower=function()return false end}",
    ],
)
def test_dead_or_unpowered_centre_does_not_supply_command(change: str) -> None:
    lua = runtime()
    lua.execute("""
        awacs.radar=false;cap.detections={bandit};cc=addStatic('CC object',2);power=addStatic('POWER object',2)
        cfg.commandCenters={{name='CC object',key='CC',side=2,power={'POWER object'}}}
    """ + change)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0


def test_human_takeover_releases_only_our_controlled_task_lease() -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit}")
    start(lua)
    lua.execute(
        "tick(5);condition=groups.CAP.pushes[1].params.stopCondition.condition;cap.player='Human'"
    )
    assert lua.eval("loadstring(condition)()") is True
    assert lua.eval("#groups.CAP.rtbs") == 0


def test_known_sam_uses_launcher_msl_and_does_not_leak_hidden_ground_position() -> None:
    lua = runtime()
    lua.execute("""
        awacs.detections={bandit}
        sam=add('SAM',1,60000,false);sam.alt=2200
        hidden=add('HIDDEN',1,50000,false);hidden.poison=true
        cfg.threats={
          {name='SAM-unit',group='SAM',side=1,known=true,radius=20000,ceiling=4000},
          {name='HIDDEN-unit',group='HIDDEN',side=1,known=false,radius=30000}
        }
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("hidden.positionReads") == 0
    lua.execute("sam.alt=0;tick(15)")
    assert lua.eval("#groups.CAP.pushes") == 1


@pytest.mark.parametrize(
    "change",
    [
        "sam.life=0",
        "radar.life=0",
        "dcsRetribution={iadsHasWorkingPower=function()return false end}",
        "cfg.threats[1].radars={};search=add('SEARCH',1,60000,false)",
        "cfg.threats[1].iadsDisabled=true;sam.positionError=true",
        "dcsRetribution={iadsCanEngage=function()return false end,iadsHasWorkingPower=function()return true end}",
    ],
)
def test_destroyed_radar_or_power_does_not_leave_a_phantom_sam_circle(
    change: str,
) -> None:
    lua = runtime()
    lua.execute("""
        awacs.detections={bandit};sam=add('SAM',1,60000,false);radar=add('RADAR',1,60000,false)
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=20000,needsRadar=true,radars={'RADAR-unit'}}}
    """ + change)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1


@pytest.mark.parametrize(
    "disabled",
    [
        "cfg.threats[1].iadsDisabled=true",
        "dcsRetribution={iadsCanEngage=function()return false end,iadsHasWorkingPower=function()return true end}",
    ],
)
def test_iads_disabled_battery_neither_holds_nor_cancels_a_strike(
    disabled: str,
) -> None:
    lua = runtime()
    lua.globals().strikeMeta = lua.table_from(
        metadata("STRIKE", "strike"), recursive=True
    )
    lua.execute("""
        cfg.flights[#cfg.flights+1]=strikeMeta
        strike=add('STRIKE',2,0,true);strike.velocity.x=220
        sam=add('SAM',1,40000,false);sam.alt=0
        radar=add('RADAR',1,40000,false)
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,
          radius=5000,ceiling=27000,needsRadar=true,radars={'RADAR-unit'}}}
    """ + disabled)
    start(lua)
    lua.execute("""
        EscalationIMAC.reached('STRIKE',2);tick(5);tick(615)
        assert(#groups.STRIKE.pushes==0 and #groups.STRIKE.rtbs==0)
        assert(not EscalationIMAC.instance.states.STRIKE.finished)
    """)


def test_iads_shutdown_releases_an_existing_strike_hold_instead_of_cancelling() -> None:
    lua = runtime()
    lua.globals().strikeMeta = lua.table_from(
        metadata("STRIKE", "strike"), recursive=True
    )
    lua.globals().deadMeta = lua.table_from(metadata("DEAD", "dead"), recursive=True)
    lua.execute("""
        cfg.flights[#cfg.flights+1]=strikeMeta;cfg.flights[#cfg.flights+1]=deadMeta
        strike=add('STRIKE',2,0,true);strike.velocity.x=220;dead=add('DEAD',2,0,true)
        sam=add('SAM',1,40000,false);sam.alt=0
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000}}
        enabled=true;dcsRetribution={iadsCanEngage=function()return enabled end}
    """)
    start(lua)
    lua.execute("""
        EscalationIMAC.reached('STRIKE',2);EscalationIMAC.reached('DEAD',2);tick(5)
        assert(EscalationIMAC.instance.states.STRIKE.order.kind=='hold')
        condition=groups.STRIKE.pushes[1].params.stopCondition.condition
        enabled=false;tick(15)
        assert(EscalationIMAC.instance.states.STRIKE.order==nil)
        assert(loadstring(condition)() and #groups.STRIKE.rtbs==0)
    """)


def test_failed_known_sam_query_keeps_its_conservative_ring() -> None:
    lua = runtime()
    lua.execute("""
        awacs.detections={bandit};sam=add('SAM',1,60000,false);sam.positionError=true
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=20000,initialPoint={x=60000,z=0}}}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("EscalationIMAC.instance.active") is True


def test_cancelled_attack_keeps_native_carrier_recovery_and_does_not_repeat_attack() -> (
    None
):
    lua = runtime()
    lua.execute("""
        cfg.flights[1].mode='strike';cfg.flights[1].endTime=nil
        cap.velocity={x=220,y=0,z=0}
        cfg.flights[1].route[5].helipadId=744;cfg.flights[1].route[5].linkUnit=744
        cfg.flights[1].route[5].airdromeId=nil
        sam=add('SAM',1,40000,false)
        cfg.threats={{name='SAM-unit',group='SAM',side=1,known=true,radius=5000}}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.rtbs") == 1
    assert lua.eval("#groups.CAP.rtbs[1].params.route.points") == 2
    assert lua.eval("groups.CAP.rtbs[1].params.route.points[2].helipadId") == 744
    assert lua.eval("groups.CAP.rtbs[1].params.route.points[2].linkUnit") == 744
    assert lua.eval("EscalationIMAC.instance.states.CAP.finished") is True


def test_recovery_does_not_land_inside_a_low_sam_just_because_cruise_is_above_it() -> (
    None
):
    lua = runtime()
    lua.execute("""
        cfg.flights[1].mode='strike';cfg.flights[1].endTime=nil
        cap.velocity={x=220,y=0,z=0}
        sam=add('SAM',1,40000,false)
        manpad=add('MANPAD',1,-50000,false);manpad.alt=0
        cfg.threats={
          {name='SAM-unit',group='SAM',side=1,known=true,radius=5000},
          {name='MANPAD-unit',group='MANPAD',side=1,known=true,radius=5000,ceiling=3500}
        }
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.rtbs") == 0
    assert lua.eval("EscalationIMAC.instance.states.CAP.order.kind") == "recoveryHold"


def test_f10_coalition_closures_pause_the_correct_side() -> None:
    lua = runtime()
    start(lua)
    lua.execute("""
        for _,m in ipairs(menus)do if m.side==1 and m.name:find('Pause')then m.fn()end end
    """)
    assert lua.eval("EscalationIMAC.instance.paused[1]") is True
    assert lua.eval("EscalationIMAC.instance.paused[2]") is None


def test_individual_ai_flight_pause_is_accessible_from_coalition_menu() -> None:
    lua = runtime()
    start(lua)
    lua.execute("""
        for _,m in ipairs(menus)do
          if m.side==2 and m.path.name=='CAP' and m.name=='Pause IMAC for this flight' then m.fn()end
        end
    """)
    assert lua.eval("EscalationIMAC.instance.states.CAP.paused") is True
    assert lua.eval("EscalationIMAC.instance.states.AWACS.paused") is None


def test_mission_end_cleans_up_and_invalidates_outstanding_leases() -> None:
    lua = runtime()
    lua.execute("awacs.detections={bandit}")
    start(lua)
    lua.execute("tick(5);handlers[1]:onEvent({id=99})")
    assert lua.eval("EscalationIMAC.instance.active") is False
    assert lua.eval("EscalationIMAC.shouldStop('CAP',1)") is True
    assert lua.eval("#groups.CAP.rtbs") == 0
