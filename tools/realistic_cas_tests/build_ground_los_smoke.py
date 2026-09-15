"""One ground LOS diagnostic. The .miz goes in Missions; metadata goes elsewhere."""

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
    parser.add_argument(
        "--output", type=Path, required=True, help="Exact .miz file, not a directory"
    )
    parser.add_argument(
        "--metadata", type=Path, required=True, help="New directory OUTSIDE Missions"
    )
    parser.add_argument(
        "--search-site",
        action="store_true",
        help="Test 34: choose a new site in-engine before spawning",
    )
    args = parser.parse_args()
    if args.output.exists() or args.metadata.exists():
        raise SystemExit("Refusing to overwrite output or metadata")
    if args.output.suffix.lower() != ".miz" or not args.output.parent.is_dir():
        raise SystemExit("Existing output parent and .miz suffix required")
    with zipfile.ZipFile(args.seed) as archive:
        entries = {n: archive.read(n) for n in archive.namelist()}
    seed = lua.loads(entries["mission"].decode())["mission"]
    b = Builder(
        seed,
        (
            "34_Realistic_CAS_clear_ground"
            if args.search_site
            else "33_Realistic_CAS_ground_LOS"
        ),
        180,
    )
    cfg = {"observers": [], "sets": []}

    def target(name, x, z):
        g = b.vehicle(name, x=x, z=z, kind="Ural-375", side="red")
        return {"name": g["units"][1]["name"], "groupName": g["name"]}

    for lane, kind, near, far in (
        ()
        if args.search_site
        else ((0, "T-72B", 2000, 4000), (1, "M-1 Abrams", 4000, 6000))
    ):
        z = Z + lane * 12000
        g = b.vehicle("GROUND_" + str(lane), x=X, z=z, kind=kind, side="blue")
        observer = g["units"][1]["name"]
        cfg["observers"].append(
            {"name": observer, "typeName": kind, "category": "ground"}
        )
        close = target("CLOSE_" + str(lane), X + 100, z)
        cfg["sets"].append(
            {
                "label": "CLOSE_" + str(lane),
                "observer": observer,
                "expected": True,
                "candidates": [close],
            }
        )
        rings = [("NEAR", near, True), ("FAR", far, False)]
        if lane == 0:
            rings.append(("CITY", 1500, True))
        for label, radius, expected in rings:
            candidates = []
            for bearing in range(8):
                angle = bearing * math.pi / 4
                name = f"{label}_{lane}_{bearing}"
                candidates.append(
                    target(
                        name, X + radius * math.cos(angle), z + radius * math.sin(angle)
                    )
                )
            cfg["sets"].append(
                {
                    "label": label + "_" + str(lane),
                    "observer": observer,
                    "expected": expected,
                    "city": label == "CITY",
                    "candidates": candidates,
                }
            )
            if label == "NEAR":
                cfg["sets"].append(
                    {
                        "label": "ORIGINAL_" + str(lane),
                        "observer": observer,
                        "expected": True,
                        "original": True,
                        "candidates": [candidates[0]],
                    }
                )
    if args.search_site:
        templates = {
            "observer": b.vehicle("VISUAL_OBSERVER", kind="T-72B", side="blue"),
            "near": b.vehicle("VISUAL_2KM", kind="Ural-375", side="red"),
            "city": b.vehicle("COVER_1500M", kind="Ural-375", side="red"),
        }
        observer = templates["observer"]["units"][1]["name"]
        cfg["observers"] = [
            {"name": observer, "typeName": "T-72B", "category": "ground"}
        ]
        for label, key in (("VISUAL_2KM", "near"), ("COVER_1500M", "city")):
            g = templates[key]
            cfg["sets"].append(
                {
                    "label": label,
                    "observer": observer,
                    "expected": True,
                    "city": key == "city",
                    "candidates": [
                        {"name": g["units"][1]["name"], "groupName": g["name"]}
                    ],
                }
            )
        # Templates are not preplaced units. Keep their IDs unique for addGroup.
        for side in ("red", "blue"):
            b.m["coalition"][side]["country"][1].pop("vehicle", None)
        b.cfg["units"] = []
        candidates = []
        # Start around the higher endpoint of test 33's measured clear 4km ray.
        offsets = sorted(
            ((x, z) for x in range(-4, 5) for z in range(-4, 5)),
            key=lambda p: p[0] ** 2 + p[1] ** 2,
        )
        for ox, oz in offsets:
            x, z = X + 2828.427 + ox * 2000, Z + 2828.427 + oz * 2000
            for bearing in range(16):
                angle = bearing * math.pi / 8
                candidates.append(
                    {
                        "observer": {"x": x, "z": z},
                        "near": {
                            "x": x + 2000 * math.cos(angle),
                            "z": z + 2000 * math.sin(angle),
                        },
                        "city": {
                            "x": x + 1500 * math.cos(angle),
                            "z": z + 1500 * math.sin(angle),
                        },
                    }
                )
        cfg["search"] = {"templates": templates, "candidates": candidates}
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
    script = (
        "RCAS_GROUND_TEST="
        + literal(cfg)
        + "\n"
        + "\n".join(p.read_text(encoding="utf-8") for p in sources)
    )
    sources.append(HERE / "ground_los_smoke.lua")
    runner = sources[-1].read_text(encoding="utf-8")
    if args.search_site:
        sources.append(HERE / "select_ground_site.lua")
        script += (
            "\nRCAS_RUN_GROUND_TEST=function()\n"
            + runner
            + "\nend\n"
            + sources[-1].read_text(encoding="utf-8")
        )
    else:
        script += "\n" + runner
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
        archive.writestr("mission", text)
        archive.writestr("l10n/DEFAULT/mapResource", "mapResource={}")
        archive.writestr(
            "l10n/DEFAULT/dictionary",
            "dictionary="
            + literal(
                {
                    "DictKey_Translation_1": "Realistic CAS: solo tierra. Game Master. Solo necesito dcs.log.\n"
                    "Acelera hasta RCAS GROUND FIN (180s). No dar ordenes.\n"
                    "Comprueba LOS antes de probar. En la 34 aparecen al terminar la busqueda.\n"
                    "Si no hay LOS, marca INCONCLUSIVE; no oculta el resultado con un PASS.",
                    "DictKey_Translation_2": "Solo log",
                    "DictKey_Translation_3": "Solo log",
                    "DictKey_Translation_4": b.name,
                }
            ),
        )
        archive.writestr("rcas_ground_test.lua", script)
        archive.writestr("rcas_ground_manifest.json", json.dumps(cfg, indent=2))
    Mission().load_file(str(args.output))
    manifest = {
        "file": str(args.output),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "seed": str(args.seed),
        "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
        "sources": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources + [Path(__file__), HERE / "build_missions.py"]
        },
    }
    args.metadata.mkdir(parents=True)
    (args.metadata / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (args.metadata / "LEEME.md").write_text(
        "# Prueba terrestre\n\nGame Master, acelerar hasta RCAS GROUND FIN (180s de ensayo). "
        "Solo log, sin observar ni dar ordenes. No hay aviones ni disparos.\n\n"
        "Se mantienen las dos parejas originales, se anaden controles a 100m y "
        "se eligen controles de 2/4/6km con LOS entre ocho orientaciones. "
        "Ninguna posicion se mueve. Falta de control despejado = inconcluso.\n\n"
        "El control de cobertura usa la misma pareja a 1500m: primero desierto y "
        "despues ciudad modelada; no cambia la geometria. El rayo elevado 10m "
        "solo se registra como diagnostico, nunca se usa para desvelar.\n\n"
        "Prefixes RCAS_GROUND_TEST (geometria/resultados) y REALISTIC_CAS_SENSOR "
        "(LOS_CLEAR/LOS_BLOCKED/ENVELOPE_REJECT). Metadatos y logs fuera de Missions.\n",
        encoding="utf-8",
    )
    if args.search_site:
        (args.metadata / "LEEME.md").write_text(
            "# Prueba 34: emplazamiento buscado en DCS\n\n"
            "Solo log. Game Master; acelera hasta RCAS GROUND FIN. Primero busca LOS "
            "para 1500m y 2000m, luego aparecen un T-72 y dos camiones. El ensayo "
            "dura 180s despues de la seleccion (hasta unos 350s totales si agota la busqueda).\n\n"
            "Solo tres unidades IA, inmortales, sin disparos. Comprueba visual a 2km "
            "y compara desierto/ciudad modelada sobre la misma pareja a 1500m. "
            "No se elevan unidades ni se omite el relieve. Busca con medio metro "
            "de margen y vuelve a comprobar los extremos reales tras aparecer.\n\n"
            "Si no hay emplazamiento, lo declara inconcluso. Los mensajes RCAS_SITE_TEST "
            "registran candidatos y seleccion; RCAS_GROUND_TEST, controles y resultado.\n",
            encoding="utf-8",
        )
    print("BUILT AND PARSED", args.output)


if __name__ == "__main__":
    main()
