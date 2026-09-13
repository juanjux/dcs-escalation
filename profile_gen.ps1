# profile_gen.ps1
# Lanza esto JUSTO despues de pulsar Take Off para capturar donde se va el tiempo
# de generacion de mision (la ventana se queda "No responde" ~2 min).
# Produce un flamegraph SVG en el Escritorio (abrelo en un navegador).
# Si da "Access is denied", abre la terminal como Administrador.
$ErrorActionPreference = "Stop"
$pyspy = "C:\Users\juanj\Saved Games\DCS\dcs-retribution-juanjux\.venv\Scripts\py-spy.exe"
$proc = Get-Process escalation_main -ErrorAction SilentlyContinue |
        Sort-Object WorkingSet64 -Descending | Select-Object -First 1
if (-not $proc) { Write-Error "escalation_main.exe no esta corriendo"; exit 1 }
$out = "$env:USERPROFILE\Desktop\gen_profile_$($proc.Id).svg"
Write-Host "Perfilando PID $($proc.Id) durante 150s -> $out (Ctrl+C cuando se descuelgue)"
& $pyspy record -o $out --pid $proc.Id --duration 150 --rate 100 --idle
Write-Host "Listo: $out"
