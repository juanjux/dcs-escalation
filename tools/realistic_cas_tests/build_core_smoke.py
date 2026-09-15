"""Build ONE AI-only mission embedding the actual prototype, not diagnostic substitutes."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile

from dcs import lua
from dcs.mission import Mission

from build_missions import Builder, HERE, X, Z, literal, validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite output")
    with zipfile.ZipFile(args.seed) as archive:
        seed = lua.loads(archive.read("mission").decode())["mission"]
        entries = {n: archive.read(n) for n in archive.namelist()}
    b = Builder(seed, "31_Realistic_CAS_core", 480)
    red = b.vehicle("RED_ARMOUR", x=X + 500, kind="T-72B", side="red", count=2)
    blue = b.vehicle("BLUE_ARMOUR", x=X, kind="M-1 Abrams", side="blue", count=2)
    for g, heading in ((red, math.pi), (blue, 0)):
        g["manualHeading"] = True
        for u in g["units"].values():
            u["heading"] = heading
        g["units"][2]["type"] = "Ural-375"
    source_paths = [
        HERE.parents[1] / "resources/plugins/realisticcas" / n
        for n in ("core.lua", "dcs.lua")
    ]
    source_paths.append(HERE / "core_smoke.lua")
    script = "\n".join(p.read_text(encoding="utf-8") for p in source_paths)
    # Allow initial waypoint options to execute before taking visibility ownership.
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
                    "DictKey_Translation_1": "Realistic CAS: nucleo real. Game Master rojo o azul.\n"
                    "Solo IA, no dar ordenes. Acelera hasta RCAS CORE FIN (480s). Guardar dcs.log.\n"
                    "Tanques inmortales. Observaciones inyectadas: no prueba sensores.",
                    "DictKey_Translation_2": "Solo log",
                    "DictKey_Translation_3": "Solo log",
                    "DictKey_Translation_4": b.name,
                }
            ),
        )
        archive.writestr("rcas_core_test.lua", script)
    # The mission has only stock ground units: no aircraft payload lookup needed.
    Mission().load_file(str(path))
    manifest = {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "seed": str(args.seed),
        "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
        "sources": {
            str(p.relative_to(HERE.parents[1])): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in source_paths + [Path(__file__), HERE / "build_missions.py"]
        },
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (args.output / "LEEME.md").write_text(
        "# Una sola prueba: nucleo real de Realistic CAS\n\n"
        "Abre `31_Realistic_CAS_core.miz`, entra como Game Master y acelera hasta "
        "`RCAS CORE FIN` (480 segundos, mas los 3 iniciales). No necesitas observar "
        "nada ni dar ordenes: solo conservar `dcs.log` al terminar.\n\n"
        "Comprueba ocultacion inicial, revelado automatico por disparos reales en ambos "
        "bandos, caducidad tras alto el fuego, renovacion mediante observacion inyectada y "
        "restauracion al apagar. Registra deteccion nativa cada 5s para contrastarla "
        "con el estado del plugin. Tanques inmortales; camiones distinguibles en sus grupos.\n\n"
        "No mide sensores ni eficacia CAS. Si no disparan, el test lo marca como fallo "
        "de cobertura: no lo confundiremos con prueba superada. Los FAIL/ERROR y "
        "RESULT quedan en `RCAS_CORE_TEST`; el nucleo usa `REALISTIC_CAS`.\n",
        encoding="utf-8",
    )
    print("BUILT AND PARSED", path)


if __name__ == "__main__":
    main()
