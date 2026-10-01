import asyncio
import json
import sys
from pathlib import Path

from sweeper import Sweeper

BANNER = r"""
  _       _
 | |_ ___| | _____      _____  ___ _ __
 | __/ _ \ |/ / __\ \ /\ / / _ \/ _ \ '_ \
 | || (_) |   <\__ \\ V  V /  __/  __/ |_) |
  \__\___/|_|\_\___/ \_/\_/ \___|\___| .__/
                                     |_|
"""


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        sys.exit(f"Can't find {path}. Copy config.example.json to config.json and edit it first.")
    return json.loads(p.read_text(encoding="utf-8"))


async def main():
    cfg = load_config(sys.argv[1] if len(sys.argv) > 1 else "config.json")
    rules, opts = cfg["rules"], cfg["options"]

    print(BANNER)
    print(f"  account   @{cfg['account']['username'].lstrip('@')}")
    print(f"  dry run   {opts.get('dry_run', True)}")
    print(f"  rules     {rules.get('logic', 'OR')} {{{', '.join(f'{k}: {v}' for k, v in rules.get('delete_if', {}).items() if v is not None)}}}")
    print(f"  dates     {', '.join(r['from'] + ' -> ' + r['to'] for r in rules.get('date_ranges') or []) or 'any'}")
    print(f"  protect   last {rules.get('min_age_days', 0)} days\n")

    bot = Sweeper(cfg)
    await bot.start()
    try:
        await bot.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
