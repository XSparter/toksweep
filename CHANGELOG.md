# Changelog

## 1.1.0 - 2026-10-01

Desktop app and Windows release.

- **Desktop app** (`gui.py`, or `toksweep.exe` from the releases page)
  - English and Italian, picked from the Windows language, switchable from the app
  - light and dark colors that follow the Windows theme, live
  - calendar date picker for the date ranges
  - fixed-size window, app logo, live log with progress counters
  - `--selftest` flag that checks dependencies, date picker and browser
- **Automatic dependency setup**: missing Python packages and the Chromium browser are
  installed on startup (`deps.py`, also runnable on its own)
- **Real login check**: asks TikTok which account the browser is logged into and stops if it
  isn't the one in the config. Headless runs no longer wait 5 minutes for a login nobody can do,
  and Stop works while waiting for a login
- Username accepted as `name`, `@name` or profile link
- Saving from the app keeps config keys the app doesn't know about
- `build.py` builds a single-file Windows exe with PyInstaller

## 1.0.0 - 2026-10-01

First public version.

- Reads exact views, likes, comments, shares and post date for every post on the profile
- Rules: views / likes / comments / shares / engagement thresholds, `OR` / `AND`, date ranges,
  protection for recent posts
- Deletes through cinema mode, one post at a time, with an identity check before each delete
- A delete only counts once TikTok's own response confirms it (catches promoted posts and
  silent server-side failures)
- Supports photo carousels
- Recovers when the player stops advancing
- Dry run by default, per-run cap, delay between deletes
- Emergency stop with `q` or a `STOP` file
- `deleted.csv` log and debug screenshots
