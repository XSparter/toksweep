"""Builds dist/toksweep.exe (single file, no console) with PyInstaller.

    python build.py

The exe is standalone: Python, the GUI, Playwright, its Node driver and Chromium are all
inside. On first launch it unpacks Chromium to the Playwright cache; nothing is downloaded.
"""
import subprocess
import sys
import zipfile
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


def make_splash() -> Path:
    """Shown while the exe unpacks itself (a few seconds): logo + name, so it doesn't look frozen."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = 420, 200
    img = Image.new("RGB", (w, h), "#1e1f22")
    logo = Image.open(ROOT / "assets" / "logo.png").convert("RGBA").resize((96, 96), Image.LANCZOS)
    img.paste(logo, (32, 52), logo)

    def font(size, bold=False):
        for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default()
    d = ImageDraw.Draw(img)
    d.text((148, 58), "toksweep", fill="#ff4d6d", font=font(34, bold=True))
    d.text((150, 108), "starting, give it a few seconds…", fill="#9aa0a6", font=font(14))
    out = BUILD / "splash.png"
    BUILD.mkdir(exist_ok=True)
    img.save(out)
    return out


def chromium_zip() -> Path:
    """Zips the Chromium build matching the installed Playwright, to ship inside the exe."""
    sys.path.insert(0, str(ROOT))
    import deps
    if not deps.ensure_browser():
        sys.exit("can't get Chromium to bundle")
    src = deps.chromium_dir()
    out = BUILD / deps.BUNDLED_ZIP
    stamp = out.with_suffix(".src")
    if out.exists() and stamp.exists() and stamp.read_text() == str(src):
        return out  # already zipped for this Chromium version
    print(f"zipping {src} ...")
    BUILD.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(src))
    stamp.write_text(str(src))
    return out


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
        "--splash", str(make_splash()),
        "--add-data", f"{ROOT / 'assets' / 'logo.png'};assets",
        "--add-data", f"{ROOT / 'assets' / 'logo-32.png'};assets",
        "--collect-data", "playwright",       # driver: node.exe + the JS package
        "--add-data", f"{chromium_zip()};.",   # the browser itself, unpacked on first launch
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
