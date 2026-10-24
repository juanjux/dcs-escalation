# Native persistent-health probe

Generate a standalone Caucasus mission from the repository root:

```powershell
python -m tools.persistent_damage_probe path/to/persistent_health_native_probe.miz
```

Open it in DCS, enter the blue Game Master slot, unpause and wait ten seconds.
No player aircraft or takeoff is needed. The mission changes no campaign data.
Three Perry ships and three placed FARP CP Blindage buildings receive native
UNIT AI SET LIFE actions: 35%, 65% and 98.212% remaining life. No explosions or
mission-sandbox bridge are used. Readings repeat every fifteen seconds and are
written to `Saved Games/DCS/Logs/dcs.log` with the `Escalation health probe` prefix.

Verify both object types against their expected percentages. A missing object,
unchanged 100% reading or nearly destroyed object is a failure, not a pass.
Check the log for native-trigger errors as well. This validates the engine
operation separately from Lua tests, which can only test context and units.

The probe does not validate baked terrain scenery. Unlike ships and placed
statics, these objects have no generated mission unit ID. That restoration path
still needs an engine bridge and must continue to fail visibly when unsupported.
