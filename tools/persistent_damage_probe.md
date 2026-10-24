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

Verify both object types against their expected percentages. Native testing
confirmed all three ships match their expected values, but all three placed
buildings remain at 100%. The production native action is therefore restricted
to ships; the static cases remain in this probe as negative controls. A missing
object, unchanged 100% reading or nearly destroyed object is a failure, not a pass.
Check the log for native-trigger errors as well. This validates the engine
operation separately from Lua tests, which can only test context and units.

The probe does not validate baked terrain scenery. Unlike ships and placed
statics, these objects have no generated mission unit ID. That restoration path
remains unsupported and fails visibly rather than returning a false full-health
snapshot that overwrites saved campaign damage. Placed buildings use a separate
startup pulse restoration path, not the native action tested here. Small balanced
pulses keep each hit above DCS's minimum damage threshold while limiting splash;
restoration accepts a two-percentage-point tolerance. Nearby fragile or
overlapping objects prevent these pulses from being applied.
