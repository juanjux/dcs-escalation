"""Generate standalone Iraq mechanism tests; never imports or edits campaign code.

Uses the user's proven Su-25T test 17 as a geometry/payload seed. Requires pydcs
and lupa from Retribution's venv. Outputs to a NEW directory (refuses overwrite).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import zipfile

from dcs import lua
from dcs.planes import plane_map
from dcs.helicopters import helicopter_map
from dcs.task import WeaponType
from lupa.lua51 import LuaRuntime

HERE = Path(__file__).resolve().parent
X, Z = 166765, 41984  # Same flat test area used in the user's successful test 17.


def literal(obj):
    """Lua 5.1 literals, including actual newlines in embedded script strings."""
    if obj is None:
        return "nil"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        assert math.isfinite(obj)
        return str(obj)
    if isinstance(obj, str):
        return (
            '"'
            + obj.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            + '"'
        )
    if isinstance(obj, list):
        obj = dict(enumerate(obj, 1))
    if isinstance(obj, dict):
        return (
            "{"
            + ",".join("[" + literal(k) + "]=" + literal(v) for k, v in obj.items())
            + "}"
        )
    raise TypeError(type(obj))


def wrapped(command, **params):
    return {
        "id": "WrappedAction",
        "params": {"action": {"id": command, "params": params}},
    }


def combo(tasks):
    result = {}
    for i, task in enumerate(tasks, 1):
        task = copy.deepcopy(task)
        task.update(number=i, auto=False, enabled=True)
        result[i] = task
    return {"id": "ComboTask", "params": {"tasks": result}}


def zone(x=X, z=Z):
    return {
        "id": "EngageTargetsInZone",
        "params": {
            "x": x,
            "y": z,
            "zoneRadius": 3000,
            "targetTypes": {1: "Ground Units"},
            "value": "Ground Units",
            "priority": 0,
        },
    }


class Builder:
    def __init__(self, seed, name, duration=600):
        self.m = copy.deepcopy(seed)
        self.name, self.nextid = name, 100
        self.seed_vehicle = copy.deepcopy(
            seed["coalition"]["blue"]["country"][4]["vehicle"]["group"][1]
        )
        self.seed_plane = copy.deepcopy(
            seed["coalition"]["red"]["country"][4]["plane"]["group"][2]
        )
        self.cfg = dict(
            name=name, duration=duration, units=[], display={}, pairs=[], actions=[]
        )
        for side in ("blue", "red"):
            self.m["coalition"][side]["country"] = {
                1: {
                    "id": 80 if side == "blue" else 81,
                    "name": "Combined Joint Task Forces " + side.title(),
                }
            }
        self.m["coalitions"] = {"blue": {1: 80}, "red": {1: 81}, "neutrals": {}}
        self.m["trig"] = {}
        self.m["trigrules"] = {}
        self.m["triggers"] = {"zones": {}}
        # Retain DCS's empty layer/role options schema, not an incomplete table.
        self.m["drawings"] = copy.deepcopy(seed["drawings"])
        self.m["requiredModules"] = {}
        self.m["usedModules"] = {}
        self.m["start_time"] = 12 * 3600
        self.m["map"] = {"centerX": X, "centerY": Z, "zoom": 80000}
        self.m["forcedOptions"] = {
            "externalViews": True,
            "optionsView": "optview_all",
            "labels": 1,
            "userMarks": True,
        }
        self.m["groundControl"]["roles"]["instructor"] = {
            "blue": 1,
            "red": 1,
            "neutrals": 0,
        }
        self.m["groundControl"]["roles"]["observer"] = {
            "blue": 1,
            "red": 1,
            "neutrals": 0,
        }
        self.m["groundControl"]["isPilotControlVehicles"] = False

    def uid(self):
        self.nextid += 1
        return self.nextid

    def add(self, side, category, g):
        c = self.m["coalition"][side]["country"][1]
        groups = c.setdefault(category, {"group": {}})["group"]
        groups[len(groups) + 1] = g
        for u in g["units"].values():
            self.cfg["units"].append(u["name"])
        return g

    def action(self, at, op, target=None, **args):
        a = dict(at=at, op=op, **args)
        if target is not None:
            a["target"] = target if isinstance(target, str) else target["name"]
        self.cfg["actions"].append(a)

    def pair(self, observer, target, label, display=True, controller="group"):
        self.cfg["pairs"].append(
            dict(
                observer=observer["name"],
                target=target["name"],
                label=label,
                display=display,
                controller=controller,
            )
        )

    def vehicle(
        self,
        name,
        x=X,
        z=Z,
        count=1,
        kind="M-1 Abrams",
        side="blue",
        hidden=False,
        immortal=True,
        hold=True,
        map_hidden=False,
    ):
        g = copy.deepcopy(self.seed_vehicle)
        g.update(
            name=name,
            groupId=self.uid(),
            x=x,
            y=z,
            hidden=map_hidden,
            hiddenOnMFD=map_hidden,
            hiddenOnPlanner=map_hidden,
        )
        seed = copy.deepcopy(g["units"][1])
        g["units"] = {}
        for i in range(1, count + 1):
            u = copy.deepcopy(seed)
            u.update(
                name=f"{name}-{i}",
                unitId=self.uid(),
                x=x,
                y=z + (i - 1) * 100,
                type=kind,
                skill="Average",
                playerCanDrive=False,
            )
            g["units"][i] = u
        point = g["route"]["points"][1]
        point.update(
            x=x,
            y=z,
            speed=0,
            task=combo(
                [
                    wrapped("SetInvisible", value=hidden),
                    wrapped("SetImmortal", value=immortal),
                    wrapped("Option", name=0, value=4 if hold else 0),
                ]
            ),
        )
        self.add(side, "vehicle", g)
        return g

    def plane(
        self,
        name,
        x=X + 18000,
        z=Z,
        altitude=2000,
        kind="Su-25T",
        size=2,
        tasks=None,
        immortal=True,
        hold=False,
        speed=150,
        pod=True,
        side="red",
    ):
        g = copy.deepcopy(self.seed_plane)
        g.update(
            name=name,
            groupId=self.uid(),
            x=x,
            y=z,
            task="CAS",
            frequency=251,
            hidden=False,
            hiddenOnMFD=False,
            hiddenOnPlanner=False,
        )
        source = copy.deepcopy(g["units"][1])
        types = {**plane_map, **helicopter_map}
        g["units"] = {}
        for i in range(1, size + 1):
            u = copy.deepcopy(source)
            u.update(
                name=f"{name}-{i}",
                unitId=self.uid(),
                x=x,
                y=z + (i - 1) * 80,
                skill="Average",
                type=kind,
                alt=altitude,
                alt_type="RADIO",
                speed=speed,
                heading=math.pi,
                psi=-math.pi,
            )
            u["callsign"] = {
                1: 3,
                2: (g["groupId"] % 9) + 1,
                3: i,
                "name": f"Uzi{g['groupId']%9+1}{i}",
            }
            u["onboard_num"] = str(u["unitId"] % 1000).zfill(3)
            if kind != "Su-25T":
                u["payload"] = dict(
                    pylons={}, fuel=types[kind].fuel_max, chaff=0, flare=0, gun=0
                )
                if kind == "FA-18C_hornet" and pod:
                    u["payload"]["pylons"][4] = {"CLSID": "{AN_ASQ_228}"}
                if kind == "A-10C_2" and pod:
                    u["payload"]["pylons"][10] = {
                        "CLSID": "{A111396E-D3E8-4b9c-8AC9-2432489304D5}"
                    }
            g["units"][i] = u
        base = copy.deepcopy(g["route"]["points"][1])
        route = {}
        initial = [
            wrapped("SetImmortal", value=immortal),
            wrapped("SetInvisible", value=False),
            wrapped("Option", name=0, value=4 if hold else 2),
            wrapped("Option", name=1, value=0),
        ]
        initial += tasks or []
        for i, (px, pz) in enumerate([(x, z), (X + 6500, z), (X + 10000, z + 6000)], 1):
            p = copy.deepcopy(base)
            p.update(
                x=px,
                y=pz,
                alt=altitude,
                alt_type="RADIO",
                speed=speed,
                ETA_locked=(i == 1),
                name=f"WP{i}",
            )
            ptasks = initial if i == 1 else []
            if i == 2:
                ptasks = [
                    {
                        "id": "Orbit",
                        "params": {
                            "pattern": "Circle",
                            "speed": speed,
                            "altitude": altitude + 200,
                            "point": {"x": px, "y": pz},
                        },
                    }
                ]
            p["task"] = combo(ptasks)
            route[i] = p
        g["route"]["points"] = route
        category = "helicopter" if kind in helicopter_map else "plane"
        self.add(side, category, g)
        return g


def cas_mission(seed, index, method, hidden, know=False):
    b = Builder(
        seed, f"{index:02d}_{method}" + ("_hidden" if hidden else "_control"), 720
    )
    target = b.vehicle("TARGET", count=6, hidden=hidden)
    params = {
        "weaponType": WeaponType.Auto.value,
        "groupAttack": True,
        "attackQtyLimit": False,
        "attackQty": 1,
        "altitudeEnabled": False,
        "directionEnabled": False,
        "expend": "Auto",
    }
    if method == "CAS" or know:
        task = zone()
    elif method == "AttackGroup":
        task = {"id": method, "params": dict(params, groupId=target["groupId"])}
    elif method == "AttackUnit":
        task = {
            "id": method,
            "params": dict(params, unitId=target["units"][1]["unitId"]),
        }
    else:
        task = {
            "id": "EngageUnit",
            "params": dict(
                params, unitId=target["units"][1]["unitId"], visible=False, priority=1
            ),
        }
    # Task exists from first waypoint; no client input or late aircraft spawns.
    f = b.plane("CAS", tasks=[task])
    for u in f["units"].values():
        b.cfg["display"][u["name"]] = True
    b.cfg["display"][target["units"][1]["name"]] = True
    for i in (1, 2):
        b.pair(f["units"][1], target["units"][i], f"target{i}")
    b.action(0, "phase", label="HIDDEN" if hidden else "VISIBLE control")
    if know:
        b.action(21, "know", f, other=target["units"][1]["name"])
    if hidden:
        for t, val, label in [
            (180, False, "REVEAL + reissue"),
            (360, True, "HIDE acquired"),
            (540, False, "REVEAL again"),
        ]:
            b.action(t, "phase", label=label)
            b.action(t, "invisible", target, value=val)
        # Explicit attack tasks may finish immediately when target is hidden.
        # Reissue once on initial reveal, identically in all six CAS controls.
    b.action(180, "task", f, task=task)
    return b


def ground_scope(seed):
    b = Builder(seed, "06_Ground_unit_vs_group", 420)
    for lane, mode in enumerate(
        ["CONTROL", "GROUP_HIDE", "UNIT1_HIDE", "GROUP_HIDE_UNIT1_SHOW"]
    ):
        z = Z + lane * 8000
        t = b.vehicle(
            mode,
            x=X,
            z=z,
            count=2,
            kind="T-72B",
            hidden=mode in ("GROUP_HIDE", "GROUP_HIDE_UNIT1_SHOW"),
        )
        o = b.vehicle("OBS_" + mode, x=X + 900, z=z, kind="M-1 Abrams", side="red")
        if mode == "UNIT1_HIDE":
            b.action(1, "invisible", t["units"][1], scope="unit", value=True)
        if mode == "GROUP_HIDE_UNIT1_SHOW":
            b.action(1, "invisible", t["units"][1], scope="unit", value=False)
        b.action(60, "roe", o, value=0)
        b.action(240, "invisible", t, value=False)
        for i in (1, 2):
            b.pair(o["units"][1], t["units"][i], f"{mode}/{i}")
            b.action(330, "invisible", t["units"][i], scope="unit", value=False)
        b.cfg["display"][o["units"][1]["name"]] = True
    b.action(0, "phase", label="Detection only; tanks HOLD")
    b.action(60, "phase", label="Observers FREE FIRE")
    b.action(240, "phase", label="All group controllers SHOW")
    b.action(330, "phase", label="All unit controllers SHOW (final positive control)")
    return b


def memory(seed):
    b = Builder(seed, "07_Memory_moving_hidden", 480)
    t = b.vehicle("MOVING_TRUCK", kind="Ural-375")
    o = b.vehicle("OBSERVER", x=X + 800, kind="M-1 Abrams", side="red")
    b.pair(o["units"][1], t["units"][1], "native memory")
    b.cfg["display"][t["units"][1]["name"]] = True
    b.action(0, "phase", label="Acquire visible truck; observer HOLD")
    b.action(60, "snapshot", t["units"][1], id=7001)
    b.action(60, "invisible", t, value=True)
    b.action(60, "phase", label="Hidden; moving away from frozen marker")
    b.action(70, "move", t, x=X - 2500, z=Z, speed=12)
    b.action(300, "invisible", t, value=False)
    b.action(300, "phase", label="Visible again (check lastPos in log)")
    return b


def fires(seed):
    b = Builder(seed, "08_Fire_events_hidden_shooters", 420)
    # Ground gun, tank cannon, AAA and SAM. All shooters invisible to opposing AI.
    for i, (kind, label, air) in enumerate(
        [
            ("M-113", "MG", False),
            ("M-1 Abrams", "TANK", False),
            ("ZSU-23-4 Shilka", "AAA", True),
            ("Osa 9A33 ln", "SAM", True),
        ]
    ):
        z = Z + i * 8000
        shooter = b.vehicle(
            label, x=X, z=z, kind=kind, side="red", hidden=True, hold=False
        )
        if air:
            target = b.plane(
                "TARGET_" + label,
                x=X + 2200,
                z=z,
                kind="MQ-9 Reaper",
                size=1,
                altitude=700,
                speed=80,
                hold=True,
                side="blue",
            )
            # Keep aircraft near its own shooter rather than default distant orbit.
            p = target["route"]["points"][2]
            p.update(x=X + 1000, y=z)
            p["task"] = combo(
                [
                    {
                        "id": "Orbit",
                        "params": {
                            "pattern": "Circle",
                            "speed": 80,
                            "altitude": 900,
                            "point": {"x": X + 1000, "y": z},
                        },
                    }
                ]
            )
        else:
            target = b.vehicle(
                "TARGET_" + label, x=X + 450, z=z, kind="Ural-375", side="blue"
            )
        b.cfg["display"][shooter["units"][1]["name"]] = True
        b.cfg["display"][target["units"][1]["name"]] = True
        b.pair(shooter["units"][1], target["units"][1], label, display=False)
    arty = b.vehicle(
        "ARTILLERY", x=X - 6000, z=Z, kind="M-109", side="red", hidden=True, hold=False
    )
    b.action(
        20,
        "task",
        arty,
        task={
            "id": "FireAtPoint",
            "params": {
                "x": X,
                "y": Z - 3000,
                "zoneRadius": 150,
                "expendQty": 6,
                "expendQtyEnabled": True,
                "weaponType": WeaponType.Auto.value,
            },
        },
    )
    b.cfg["display"][arty["units"][1]["name"]] = True
    b.action(
        0, "phase", label="Hidden shooters, visible immortal targets. No auto-reveal."
    )
    return b


def sensors(seed, index, weather):
    b = Builder(seed, f"{index:02d}_Sensors_{weather}", 600)
    if weather == "cloud":
        b.m["weather"]["clouds"] = {
            "base": 1500,
            "thickness": 2000,
            "density": 10,
            "iprecptns": 0,
            "preset": "Preset20",
        }
    if weather == "night":
        b.m["start_time"] = 0
    targets = b.vehicle("STATIONARY", count=3)
    moving = b.vehicle("MOVING", x=X, z=Z + 1500, count=1)
    b.action(1, "move", moving, x=X, z=Z + 6500, speed=10)
    profiles = [
        ("HORNET_POD", "FA-18C_hornet", 2500, 150, True),
        ("HORNET_NO_POD", "FA-18C_hornet", 2500, 150, False),
        ("F15C_CONTROL", "F-15C", 2500, 150, False),
        ("A10_POD", "A-10C_2", 2500, 130, True),
        ("MQ9_2000", "MQ-9 Reaper", 2000, 85, False),
        ("MQ9_5000", "MQ-9 Reaper", 5000, 85, False),
        ("KIOWA_300", "OH58D", 300, 50, False),
    ]
    for i, (name, kind, alt, speed, pod) in enumerate(profiles):
        f = b.plane(
            name,
            x=X + 16000,
            z=Z + (i - 3) * 300,
            altitude=alt,
            kind=kind,
            size=1,
            hold=True,
            speed=speed,
            pod=pod,
            tasks=[zone()],
        )
        b.pair(f["units"][1], targets["units"][1], name, display=True)
        b.pair(f["units"][1], moving["units"][1], name + "/moving", display=False)
    b.action(
        0, "phase", label="Sensor probes, HOLD FIRE. See log: VISUAL / OPTIC / RADAR"
    )
    return b


def fac(seed):
    b = Builder(seed, "12_FAC_vulnerability", 480)
    target = b.vehicle("FAC_TARGET", count=2, hidden=True)
    sam = b.vehicle(
        "HIDDEN_OSA",
        x=X + 3500,
        z=Z + 1000,
        kind="Osa 9A33 ln",
        hold=False,
        hidden=True,
    )
    task = {
        "id": "FAC",
        "params": {
            "designation": "Laser",
            "frequency": 30000000,
            "modulation": 1,
            "datalink": True,
            "callname": 1,
            "number": 1,
        },
    }
    f = b.plane(
        "JTAC_MQ9",
        x=X + 6000,
        z=Z,
        kind="MQ-9 Reaper",
        altitude=1800,
        size=1,
        speed=85,
        hold=True,
        immortal=False,
        tasks=[task],
    )
    # Protect it only during initial sensor sampling, then explicitly remove protection.
    f["route"]["points"][1]["task"]["params"]["tasks"][2] = dict(
        wrapped("SetInvisible", value=True), auto=False, enabled=True, number=2
    )
    b.action(0, "phase", label="JTAC invisible (NOT immortal); target hidden")
    b.action(90, "invisible", target, value=False)
    b.action(90, "phase", label="Target revealed; FAC sensor test")
    b.action(210, "invisible", f, value=False)
    b.action(210, "phase", label="JTAC vulnerable; hidden OSA may fire")
    b.pair(f["units"][1], target["units"][1], "FAC contact")
    b.pair(sam["units"][1], f["units"][1], "OSA -> JTAC", display=False)
    for g in (f, sam):
        b.cfg["display"][g["units"][1]["name"]] = True
    return b


def f10(seed):
    b = Builder(seed, "13_F10_native_and_markers", 300)
    for i, (name, side, hidden, invisible) in enumerate(
        [
            ("BLUE_NORMAL", "blue", False, False),
            ("BLUE_AI_HIDDEN", "blue", False, True),
            ("BLUE_MAP_HIDDEN", "blue", True, False),
            ("RED_NORMAL", "red", False, False),
            ("RED_AI_HIDDEN", "red", False, True),
            ("RED_MAP_HIDDEN", "red", True, False),
        ]
    ):
        g = b.vehicle(
            name, x=X + i * 500, z=Z, side=side, hidden=invisible, map_hidden=hidden
        )
        b.action(
            0,
            "mark",
            id=8000 + i,
            x=X + i * 500,
            z=Z + 250,
            text=name + " reference (script ALL)",
        )
        b.action(120, "invisible", g, value=not invisible)
    b.action(0, "mark", id=8100, x=X, z=Z - 1000, text="SCRIPT: ONLY BLUE", coalition=2)
    b.action(
        0, "mark", id=8101, x=X + 1000, z=Z - 1000, text="SCRIPT: ONLY RED", coalition=1
    )
    b.action(
        0,
        "phase",
        label="GM can bypass coalition fog. Not a player-visibility verdict.",
    )
    b.action(120, "phase", label="SetInvisible toggled, native hidden flags UNCHANGED")
    b.action(240, "removeMark", id=8100)
    b.action(240, "removeMark", id=8101)
    b.action(240, "phase", label="Coalition script marks removed")
    return b


def validate(mission_text, script, b):
    runtime = LuaRuntime()
    runtime.compile(mission_text)
    runtime.compile(script)
    runtime.execute(mission_text)  # Data-only mission definition.
    # Compile code that DCS evaluates *after* loading mission, catches old test07's bug.
    for table in ("actions", "conditions", "func"):
        for body in b.m["trig"][table].values():
            runtime.compile(body)
    ids, names, groupids = set(), set(), set()
    for c in b.m["coalition"].values():
        for country in c.get("country", {}).values():
            for category in ("plane", "helicopter", "vehicle"):
                for g in country.get(category, {}).get("group", {}).values():
                    assert g["groupId"] not in groupids
                    groupids.add(g["groupId"])
                    for u in g["units"].values():
                        assert u["unitId"] not in ids and u["name"] not in names
                        assert u["skill"] not in ("Client", "Player")
                        ids.add(u["unitId"])
                        names.add(u["name"])
    assert set(b.cfg["units"]) == names
    for p in b.cfg["pairs"]:
        assert p["observer"] in names and p["target"] in names
    assert b.m["groundControl"]["roles"]["instructor"]["blue"] == 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite existing output directory")
    with zipfile.ZipFile(args.seed) as z:
        entries = {
            name: z.read(name)
            for name in z.namelist()
            if name != "su25t_test_manifest.json"
        }
    seed = lua.loads(entries["mission"].decode())["mission"]
    builders = [
        cas_mission(seed, 0, "CAS", False),
        cas_mission(seed, 1, "CAS", True),
        cas_mission(seed, 2, "AttackGroup", True),
        cas_mission(seed, 3, "AttackUnit", True),
        cas_mission(seed, 4, "EngageUnit", True),
        cas_mission(seed, 5, "knowTarget", True, True),
        ground_scope(seed),
        memory(seed),
        fires(seed),
        sensors(seed, 9, "day"),
        sensors(seed, 10, "cloud"),
        sensors(seed, 11, "night"),
        fac(seed),
        f10(seed),
    ]
    diag = (HERE / "diagnostics.lua").read_text(encoding="utf-8")
    built = []
    for b in builders:
        script = "RCAS_CONFIG=" + literal(b.cfg) + "\n" + diag
        action = "a_do_script(" + literal(script) + "); mission.trig.func[1]=nil;"
        b.m["trig"] = {
            "actions": {1: action},
            "conditions": {1: "return(c_time_after(0))"},
            "func": {
                1: "if mission.trig.conditions[1]() then mission.trig.actions[1]() end"
            },
            "flag": {1: True},
            "events": {},
            "customStartup": {},
            "funcStartup": {},
        }
        b.m["trigrules"] = {
            1: {
                "actions": {
                    1: {
                        "predicate": "a_do_script",
                        "text": script,
                        "KeyDict_text": script,
                    }
                },
                "rules": {1: {"predicate": "c_time_after", "seconds": 0}},
                "predicate": "triggerOnce",
                "eventlist": "",
                "comment": b.name,
                "colorItem": "0xffffffff",
            }
        }
        data = "mission=" + literal(b.m) + "\n"
        validate(data, script, b)
        built.append((b, data, script))
    args.output.mkdir(parents=True)
    manifest = {
        "seed": str(args.seed),
        "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "diagnostics_sha256": hashlib.sha256(diag.encode()).hexdigest(),
        "missions": [],
    }
    for b, data, script in built:
        p = args.output / (b.name + ".miz")
        with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, content in entries.items():
                if name not in (
                    "mission",
                    "l10n/DEFAULT/dictionary",
                    "l10n/DEFAULT/mapResource",
                ):
                    z.writestr(name, content)
            z.writestr("mission", data.encode("utf-8"))
            z.writestr(
                "l10n/DEFAULT/dictionary",
                "dictionary="
                + literal(
                    {
                        "DictKey_Translation_1": b.name
                        + "\nAI only. Join blue/red GAME MASTER. Do not drive units.\n"
                        "Observe counters; errors must remain zero. RCAS_TEST records in Saved Games/DCS/Logs/dcs.log.\n"
                        "See LEEME.md beside the missions. Engineering test, NOT campaign plugin.",
                        "DictKey_Translation_2": "Observe only",
                        "DictKey_Translation_3": "Observe only",
                        "DictKey_Translation_4": b.name,
                    }
                ),
            )
            z.writestr("l10n/DEFAULT/mapResource", "mapResource={}")
            z.writestr("rcas_diagnostics.lua", script)
            z.writestr("rcas_manifest.json", json.dumps(b.cfg, indent=2))
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None
        manifest["missions"].append(
            dict(
                file=p.name,
                duration=b.cfg["duration"],
                sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            )
        )
        print("VALID", p.name)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (args.output / "LEEME.md").write_text(
        (HERE / "LEEME.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    print(f"Generated {len(built)} validated AI-only missions: {args.output}")


if __name__ == "__main__":
    main()
