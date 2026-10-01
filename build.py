"""Builds dist/toksweep.exe (single file, no console) with PyInstaller.

    python build.py

The exe bundles Python, the GUI, Playwright and its Node driver. Chromium itself is
not bundled (~150 MB): the app downloads it on first launch if it's missing.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"


def make_icon() -> Path:
    from PIL import Image
    ico = BUILD / "toksweep.ico"
    BUILD.mkdir(exist_ok=True)
    Image.open(ROOT / "assets" / "logo.png").save(
        ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico


def babel_data() -> list[str]:
    # tkcalendar formats dates through babel: ship only the locales the GUI uses, not all 700+
    import babel
    base = Path(babel.__file__).parent
    files = [base / "global.dat"] + [base / "locale-data" / f"{n}.dat" for n in ("root", "it", "it_IT", "en", "en_US")]
    args = ["--add-data", f"{base / 'locale-data' / 'LICENSE.unicode'};babel/locale-data"] \
        if (base / "locale-data" / "LICENSE.unicode").exists() else []
    for f in files:
        dest = "babel" if f.name == "global.dat" else "babel/locale-data"
        args += ["--add-data", f"{f};{dest}"]
    return args


def main():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt"),
                           "pyinstaller", "pillow"])
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", "toksweep",
        "--icon", str(make_icon()),
        "--add-data", f"{ROOT / 'assets' / 'logo.png'};assets",
        "--add-data", f"{ROOT / 'assets' / 'logo-32.png'};assets",
        "--collect-data", "playwright",       # driver: node.exe + the JS package
        "--hidden-import", "babel.numbers",   # tkcalendar imports it lazily
        *babel_data(),
        "--distpath", str(ROOT / "dist"), "--workpath", str(BUILD), "--specpath", str(BUILD),
        str(ROOT / "gui.py"),
    ]
    subprocess.check_call(cmd, cwd=ROOT)
    exe = ROOT / "dist" / "toksweep.exe"
    print(f"\nbuilt {exe}  ({exe.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
