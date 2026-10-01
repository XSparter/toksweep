"""
toksweep - cleans up your TikTok profile by deleting the videos that didn't make it.

How it works, in short:
  1. open your profile and let TikTok load the whole grid; while it does, we listen to
     its own /api/post/item_list/ responses, which carry views, likes and post date
  2. open the first video from the grid (cinema mode - the only place where TikTok
     shows "Delete" reliably) and walk down with the "next video" arrow
  3. for every video, check the rules; if it has to go, use the "..." menu like a human would

We never call the delete API ourselves: TikTok signs those requests in the browser,
so we just click the buttons and let it do its thing.
"""
import asyncio
import csv
import json
import re
import threading
import time
from datetime import datetime, timezone, date
from pathlib import Path

from playwright.async_api import async_playwright, Page, Response

try:
    import msvcrt          # windows only, used for the 'q' key
except ImportError:
    msvcrt = None

STOP_FILE = Path("STOP")
DEBUG_DIR = Path("debug")
DELETED_LOG = Path("deleted.csv")

ITEM_LIST_API = "/api/post/item_list/"

# TikTok's own test ids. Way more stable than class names, and they don't change with the UI language.
SEL_GRID_ITEM = '[data-e2e="user-post-item"]'
SEL_CINEMA_MENU = '[data-e2e="cinema-more-menu-trigger"]'
SEL_DELETE_ITEM = '[data-e2e="more-menu-popover_delete-content"]'
SEL_CONFIRM = '[data-e2e="video-modal-delete"]'
SEL_NEXT = 'button[aria-label="Next video"]'


class Sweeper:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.handle = cfg["account"]["username"].lstrip("@")
        self.profile_url = f"https://www.tiktok.com/@{self.handle}"
        self.rules = cfg["rules"]
        self.opts = cfg["options"]

        self.videos: list[dict] = []          # same order as the profile grid
        self.by_id: dict[str, dict] = {}
        self.page: Page | None = None
        self._stop = asyncio.Event()
        self._loop = None
        self._has_more = True

    # --- emergency brake -------------------------------------------------------

    def _watch_for_stop(self):
        # 'q' in the console, or just drop a file called STOP next to the script
        STOP_FILE.unlink(missing_ok=True)

        def watch():
            while not self._stop.is_set():
                pressed_q = msvcrt and msvcrt.kbhit() and msvcrt.getch().lower() == b"q"
                if pressed_q or STOP_FILE.exists():
                    print("\n[stop] ok, finishing the current step and quitting...\n", flush=True)
                    self._loop.call_soon_threadsafe(self._stop.set)
                    return
                time.sleep(0.05)

        threading.Thread(target=watch, daemon=True).start()

    async def stopped(self) -> bool:
        await asyncio.sleep(0)
        return self._stop.is_set()

    # --- browser ---------------------------------------------------------------

    async def start(self):
        # persistent profile = you log in once and TikTok remembers you
        profile = Path(self.opts.get("browser_profile_dir", "browser_profile")).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._ctx = await self._pw.chromium.launch_persistent_context(
            str(profile),
            headless=self.opts.get("headless", False),
            locale=self.opts.get("locale", "en-US"),
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()

    async def close(self):
        await self._ctx.close()
        await self._pw.stop()

    async def ensure_logged_in(self):
        await self.page.goto("https://www.tiktok.com/", wait_until="networkidle")
        if await self.page.query_selector('[data-e2e="nav-profile"]'):
            return
        print("\nNot logged in. Log in from the browser window, I'll wait (5 min max)...", flush=True)
        await self.page.wait_for_selector('[data-e2e="nav-profile"]', timeout=300_000)
        print("Logged in, let's go.\n")
        await self.page.wait_for_timeout(2000)

    # --- stats -----------------------------------------------------------------

    def _ingest(self, items: list):
        for item in items:
            vid = str(item.get("id") or "")
            if not vid or vid in self.by_id:
                continue
            stats = item.get("stats") or {}
            v = {
                "id": vid,
                "desc": (item.get("desc") or "")[:80],
                "create_time": item.get("createTime") or 0,
                "views": stats.get("playCount") or 0,
                "likes": stats.get("diggCount") or 0,
                "comments": stats.get("commentCount") or 0,
                "shares": stats.get("shareCount") or 0,
            }
            self.videos.append(v)
            self.by_id[vid] = v

    async def _on_response(self, resp: Response):
        if ITEM_LIST_API not in resp.url:
            return
        try:
            data = await resp.json()
        except Exception:
            return
        self._has_more = bool(data.get("hasMore"))
        self._ingest(data.get("itemList") or [])

    async def load_stats(self):
        self.page.on("response", self._on_response)
        print(f"Loading {self.profile_url}")
        await self.page.goto(self.profile_url, wait_until="networkidle")

        idle, last = 0, 0
        while idle < 6 and not await self.stopped():
            await self.page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'})")
            await self.page.wait_for_timeout(1800)
            idle = idle + 1 if len(self.videos) == last else 0
            last = len(self.videos)
            if not self._has_more and self.videos:
                break
            print(f"  {len(self.videos)} posts so far...", end="\r", flush=True)
        print(f"\nGot stats for {len(self.videos)} posts.\n", flush=True)

    # --- rules -----------------------------------------------------------------

    @staticmethod
    def post_date(ts: int) -> date:
        # local time on purpose: a video posted at 1am belongs to that day, not to UTC's yesterday
        return datetime.fromtimestamp(ts).date()

    @staticmethod
    def age_days(ts: int) -> float:
        return (datetime.now(timezone.utc).timestamp() - ts) / 86400

    def _in_ranges(self, ts: int) -> bool:
        ranges = self.rules.get("date_ranges") or []
        if not ranges:
            return True
        d = self.post_date(ts)
        return any(date.fromisoformat(r["from"]) <= d <= date.fromisoformat(r["to"]) for r in ranges)

    def _oldest_range_start(self) -> date | None:
        ranges = self.rules.get("date_ranges") or []
        return min((date.fromisoformat(r["from"]) for r in ranges), default=None)

    def verdict(self, v: dict) -> tuple[bool, str]:
        """(delete it?, why)"""
        if not v["create_time"]:
            return False, "unknown date"
        keep_days = self.rules.get("min_age_days", 0)
        if self.age_days(v["create_time"]) < keep_days:
            return False, f"newer than {keep_days} days"
        if not self._in_ranges(v["create_time"]):
            return False, "outside date ranges"

        limits = self.rules.get("delete_if", {})
        engagement = (v["likes"] + v["comments"] + v["shares"]) / v["views"] * 100 if v["views"] else 0
        values = {
            "views_below": v["views"],
            "likes_below": v["likes"],
            "comments_below": v["comments"],
            "shares_below": v["shares"],
            "engagement_rate_below": engagement,
        }
        active = {k: lim for k, lim in limits.items() if lim is not None and k in values}
        hits = [f"{k.replace('_below', '')} {values[k]:.0f} < {lim}" for k, lim in active.items() if values[k] < lim]

        if not hits:
            return False, "ok"
        if self.rules.get("logic", "OR").upper() == "AND" and len(hits) < len(active):
            return False, "only some AND rules matched"
        return True, ", ".join(hits)

    # --- navigation ------------------------------------------------------------

    def current_id(self) -> str | None:
        # photo carousels live under /photo/, everything else under /video/
        m = re.search(r"/(?:video|photo)/(\d+)", self.page.url)
        return m.group(1) if m else None

    def on_own_post(self) -> bool:
        return bool(re.search(rf"/@{re.escape(self.handle.lower())}/(?:video|photo)/\d+", self.page.url.lower()))

    async def in_cinema(self) -> bool:
        el = await self.page.query_selector(SEL_CINEMA_MENU)
        return bool(el and await el.is_visible())

    async def open_from_grid(self, vid: str | None = None) -> bool:
        # Sometimes TikTok opens the plain video page instead of cinema mode.
        # That page has no Delete and its "next" goes to random recommended stuff, so we retry.
        for attempt in range(3):
            await self.page.goto(self.profile_url, wait_until="networkidle")
            await self.page.evaluate("window.scrollTo(0, 0)")
            await self.page.wait_for_timeout(2500)

            tile = self.page.locator(SEL_GRID_ITEM).first
            if vid:
                tile = self.page.locator(SEL_GRID_ITEM).filter(
                    has=self.page.locator(f'a[href*="/{vid}"]')).first
                # scroll the page itself: the mouse wheel goes to whatever is under the cursor,
                # which is often the sidebar
                for _ in range(150):
                    if await tile.count() and await tile.is_visible():
                        break
                    if await self.stopped():
                        return False
                    await self.page.evaluate("window.scrollBy({top: 700, behavior: 'instant'})")
                    await self.page.wait_for_timeout(600)
                else:
                    return False

            await tile.scroll_into_view_if_needed()
            await tile.click()
            try:
                await self.page.wait_for_selector(SEL_CINEMA_MENU, timeout=8000)
                await self.page.wait_for_timeout(1000)
                if self.on_own_post():
                    return True
            except Exception:
                pass
            print(f"    (didn't land in cinema mode, retry {attempt + 1}/3)", flush=True)
        return False

    async def _click_next(self, cur: str) -> str | None:
        btn = await self.page.query_selector(SEL_NEXT)
        if not btn or not await btn.is_visible() or await btn.is_disabled():
            return None
        await btn.click()
        try:
            await self.page.wait_for_function(
                "id => !location.href.includes(id) && /\\/(video|photo)\\/\\d+/.test(location.href)",
                arg=cur, timeout=6000)
        except Exception:
            return None
        await self.page.wait_for_timeout(1200)
        if not self.on_own_post() or not await self.in_cinema():
            return None
        return self.current_id()

    async def advance(self, cur: str, seen: set[str]) -> str | None:
        # the player sometimes just stops (end of what it loaded). give it a moment,
        # then fall back to reopening the grid at the first post we haven't seen yet.
        for _ in range(3):
            if not self.on_own_post() or not await self.in_cinema():
                break
            nxt = await self._click_next(cur)
            if nxt:
                return nxt
            await self.page.wait_for_timeout(4000)

        left = [v["id"] for v in self.videos if v["id"] not in seen]
        if not left or await self.stopped():
            return None
        print(f"    (player got stuck, reopening the grid at {left[0]})", flush=True)
        return self.current_id() if await self.open_from_grid(left[0]) else None

    # --- deleting --------------------------------------------------------------

    async def _confirm_dialog(self) -> bool:
        # "Are you sure?" popup. Delete is the *first* button, Cancel the second, so going
        # by position is a trap. The test id is language independent and that's all we trust:
        # if it ever disappears we'd rather fail than click something random.
        try:
            btn = await self.page.wait_for_selector(SEL_CONFIRM, state="visible", timeout=5000)
        except Exception:
            await self.page.keyboard.press("Escape")
            return False
        await btn.click()
        return True

    async def delete_current(self) -> bool:
        menu = await self.page.query_selector(SEL_CINEMA_MENU)
        if not menu or not await menu.is_visible():
            return False
        await menu.click()
        try:
            item = await self.page.wait_for_selector(SEL_DELETE_ITEM, state="visible", timeout=4000)
        except Exception:
            await self.page.keyboard.press("Escape")
            return False
        await item.click()
        await self.page.wait_for_timeout(1000)
        return await self._confirm_dialog()

    async def save_debug(self, tag: str):
        DEBUG_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%H%M%S")
        await self.page.screenshot(path=str(DEBUG_DIR / f"{stamp}_{tag}.png"))
        print(f"    screenshot saved: debug/{stamp}_{tag}.png", flush=True)

    def log_deleted(self, v: dict, why: str):
        first = not DELETED_LOG.exists()
        with DELETED_LOG.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if first:
                w.writerow(["deleted_at", "id", "posted", "views", "likes", "comments", "reason"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), v["id"], self.post_date(v["create_time"]),
                        v["views"], v["likes"], v["comments"], why])

    # --- main loop -------------------------------------------------------------

    async def run(self):
        self._loop = asyncio.get_running_loop()
        self._watch_for_stop()
        print("To stop: press 'q' here, or create a file named STOP in this folder.\n", flush=True)

        await self.ensure_logged_in()
        await self.load_stats()
        if not self.videos or await self.stopped():
            return

        dry = self.opts.get("dry_run", True)
        cap = self.opts.get("max_deletes_per_run", 50)
        pause = self.opts.get("delay_between_deletes_seconds", 3)
        oldest = self._oldest_range_start()
        planned = sum(1 for v in self.videos if self.verdict(v)[0])

        print(f"{planned} posts match the rules  (dry run: {dry}, cap: {cap})")
        print("-" * 80, flush=True)

        if not await self.open_from_grid():
            print("Couldn't open the first post in cinema mode.")
            await self.save_debug("open_first")
            return

        seen: set[str] = set()
        deleted = fails = too_old = n = 0
        cur = self.current_id()

        while cur and not await self.stopped():
            if cur in seen:
                cur = await self.advance(cur, seen)
                continue
            seen.add(cur)
            n += 1

            v = self.by_id.get(cur)
            if not v:
                print(f"{n:>5}  ??    {cur}  no stats for this one, skipping", flush=True)
                cur = await self.advance(cur, seen)
                continue

            go, why = self.verdict(v)
            if go and deleted >= cap:
                go, why = False, "cap reached"
            tag = ("DRY" if dry else "DEL") if go else "keep"
            print(f"{n:>5}  {tag:<5} {cur}  {self.post_date(v['create_time'])}  "
                  f"{v['views']:>8} views {v['likes']:>6} likes  {why}", flush=True)

            # grid is newest first, so once we're well past the oldest range there's nothing left to do
            if oldest and self.post_date(v["create_time"]) < oldest:
                too_old += 1
                if too_old >= 8:
                    print("Past the oldest date range, done.", flush=True)
                    break
            else:
                too_old = 0

            # paranoia: make sure the player really shows the post we just judged
            if go and not dry and (self.current_id() != v["id"] or not self.on_own_post()
                                   or not await self.in_cinema()):
                print("      player shows something else, not touching it", flush=True)
                go = False

            if go and not dry:
                if await self.delete_current():
                    try:
                        await self.page.wait_for_function("id => !location.href.includes(id)", arg=cur, timeout=8000)
                    except Exception:
                        pass
                    await self.page.wait_for_timeout(1500)
                    deleted += 1
                    fails = 0
                    self.log_deleted(v, why)
                    print(f"      deleted ({deleted}/{min(planned, cap)})", flush=True)
                    if pause:
                        await asyncio.sleep(pause)

                    # after a delete TikTok usually jumps to the next post on its own
                    nxt = self.current_id()
                    if nxt and nxt != cur and self.on_own_post() and await self.in_cinema():
                        cur = nxt
                        continue
                    left = [x["id"] for x in self.videos if x["id"] not in seen]
                    if not left or not await self.open_from_grid(left[0]):
                        print("Couldn't get back into the feed after deleting.", flush=True)
                        await self.save_debug("reopen")
                        break
                    cur = self.current_id()
                    continue

                fails += 1
                print("      delete failed", flush=True)
                await self.save_debug(f"delete_fail_{cur}")
                await self.page.keyboard.press("Escape")
                if fails >= 3:
                    print("Three failures in a row, stopping to be safe.", flush=True)
                    break

            cur = await self.advance(cur, seen)

        missed = sum(1 for v in self.videos if v["id"] not in seen and self.verdict(v)[0])
        done = sum(1 for i in seen if i in self.by_id and self.verdict(self.by_id[i])[0]) if dry else deleted
        print("\n" + "=" * 80)
        print(f"Seen: {len(seen)}   {'Would delete' if dry else 'Deleted'}: {done}   Matching but not reached: {missed}")
        print("=" * 80, flush=True)
