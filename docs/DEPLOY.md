# Deploying to Jeff's PC

## What Jeff does

1. Download **AJZ-Setup.exe** from the release link.
2. Save the emailed **config.json** into the same folder.
3. Double-click **AJZ-Setup.exe**.

Then, whenever he wants current numbers: **double-click "AJZ Dashboard" on the desktop.**
It fetches, updates, and opens the workbook in one click.

If a step gets added here, something has gone wrong with the design.

> There is no scheduled task. A 6am one was tried and removed — see [spec §3.3a](AJZ_SPEC.md)
> for why, and for the cost it carries (history samples irregularly).

---

## What Dave does

**1. Build.** Push to `main`, or trigger `Build Windows installer`, then download the
`ajz-refresh-windows` artifact. Cross-building a Windows exe from macOS is impossible, so
CI *is* the build. It also runs the suite on Ubuntu and Windows, which is what catches
the file-locking and path bugs macOS cannot.

**2. Publish.** Gmail blocks `.exe` attachments, and Actions artifacts need a GitHub
login. A release asset downloads from a plain link with no sign-in:

```
gh release upload v1.1.0 AJZ-Setup.exe --repo dbordwell/JEFF --clobber
```

**3. Send the key separately.** The repo is public, so `config.json` cannot ship with the
release. Email it — a small text file passes fine:

```json
{ "fmp_api_key": "the-rotated-key" }
```

Setup reads it from **the folder the exe runs from**, then copies it to
`%LOCALAPPDATA%\AJZ\config.json`. Both files must be in the same folder; that is the price
of a public download link, and the only fiddly part of the install.

The key never goes in the workbook, so the dashboard is safe to email to anyone.

---

## What gets installed

```
%LOCALAPPDATA%\AJZ\
    ajz-refresh.exe      copied here so the shortcut has a stable target
    config.json          the API key
    AJZ Dashboard.xlsx   the workbook itself
    history.sqlite       snapshots, survive workbook regeneration
    backups\             last 30 copies
    logs\refresh.log     diagnostics
    refresh.lock         held during a refresh

Desktop\
    AJZ Dashboard.lnk    the only thing Jeff clicks
```

Two details that are easy to get wrong:

- **The Desktop comes from the registry**, not `~/Desktop`. OneDrive backup moves it to
  `%USERPROFILE%\OneDrive\Desktop`, and the shortcut would otherwise land unseen.
- **The workbook sits beside the program, not on the Desktop.** A Desktop copy would be a
  stale copy waiting to be opened by mistake, showing old numbers under a confident banner.

Setup runs one refresh immediately, so the first open shows real numbers.

---

## Debugging remotely

```
ajz-refresh --status      what is installed, what is missing
ajz-refresh --verbose     refresh with full logging and the ranked table
ajz-refresh --no-open     refresh without launching Excel
ajz-refresh --uninstall   remove the desktop shortcut, keep all data
```

To stop using it, Jeff can just delete the shortcut — there is no background process.
`--uninstall` deliberately leaves the workbook, conviction scores, history and backups:
deleting his hand-entered scores because he stopped using the dashboard would be
wildly disproportionate.

If he has OneDrive, putting the workbook in a synced folder gives Dave a live copy to
inspect without asking him for anything.

## Exit codes

| Code | Meaning | The file |
|-----:|---------|----------|
| 0 | success | rewritten |
| 2 | no API key configured | untouched |
| 3 | could not read the existing workbook | **untouched — deliberately** |
| 4 | open in Excel | untouched, told to close and click again |
| 5 | another refresh running | untouched |

Code 3 matters most: if we cannot prove what conviction scores he had, we do not
overwrite them. A refresh that does not happen is an annoyance; one that blanks his
scores is unrecoverable.

## Not yet verified

The tests assert we build the right command, not that Windows accepts it. Unproven until
the first real install: that PowerShell creates the `.lnk`, that the registry Desktop
lookup handles OneDrive redirection, and that a locked-by-Excel file behaves as expected.

All three now fail in front of someone who is watching, which is the substantive change.
