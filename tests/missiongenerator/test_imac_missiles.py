"""Native Weapon contacts must not be treated as Units or reveal their launchers."""

from typing import Any

import pytest

from .test_imac_dcs import runtime as native_runtime, start


def runtime() -> Any:
    lua = native_runtime()
    lua.execute("""
        missile={id_=101,side=1,x=120000,alt=100,observedX=120000,alive=true,
          attributes={['Cruise missiles']=true},category=1,positionReads=0,poison=true,
          velocity={x=-250,y=0,z=0}}
        function missile:isExist()return self.alive end
        function missile:getCoalition()return self.side end
        -- Some native builds report descriptor categories here. Missile=1
        -- collides with Unit.HELICOPTER; only the Weapon API identifies it.
        function missile:getCategory()return 1 end
        function missile:getDesc()return {category=self.category,attributes=self.attributes}end
        function missile:getLauncher()error('launcher intelligence is forbidden')end
        function missile:getGroup()error('Weapons have no Group')end
        function missile:isActive()error('Weapons have no isActive')end
        function missile:getPoint()
          self.positionReads=self.positionReads+1
          assert(not self.poison,'undetected weapon position was read')
          return {x=self.x,y=self.alt,z=0}
        end
        function missile:getVelocity()assert(not self.poison);return self.velocity end
        awacs.detections={missile}
    """)
    return lua


@pytest.mark.parametrize(
    "attributes",
    [
        "{['Cruise missiles']=true}",
        "{['Anti-Ship missiles']=true}",
        "{['Antiship Missiles']=true}",
    ],
)
def test_known_interceptable_weapons_use_native_engagement_filters(
    attributes: str,
) -> None:
    lua = runtime()
    lua.execute("missile.attributes=" + attributes)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    assert lua.eval("missile.positionReads") == 0
    assert lua.eval("groups.CAP.pushes[1].id") == "ControlledTask"
    assert lua.eval("groups.CAP.pushes[1].params.task.id") == "Mission"
    points = lua.eval("groups.CAP.pushes[1].params.task.params.route.points")
    assert len(points) == 2
    assert points[2].x < 120000  # Observed velocity predicts an intercept ahead.
    for point in points.values():
        assert point.alt == 6000  # A low missile does not force low transit.
        engage = point.task.params.tasks[1]
        assert engage.id == "EngageTargets"
        assert set(engage.params.targetTypes.values()) == {
            "Cruise missiles",
            "Antiship Missiles",
        }
        assert engage.params.groupId is None and engage.params.unitId is None
        assert engage.params.maxDistEnabled is True
    assert points[2].task.params.tasks[2].id == "Orbit"


@pytest.mark.parametrize(
    "change",
    [
        "missile.knownType=false",
        "missile.distanceKnown=false",
        "missile.detected=false",
        "missile.attributes={['AA Missiles']=true}",
        "missile.attributes={['SA Missiles']=true}",
        "missile.attributes={['AG Missiles']=true}",
        "missile.category=3",
        "missile.category=0",
        "missile.side=2",
        "missile.side=0",
        "missile.alive=false",
    ],
)
def test_other_weapons_and_unconfirmed_positions_never_trigger_interception(
    change: str,
) -> None:
    lua = runtime()
    lua.execute("missile.visible=true;" + change)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("missile.positionReads") == 0


def test_current_missile_detection_requires_range_before_live_coordinates() -> None:
    lua = runtime()
    lua.execute("missile.visible=true;missile.poison=false")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 1
    assert lua.eval("missile.positionReads") > 0


def test_weapon_without_unit_get_id_uses_its_native_handle() -> None:
    lua = runtime()
    assert lua.eval("missile.getID==nil") is True
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order.data.key") == "weapon:101"
    assert (
        lua.eval("#logs>0 and table.concat(logs,';'):find('IMAC|ERROR|',1,true)==nil")
        is True
    )


def test_unidentifiable_weapon_is_not_cached_as_a_shared_nil_target() -> None:
    lua = runtime()
    lua.execute("missile.id_=nil")
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    assert lua.eval("table.concat(logs,';'):find('IMAC|ERROR|',1,true)==nil") is True


def test_separate_sensor_wrappers_share_the_same_weapon_identity() -> None:
    lua = runtime()
    lua.execute("""
        duplicate={};for key,value in pairs(missile)do duplicate[key]=value end
        assert(duplicate~=missile and duplicate.id_==missile.id_)
        cap.detections={duplicate}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert "tracks: 1" in lua.eval("EscalationIMAC.status(2)")
    assert lua.eval("#groups.CAP.pushes") == 1


@pytest.mark.parametrize("removed", [True, False])
def test_missile_removal_or_contact_expiry_releases_the_original_route(
    removed: bool,
) -> None:
    lua = runtime()
    start(lua)
    lua.execute("tick(5);awacs.detections={};cap.detections={missile}")
    if removed:
        lua.execute("missile.alive=false;tick(15)")
    else:
        # Assigned interceptors must not renew their own mission-created contact.
        lua.execute("tick(20);tick(40)")
    assert lua.eval("EscalationIMAC.instance.states.CAP.order==nil") is True
    assert lua.eval("#groups.CAP.rtbs") == 0
    assert lua.eval("#groups.CAP.pushes") == 1


def test_returning_escort_uses_native_aircraft_task_only_after_its_split() -> None:
    lua = native_runtime()
    lua.execute("""
        cfg.flights[1].mode='observe';cfg.flights[1].returnInterceptor=true
        cfg.flights[1].returnStartIndex=4;cfg.flights[1].approachIndex=5
        awacs.detections={bandit}
    """)
    start(lua)
    lua.execute("tick(5)")
    assert lua.eval("#groups.CAP.pushes") == 0
    lua.execute("EscalationIMAC.reached('CAP',4);tick(15)")
    assert lua.eval("groups.CAP.pushes[1].params.task.id") == "AttackGroup"
    assert lua.eval("groups.CAP.pushes[1].params.task.params.groupId") == "BOMBER"


def test_returning_escort_has_individual_f10_pause_controls() -> None:
    lua = native_runtime()
    lua.execute("cfg.flights[1].mode='observe';cfg.flights[1].returnInterceptor=true")
    start(lua)
    lua.execute("""
        for _,menu in ipairs(menus)do
          if menu.side==2 and menu.path.name=='CAP' and menu.name=='Pause IMAC for this flight' then
            menu.fn()
          end
        end
    """)
    assert lua.eval("EscalationIMAC.instance.states.CAP.paused") is True
