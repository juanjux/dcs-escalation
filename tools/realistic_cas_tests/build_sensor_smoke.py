"""One daytime in-engine perception test; no piloted slots, no campaign imports."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from dcs import lua
from dcs.mission import Mission
from build_missions import Builder, HERE, X, Z, literal, validate, zone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite output")
    with zipfile.ZipFile(args.seed) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    seed = lua.loads(entries["mission"].decode())["mission"]
    b = Builder(seed, "32_Realistic_CAS_sensors", 380)
    cfg = {"groups": [], "targets": [], "observers": [], "zones": []}

    def target(name, x, z, expect):
        g = b.vehicle(name, x=x, z=z, kind="Ural-375", side="red")
        cfg["groups"].append({"name": name, "originalInvisible": False})
        cfg["targets"].append(
            {"name": g["units"][1]["name"], "groupName": name, "expect": expect}
        )

    for lane, kind, near, far in (
        (0, "T-72B", 2000, 4000),
        (1, "M-1 Abrams", 4000, 6000),
    ):
        z = Z + lane * 12000
        g = b.vehicle("GROUND_" + str(lane), x=X, z=z, kind=kind, side="blue")
        cfg["observers"].append(
            {"name": g["units"][1]["name"], "typeName": kind, "category": "ground"}
        )
        target("NEAR_" + str(lane), X + near, z, True)
        target("FAR_" + str(lane), X + far, z, False)
    z = Z + 24000
    g = b.vehicle("CITY_OBSERVER", x=X, z=z, kind="T-72B", side="blue")
    cfg["observers"].append(
        {"name": g["units"][1]["name"], "typeName": "T-72B", "category": "ground"}
    )
    target("CITY_HIDDEN", X + 1500, z, False)
    cfg["zones"].append({"x": X + 1500, "z": z, "radius": 1500, "cover": "city"})

    for lane, kind, name, pod in (
        (1, "F-15C", "VISUAL_F15", False),
        (2, "A-10C_2", "POD_A10", True),
        (3, "FA-18C_hornet", "RADAR_F18", False),
    ):
        z = Z + lane * 40000
        g = b.plane(
            name,
            z=z,
            kind=kind,
            size=1,
            altitude=2000,
            pod=pod,
            side="blue",
            hold=True,
            tasks=[zone(x=X, z=z)],
        )
        cfg["observers"].append(
            {
                "name": g["units"][1]["name"],
                "typeName": kind,
                "category": "air",
                "role": "CAS",
                "equipment": {"targetingPod": pod},
            }
        )
        target(name + "_TARGET", X, z, True)

    root = HERE.parents[1]
    plugin = root / "resources/plugins/realisticcas"
    sources = [
        plugin / n
        for n in (
            "core.lua",
            "dcs.lua",
            "sensors.lua",
            "environment.lua",
            "detection.lua",
            "detectors-dcs.lua",
        )
    ]
    sources.append(HERE / "sensor_smoke.lua")
    script = (
        "RCAS_SENSOR_TEST="
        + literal(cfg)
        + "\n"
        + "\n".join(p.read_text(encoding="utf-8") for p in sources)
    )
    action = "a_do_script(" + literal(script) + "); mission.trig.func[1]=nil;"
    b.m["trig"] = {
        "actions": {1: action},
        "conditions": {1: "return(c_time_after(3))"},
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
                1: {"predicate": "a_do_script", "text": script, "KeyDict_text": script}
            },
            "rules": {1: {"predicate": "c_time_after", "seconds": 3}},
            "predicate": "triggerOnce",
            "eventlist": "",
            "comment": b.name,
            "colorItem": "0xffffffff",
        }
    }
    text = "mission=" + literal(b.m) + "\n"
    validate(text, script, b)
    args.output.mkdir(parents=True)
    path = args.output / (b.name + ".miz")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            if name in (
                "mission",
                "l10n/DEFAULT/dictionary",
                "l10n/DEFAULT/mapResource",
            ):
                continue
            if name.endswith(("manifest.json", "diagnostics.lua")):
                continue
            archive.writestr(name, content)
        archive.writestr("mission", text)
        archive.writestr("l10n/DEFAULT/mapResource", "mapResource={}")
        archive.writestr(
            "l10n/DEFAULT/dictionary",
            "dictionary="
            + literal(
                {
                    "DictKey_Translation_1": "Realistic CAS sensores. Game Master. Solo log.\n"
                    "Acelera hasta RCAS SENSOR FIN, 380 segundos. No dar ordenes.\n"
                    "Nadie dispara. Unidades inmortales. Geometria y LOS reales, cobertura modelada.",
                    "DictKey_Translation_2": "Solo log",
                    "DictKey_Translation_3": "Solo log",
                    "DictKey_Translation_4": b.name,
                }
            ),
        )
        archive.writestr("rcas_sensor_test.lua", script)
        archive.writestr("rcas_sensor_manifest.json", json.dumps(cfg, indent=2))
    # Avoid unrelated user/mod payload presets while parsing this stock-unit mission.
    from dcs.planes import plane_map

    for kind in ("F-15C", "A-10C_2", "FA-18C_hornet"):
        plane_map[kind].payloads = {}
    Mission().load_file(str(path))
    manifest = {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "sources": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources + [Path(__file__), HERE / "build_missions.py"]
        },
        "seed": str(args.seed),
        "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (args.output / "LEEME.md").write_text(
        "# Una prueba conjunta de sensores\n\n"
        "Abre `32_Realistic_CAS_sensors.miz`, Game Master, sin dar ordenes. Acelera "
        "hasta **RCAS SENSOR FIN** (380 segundos + los 3 iniciales). Solo necesito `dcs.log`.\n\n"
        "Prueba deteccion terrestre visual/termica, limite de distancia, cobertura "
        "urbana modelada, visual desde F-15, pod A-10 y radar Hornet. Todos en "
        "WEAPON HOLD e inmortales. No valida combate, noche, nubes ni GMTI en motor.\n\n"
        "En el Hornet hay que comprobar en el log si la primera deteccion fue "
        "radar o visual: un PASS de contacto no demuestra que getRadar funcione "
        "en busqueda terrestre. Guardamos estado de radar y motivo del contacto.\n\n"
        "A los 300s se apagan los sensores, a los 350s se comprueba expiracion "
        "y a los 380s se restaura visibilidad. Cobertura ciudad/desierto declarada "
        "en el modelo, no clasificada automaticamente por DCS.\n",
        encoding="utf-8",
    )
    print("BUILT AND PARSED", path)


if __name__ == "__main__":
    main()
