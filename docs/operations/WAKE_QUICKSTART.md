# Durable Wake Quickstart

`eml-wake` processes one authorized durable request with one fresh provider
worker. It does not resume or impersonate a historical AI instance.

## Install

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
```

## Prepare local state

Copy the example config outside the repository and replace only paths and
policy values that belong to your machine:

```powershell
Copy-Item examples\wake\config.example.json <config-path>
New-Item -ItemType Directory -Path <wake-root> -Force
```

Keep payloads under an allowlisted root declared by the local config. Do not
commit the populated config, wake root, request files, ACKs, or provider output.

## Create one CTCL-anchored request

```powershell
eml-wake --root <wake-root> --config <config-path> create `
  --payload <payload-file> `
  --sender agent://example/controller `
  --authority principal:example/cross-dialogue `
  --target-kind generic_worker `
  --target-ref worker:claude:generic `
  --model claude-haiku-4-5-20251001 `
  --tools-policy no_tools
```

## Process and inspect

For one bounded pass:

```powershell
eml-wake --root <wake-root> --config <config-path> run-once
eml-wake --root <wake-root> --config <config-path> status <wake-id>
```

For a continuous local watchdog:

```powershell
scripts\Start-EmlWakeWatchdog.ps1 `
  -ProjectRoot (Get-Location) `
  -ConfigPath <config-path> `
  -WakeRoot <wake-root> `
  -PidPath <pid-record-path>
```

The stop script verifies the recorded process identity before stopping it:

```powershell
scripts\Stop-EmlWakeWatchdog.ps1 -PidPath <pid-record-path>
```

## Boundary

```text
fresh worker != resident
ACK committed != courier notified
wake_id duplicate != provider replay permission
request CTCL anchor != ACK CTCL anchor
exact_instance target != spawn permission
```

Provider or CTCL unavailability never authorizes a blind retry. Inspect the
durable status and create a new, explicitly authorized attempt only when the
previous state makes that safe.
