<#
run_from_source.ps1 — pull, and run the fork straight from the Python files.

PyInstaller is for making something to hand to somebody else. Nothing in the app
needs to be frozen to run: the exe is the same Python, and everything it is bundled
with (resources, the built map, the agent docs) is already in the repo. So the
everyday loop is a pull and a launch, and dist_full_fork only has to be rebuilt for
a release.

The one thing that still has to be built is the React map, and only when the client
sources have actually changed -- so this looks at what the pull brought in and runs
`npm run build` (about a minute) only then. Same for requirements.txt.

Usage:
  .\run_from_source.ps1                # pull if it is safe to, build if needed, run
  .\run_from_source.ps1 -NoPull        # run what is in the tree right now
  .\run_from_source.ps1 -Console       # keep a console window for the output

Notes:
  * The repo is the install directory in this mode. state.json, logs/ and
    liberation_preferences.json land here rather than in dist_full_fork -- all three
    are in .gitignore already. The campaigns, factions and layouts live in
    Saved Games\DCS\Retribution either way, so a save is the same save.
  * Do not run this and dist_full_fork at once: they want the same port (16880) and
    the same save files.
#>
param(
    [switch]$NoPull,
    [switch]$Console
)

$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\juanj\Saved Games\DCS\dcs-retribution-juanjux'
$venv = Join-Path $repo '.venv\Scripts'
Set-Location $repo

function Die($msg) { Write-Host "ABORT: $msg" -ForegroundColor Red; exit 1 }
function Say($msg) { Write-Host $msg -ForegroundColor Cyan }

if (-not (Test-Path (Join-Path $venv 'python.exe'))) {
    Die "No virtualenv at $venv. Create it and pip install -r requirements.txt."
}

# --- 1) Pull, when that is a safe thing to do -------------------------------------
$before = (git rev-parse HEAD).Trim()
if (-not $NoPull) {
    $branch = (git rev-parse --abbrev-ref HEAD).Trim()
    # Only what tracked files say: _notas/ and other untracked scratch are nobody's
    # business and must not stop a launch.
    $dirty = (git status --porcelain --untracked-files=no)
    if ($branch -ne 'master') {
        Say "On $branch, not master -- running it as it is, no pull."
    } elseif ($dirty) {
        Say 'Uncommitted changes -- running them as they are, no pull.'
    } else {
        Say 'Pulling master...'
        git pull --ff-only origin master
        if ($LASTEXITCODE -ne 0) { Die 'Pull failed. Sort the tree out and try again.' }
    }
}
$after = (git rev-parse HEAD).Trim()

# --- 2) Build only what the pull actually touched ---------------------------------
if ($before -ne $after) {
    $changed = git diff --name-only $before $after

    if ($changed | Where-Object { $_ -like 'client/src/*' -or $_ -eq 'client/package.json' }) {
        Say 'The map changed -- npm run build (about a minute)...'
        Push-Location (Join-Path $repo 'client')
        npm run build
        $ok = $LASTEXITCODE -eq 0
        Pop-Location
        if (-not $ok) { Die 'The client build failed.' }
    }

    if ($changed -contains 'requirements.txt') {
        Say 'requirements.txt changed -- pip install...'
        & (Join-Path $venv 'python.exe') -m pip install -q -r requirements.txt
        if ($LASTEXITCODE -ne 0) { Die 'pip install failed.' }
    }
}

if (-not (Test-Path (Join-Path $repo 'client\build\index.html'))) {
    Say 'No built map in the tree -- npm run build (about a minute)...'
    Push-Location (Join-Path $repo 'client')
    npm run build
    $ok = $LASTEXITCODE -eq 0
    Pop-Location
    if (-not $ok) { Die 'The client build failed.' }
}

# --- 3) Run it --------------------------------------------------------------------
# One at a time. The app takes a lock in %TEMP% and a second instance exits without
# a window, which from a desktop icon looks exactly like nothing happening.
$running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'escalation_main.exe' -or
    ($_.Name -like 'python*.exe' -and $_.CommandLine -like '*qt_ui.main*')
}
if ($running) {
    Die ('Escalation is already running (' + $running[0].Name +
         '). Close it first -- only one instance can have the web server.')
}

# As a module, from the repo: `python qt_ui/main.py` puts qt_ui on the path instead
# of the repo and every `from game import ...` fails. The PyInstaller spec does the
# same thing with pathex=['.'].
Say "Running from source: $(git log -1 --format='%h %s')"

if ($Console) {
    & (Join-Path $venv 'python.exe') -m qt_ui.main @args
} else {
    Start-Process -FilePath (Join-Path $venv 'pythonw.exe') `
        -ArgumentList '-m', 'qt_ui.main' -WorkingDirectory $repo
}
