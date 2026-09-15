"""Matched combat A/B: fixed pydcs forces, different Realistic CAS enable flag only."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile

from dcs import lua
from dcs.mission import Mission
from dcs.planes import plane_map
from dcs.task import Targets
from build_missions import Builder, HERE, X, Z, literal, validate, combo, wrapped, zone


def build_scenario(seed, revision=43):
    b = Builder(seed, "Realistic CAS matched battle", 1800)
    b.m["weather"]["clouds"] = {
        "base": 2500,
        "thickness": 200,
        "density": 0,
        "iprecptns": 0,
    }
    b.m["weather"]["enable_fog"] = False
    b.m["weather"]["auto_fog"] = False
    cfg = {
        "duration": 1800,
        "groundOpenAt": 180,
        "acquisitionSeconds": 20,
        "ttl": 600,
        "groups": [],
        "targets": [],
        "observers": [],
        "units": [],
    }
    if revision >= 40:
        cfg.update(groundHoldFire=True, unlimitedWeaponsRequested=True)
        cfg.pop("groundOpenAt")
        # Native mission option exists in DCS MissionOptionsView. Its effect on
        # AI is an ENGINE TEST, not inferred from the checkbox or its name.
        b.m["forcedOptions"]["unlimitedWeapons"] = True
    if revision >= 41:
        cfg["unlimitedWeaponsRequested"] = False
        b.m["forcedOptions"]["unlimitedWeapons"] = False
        cfg["storesPerAircraft"] = {"AGM-65D": 6, "APKWS AGR-20A": 49, "GBU-12": 2}
    if revision >= 42:
        cfg["storesPerAircraft"] = {"AGM-65D": 6, "GBU-38": 4}
    for side, count in (("red", 12), ("blue", 6)):
        for i in range(count):
            kind = "BMP-2" if i % 3 == 2 else "T-72B"
            x = X if side == "red" else X + 2400
            z = Z + (i - (count - 1) / 2) * 350
            sector = "FRONT"
            if revision >= 39:
                # DISTANCE_FROM_FRONTLINE in ai_ground_planner.py: tanks
                # 2200..3200m, IFVs 2700..3700m on EACH side. Deterministic
                # sampling and a 24km test segment replace campaign randomness.
                depth = (2700 if kind == "BMP-2" else 2200) + (i % 5) * 250
                if side == "blue" and kind == "T-72B":
                    depth = 2400 + (i % 5) * 200
                x = X + (-depth if side == "red" else depth)
                z = Z - 12000 + i * 24000 / (count - 1)
                sector = (
                    "SOUTH" if z < Z - 4000 else "NORTH" if z > Z + 4000 else "CENTER"
                )
            name = (
                f"{side.upper()}_{sector}_{i+1:02d}"
                if revision >= 39
                else f"{side.upper()}_{i+1:02d}"
            )
            g = b.vehicle(
                name, x=x, z=z, count=2, kind=kind, side=side, immortal=False, hold=True
            )
            # No later SetInvisible(false) can undo the plugin's ownership.
            p = g["route"]["points"][1]
            p["task"] = combo(
                [
                    wrapped("SetImmortal", value=False),
                    wrapped("Option", name=0, value=4),
                ]
            )
            g["route"]["points"] = {1: p}
            cfg["groups"].append(
                {"name": g["name"], "originalInvisible": False, "side": side}
            )
            for u in g["units"].values():
                if revision >= 39:
                    # pydcs VehicleGroup.Formation.Line defaults to 20m.
                    u["y"] = z + (u["name"].endswith("-2") and 20 or 0)
                u["heading"] = 0 if side == "red" else 3.141592653589793
                cfg["targets"].append({"name": u["name"], "groupName": g["name"]})
                cfg["observers"].append(
                    {"name": u["name"], "typeName": kind, "category": "ground"}
                )
                cfg["units"].append(
                    {
                        "name": u["name"],
                        "groupName": g["name"],
                        "side": side,
                        "kind": "ground",
                        "sector": sector,
                    }
                )
    f = b.plane(
        "BLUE_CAS",
        x=X + 30000,
        z=Z,
        altitude=2500,
        kind="A-10C_2",
        size=4 if revision == 42 else 2,
        tasks=[zone(x=X + 1200, z=Z)],
        immortal=False,
        hold=False,
        speed=150,
        pod=True,
        side="blue",
    )
    if revision >= 39:
        # CasFlightPlan uses plain FLOT START/END, NOT OrbitAction. Mirror that
        # route and casingress.py's EngageTargetsInZone (default radius 10NM).
        old = f["route"]["points"]
        initial = copy.deepcopy(old[1]["task"]["params"]["tasks"])
        search = initial.pop(5)
        kinds = [
            Targets.All.GroundUnits.GroundVehicles.id,
            Targets.All.GroundUnits.AirDefence.AAA.id,
            Targets.All.GroundUnits.Infantry.id,
        ]
        search["params"].update(
            x=X,
            y=Z,
            zoneRadius=18520,
            targetTypes=dict(enumerate(kinds, 1)),
            value=";".join(kinds),
        )
        route = {}
        coords = [
            ("APPROACH", X + 20000, Z - 23000),
            ("INGRESS CAS", X + 5000, Z - 16000),
            ("FLOT START", X, Z - 15000),
            ("FLOT END", X, Z + 15000),
            ("EGRESS", X + 20000, Z + 20000),
            ("EXIT", X + 50000, Z + 30000),
        ]
        for index, (name, px, pz) in enumerate(coords, 1):
            p = copy.deepcopy(old[1])
            p.update(
                name=name, x=px, y=pz, alt=2500, alt_type="BARO", ETA_locked=index == 1
            )
            p["task"] = combo(
                list(initial.values()) if index == 1 else [search] if index == 2 else []
            )
            route[index] = p
        f["route"]["points"] = route
        f.update(x=coords[0][1], y=coords[0][2])
        for index, u in enumerate(f["units"].values()):
            u.update(
                x=coords[0][1], y=coords[0][2] + index * 80, alt=2500, alt_type="BARO"
            )
        cfg["layout"] = (
            "24km dispersed front; CAS ingress -> FLOT START -> FLOT END -> egress; no orbit"
        )
        cfg["searchZone"] = {"x": X, "z": Z, "radius": 18520}
        cfg["patrol"] = {"x": X, "z1": Z - 15000, "z2": Z + 15000, "altitudeMSL": 2500}
    missile = "{DAC53A2F-79CA-42FF-A77A-F5649B601308}"
    aircraft_type = plane_map["A-10C_2"]
    for pylon in (3, 9):
        allowed = [
            v[1]["clsid"]
            for v in vars(getattr(aircraft_type, f"Pylon{pylon}")).values()
            if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict)
        ]
        assert missile in allowed, f"AGM-65D rack not allowed on A-10 pylon {pylon}"
    for u in f["units"].values():
        u["payload"]["pylons"].update({3: {"CLSID": missile}, 9: {"CLSID": missile}})
        if revision >= 40:
            # Generous conventional load remains useful even if the native
            # unlimitedWeapons option does not replenish AI stores.
            additions = {
                2: "{174C6E6D-0C3D-42ff-BCB3-0853CB371F5C}",
                4: "{60CC734F-0AFA-4E2E-82B8-93B941AB11CF}",
                8: "{60CC734F-0AFA-4E2E-82B8-93B941AB11CF}",
                5: "{DB769D48-67D7-42ED-A2BE-108D566C8B1E}",
                7: "{DB769D48-67D7-42ED-A2BE-108D566C8B1E}",
            }
            if revision >= 41:
                additions.update(
                    {
                        2: "{LAU-131 - 7 AGR-20A}",
                        4: "{LAU-131x3 - 7 AGR-20A}",
                        8: "{LAU-131x3 - 7 AGR-20A}",
                    }
                )
            if revision >= 42:
                # With Maverick racks retained on 3/9, the remaining certified
                # GBU-38 stations are 4/5/7/8. Station2 cannot carry a JDAM.
                additions = {pylon: "{GBU-38}" for pylon in (4, 5, 7, 8)}
            for pylon, clsid in additions.items():
                stores = [
                    v[1]["clsid"]
                    for v in vars(getattr(aircraft_type, f"Pylon{pylon}")).values()
                    if isinstance(v, tuple) and len(v) == 2 and isinstance(v[1], dict)
                ]
                assert clsid in stores, f"Unsupported payload {clsid} on pylon {pylon}"
                u["payload"]["pylons"][pylon] = {"CLSID": clsid}
        u["payload"].update(gun=100, chaff=120, flare=120)
        cfg["observers"].append(
            {
                "name": u["name"],
                "typeName": "A-10C_2",
                "category": "air",
                "role": "CAS",
                "equipment": {"targetingPod": True},
            }
        )
        cfg["units"].append(
            {"name": u["name"], "groupName": f["name"], "side": "blue", "kind": "cas"}
        )
    if revision >= 39:
        ground = {
            side: [
                u
                for g in b.m["coalition"][side]["country"][1]["vehicle"][
                    "group"
                ].values()
                for u in g["units"].values()
            ]
            for side in ("red", "blue")
        }
        closest = min(
            ((r["x"] - u["x"]) ** 2 + (r["y"] - u["y"]) ** 2) ** 0.5
            for r in ground["red"]
            for u in ground["blue"]
        )
        assert closest > 4500, "Initial opponents within modeled ground IR range"
        for u in ground["red"] + ground["blue"]:
            assert (
                (u["x"] - X) ** 2 + (u["y"] - Z) ** 2
            ) ** 0.5 < 18520, "Target outside native CAS zone"
            depth = abs(u["x"] - X)
            assert (
                (2700 <= depth <= 3700)
                if u["type"] == "BMP-2"
                else (2200 <= depth <= 3200)
            )
        assert f["route"]["points"][3]["x"] == X == f["route"]["points"][4]["x"]
        assert "Orbit" not in literal(f["route"])
        cfg["closestGroundOpponentsMetres"] = closest
    return b, cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument(
        "--missions", type=Path, required=True, help="Existing Missions root"
    )
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument(
        "--revision", type=int, choices=(38, 39, 40, 41, 42, 43), default=43
    )
    args = parser.parse_args()
    paths = [
        args.missions / f"{args.revision}A_Realistic_CAS_battle_OFF.miz",
        args.missions / f"{args.revision}B_Realistic_CAS_battle_ON.miz",
    ]
    if (
        not args.missions.is_dir()
        or args.metadata.exists()
        or any(p.exists() for p in paths)
    ):
        raise SystemExit(
            "Existing Missions root, new metadata and new output filenames required"
        )
    if args.metadata.resolve().is_relative_to(args.missions.resolve()):
        raise SystemExit("Metadata must be outside Missions")
    with zipfile.ZipFile(args.seed) as archive:
        entries = {n: archive.read(n) for n in archive.namelist()}
    seed = lua.loads(entries["mission"].decode())["mission"]
    b, cfg = build_scenario(seed, args.revision)
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
    sources.append(HERE / "combat_smoke.lua")
    bundle = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    common_hash = hashlib.sha256(literal(b.m).encode()).hexdigest()
    outputs = []
    instructions = (
        "# Combate A/B 38\n\n"
        "Ejecuta 38A OFF y luego 38B ON, Game Master. Solo necesito log. "
        "Acelera ambas al mismo factor hasta **RCAS BATTLE FIN**, 1800s (~30 minutos simulados). "
        "No cierres DCS entre ambas si quieres conservarlas juntas en dcs.log; si lo cierras, "
        "avisa al terminar A para archivar su log antes de ejecutar B.\n\n"
        "Mismos 24 vehiculos rojos, 12 azules y 2 A-10C II azules. Cada A-10 lleva "
        "6 AGM-65D, pod y canon. Los grupos terrestres tienen dos vehiculos; "
        "ambos bandos combinan T-72B/BMP-2 y pueden disparar desde t=180s. "
        "CAS llega desde 30km. Nadie es inmortal; no hay SAM ni cazas en este primer diferencial.\n\n"
        "B: niebla simetrica, tiempo de busqueda20s y TTL600s; fuego desvela "
        "inmediatamente. A: sin ocultacion ni sensores del plugin. Misma geometria, "
        "tareas, skill, horario, cargas y meteorologia; el hash base debe coincidir. "
        "La IA DCS sigue siendo no determinista: una pareja sirve de diagnostico, "
        "no prueba estadistica ni garantia de balance.\n\n"
        "Cada 30s: vivos, danados, bajas atribuidas a CAS/tierra/fuego amigo o sin "
        "atribucion, contactos y adquisiciones. KILL nativo acredita autor; HIT "
        "solo registra ultimo atacante, nunca lo convierte en derribo confirmado. "
        "Tambien se guardan municiones y estado de los A-10 cada 60s. "
        "No se marca como fallo que mueran muchos/pocos tanques: ese es el dato a comparar. "
        "Cero disparos CAS hace la comparacion inconclusa, no una victoria del plugin.\n"
    )
    instructions = instructions.replace("38", str(args.revision))
    if args.revision >= 39:
        instructions += (
            "\nRevision 39: grupos repartidos por 24km de frente; tanques a2200-3200m "
        )
        instructions += (
            "y BMP a2700-3700m de SU lado, conforme a ai_ground_planner.py. Separacion "
        )
        instructions += (
            "entre miembros20m. Zona CAS10NM centrada en el frente; recorrido central "
        )
        instructions += (
            "FLOT START -> FLOT END de30km, seguido de egress, SIN OrbitAction, como "
        )
        instructions += "CasFlightPlan. Altitud2500m MSL. No es necesario observar. "
        instructions += "El log separa SOUTH/CENTER/NORTH, primera deteccion y bajas CAS. Las perdidas "
        instructions += "o retiradas del CAS se registran como factores de comparacion, no se ignoran.\n"
    if args.revision >= 40:
        instructions = instructions.replace(
            "6 AGM-65D, pod y canon.",
            "6 AGM-65D, 6 Mk-82, 2 GBU-12, 7 cohetes Hydra HEAT, pod y canon.",
        )
        instructions = instructions.replace(
            "pueden disparar desde t=180s.",
            "NO PUEDEN DISPARAR durante toda la prueba (ROE HOLD FIRE).",
        )
        if args.revision == 40:
            instructions += "\nRevision40: opcion nativa unlimitedWeapons activada en A y B; efecto sobre "
            instructions += "IA pendiente de comprobar por log. No se afirma que funcione por estar "
            instructions += "activada. Se comparan cargas iniciales y lanzamientos por tipo y avion; "
            instructions += "AMMO_EXCEEDED_INITIAL acredita lanzamientos por encima de la carga inicial "
            instructions += "para ese tipo, no todas las armas. La carga ampliada permite probar incluso "
            instructions += "si la IA ignora esa opcion. Un disparo terrestre marca error/inconcluso.\n"
    if args.revision == 41:
        instructions = instructions.replace(
            "6 AGM-65D, 6 Mk-82, 2 GBU-12, 7 cohetes Hydra HEAT, pod y canon.",
            "6 AGM-65D, 49 APKWS AGR-20A, 2 GBU-12, pod y canon.",
        )
        instructions += (
            "\nRevision41: APKWS en lugar de las seis Mk-82 y los cohetes no guiados; "
        )
        instructions += (
            "21+21+7 APKWS por avion. Municion finita, unlimitedWeapons desactivado "
        )
        instructions += (
            "tras no reponer cargas IA en la40. Geometria, ruta, skill y sensores "
        )
        instructions += (
            "identicos a40; siguen todos los vehiculos en HOLD FIRE. No hay JTAC "
        )
        instructions += (
            "adicional ni coordenadas nuevas: el A-10 usa su propio pod. Log de "
        )
        instructions += (
            "municion inicial, disparos por tipo y bajas. Un disparo terrestre "
        )
        instructions += (
            "marca error/inconcluso. Solo necesito el log, hasta RCAS BATTLE FIN.\n"
        )
    if args.revision >= 42:
        instructions = instructions.replace(
            "12 azules y 2 A-10C II azules.", "12 azules y 4 A-10C II azules."
        )
        instructions = instructions.replace(
            "6 AGM-65D, 6 Mk-82, 2 GBU-12, 7 cohetes Hydra HEAT, pod y canon.",
            "6 AGM-65D, 4 GBU-38 JDAM de500lb, pod y canon.",
        )
        instructions += (
            "\nRevision42: cuatro A-10 en un vuelo, SIN APKWS. Se sustituyen los "
        )
        instructions += (
            "cohetes y las GBU-12 por cuatro GBU-38 por avion (estaciones4/5/7/8). "
        )
        instructions += (
            "Se conservan seis Mavericks, pod y canon; no hay JDAM compatibles con "
        )
        instructions += (
            "la estacion2 y queda vacia. Total del vuelo:24 Mavericks y16 GBU-38. "
        )
        instructions += (
            "Mismos blancos, geometria, ruta central, altitud y sensores que41. "
        )
        instructions += (
            "Vehiculos en HOLD FIRE permanente, municion finita. AI Average, "
        )
        instructions += (
            "Game Master, solo log hasta RCAS BATTLE FIN en ambas variantes.\n"
        )
    if args.revision >= 43:
        instructions = instructions.replace(
            "12 azules y 4 A-10C II azules.", "12 azules y 2 A-10C II azules."
        )
        instructions = instructions.replace(
            "Revision42: cuatro A-10 en un vuelo,", "Revision43: dos A-10 en un vuelo,"
        )
        instructions = instructions.replace(
            "Total del vuelo:24 Mavericks y16 GBU-38.",
            "Total del vuelo:12 Mavericks y8 GBU-38.",
        )
        instructions += (
            "\nRespecto a42 solo se reduce el vuelo de cuatro a dos aviones. "
        )
        instructions += (
            "Cada uno conserva seis Mavericks y cuatro GBU-38; no se cambian "
        )
        instructions += "blancos, geometria, ruta, sensores ni HOLD FIRE terrestre.\n"
    for path, enabled in zip(paths, (False, True)):
        local_cfg = {
            **cfg,
            "enabled": enabled,
            "variant": "ON" if enabled else "OFF",
            "scenarioHash": common_hash,
        }
        script = "RCAS_COMBAT_TEST=" + literal(local_cfg) + "\n" + bundle
        m = copy.deepcopy(b.m)
        m["trig"] = {
            "actions": {
                1: "a_do_script(" + literal(script) + "); mission.trig.func[1]=nil;"
            },
            "conditions": {1: "return(c_time_after(1))"},
            "func": {
                1: "if mission.trig.conditions[1]() then mission.trig.actions[1]() end"
            },
            "flag": {1: True},
            "events": {},
            "customStartup": {},
            "funcStartup": {},
        }
        m["trigrules"] = {
            1: {
                "actions": {
                    1: {
                        "predicate": "a_do_script",
                        "text": script,
                        "KeyDict_text": script,
                    }
                },
                "rules": {1: {"predicate": "c_time_after", "seconds": 1}},
                "predicate": "triggerOnce",
                "eventlist": "",
                "comment": "Realistic CAS combat " + local_cfg["variant"],
                "colorItem": "0xffffffff",
            }
        }
        mission_text = "mission=" + literal(m) + "\n"
        validation_builder = copy.copy(b)
        validation_builder.m = m
        validate(mission_text, script, validation_builder)
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
                        "DictKey_Translation_4": path.stem,
                    }
                ),
            )
            archive.writestr("rcas_combat_test.lua", script)
        aircraft_type = plane_map["A-10C_2"]
        aircraft_type.payloads = {}
        Mission().load_file(str(path))
        outputs.append(
            {
                "file": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "enabled": enabled,
            }
        )
    args.metadata.mkdir(parents=True)
    (args.metadata / "LEEME.md").write_text(instructions, encoding="utf-8")
    (args.metadata / "manifest.json").write_text(
        json.dumps(
            {
                "outputs": outputs,
                "scenarioHash": common_hash,
                "config": cfg,
                "seed": str(args.seed),
                "seed_sha256": hashlib.sha256(args.seed.read_bytes()).hexdigest(),
                "sources": {
                    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sources + [Path(__file__), HERE / "build_missions.py"]
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    for p in paths:
        print("BUILT AND PARSED", p)
    print("MATCHED SCENARIO SHA256", common_hash)


if __name__ == "__main__":
    main()
