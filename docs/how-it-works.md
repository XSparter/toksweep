# How toksweep works

Notes on the TikTok web app, written while building this. Useful if something breaks.

## Where the numbers come from

When you open a profile, the page calls

```
GET https://www.tiktok.com/api/post/item_list/?secUid=...&cursor=...&count=16...
```

every time you scroll near the bottom of the grid. Each response has an `itemList` array and
a `hasMore` flag. Every item carries:

| field                 | meaning                          |
|-----------------------|----------------------------------|
| `id`                  | post id (also in the URL)        |
| `createTime`          | unix timestamp of publication    |
| `stats.playCount`     | views                            |
| `stats.diggCount`     | likes                            |
| `stats.commentCount`  | comments                         |
| `stats.shareCount`    | shares                           |
| `imagePost`           | present on photo carousels       |

toksweep doesn't call this endpoint itself (the request needs signed parameters like
`X-Bogus` and `msToken`). It scrolls the grid and reads the responses the page gets anyway.

Fun fact: the post id also encodes the creation time. `id >> 32` is the unix timestamp.

## Why cinema mode

There are two ways a post opens on desktop:

- **cinema mode**: you click a tile in the profile grid. Full-screen player, comments on the
  right, a `...` button at the bottom right of the player. This one has *Delete*.
- **video page**: you open `/@user/video/<id>` directly, or sometimes TikTok decides to
  navigate there anyway. Side panel says "You may like". No reliable *Delete*, and the
  next/previous arrows move into recommended videos from other accounts.

toksweep only acts in cinema mode. It checks for `[data-e2e="cinema-more-menu-trigger"]`
and for the URL being `/@<you>/video/...` or `/@<you>/photo/...`. If either check fails it
reopens the grid.

## Login check

Before anything else toksweep asks TikTok who's logged in, from inside the page:

```
GET /passport/web/account/info/?aid=1988      (same origin, browser cookies)
-> {"message": "success", "data": {"username": "you", ...}}   logged in
-> {"message": "error", ...}                                   logged out
```

It's a read-only lookup, the same one the web app makes. If it fails for any reason, the
fallback is the sidebar's *Profile* link, which points to `/@you` only when logged in.
The username found there must match the one in the config (case-insensitive), otherwise
the run stops before reading the grid.

## Selectors in use

TikTok ships `data-e2e` attributes for its own tests. They don't depend on the UI language
and they change much less often than class names.

| what                       | selector                                         |
|----------------------------|--------------------------------------------------|
| grid tile                  | `[data-e2e="user-post-item"]`                    |
| player `...` menu          | `[data-e2e="cinema-more-menu-trigger"]`          |
| *Delete* in that menu      | `[data-e2e="more-menu-popover_delete-content"]`  |
| *Delete* in the confirm    | `[data-e2e="video-modal-delete"]`                |
| next post                  | `button[aria-label="Next video"]`                |
| logged-in check (fallback) | `[data-e2e="nav-profile"]` (its link is `/@you`) |

Careful with the confirm popup: *Delete* is the first button and *Cancel* the second, so
"click the last button" cancels. Only the test id is used, on purpose.

`aria-label="Next video"` is in English even when the UI is in Italian, so it looks safe
across languages, but it's the one selector here that isn't a test id. If navigation breaks
in your language, that's the first thing to check.

## Things that bit me

- **Photo posts** live under `/photo/<id>`, not `/video/<id>`. Anything that only expects
  `/video/` gets stuck on the first carousel.
- **The player stops** after a while, once it reaches the end of what it preloaded. The
  *next* arrow just does nothing. toksweep waits, retries, then reopens the grid at the
  first post it hasn't seen.
- **Background tabs get throttled.** If the browser window is minimized or covered, timers
  slow down and the player stops reacting. Keep it in the foreground.
- **Mouse wheel** over the player does not move to the next post in cinema mode. The arrow
  button does.
- **The grid is virtualized**: only ~100 tiles exist in the DOM at once, so finding an
  older post means scrolling until it's rendered.
- **The `<a>` on each tile** is an empty overlay with zero size. Click the tile, not the link.
- **UTC vs local time**: dates are compared in local time, otherwise late-night posts land
  on the previous day and fall out of the range you meant.
