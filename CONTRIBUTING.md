# Contributing

Issues and pull requests are welcome.

**Something broke?** TikTok changes its UI from time to time. Open an issue with:

- what you ran (dry run or not, rough number of posts)
- the last 20 lines of output
- the screenshot from `debug/` if there is one (crop out anything private)

**Want to fix it yourself?** `docs/how-it-works.md` lists every selector and why it's there.
`tools/request-logger.user.js` helps you see what the web app is doing.

A few ground rules:

- keep the dry run as the default
- never call TikTok's private endpoints directly; click through the UI
- no new dependencies unless they really pull their weight
- test against a real profile in dry-run mode before sending a PR
