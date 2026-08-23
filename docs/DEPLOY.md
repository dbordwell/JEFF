# Deploying to Jeff's PC

Two documents in one: what Dave does, and the three lines Jeff needs.

---

## What Jeff has to do

1. Download **AJZ-Setup.exe** from the release link.
2. Save the emailed **config.json** into the same folder.
3. Double-click **AJZ-Setup.exe**.

Then, whenever he wants the latest numbers: **double-click "AJZ Dashboard" on the
desktop.** It fetches, updates, and opens the workbook in one click.

If a step gets added here, something has gone wrong with the design.

---

## Why on-demand, and not a 6am scheduled task

The original design registered a `schtasks` job to refresh unattended each morning. It
was removed before the first handover. The reasoning is worth keeping, because "make it
automatic" is a tempting thing to re-add:

- **`schtasks` skips, it does not defer.** Its defaults do not set `StartWhenAvailable`
  and do set `DisallowStartIfOnBatteries`. A machine that is off, asleep, or on battery
  at 06:00 misses the run entirely and never catches up. A home PC that is off overnight
  would have refreshed exactly never, while continuing to look installed.
- **An unattended run cannot report its own absence.** The status banner is written *by*
  the refresh, so "I never ran" is the one state it structurally cannot describe. The
  workbook would keep saying *"Data current as of \<install day\>"* with total confidence.
- **We could not verify it.** Whether Windows accepts our invocation, and whether the
  task actually fires, was untestable from macOS on a machine we have no access to, for
  a user who cannot read a log.

On-demand deletes all three rather than mitigating them, and it is what was actually
asked for: one-click refresh. The person clicking is present to see what happened, which
is worth more than any amount of self-reporting machinery.

**The cost, stated plainly:** history snapshots only accumulate on runs, so a month
without opening it leaves a month-shaped hole and the rank-change alerts sample more
irregularly. That is a fair price and is not a reason to add scheduling back.

---

## What Dave does

### 1. Build the binary

Cross-building a Windows executable from macOS is not possible, so this runs on a Windows
CI runner. Push to `main`, or trigger `Build Windows installer` manually, then download
the `ajz-refresh-windows` artifact.

The workflow also runs the full test suite on **both** Ubuntu and Windows. That matters:
file locking and path handling differ on Windows, and those are precisely the areas the
macOS development machine cannot exercise.

### 2. Publish it where Jeff can reach it

Gmail blocks `.exe` attachments, including inside a zip. **Actions artifacts require a
logged-in GitHub account**, so that link dead-ends for him. A **release asset** downloads
from a plain link with no sign-in:

```
gh release upload v1.0.0 AJZ-Setup.exe --repo dbordwell/JEFF --clobber
```

### 3. Send the key separately

The repo is public, so `config.json` cannot ship with the release. Email it as an
attachment — it is a small text file and passes fine:

```json
{ "fmp_api_key": "the-rotated-key" }
```

Setup reads it from **the folder the exe is run from**, then copies it to
`%LOCALAPPDATA%\AJZ\config.json`. Both files must be in the same folder — that is the
only fiddly part of the install, and it is the price of a public download link.

**The key never goes in the workbook.** v5.1 kept it in `Settings!B1`, which made the
spreadsheet itself a secret and it was then emailed around. The dashboard we produce is
safe to send to anyone.

---

## What the installer does

```
%LOCALAPPDATA%\AJZ\
    ajz-refresh.exe      copied here so the shortcut points at a stable path
    config.json          the API key
    AJZ Dashboard.xlsx   the workbook itself
    history.sqlite       snapshots — survives workbook regeneration
    backups\             last 30 copies of the workbook
    logs\refresh.log     diagnostics, for Dave
    refresh.lock         held while a refresh runs

Desktop\
    AJZ Dashboard.lnk    the only thing Jeff clicks
```

The shortcut is created through `WScript.Shell` via PowerShell, since a `.lnk` is a
binary OLE structure. The Desktop location is read from the registry rather than assumed
to be `~/Desktop` — with OneDrive Desktop backup enabled it is
`%USERPROFILE%\OneDrive\Desktop`, and writing to the wrong one would put the icon
somewhere he never looks.

**The workbook lives beside the program, not on the Desktop.** One clickable thing. A
second copy on the Desktop would be a stale copy waiting to be opened by mistake, showing
yesterday's numbers under a confident banner.

Setup then runs one refresh immediately, so his first open shows real numbers rather than
"check back later".

---

## Remote debugging

```
ajz-refresh --status      what is installed, what is missing
ajz-refresh --verbose     refresh with full logging and the ranked table
ajz-refresh --no-open     refresh without launching Excel
ajz-refresh --uninstall   remove the desktop shortcut (keeps all data)
```

`--uninstall` deliberately leaves the workbook, conviction scores, history and backups
alone. Deleting Jeff's hand-entered scores because he asked to stop using the dashboard
would be wildly disproportionate.

To stop it himself, he can simply delete the desktop shortcut. There is no background
process to disable.

If Jeff has OneDrive, putting the workbook in a synced folder gives Dave a live copy to
inspect without ever asking him for anything.

---

## Exit codes

| Code | Meaning | What happened to the file |
|-----:|---------|---------------------------|
| 0 | success | rewritten |
| 2 | no API key configured | untouched |
| 3 | could not read the existing workbook | **untouched — deliberately** |
| 4 | workbook open in Excel | untouched, told to close and click again |
| 5 | another refresh already running | untouched |

Code 3 is the important one. If we cannot prove what conviction scores Jeff had, we do not
overwrite them. A refresh that does not happen is an annoyance; one that silently blanks
his scores is unrecoverable.

Code 5 exists because double-clicking twice is the expected human response to something
that takes a few seconds. The lock is an OS file lock, so it is released even if a run
crashes — there is no stale lock to clear.

---

## What is NOT verified

Being straight about the limits of a build authored on macOS:

- **Tested on Windows CI:** the full suite, and that the frozen binary starts.
- **NOT tested anywhere:** that PowerShell creates the `.lnk` on a real machine, that the
  registry Desktop lookup returns what we expect under OneDrive redirection, and that a
  locked-by-Excel file behaves as expected. The unit tests assert we build the *right
  command*, not that Windows accepts it.

So the first install is still the real test — but the failure modes are now visible.
Jeff is watching the window when it runs, and anything that goes wrong prints a sentence
he can read out over the phone. That is the substantive change: it is no longer possible
for this to fail silently for weeks.
