# Contributing

Issues and pull requests are welcome.

**Something broke?** TikTok changes its UI from time to time. Open an issue with:

- what you ran (dry run or not, rough number of posts)
- the last 20 lines of output
- your `selftest.txt` (run `toksweep.exe --selftest` or `python gui.py --selftest`)
- the screenshot from `debug/` if there is one (crop out anything private)

**Want to fix it yourself?** `docs/how-it-works.md` lists every selector and why it's there.
`tools/request-logger.user.js` helps you see what the web app is doing.

A few ground rules:

- keep the dry run as the default
- never call TikTok endpoints that change anything; click through the UI. The only direct
  call is the read-only account lookup used by the login check
- no new dependencies unless they really pull their weight
- test against a real profile in dry-run mode before sending a PR

## Development setup

```bash
pip install -r requirements.txt
playwright install chromium
python gui.py            # desktop app
python main.py           # command line
python gui.py --selftest # quick health check
python build.py          # Windows exe in dist/
```

GUI text lives in the `STRINGS` table at the top of `gui.py`. To add a language, copy the
`"en"` block, translate it, and add the code to `LANGS`. Missing keys fall back to English.
