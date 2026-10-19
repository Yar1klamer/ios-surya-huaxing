# Working on ios-sweet

## Current owner and target (2026-10-19)

- This checkout targets Poco X3 NFC (`surya`). Read the SURYA handoff at the top
  of NOTES.md before upstream history.
- The owner's original project is suspended and preserved separately. Do not
  resume or delete it unless asked. Keep this adaptation in this checkout.
- Historical sweet results and device permissions below describe the upstream
  owner's Redmi, not authorization to erase this owner's Poco.
- Work in batches with host validation. Observe actual device boot results;
  successful compilation or fastboot transfer does not establish a working boot.

- Read `NOTES.md` before starting; it contains the project goal, hardware facts,
  current blocker, local artifact locations and the next concrete action.
- The user switches agents frequently. Update the active handoff in `NOTES.md`
  after each milestone and before stopping. Record commits, CI run IDs, exact
  build/boot results and unfinished work. Distinguish observations from guesses.
- Commit completed changes. Use `gh` for GitHub Actions kernel builds and logs.
  Local single-file cross-compiles are useful before spending a CI run.
- Device bring-up uses temporary `fastboot boot` images. Preserve the Android
  installation and partition backups. The user approved (2026-10-15) using
  internal UFS for iOS and said Android may be deleted: the iOS root goes
  into the existing `userdata` partition (no GPT changes). Keep bootloaders,
  recovery, modem, persist and the backups intact, and confirm each
  destructive step with the user before running it.
- Keep device dumps, serial numbers and downloaded Apple artifacts out of git.
