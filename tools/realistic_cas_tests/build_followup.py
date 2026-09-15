"""Second-round DCS experiments. Separate matched files, no campaign modifications."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import zipfile

from dcs import lua
from dcs.task import WeaponType
from build_missions import Builder, HERE, X, Z, combo, literal, validate, zone


def ground(seed, index, kind, variant):
    b = Builder(seed, f"{index:02d}_{kind}_{variant}", 650)
    observer = b.vehicle("ABRAMS_OBSERVADOR", x=X + 500, z=Z, side="red")
    observer["manualHeading"] = True
    observer["units"][1]["heading"] = math.pi
    targets = b.vehicle(
        "BLANCOS",
        count=2 if kind == "scope" else 1,
        kind="T-72B" if kind == "scope" else "Ural-375",
    )
    if kind == "scope":
        targets["units"][2]["type"] = "Ural-375"
    names = [u["name"] for u in targets["units"].values()]
    for u in targets["units"].values():
        b.pair(observer["units"][1], u, u["name"], display=False)
        b.cfg["display"][u["name"]] = True
    b.cfg["display"][observer["units"][1]["name"]] = True
    b.action(0, "ground_roe", observer, value="WEAPON_HOLD")
    b.action(0, "ground_roe", targets, value="WEAPON_HOLD")
    b.cfg["experiment"] = {
        "kind": kind,
        "variant": variant,
        "targets": names,
        "targetGroup": targets["name"],
        "observer": observer["units"][1]["name"],
        "observerGroup": observer["name"],
    }
    return b


def air(seed, index, method, variant):
    b = Builder(seed, f"{index:02d}_{method}_{variant}", 900)
    targets = b.vehicle("BLANCOS", count=6, hidden=variant == "always_hidden")
    if method == "CAS":
        task = zone()
    else:
        task = {
            "id": "AttackUnit",
            "params": {
                "unitId": targets["units"][1]["unitId"],
                "weaponType": WeaponType.Auto.value,
                "groupAttack": True,
                "attackQtyLimit": False,
                "attackQty": 1,
                "altitudeEnabled": False,
                "directionEnabled": False,
                "expend": "Auto",
            },
        }
    f = b.plane("CAS", tasks=[task])
    for u in f["units"].values():
        b.cfg["display"][u["name"]] = True
    for u in targets["units"].values():
        b.cfg["display"][u["name"]] = True
    b.pair(f["units"][1], targets["units"][1], "Lider -> tanque1")
    b.pair(f["units"][2], targets["units"][1], "Punta -> tanque1")
    b.cfg["experiment"] = {
        "kind": "air",
        "variant": variant,
        "method": method,
        "shooters": [u["name"] for u in f["units"].values()],
        "targetGroup": targets["name"],
    }
    b.action(0, "ground_roe", targets, value="WEAPON_HOLD")
    return b


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite output")
    with zipfile.ZipFile(args.seed) as z:
        entries = {
            n: z.read(n) for n in z.namelist() if n != "su25t_test_manifest.json"
        }
    seed = lua.loads(entries["mission"].decode())["mission"]
    suites = [
        ground(seed, 20, "scope", "control"),
        ground(seed, 21, "scope", "unit"),
        ground(seed, 22, "scope", "group"),
        ground(seed, 23, "memory", "control"),
        ground(seed, 24, "memory", "hidden"),
        air(seed, 25, "CAS", "control"),
        air(seed, 26, "CAS", "revoke"),
        air(seed, 27, "CAS", "always_hidden"),
        air(seed, 28, "AttackUnit", "control"),
        air(seed, 29, "AttackUnit", "revoke"),
        air(seed, 30, "AttackUnit", "always_hidden"),
    ]
    runner = (HERE / "followup.lua").read_text(encoding="utf-8")
    diagnostics = (HERE / "diagnostics.lua").read_text(encoding="utf-8")
    built = []
    for b in suites:
        script = "RCAS_CONFIG=" + literal(b.cfg) + "\n" + runner + "\n" + diagnostics
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
        text = "mission=" + literal(b.m) + "\n"
        validate(text, script, b)
        built.append((b, text, script))
    args.output.mkdir(parents=True)
    manifest = {
        "seed": str(args.seed),
        "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
        "sources": {
            n: hashlib.sha256((HERE / n).read_bytes()).hexdigest()
            for n in (
                "build_followup.py",
                "build_missions.py",
                "diagnostics.lua",
                "followup.lua",
            )
        },
        "missions": [],
    }
    for b, text, script in built:
        path = args.output / (b.name + ".miz")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, content in entries.items():
                if name not in (
                    "mission",
                    "l10n/DEFAULT/dictionary",
                    "l10n/DEFAULT/mapResource",
                ):
                    z.writestr(name, content)
            z.writestr("mission", text)
            z.writestr("l10n/DEFAULT/mapResource", "mapResource={}")
            z.writestr(
                "l10n/DEFAULT/dictionary",
                "dictionary="
                + literal(
                    {
                        "DictKey_Translation_1": b.name
                        + "\nAI only. GAME MASTER blue/red. No driving or commands.\n"
                        "Event-driven test. Follow ESTADO. INVALID means no conclusion.\n"
                        "Screenshots + dcs.log RCAS_TEST. Read LEEME.md beside missions.",
                        "DictKey_Translation_2": "Observe only",
                        "DictKey_Translation_3": "Observe only",
                        "DictKey_Translation_4": b.name,
                    }
                ),
            )
            z.writestr("rcas_diagnostics.lua", script)
            z.writestr("rcas_manifest.json", json.dumps(b.cfg, indent=2))
        manifest["missions"].append(
            {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
        print("BUILT", path.name)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (args.output / "LEEME.md").write_text(
        (HERE / "FOLLOWUP.md").read_text(encoding="utf-8"), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
