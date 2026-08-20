# Deploying to Jeff's PC

Two documents in one: what Dave does, and the four lines Jeff needs.

---

## What Jeff has to do

1. Double-click **AJZ Setup.exe**.
2. Open **AJZ Dashboard** on his desktop.

That is the whole thing. No prompts, no key to paste, no console window, no button to
press afterwards. If a step gets added here, something has gone wrong with the design.

---

## What Dave does

### 1. Build the binary

Cross-building a Windows executable from macOS is not possible, so this runs on a Windows
CI runner. Push to `main`, or trigger `Build Windows installer` manually, then download
the `ajz-refresh-windows` artifact.

The workflow also runs the full test suite on **both** Ubuntu and Windows. That matters:
file locking and path handling differ on Windows, and those are precisely the areas the
macOS development machine cannot exercise.

### 2. Bundle the key

Put a `config.json` next to the exe in the folder you hand over:

```json
{ "fmp_api_key": "the-rotated-key" }
```

The installer copies it to `%LOCALAPPDATA%\AJZ\config.json`. This is what keeps setup
question-free: Jeff never sees or types the key.

**The key never goes in the workbook.** v5.1 kept it in `Settings!B1`, which made the
spreadsheet itself a secret and it was then emailed around. The dashboard we produce is
safe to send to anyone.

### 3. Hand over

Zip the folder (`ajz-refresh.exe` + `config.json`), rename the exe to `AJZ Setup.exe` if
you like, and send it. No admin rights needed, and no need to touch his machine.

---

## What the installer does

```
%LOCALAPPDATA%\AJZ\
    ajz-refresh.exe      copied here so the task points at a stable path
    config.json          the API key
    history.sqlite       weekly snapshots — survives workbook regeneration
    backups\             last 30 copies of the workbook
    logs\refresh.log     diagnostics, for Dave

Desktop\
    AJZ Dashboard.xlsx   the only file Jeff ever opens
```

Plus a **user-level** scheduled task, `AJZ Dashboard Refresh`, daily at 06:00:

```
schtasks /Create /TN "AJZ Dashboard Refresh" /TR "<exe>" /SC DAILY /ST 06:00 /F
```

No `/RU`, no `/RL`, no `SYSTEM` — those would force an elevation prompt, and the task
must run as Jeff anyway so it can write to his Desktop. `/F` makes reinstalling
idempotent.

It then runs one refresh immediately, so his first open shows real numbers rather than
"check back tomorrow."

---

## Remote debugging

```
ajz-refresh --status      what is installed, what is missing
ajz-refresh --verbose     run a refresh with full logging
ajz-refresh --uninstall   remove the schedule (keeps all data)
```

`--uninstall` deliberately leaves the workbook, conviction scores, history and backups
alone. Deleting Jeff's hand-entered scores because he asked to stop a daily refresh would
be wildly disproportionate.

If Jeff has OneDrive, putting the workbook in a synced folder gives Dave a live copy to
inspect without ever asking him for anything.

---

## Exit codes

| Code | Meaning | What happened to the file |
|-----:|---------|---------------------------|
| 0 | success | rewritten |
| 2 | no API key configured | untouched |
| 3 | could not read the existing workbook | **untouched — deliberately** |
| 4 | workbook open in Excel | untouched, retries tomorrow |

Code 3 is the important one. If we cannot prove what conviction scores Jeff had, we do not
overwrite them. A refresh that does not happen is an annoyance; one that silently blanks
his scores is unrecoverable.

---

## What is NOT verified

Being straight about the limits of a build authored on macOS:

- **Tested on Windows CI:** the full suite, and that the frozen binary starts.
- **NOT tested anywhere:** that `schtasks` accepts our command on a real machine, that the
  task fires at 06:00, and that a locked-by-Excel file behaves as expected. The unit tests
  assert we build the *right command*, not that Windows accepts it.

So the first install is the real test. Run `ajz-refresh --status` afterwards to confirm
`task_scheduled` is `True`, and check the next morning that the banner date has moved.
