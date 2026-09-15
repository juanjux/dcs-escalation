"""Test 35: fixed clear geometry, model night/IR differential in live DCS."""

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from dcs import lua
from dcs.mission import Mission
from build_missions import Builder, HERE, X, Z, literal, validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument(
        "--clouds",
        action="store_true",
        help="Build test36 airborne cloud differential instead",
    )
    args = parser.parse_args()
    if args.output.exists() or args.metadata.exists():
        raise SystemExit("Refusing to overwrite output or metadata")
    if args.output.suffix.lower() != ".miz" or not args.output.parent.is_dir():
        raise SystemExit("Provide an exact .miz in an existing directory")
    if args.metadata.resolve().is_relative_to(args.output.parent.resolve()):
        raise SystemExit("Metadata must be outside Missions")
    with zipfile.ZipFile(args.seed) as archive:
        entries = {n: archive.read(n) for n in archive.namelist()}
    seed = lua.loads(entries["mission"].decode())["mission"]
    b = Builder(
        seed,
        "36_Realistic_CAS_clouds" if args.clouds else "35_Realistic_CAS_night_IR",
        500 if args.clouds else 240,
    )
    b.m["start_time"] = 23 * 3600
    # Test34 candidate64, verified with actual DCS LOS. Recheck at runtime.
    o = b.vehicle(
        "THERMAL_OBSERVER", x=169593.43, z=46812.43, kind="M-1 Abrams", side="blue"
    )
    t = b.vehicle("TRUCK_2KM", x=171441.19, z=46047.06, kind="Ural-375", side="red")
    # Stationary single-point routes: do not inherit seed convoy waypoints.
    for g in (o, t):
        g["route"]["points"] = {1: g["route"]["points"][1]}
    cfg = {
        "observer": o["units"][1]["name"],
        "target": {"name": t["units"][1]["name"], "groupName": t["name"]},
    }
    if args.clouds:
        # Discard the night-only setup, preserving the proven seed and unique IDs.
        b = Builder(seed, "36_Realistic_CAS_clouds", 500)
        b.m["weather"]["clouds"] = {
            "base": 1500,
            "thickness": 2000,
            "density": 10,
            "iprecptns": 0,
            "preset": "Preset20",
        }
        o = b.plane(
            "POD_A10",
            x=X + 6500,
            z=Z,
            kind="A-10C_2",
            size=1,
            altitude=4000,
            speed=120,
            pod=True,
            side="blue",
            hold=True,
        )
        # Orbit immediately; BARO avoids the AGL/MSL ambiguity of earlier probes.
        wp = o["route"]["points"][1]
        wp["alt_type"] = "BARO"
        wp["task"]["params"]["tasks"][4] = {
            "id": "Orbit",
            "enabled": True,
            "auto": False,
            "number": 4,
            "params": {
                "pattern": "Circle",
                "speed": 120,
                "altitude": 4000,
                "point": {"x": X + 6500, "y": Z},
            },
        }
        o["route"]["points"] = {1: wp}
        o["units"][1]["alt_type"] = "BARO"
        t = b.vehicle("CLOUD_TRUCK", x=X, z=Z, kind="Ural-375", side="red")
        t["route"]["points"] = {1: t["route"]["points"][1]}
        cfg = {
            "observer": o["units"][1]["name"],
            "target": {"name": t["units"][1]["name"], "groupName": t["name"]},
        }
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
    sources.append(HERE / ("cloud_smoke.lua" if args.clouds else "night_smoke.lua"))
    config_name = "RCAS_CLOUD_TEST" if args.clouds else "RCAS_NIGHT_TEST"
    script = (
        config_name
        + "="
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
    mission_text = "mission=" + literal(b.m) + "\n"
    validate(mission_text, script, b)
    instructions = (
        "# Prueba 35: noche e IR\n\n"
        "Game Master. Solo log: acelerar hasta **RCAS NIGHT FIN**, unos 233 segundos. "
        "No hay que observar vuelos ni dar ordenes. Un Abrams y un camion inmortales, sin disparos.\n\n"
        "Cinco fases de 45s, misma geometria despejada a 2km: dia sin IR (visual), "
        "noche sin IR (oculto), noche con IR (termico), noche sin IR otra vez (caduca), "
        "dia sin IR (recupera visual). TTL de prueba: 15s. Cada positivo exige el canal exacto.\n\n"
        "DCS permanece a las 23:00: las fases diurnas cambian solo la iluminacion "
        "exportada al modelo. Activar/desactivar IR cambia solo los metadatos del "
        "detector del plugin, no un interruptor fisico de la IA. Esto verifica el "
        "plugin integrado, no calibra opticas nativas ni capacidades reales.\n\n"
        "La LOS se comprueba cada 5s; si falta, el resultado sera inconcluso, nunca "
        "un falso PASS. Log: RCAS_NIGHT_TEST y REALISTIC_CAS_SENSOR.\n"
    )
    if args.clouds:
        instructions = (
            "# Prueba 36: nubes y pod A-10\n\n"
            "Game Master. Solo log. Acelera hasta **RCAS CLOUD FIN**, unos 490s. "
            "Un A-10 con pod, un camion; inmortales, sin disparos.\n\n"
            "Cuatro fases de 120s: transparente (EO), visual bloqueada pero IR "
            "parcialmente transmitido (IR), ambos bloqueados (oculto), recuperacion (EO). "
            "DCS conserva las mismas nubes: solo cambia la transmision del modelo. "
            "No mide la fisica nativa del pod ni calibra densidades reales.\n\n"
            "Usa pose, altura BARO, LOS y movimiento reales del avion. Comprueba "
            "oportunidades geometricas despejadas independientemente de la atenuacion. "
            "Si no las hay, marca inconcluso; si las hay pero falla el canal/contacto, fallo. "
            "La capa modelada esta entre 1500 y 3500m MSL. TTL15s. "
            "Solo necesito dcs.log; RCAS_CLOUD_TEST detalla cada control.\n"
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
        archive.writestr(
            "rcas_cloud_test.lua" if args.clouds else "rcas_night_test.lua", script
        )
    if args.clouds:
        from dcs.planes import plane_map

        plane_map["A-10C_2"].payloads = {}
    Mission().load_file(str(args.output))
    args.metadata.mkdir(parents=True)
    (args.metadata / "LEEME.md").write_text(instructions, encoding="utf-8")
    manifest = {
        "file": str(args.output),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "seed": str(args.seed),
        "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
        "sources": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources + [Path(__file__), HERE / "build_missions.py"]
        },
        "config": cfg,
    }
    (args.metadata / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print("BUILT AND PARSED", args.output)


if __name__ == "__main__":
    main()
