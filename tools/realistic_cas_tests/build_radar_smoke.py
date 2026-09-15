"""Test37: live aircraft radar state and moving target velocity, no player slots."""

import argparse
import copy
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
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.metadata.exists():
        raise SystemExit("Refusing to overwrite output or metadata")
    if args.output.suffix.lower() != ".miz" or not args.output.parent.is_dir():
        raise SystemExit("Exact .miz in existing directory required")
    if args.metadata.resolve().is_relative_to(args.output.parent.resolve()):
        raise SystemExit("Metadata must be outside Missions")
    with zipfile.ZipFile(args.seed) as archive:
        entries = {n: archive.read(n) for n in archive.namelist()}
    seed = lua.loads(entries["mission"].decode())["mission"]
    b = Builder(seed, "37_Realistic_CAS_GMTI", 620)
    b.m["start_time"] = 23 * 3600
    aircraft = b.plane(
        "RADAR_HORNET",
        x=X + 18000,
        z=Z,
        kind="FA-18C_hornet",
        size=1,
        altitude=4500,
        speed=150,
        pod=False,
        side="blue",
        hold=True,
        tasks=[zone(x=X, z=Z)],
    )
    wp = aircraft["route"]["points"][1]
    wp["alt_type"] = "BARO"
    tasks = wp["task"]["params"]["tasks"]
    tasks[len(tasks) + 1] = {
        "id": "Orbit",
        "enabled": True,
        "auto": False,
        "number": len(tasks) + 1,
        "params": {
            "pattern": "Circle",
            "speed": 150,
            "altitude": 4500,
            "point": {"x": X + 18000, "y": Z},
        },
    }
    aircraft["route"]["points"] = {1: wp}
    aircraft["units"][1]["alt_type"] = "BARO"
    cfg = {"observer": aircraft["units"][1]["name"], "targets": [], "groups": []}
    for name, x, z, kind in [
        ("MOVING_FAR", X - 2000, Z - 300, "moving"),
        ("STATIC_FAR", X - 2000, Z + 300, "far"),
        ("STATIC_NEAR", X + 10000, Z, "near"),
    ]:
        g = b.vehicle(name, x=x, z=z, kind="Ural-375", side="red")
        p = g["route"]["points"][1]
        g["route"]["points"] = {1: p}
        if kind == "moving":
            p.update(
                speed=6, speed_locked=True, action="Off Road", type="Turning Point"
            )
            destination = copy.deepcopy(p)
            destination.update(
                x=x + 8000,
                y=z,
                ETA_locked=False,
                task={"id": "ComboTask", "params": {"tasks": {}}},
            )
            g["route"]["points"][2] = destination
        cfg["targets"].append(
            {"name": g["units"][1]["name"], "groupName": name, "kind": kind}
        )
        cfg["groups"].append({"name": name, "originalInvisible": False})
    root = HERE.parents[1]
    sources = [
        root / "resources/plugins/realisticcas" / n
        for n in (
            "core.lua",
            "dcs.lua",
            "sensors.lua",
            "environment.lua",
            "detection.lua",
            "detectors-dcs.lua",
        )
    ]
    sources.append(HERE / "radar_smoke.lua")
    script = (
        "RCAS_RADAR_TEST="
        + literal(cfg)
        + "\n"
        + "\n".join(p.read_text(encoding="utf-8") for p in sources)
    )
    b.m["trig"] = {
        "actions": {
            1: "a_do_script(" + literal(script) + "); mission.trig.func[1]=nil;"
        },
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
    mission_text = "mission=" + literal(b.m) + "\n"
    validate(mission_text, script, b)
    instructions = (
        "# Prueba 37: RBM / GMTI\n\n"
        "Game Master. Solo log. Acelera hasta **RCAS RADAR FIN**, unos 615 segundos. "
        "Sin ordenes ni observacion manual. Un Hornet sin pod, tres camiones; inmortales y sin disparos.\n\n"
        "Camion cercano estatico: RBM. Camion lejano movil: GMTI. Camion lejano "
        "estatico: oculto. Fases de 120s: CAS, STRIKE (ningun radar de tierra), "
        "CAS sin capacidad GMTI (solo cercano), BAI y Armed Recon (ambos canales).\n\n"
        "Las fases modifican metadatos del plugin, no la tarea nativa del Hornet. "
        "Hora nocturna evita rescate visual. getRadar aporta solo encendido: "
        "no se lee ni se afirma conocer el modo/barrido GMTI real del avion. "
        "La velocidad de los camiones y la geometria vienen del motor.\n\n"
        "Registra velocidad, componente radial, rumbo, distancia, LOS y estado "
        "del radar. Si no hay suficientes ventanas geometricas, radar encendido o "
        "movimiento real, marca inconcluso. TTL15s. Fuera de esas precondiciones "
        "no se atribuye un fallo al sensor. Archiva dcs.log al terminar.\n"
    )
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
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
        archive.writestr("mission", mission_text)
        archive.writestr("l10n/DEFAULT/mapResource", "mapResource={}")
        archive.writestr(
            "l10n/DEFAULT/dictionary",
            "dictionary="
            + literal(
                {
                    "DictKey_Translation_1": instructions,
                    "DictKey_Translation_2": "Solo log",
                    "DictKey_Translation_3": "Solo log",
                    "DictKey_Translation_4": b.name,
                }
            ),
        )
        archive.writestr("rcas_radar_test.lua", script)
    from dcs.planes import plane_map

    plane_map["FA-18C_hornet"].payloads = {}
    Mission().load_file(str(args.output))
    args.metadata.mkdir(parents=True)
    (args.metadata / "LEEME.md").write_text(instructions, encoding="utf-8")
    (args.metadata / "manifest.json").write_text(
        json.dumps(
            {
                "file": str(args.output),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "seed": str(args.seed),
                "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
                "sources": {
                    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources + [Path(__file__), HERE / "build_missions.py"]
                },
                "config": cfg,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("BUILT AND PARSED", args.output)


if __name__ == "__main__":
    main()
