# Changelog

## 1.0.0 - 2026-10-01

First public version.

- Reads exact views, likes, comments, shares and post date for every post on the profile
- Rules: views / likes / comments / shares / engagement thresholds, `OR` / `AND`, date ranges,
  protection for recent posts
- Deletes through cinema mode, one post at a time, with an identity check before each delete
- Supports photo carousels
- Recovers when the player stops advancing
- Dry run by default, per-run cap, delay between deletes
- Emergency stop with `q` or a `STOP` file
- `deleted.csv` log and debug screenshots
