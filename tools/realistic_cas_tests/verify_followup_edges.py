"""Exercise invalid paths and matching scenario geometry with test doubles."""

from pathlib import Path
import argparse
import zipfile
from dcs import lua
from lupa.lua51 import LuaRuntime
from verify_missions import MOCK


def run(root, file, setup, event, expected, forbidden=None):
    with zipfile.ZipFile(root / file) as z:
        text = z.read("mission").decode()
    rt = LuaRuntime()
    rt.execute(text)
    rt.execute(MOCK)
    rt.execute(setup)
    rt.execute("assert(loadstring(mission.trig.actions[1]))()")
    rt.execute(event)
    rt.execute("""
      local n=0
      while #_pending>0 do
        local p=table.remove(_pending,1); _clock=p.t
        local t=p.f(p.a,p.t)
        if t then _pending[#_pending+1]={f=p.f,a=p.a,t=t} end
        n=n+1; assert(n<2000)
      end
    """)
    logs = "\n".join(rt.globals()._logs.values())
    assert "|ERROR|" not in logs
    assert expected in logs, expected
    if forbidden:
        assert forbidden not in logs
    print("PASS", file, expected)


SHOT = """
_handler:onEvent({id=world.event.S_EVENT_SHOT,initiator=_units['CAS-1'],
 weapon={getTypeName=function() return 'X_29T' end,isExist=function() return false end}})
"""


def main(root):
    run(
        root,
        "21_scope_unit.miz",
        "for _,g in pairs(_groups) do g.controller.isTargetDetected=function() return false end end",
        "",
        "INVALID: no adquirio todos",
        "op=invisible",
    )
    run(
        root,
        "24_memory_hidden.miz",
        "for _,g in pairs(_groups) do g.controller.setTask=function() end end",
        "",
        "INVALID: camion no se desplazo",
    )
    run(
        root,
        "24_memory_hidden.miz",
        "land.isVisible=function() return _clock<100 end",
        "",
        "INVALID COMPARACION: perdio LOS",
    )
    run(root, "26_CAS_revoke.miz", "", "", "INVALID: sin primer Kh-29T", "op=invisible")
    run(
        root,
        "26_CAS_revoke.miz",
        "for _,u in pairs(_units) do u.getAmmo=function() return {} end end",
        SHOT,
        "INVALID: sin Kh-29T restante",
        "op=invisible",
    )
    run(
        root,
        "30_AttackUnit_always_hidden.miz",
        "",
        SHOT,
        "RESULTADO: LANZO CONTRA OCULTO",
    )

    def coalition(n):
        path = next(root.glob(n + "_*.miz"))
        with zipfile.ZipFile(path) as z:
            return lua.loads(z.read("mission").decode())["mission"]["coalition"]

    for a, b in [("20", "21"), ("20", "22"), ("23", "24"), ("25", "26"), ("28", "29")]:
        assert coalition(a) == coalition(b), f"Nonmatching geometry/payload: {a}/{b}"
        print("PASS identical coalition definitions", a, b)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    main(parser.parse_args().directory)
