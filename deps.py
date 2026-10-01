"""Controllo dipendenze: installa da solo quello che manca.

- pacchetti Python mancanti -> pip install (solo da sorgente: nell'exe sono già inclusi)
- browser Chromium di Playwright mancante -> lo estrae dalla copia inclusa nell'exe;
  da sorgente (o se l'estrazione fallisce) lo scarica con `playwright install chromium`
"""
import importlib.util
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# modulo da importare -> pacchetto pip
REQUIRED = {
    "playwright": "playwright>=1.45",
    "tkcalendar": "tkcalendar>=1.6",
}

FROZEN = getattr(sys, "frozen", False)
BUNDLED_ZIP = "chromium.zip"  # dentro l'exe, messo lì da build.py
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


def chromium_dir() -> Path | None:
    """Dove Playwright si aspetta Chromium (es. ...\\ms-playwright\\chromium-1234)."""
    from playwright._impl._driver import compute_driver_executable, get_driver_env
    node, cli = compute_driver_executable()
    # --dry-run elenca i percorsi senza scaricare nulla
    dry = subprocess.run([node, cli, "install", "chromium", "--no-shell", "--dry-run"], capture_output=True,
                         text=True, env=get_driver_env(), creationflags=NO_WINDOW, timeout=60)
    for line in dry.stdout.splitlines():
        if line.strip().lower().startswith("install location:"):
            p = Path(line.split(":", 1)[1].strip())
            if p.name.startswith("chromium-"):
                return p
    return None


def _installed(p: Path | None) -> bool:
    return bool(p) and (p / "INSTALLATION_COMPLETE").exists()


def _extract_bundled(target: Path, log=None) -> bool:
    """Exe standalone: Chromium viaggia dentro l'exe come zip, lo scompattiamo una volta sola."""
    bundled = Path(getattr(sys, "_MEIPASS", "")) / BUNDLED_ZIP if FROZEN else None
    if not bundled or not bundled.exists():
        return False
    _say(log, "[deps] unpacking the built-in Chromium (first launch only, ~30 s)...")
    tmp = target.with_name(target.name + ".partial")
    shutil.rmtree(tmp, ignore_errors=True)
    with zipfile.ZipFile(bundled) as z:
        z.extractall(tmp)
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)  # tutto o niente: una estrazione interrotta non lascia un browser a metà
    return _installed(target)


def ensure_browser(log=None) -> bool:
    """Chromium per Playwright: già presente, oppure estratto dall'exe, oppure scaricato. True se pronto."""
    try:
        from playwright._impl._driver import compute_driver_executable, get_driver_env
    except ImportError:
        _say(log, "[deps] playwright not available, can't check the browser.")
        return False
    try:
        target = chromium_dir()
    except Exception as e:
        _say(log, f"[deps] can't locate the browser: {e}")
        target = None
    if _installed(target):
        return True
    try:
        if target and _extract_bundled(target, log):
            _say(log, "[deps] Chromium ready.")
            return True
    except Exception as e:
        _say(log, f"[deps] built-in Chromium failed to unpack ({e}), downloading it instead.")
    node, cli = compute_driver_executable()
    _say(log, "[deps] downloading Chromium for Playwright (one time, ~150 MB)...")
    r = subprocess.run([node, cli, "install", "chromium", "--no-shell"], capture_output=True, text=True,
                       env=get_driver_env(), creationflags=NO_WINDOW)
    if r.returncode != 0:
        _say(log, f"[deps] browser install failed:\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
        return False
    _say(log, "[deps] Chromium ready.")
    return True


def ensure_all(log=None) -> bool:
    return ensure_packages(log) and ensure_browser(log)


if __name__ == "__main__":
    sys.exit(0 if ensure_all() else 1)
