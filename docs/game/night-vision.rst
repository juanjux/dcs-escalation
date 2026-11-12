Night vision goggles
====================

Escalation selects night vision goggles (NVG) for player flights whose planned
start-to-landing window overlaps darkness, where DCS provides a mission setting
for the equipment. If the module offers a combined helmet sight and NVG option,
the generator uses it. If the two are mutually exclusive, it selects NVG.
Explicit opt-outs and campaign equipment-date restrictions still apply.

Mission settings
----------------

The following flyable aircraft in Escalation expose an NVG setting:

* Combined helmet sight and goggles: A-10C II.
* Exclusive helmet options: F-16C Block 50, F/A-18C Lot 20, CJS F/A-18E,
  F/A-18F and EA-18G, Ka-50 III, and the Su-30MKA, MKI, MKM and SM mod.
* Independent switches: Community A-4E-C, AV-8B N/A, F-15E Strike Eagle,
  M-2000C, F-4E Phantom II, AH-64D and Mi-24P. Some switches default to on.

The generator reads the mission properties in pydcs and Escalation's mod
definitions. The Community A-4E-C setting is defined in the mod's
`aircraft source <https://github.com/Community-A-4E/community-a4e-c/blob/master/A-4E-C/A-4E-C.lua>`_.

Cockpit equipment
-----------------

These aircraft have goggles available from the DCS cockpit. Escalation shows
this in the player flight's Payload tab.

* A-10C Warthog.
  `DCS flight manual <https://www.digitalcombatsimulator.com/upload/iblock/7aa/DCS%20A-10C%20Flight%20Manual%20EN.pdf>`_
* F-14A-95-GR, F-14A-135-GR Early and Late, F-14B and F-14B(U).
  `Heatblur developer confirmation <https://forum.dcs.world/topic/217204-f14-night-vision-goggles/>`_,
  `DCS module release notes <https://www.digitalcombatsimulator.com/en/news/changelog/release/2.9.28.26283/>`_
* F-15EX, F-15EX CFT and F-15IA. The F-15EX V3 mod maps all three variants to
  the input profile that defines the goggles toggle.
* JF-17 Thunder. The module ships a helmet NVG device and goggles controls.
  `DCS module file manifest <https://steamdb.info/depot/1199120/apps/>`_
* Ka-50 (Black Shark 2).
  `DCS flight manual <https://www.digitalcombatsimulator.com/upload/iblock/dfc/DCS%20BS2%20Flight_Manual_EN.pdf>`_
* Mi-8MTV2 and SA342M Gazelle.
  `DCS beta tester report <https://forum.dcs.world/topic/246561-nvg-doesnt-work-in-the-latest-ob-patch/>`_
* SA342 Minigun.
  `DCS changelog for the NVG tracer option <https://www.digitalcombatsimulator.com/en/news/changelog/release/?PAGEN_2=7&_=1703306368084>`_
* CH-47F Chinook.
  `Eagle Dynamics development report <https://www.digitalcombatsimulator.com/en/news/2024-08-02/>`_
* OH-58D Kiowa Warrior.
  `DCS module changelog <https://www.digitalcombatsimulator.com/en/news/changelog/release/2.9.10.3948/>`_
* UH-1H Huey.
  `DCS flight manual <https://www.digitalcombatsimulator.com/upload/iblock/7c7/DCS%20UH-1H%20Flight%20Manual_EN.pdf>`_
* OH-6A mod, version 1.1 or later.
  `Mod team release announcement <https://www.reddit.com/r/hoggit/comments/1cklzl7/oh6a_mod_v11_is_available/>`_
* UH-60L Black Hawk and UH-60L DAP.
  `UH-60L mod controls <https://github.com/Kinkkujuustovoileipa/uh-60l/blob/main/Input/keyboard/default.lua>`_,
  `armed mod manual <https://www.aacaac.co.uk/dcs_mods/manuals/UH-60L/armed_manual.pdf>`_

Scope
-----

This inventory covers flyable variants in the Escalation aircraft catalog.
Confirmation comes from a mission property, a cockpit control, or a report
of the module's goggles working in DCS. The MiG-29A's ``NVG`` control is an
avionics navigation mode, and the C-130J manual documents NVIS lighting.
Goggles on either module remain unconfirmed. Custom keybinding patches
are outside this inventory.
