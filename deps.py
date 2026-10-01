"""Controllo dipendenze: installa da solo quello che manca.

- pacchetti Python mancanti -> pip install (solo da sorgente: nell'exe sono già inclusi)
- browser Chromium di Playwright mancante -> `playwright install chromium`
  (funziona anche dall'exe, usa il driver Node incluso nel pacchetto playwright)
"""
import importlib.util
import subprocess
import sys

# modulo da importare -> pacchetto pip
REQUIRED = {
    "playwright": "playwright>=1.45",
    "tkcalendar": "tkcalendar>=1.6",
}

FROZEN = getattr(sys, "frozen", False)
# niente finestre console che lampeggiano quando gira come .exe senza console
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _say(log, msg: str):
    if log:
        log(msg + "\n")
    else:
        print(msg, flush=True)


def missing_packages() -> list[str]:
    return [pip for mod, pip in REQUIRED.items() if importlib.util.find_spec(mod) is None]


def ensure_packages(log=None) -> bool:
    """True se alla fine tutti i pacchetti ci sono."""
    missing = missing_packages()
    if not missing:
        return True
    if FROZEN:
        _say(log, f"[deps] missing from the build: {', '.join(missing)}")
        return False
    _say(log, f"[deps] installing: {', '.join(missing)} ...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", *missing],
                       capture_output=True, text=True, creationflags=NO_WINDOW)
    if r.returncode != 0:
        _say(log, f"[deps] pip failed:\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
        return False
    importlib.invalidate_caches()
    still = missing_packages()
    if still:
        _say(log, f"[deps] still missing after pip: {', '.join(still)}")
        return False
    _say(log, "[deps] packages installed.")
    return True


def ensure_browser(log=None) -> bool:
    """Scarica Chromium per Playwright se non c'è già. True se pronto."""
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
    except ImportError:
        _say(log, "[deps] playwright not available, can't check the browser.")
        return False
    node, cli = compute_driver_executable()
    cmd = [node, cli, "install", "chromium"]
    env = get_driver_env()
    # --dry-run elenca i percorsi senza scaricare: se esistono già, siamo a posto
    try:
        dry = subprocess.run(cmd + ["--dry-run"], capture_output=True, text=True,
                             env=env, creationflags=NO_WINDOW, timeout=60)
        from pathlib import Path
        locations = [line.split(":", 1)[1].strip() for line in dry.stdout.splitlines()
                     if line.strip().lower().startswith("install location:")]
        if locations and all(Path(p).exists() for p in locations):
            return True
    except Exception:
        pass
    _say(log, "[deps] downloading Chromium for Playwright (one time, ~150 MB)...")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, creationflags=NO_WINDOW)
    if r.returncode != 0:
        _say(log, f"[deps] browser install failed:\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
        return False
    _say(log, "[deps] Chromium ready.")
    return True


def ensure_all(log=None) -> bool:
    return ensure_packages(log) and ensure_browser(log)


if __name__ == "__main__":
    sys.exit(0 if ensure_all() else 1)
