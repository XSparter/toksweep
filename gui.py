"""toksweep GUI - interfaccia grafica per configurare e avviare lo sweeper.

Uso:
    python gui.py [config.json]

- Italiano / inglese (automatico dalla lingua di Windows, cambiabile dal menu in alto)
- Colori chiari / scuri che seguono il tema di Windows, anche mentre è aperta
- Calendario per scegliere gli intervalli di date
- All'avvio controlla le dipendenze e installa quelle mancanti (pacchetti + Chromium)
"""
import asyncio
import copy
import csv
import json
import locale
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import date

import deps

__version__ = "1.1.0"

FROZEN = getattr(sys, "frozen", False)
# da exe: i file utente (config, profilo, deleted.csv) stanno accanto all'exe
BASE_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
# risorse incluse nel bundle (logo)
RES_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
DEFAULT_CONFIG = BASE_DIR / "config.json"
SETTINGS_FILE = BASE_DIR / "gui_settings.json"
STOP_FILE = BASE_DIR / "STOP"
DELETED_LOG = BASE_DIR / "deleted.csv"
RUN_DONE = object()  # sentinel in coda: il worker ha finito
DEPS_DONE = object()  # sentinel in coda: controllo dipendenze finito

if FROZEN:
    # nell'exe Playwright cercherebbe Chromium dentro la cartella temporanea dell'exe,
    # che sparisce a ogni chiusura: usa la cache standard, condivisa con l'installazione da sorgente
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(
        Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ms-playwright")

RULE_KEYS = ["views_below", "likes_below", "comments_below", "shares_below", "engagement_rate_below"]

DEFAULT_CFG = {
    "account": {"username": ""},
    "rules": {
        "date_ranges": [],
        "min_age_days": 7,
        "delete_if": {"views_below": 4000},
        "logic": "OR",
    },
    "options": {
        "dry_run": True,
        "max_deletes_per_run": 50,
        "delay_between_deletes_seconds": 3,
        "headless": False,
        "locale": "en-US",
        "browser_profile_dir": "browser_profile",
    },
}

# ---------------------------------------------------------------- lingue

LANGS = {"it": "Italiano", "en": "English"}

STRINGS = {
    "it": {
        "config": "Config:", "browse": "Sfoglia…", "reload": "Ricarica", "save": "Salva", "language": "Lingua:",
        "account": "Account", "username": "Username:", "username_hint": "con o senza @, va bene anche il link del profilo",
        "rules": "Regole di eliminazione", "protect_days": "Proteggi ultimi N giorni:", "logic": "Logica:",
        "logic_hint": "OR = basta una regola · AND = tutte", "delete_if": "Elimina se (spunta per attivare):",
        "views_below": "Views sotto", "likes_below": "Like sotto", "comments_below": "Commenti sotto",
        "shares_below": "Condivisioni sotto", "engagement_rate_below": "Engagement % sotto",
        "ranges": "Intervalli date (vuoto = qualsiasi data)", "add": "Aggiungi…", "edit": "Modifica…", "remove": "Rimuovi",
        "options": "Opzioni", "dry_run": "Dry run (non cancellare, solo anteprima)",
        "dry_safe": "Modalità sicura: non cancella nulla.", "dry_real": "⚠ REALE: eliminerà davvero i video!",
        "max_deletes": "Max eliminazioni:", "delay": "Pausa tra delete (s):", "headless": "Headless (nascondi browser)",
        "profile": "Profilo browser:", "start": "▶ Avvia", "stop": "■ Stop",
        "status": "Stato:", "st_idle": "inattivo", "st_running": "in esecuzione…", "st_stopping": "arresto…",
        "st_deps": "controllo dipendenze…", "st_deps_fail": "dipendenze mancanti",
        "clear_log": "Pulisci log", "save_log": "Salva log…",
        "hint": "Per fermare premi Stop. Il browser deve restare aperto durante il run.",
        "range_title": "Intervallo date", "from": "Dal:", "to": "Al:", "ok": "OK", "cancel": "Annulla",
        "bad_dates": "Date non valide", "bad_dates_fmt": "Usa il formato YYYY-MM-DD per entrambe.",
        "bad_dates_order": "'Dal' deve essere prima o uguale ad 'Al'.",
        "bad_value": "Valore non valido", "bad_value_for": "Valore non valido per '{label}': {value!r}",
        "no_user": "Manca username", "no_user_msg": "Inserisci il tuo username TikTok.",
        "cfg_missing": "Nessun {name}: parto dai valori predefiniti (Salva per crearlo).",
        "cfg_invalid": "Config non valido", "cfg_loaded": "Config caricato da {path}",
        "cfg_saved": "Config salvato in {path}", "saved": "Salvato",
        "confirm_title": "Conferma ELIMINAZIONE REALE",
        "confirm_msg": "Dry run disattivato: i video verranno CANCELLATI davvero.\n\nTikTok non ha cestino. Continuare?",
        "save_failed": "Salvataggio fallito", "start_msg": "Avvio — @{user} (dry_run={dry})",
        "finished": "Finito.", "error": "Errore", "stop_req": "Stop richiesto, finisco il passo corrente…",
        "close_title": "Chiudere?", "close_msg": "Un run è in corso. Chiudere comunque?",
        "deleted_none": "Nessun deleted.csv ancora.", "deleted_title": "deleted.csv — {n} eliminati",
        "deps_ok": "Dipendenze a posto.", "deps_fail": "Alcune dipendenze non si sono installate: guarda il log.",
    },
    "en": {
        "config": "Config:", "browse": "Browse…", "reload": "Reload", "save": "Save", "language": "Language:",
        "account": "Account", "username": "Username:", "username_hint": "with or without @, a profile link works too",
        "rules": "Delete rules", "protect_days": "Protect last N days:", "logic": "Logic:",
        "logic_hint": "OR = any rule · AND = all of them", "delete_if": "Delete if (tick to enable):",
        "views_below": "Views below", "likes_below": "Likes below", "comments_below": "Comments below",
        "shares_below": "Shares below", "engagement_rate_below": "Engagement % below",
        "ranges": "Date ranges (empty = any date)", "add": "Add…", "edit": "Edit…", "remove": "Remove",
        "options": "Options", "dry_run": "Dry run (delete nothing, preview only)",
        "dry_safe": "Safe mode: nothing gets deleted.", "dry_real": "⚠ LIVE: videos will really be deleted!",
        "max_deletes": "Max deletes:", "delay": "Pause between deletes (s):", "headless": "Headless (hide browser)",
        "profile": "Browser profile:", "start": "▶ Start", "stop": "■ Stop",
        "status": "Status:", "st_idle": "idle", "st_running": "running…", "st_stopping": "stopping…",
        "st_deps": "checking dependencies…", "st_deps_fail": "missing dependencies",
        "clear_log": "Clear log", "save_log": "Save log…",
        "hint": "Press Stop to halt. Keep the browser open while it runs.",
        "range_title": "Date range", "from": "From:", "to": "To:", "ok": "OK", "cancel": "Cancel",
        "bad_dates": "Invalid dates", "bad_dates_fmt": "Use the YYYY-MM-DD format for both.",
        "bad_dates_order": "'From' must be on or before 'To'.",
        "bad_value": "Invalid value", "bad_value_for": "Invalid value for '{label}': {value!r}",
        "no_user": "Username missing", "no_user_msg": "Enter your TikTok username.",
        "cfg_missing": "No {name}: starting from defaults (Save to create it).",
        "cfg_invalid": "Invalid config", "cfg_loaded": "Config loaded from {path}",
        "cfg_saved": "Config saved to {path}", "saved": "Saved",
        "confirm_title": "Confirm REAL DELETION",
        "confirm_msg": "Dry run is off: videos will REALLY be deleted.\n\nTikTok has no trash bin. Continue?",
        "save_failed": "Save failed", "start_msg": "Starting — @{user} (dry_run={dry})",
        "finished": "Done.", "error": "Error", "stop_req": "Stop requested, finishing the current step…",
        "close_title": "Close?", "close_msg": "A run is in progress. Close anyway?",
        "deleted_none": "No deleted.csv yet.", "deleted_title": "deleted.csv — {n} deleted",
        "deps_ok": "Dependencies OK.", "deps_fail": "Some dependencies failed to install: see the log.",
    },
}


def system_lang() -> str:
    try:
        import ctypes
        if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x10:  # LANG_ITALIAN
            return "it"
    except Exception:
        pass
    name = (locale.getlocale()[0] or "").lower()
    return "it" if name.startswith(("it", "italian")) else "en"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data: dict):
    try:
        SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def normalize_handle(raw: str) -> str:
    try:
        from sweeper import normalize_handle as norm
    except ImportError:  # playwright non ancora installato
        return (raw or "").strip().lstrip("@")
    return norm(raw)

# ---------------------------------------------------------------- colori

PALETTES = {
    "light": {"bg": "#f4f5f7", "fg": "#1d1f23", "field": "#ffffff", "muted": "#6b7280", "border": "#c9ced6",
              "accent": "#e8335a", "accent_fg": "#ffffff", "ok": "#15803d", "warn": "#c62828",
              "sel": "#fbd3dc", "hover": "#e6e8ec"},
    "dark": {"bg": "#1e1f22", "fg": "#e6e6e6", "field": "#2b2d31", "muted": "#9aa0a6", "border": "#43464d",
             "accent": "#ff4d6d", "accent_fg": "#ffffff", "ok": "#4ade80", "warn": "#ff6b6b",
             "sel": "#5a2a35", "hover": "#35383e"},
}


def system_theme() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return "light" if winreg.QueryValueEx(k, "AppsUseLightTheme")[0] else "dark"
    except Exception:
        return "light"


def dark_title_bar(win: tk.Misc, dark: bool):
    """Barra del titolo scura su Windows 10/11 (ignorato altrove)."""
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nuovo, vecchio)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:
        pass


class QueueWriter:
    """File-like che redirige print() verso una Queue (thread-safe)."""
    def __init__(self, q: queue.Queue):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(s)

    def flush(self):
        pass


class DateRangeDialog(tk.Toplevel):
    def __init__(self, app: "ToksweepGUI", initial_from="", initial_to=""):
        super().__init__(app)
        self.app = app
        t, pal = app.t, app.pal
        self.title(t("range_title"))
        self.resizable(False, False)
        self.configure(bg=pal["bg"])
        self.result = None
        self.transient(app)

        frm = ttk.Frame(self, padding=14)
        frm.pack()
        ttk.Label(frm, text=t("from")).grid(row=0, column=0, padx=(0, 10), pady=6, sticky="w")
        ttk.Label(frm, text=t("to")).grid(row=1, column=0, padx=(0, 10), pady=6, sticky="w")
        self.e_from = self._date_field(frm, initial_from)
        self.e_to = self._date_field(frm, initial_to)
        self.e_from.grid(row=0, column=1, pady=6)
        self.e_to.grid(row=1, column=1, pady=6)

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text=t("ok"), style="Accent.TButton", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text=t("cancel"), command=self.destroy).pack(side="left", padx=4)
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())

        dark_title_bar(self, app.theme == "dark")
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.e_from.focus_set()

    def _date_field(self, parent, initial: str):
        """Campo data con calendario a tendina (tkcalendar); se manca, un Entry semplice."""
        pal = self.app.pal
        try:
            from tkcalendar import DateEntry
            d = date.fromisoformat(initial) if initial else date.today()
            w = DateEntry(
                parent, width=14, date_pattern="yyyy-mm-dd", firstweekday="monday",
                locale="it_IT" if self.app.lang == "it" else "en_US",
                year=d.year, month=d.month, day=d.day,
                background=pal["accent"], foreground=pal["accent_fg"], bordercolor=pal["border"],
                headersbackground=pal["bg"], headersforeground=pal["fg"],
                normalbackground=pal["field"], normalforeground=pal["fg"],
                weekendbackground=pal["field"], weekendforeground=pal["fg"],
                othermonthbackground=pal["bg"], othermonthforeground=pal["muted"],
                othermonthwebackground=pal["bg"], othermonthweforeground=pal["muted"],
                selectbackground=pal["accent"], selectforeground=pal["accent_fg"],
                tooltipbackground=pal["field"], tooltipforeground=pal["fg"],
            )
            return w
        except Exception:
            e = ttk.Entry(parent, width=16)
            e.insert(0, initial or date.today().isoformat())
            return e

    def _ok(self):
        t = self.app.t
        f, to = self.e_from.get().strip(), self.e_to.get().strip()
        try:
            date.fromisoformat(f)
            date.fromisoformat(to)
        except ValueError:
            messagebox.showerror(t("bad_dates"), t("bad_dates_fmt"), parent=self)
            return
        if f > to:
            messagebox.showerror(t("bad_dates"), t("bad_dates_order"), parent=self)
            return
        self.result = {"from": f, "to": to}
        self.destroy()


class ToksweepGUI(tk.Tk):
    def __init__(self, config_path: Path, lang: str | None = None, theme: str | None = None):
        super().__init__()
        self.title(f"toksweep {__version__} — TikTok External Admin Console")
        self.resizable(False, False)

        self.settings = load_settings()
        self.lang = lang or self.settings.get("lang") or system_lang()
        if self.lang not in STRINGS:
            self.lang = "en"
        self.forced_theme = theme  # None = segui Windows
        self.theme = theme or system_theme()
        self.pal = PALETTES[self.theme]
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.config_path = Path(config_path)
        self.log_queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.running = False
        self.deps_ready = False
        self.deps_checking = False
        self.bot = None  # Sweeper instance, per stop immediato
        self._cr_pending = False
        self.loaded_cfg: dict = copy.deepcopy(DEFAULT_CFG)  # per non perdere chiavi che la GUI non gestisce
        self.ranges: list[dict] = []
        self.status_key = "st_idle"

        self._make_vars()
        self._set_icon()
        self._apply_theme()
        self._build_widgets()
        # dimensione fissa: quella richiesta dal layout + margine, uguale per tutte le lingue
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth() + 40}x{self.winfo_reqheight()}")
        self.load_config()
        self.after(150, self._drain_log)
        self.after(2000, self._watch_theme)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._check_deps()

    def t(self, key: str, **kw) -> str:
        s = STRINGS[self.lang].get(key) or STRINGS["en"].get(key, key)
        return s.format(**kw) if kw else s

    # ---------- stato del form (sopravvive al cambio lingua) ----------
    def _make_vars(self):
        self.var_config_path = tk.StringVar(value=str(self.config_path))
        self.var_lang = tk.StringVar(value=LANGS[self.lang])
        self.var_username = tk.StringVar()
        self.var_min_age = tk.StringVar(value="7")
        self.var_logic = tk.StringVar(value="OR")
        self.rule_vars = {k: (tk.BooleanVar(value=False), tk.StringVar(value="")) for k in RULE_KEYS}
        self.var_dry = tk.BooleanVar(value=True)
        self.var_maxdel = tk.StringVar(value="50")
        self.var_delay = tk.StringVar(value="3")
        self.var_headless = tk.BooleanVar(value=False)
        self.var_profile = tk.StringVar(value="browser_profile")
        self.var_status = tk.StringVar()

    def _set_icon(self):
        self._logo = None
        try:
            self._icon = tk.PhotoImage(file=str(RES_DIR / "assets" / "logo.png"))
            self.iconphoto(True, self._icon)
            self._logo = tk.PhotoImage(file=str(RES_DIR / "assets" / "logo-32.png"))
        except Exception:
            pass

    # ---------- tema ----------
    def _apply_theme(self):
        p = self.pal
        s = self.style
        self.configure(bg=p["bg"])
        s.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"], troughcolor=p["field"],
                    selectbackground=p["accent"], selectforeground=p["accent_fg"], insertcolor=p["fg"],
                    focuscolor=p["accent"], arrowcolor=p["fg"])
        s.configure("TFrame", background=p["bg"])
        s.configure("TLabel", background=p["bg"], foreground=p["fg"])
        s.configure("Muted.TLabel", foreground=p["muted"])
        s.configure("Ok.TLabel", foreground=p["ok"], font=("Segoe UI", 9, "bold"))
        s.configure("Warn.TLabel", foreground=p["warn"], font=("Segoe UI", 9, "bold"))
        s.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        s.configure("Brand.TLabel", font=("Segoe UI", 14, "bold"), foreground=p["accent"])
        s.configure("TLabelframe", background=p["bg"], bordercolor=p["border"])
        s.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"], font=("Segoe UI", 9, "bold"))
        s.configure("TButton", background=p["field"], foreground=p["fg"], bordercolor=p["border"], padding=(8, 3))
        s.map("TButton", background=[("disabled", p["bg"]), ("pressed", p["sel"]), ("active", p["hover"])],
              foreground=[("disabled", p["muted"])])
        s.configure("Accent.TButton", background=p["accent"], foreground=p["accent_fg"], bordercolor=p["accent"])
        s.map("Accent.TButton", background=[("disabled", p["border"]), ("pressed", p["warn"]), ("active", p["warn"])],
              foreground=[("disabled", p["muted"])])
        for w in ("TEntry", "TSpinbox", "TCombobox"):
            s.configure(w, fieldbackground=p["field"], foreground=p["fg"], insertcolor=p["fg"],
                        bordercolor=p["border"], arrowcolor=p["fg"], background=p["field"])
            s.map(w, fieldbackground=[("disabled", p["bg"]), ("readonly", p["field"])],
                  foreground=[("disabled", p["muted"])],
                  selectbackground=[("readonly", p["field"])], selectforeground=[("readonly", p["fg"])])
        s.configure("TCheckbutton", background=p["bg"], foreground=p["fg"],
                    indicatorbackground=p["field"], indicatorforeground=p["accent"])
        s.map("TCheckbutton", background=[("active", p["bg"])],
              indicatorbackground=[("selected", p["field"]), ("active", p["hover"])])
        s.configure("Treeview", background=p["field"], fieldbackground=p["field"], foreground=p["fg"])
        s.configure("Treeview.Heading", background=p["bg"], foreground=p["fg"])
        s.map("Treeview", background=[("selected", p["accent"])], foreground=[("selected", p["accent_fg"])])
        for sb in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            s.configure(sb, background=p["field"], troughcolor=p["bg"], arrowcolor=p["fg"])
        # tendina delle combobox (widget tk classici)
        self.option_add("*TCombobox*Listbox.background", p["field"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", p["accent_fg"])
        self._theme_tk_widgets(self)
        dark_title_bar(self, self.theme == "dark")

    def _theme_tk_widgets(self, root: tk.Misc):
        p = self.pal
        for w in root.winfo_children():
            if isinstance(w, (tk.Text, tk.Listbox)):
                w.configure(bg=p["field"], fg=p["fg"], selectbackground=p["accent"],
                            selectforeground=p["accent_fg"], highlightthickness=1,
                            highlightbackground=p["border"], highlightcolor=p["accent"], relief="flat")
                if isinstance(w, tk.Text):
                    w.configure(insertbackground=p["fg"])
            elif isinstance(w, tk.Toplevel):
                w.configure(bg=p["bg"])
                dark_title_bar(w, self.theme == "dark")
            self._theme_tk_widgets(w)

    def _watch_theme(self):
        if not self.forced_theme:
            th = system_theme()
            if th != self.theme:
                self.theme, self.pal = th, PALETTES[th]
                self._apply_theme()
        self.after(2000, self._watch_theme)

    # ---------- layout ----------
    def _build_widgets(self):
        t = self.t
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        self.root_frame = root

        # Barra superiore
        top = ttk.Frame(root)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        brand = ttk.Frame(top)
        brand.pack(side="left", padx=(0, 16))
        if self._logo:
            ttk.Label(brand, image=self._logo).pack(side="left", padx=(0, 6))
        ttk.Label(brand, text="toksweep", style="Brand.TLabel").pack(side="left")
        ttk.Label(brand, text=f" v{__version__}", style="Muted.TLabel").pack(side="left", pady=(4, 0))
        ttk.Label(top, text=t("config")).pack(side="left")
        ttk.Entry(top, textvariable=self.var_config_path, width=44).pack(side="left", padx=6)
        ttk.Button(top, text=t("browse"), command=self._browse_config).pack(side="left", padx=2)
        ttk.Button(top, text=t("reload"), command=self.load_config).pack(side="left", padx=2)
        ttk.Button(top, text=t("save"), command=self.save_config).pack(side="left", padx=2)
        cb = ttk.Combobox(top, textvariable=self.var_lang, values=list(LANGS.values()), width=9, state="readonly")
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", self._on_lang_selected)
        ttk.Label(top, text=t("language")).pack(side="right", padx=(12, 6))

        left = ttk.Frame(root, width=430)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew")

        # --- Account ---
        acc = ttk.LabelFrame(left, text=t("account"), padding=8)
        acc.pack(fill="x", pady=(0, 6))
        ttk.Label(acc, text=t("username")).grid(row=0, column=0, sticky="w")
        e_user = ttk.Entry(acc, textvariable=self.var_username, width=30)
        e_user.grid(row=0, column=1, padx=6, sticky="ew")
        e_user.bind("<FocusOut>", lambda _e: self.var_username.set(normalize_handle(self.var_username.get())))
        ttk.Label(acc, text=t("username_hint"), style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w")
        acc.columnconfigure(1, weight=1)

        # --- Regole ---
        rules = ttk.LabelFrame(left, text=t("rules"), padding=8)
        rules.pack(fill="x", pady=6)
        ttk.Label(rules, text=t("protect_days")).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(rules, from_=0, to=3650, textvariable=self.var_min_age, width=8).grid(
            row=0, column=1, sticky="w", padx=6)
        ttk.Label(rules, text=t("logic")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(rules, textvariable=self.var_logic, values=["OR", "AND"], width=6, state="readonly").grid(
            row=1, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(rules, text=t("logic_hint"), style="Muted.TLabel").grid(row=1, column=2, sticky="w")
        ttk.Label(rules, text=t("delete_if")).grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 2))
        self.rule_entries = {}
        for i, key in enumerate(RULE_KEYS, start=3):
            on, val = self.rule_vars[key]
            ttk.Checkbutton(rules, text=t(key), variable=on, command=self._refresh_rule_entries).grid(
                row=i, column=0, sticky="w")
            e = ttk.Entry(rules, textvariable=val, width=12)
            e.grid(row=i, column=1, sticky="w", padx=6, pady=1)
            self.rule_entries[key] = e

        # --- Intervalli date ---
        dr = ttk.LabelFrame(left, text=t("ranges"), padding=8)
        dr.pack(fill="x", pady=6)
        self.lst_ranges = tk.Listbox(dr, height=4, font=("Consolas", 9), activestyle="none")
        self.lst_ranges.pack(fill="x")
        self.lst_ranges.bind("<Double-Button-1>", lambda _e: self._edit_range())
        br = ttk.Frame(dr)
        br.pack(fill="x", pady=(6, 0))
        ttk.Button(br, text=t("add"), command=self._add_range).pack(side="left", padx=(0, 4))
        ttk.Button(br, text=t("edit"), command=self._edit_range).pack(side="left", padx=4)
        ttk.Button(br, text=t("remove"), command=self._del_range).pack(side="left", padx=4)

        # --- Opzioni ---
        opts = ttk.LabelFrame(left, text=t("options"), padding=8)
        opts.pack(fill="x", pady=6)
        ttk.Checkbutton(opts, text=t("dry_run"), variable=self.var_dry, command=self._refresh_dry_warning).grid(
            row=0, column=0, columnspan=3, sticky="w")
        self.lbl_dry_warn = ttk.Label(opts, text="")
        self.lbl_dry_warn.grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(opts, text=t("max_deletes")).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Spinbox(opts, from_=1, to=10000, textvariable=self.var_maxdel, width=10).grid(row=2, column=1, sticky="w")
        ttk.Label(opts, text=t("delay")).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Spinbox(opts, from_=0, to=120, increment=0.5, textvariable=self.var_delay, width=10).grid(
            row=3, column=1, sticky="w")
        ttk.Checkbutton(opts, text=t("headless"), variable=self.var_headless).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(opts, text=t("profile")).grid(row=5, column=0, sticky="w", pady=2)
        ttk.Entry(opts, textvariable=self.var_profile, width=24).grid(row=5, column=1, sticky="ew", padx=(0, 4))
        ttk.Button(opts, text="…", width=3, command=self._browse_profile).grid(row=5, column=2)
        opts.columnconfigure(1, weight=1)

        # --- Azioni ---
        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=(8, 0))
        self.btn_start = ttk.Button(actions, text=t("start"), style="Accent.TButton", command=self.start_run)
        self.btn_start.pack(side="left", padx=(0, 4), fill="x", expand=True)
        self.btn_stop = ttk.Button(actions, text=t("stop"), command=self.stop_run)
        self.btn_stop.pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(actions, text="deleted.csv", command=self._open_deleted).pack(side="left", padx=(4, 0))

        # --- Destra: stato + log ---
        status = ttk.Frame(right)
        status.pack(fill="x")
        ttk.Label(status, text=t("status")).pack(side="left")
        ttk.Label(status, textvariable=self.var_status, style="Status.TLabel").pack(side="left", padx=6)
        ttk.Button(status, text=t("clear_log"), command=lambda: self.txt_log.delete("1.0", "end")).pack(side="right")
        ttk.Button(status, text=t("save_log"), command=self._save_log).pack(side="right", padx=4)

        logbox = ttk.Frame(right)
        logbox.pack(fill="both", expand=True, pady=6)
        # niente a capo: le righe dello sweeper sono una tabella
        self.txt_log = tk.Text(logbox, wrap="none", width=96, height=35, font=("Consolas", 9), padx=6, pady=4)
        scroll = ttk.Scrollbar(logbox, command=self.txt_log.yview)
        xscroll = ttk.Scrollbar(logbox, orient="horizontal", command=self.txt_log.xview)
        self.txt_log.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.txt_log.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        logbox.rowconfigure(0, weight=1)
        logbox.columnconfigure(0, weight=1)
        ttk.Label(right, text=t("hint"), style="Muted.TLabel").pack(fill="x")

        self._refresh_list()
        self._refresh_dry_warning()
        self._refresh_rule_entries()
        self._refresh_buttons()
        self.var_status.set(t(self.status_key))
        self._theme_tk_widgets(self)

    def _on_lang_selected(self, _e=None):
        code = next(c for c, name in LANGS.items() if name == self.var_lang.get())
        if code == self.lang:
            return
        self.lang = code
        self.settings["lang"] = code
        save_settings(self.settings)
        log = self.txt_log.get("1.0", "end-1c")
        self.root_frame.destroy()
        self._build_widgets()
        self.txt_log.insert("end", log)
        self.txt_log.see("end")

    # ---------- config ----------
    def _num(self, var: tk.Variable, label_key: str, cast=int):
        raw = str(var.get()).strip().replace(",", ".")
        try:
            num = float(raw)
            if cast is int and not num.is_integer():
                raise ValueError
            return cast(num)
        except ValueError:
            raise ValueError(self.t("bad_value_for", label=self.t(label_key).rstrip(":"), value=raw))

    def _current_cfg(self) -> dict:
        delete_if = {}
        for key, (on, val) in self.rule_vars.items():
            if on.get():
                num = self._num(val, key, float)
                delete_if[key] = int(num) if num.is_integer() else num
            else:
                delete_if[key] = None
        cfg = copy.deepcopy(self.loaded_cfg)
        cfg.setdefault("account", {})["username"] = normalize_handle(self.var_username.get())
        cfg.setdefault("rules", {}).update({
            "date_ranges": list(self.ranges),
            "min_age_days": self._num(self.var_min_age, "protect_days"),
            "delete_if": delete_if,
            "logic": self.var_logic.get().upper(),
        })
        delay = self._num(self.var_delay, "delay", float)
        cfg.setdefault("options", {}).update({
            "dry_run": bool(self.var_dry.get()),
            "max_deletes_per_run": self._num(self.var_maxdel, "max_deletes"),
            "delay_between_deletes_seconds": int(delay) if delay.is_integer() else delay,
            "headless": bool(self.var_headless.get()),
            "browser_profile_dir": self.var_profile.get().strip() or "browser_profile",
        })
        cfg["options"].setdefault("locale", "en-US")
        return cfg

    def _apply_cfg(self, cfg: dict):
        self.var_username.set(normalize_handle(cfg.get("account", {}).get("username", "")))
        rules = cfg.get("rules", {})
        self.var_min_age.set(str(rules.get("min_age_days", 7)))
        self.var_logic.set(str(rules.get("logic", "OR")).upper())
        delete_if = rules.get("delete_if", {}) or {}
        for key, (on, val) in self.rule_vars.items():
            lim = delete_if.get(key, None)
            on.set(lim is not None)
            val.set("" if lim is None else str(lim))
        self.ranges = [{"from": str(r.get("from")), "to": str(r.get("to"))} for r in rules.get("date_ranges") or []]
        opts = cfg.get("options", {})
        self.var_dry.set(bool(opts.get("dry_run", True)))
        self.var_maxdel.set(str(opts.get("max_deletes_per_run", 50)))
        self.var_delay.set(str(opts.get("delay_between_deletes_seconds", 3)))
        self.var_headless.set(bool(opts.get("headless", False)))
        self.var_profile.set(str(opts.get("browser_profile_dir", "browser_profile")))
        self._refresh_list()
        self._refresh_dry_warning()
        self._refresh_rule_entries()

    def _cfg_path(self) -> Path:
        return Path(self.var_config_path.get().strip() or str(DEFAULT_CONFIG))

    def load_config(self):
        p = self._cfg_path()
        self.config_path = p
        try:
            cfg = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            cfg = copy.deepcopy(DEFAULT_CFG)
            self.log(f"[gui] {self.t('cfg_missing', name=p.name)}\n")
        except Exception as e:
            messagebox.showerror(self.t("cfg_invalid"), str(e))
            return
        else:
            self.log(f"[gui] {self.t('cfg_loaded', path=p)}\n")
        self.loaded_cfg = cfg
        self._apply_cfg(cfg)

    def _write_cfg(self, cfg: dict) -> Path:
        p = self._cfg_path()
        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        self.config_path = p
        self.loaded_cfg = cfg
        return p

    def _validated_cfg(self) -> dict | None:
        try:
            cfg = self._current_cfg()
        except ValueError as e:
            messagebox.showerror(self.t("bad_value"), str(e))
            return None
        if not cfg["account"]["username"]:
            messagebox.showerror(self.t("no_user"), self.t("no_user_msg"))
            return None
        self.var_username.set(cfg["account"]["username"])
        return cfg

    def save_config(self):
        cfg = self._validated_cfg()
        if cfg is None:
            return
        try:
            p = self._write_cfg(cfg)
        except Exception as e:
            messagebox.showerror(self.t("save_failed"), str(e))
            return
        self.log(f"[gui] {self.t('cfg_saved', path=p)}\n")
        messagebox.showinfo(self.t("saved"), self.t("cfg_saved", path=p))

    # ---------- piccoli helper UI ----------
    def _refresh_dry_warning(self):
        if self.var_dry.get():
            self.lbl_dry_warn.config(text=self.t("dry_safe"), style="Ok.TLabel")
        else:
            self.lbl_dry_warn.config(text=self.t("dry_real"), style="Warn.TLabel")

    def _refresh_rule_entries(self):
        for key, e in self.rule_entries.items():
            e.state(["!disabled"] if self.rule_vars[key][0].get() else ["disabled"])

    def _refresh_list(self):
        self.lst_ranges.delete(0, "end")
        for r in self.ranges:
            self.lst_ranges.insert("end", f"  {r['from']}  →  {r['to']}")

    def _refresh_buttons(self):
        can_start = not self.running and self.deps_ready
        self.btn_start.state(["!disabled"] if can_start else ["disabled"])
        self.btn_stop.state(["!disabled"] if self.running else ["disabled"])

    def _set_status(self, key: str):
        self.status_key = key
        self.var_status.set(self.t(key))

    def _browse_config(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("*", "*.*")], initialdir=str(BASE_DIR))
        if f:
            self.var_config_path.set(f)
            self.load_config()

    def _browse_profile(self):
        d = filedialog.askdirectory(initialdir=str(BASE_DIR))
        if d:
            self.var_profile.set(d)

    def _add_range(self):
        last = self.ranges[-1]["to"] if self.ranges else ""
        d = DateRangeDialog(self, last, date.today().isoformat())
        self.wait_window(d)
        if d.result:
            self.ranges.append(d.result)
            self.ranges.sort(key=lambda r: r["from"])
            self._refresh_list()

    def _edit_range(self):
        sel = self.lst_ranges.curselection()
        if not sel:
            return
        r = self.ranges[sel[0]]
        d = DateRangeDialog(self, r["from"], r["to"])
        self.wait_window(d)
        if d.result:
            self.ranges[sel[0]] = d.result
            self.ranges.sort(key=lambda x: x["from"])
            self._refresh_list()

    def _del_range(self):
        for i in reversed(self.lst_ranges.curselection()):
            del self.ranges[i]
        self._refresh_list()

    def _open_deleted(self):
        if not DELETED_LOG.exists():
            messagebox.showinfo("deleted.csv", self.t("deleted_none"))
            return
        try:
            with DELETED_LOG.open(encoding="utf-8") as f:
                rows = list(csv.reader(f))
            win = tk.Toplevel(self)
            win.title(self.t("deleted_title", n=len(rows) - 1))
            win.geometry("760x420")
            win.resizable(False, False)
            frame = ttk.Frame(win, padding=6)
            frame.pack(fill="both", expand=True)
            tree = ttk.Treeview(frame, columns=rows[0], show="headings")
            sb = ttk.Scrollbar(frame, command=tree.yview)
            tree.configure(yscrollcommand=sb.set)
            for c in rows[0]:
                tree.heading(c, text=c)
                tree.column(c, width=105)
            for r in rows[1:][-500:]:
                tree.insert("", "end", values=r)
            tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            self._theme_tk_widgets(self)
        except Exception as e:
            messagebox.showerror(self.t("error"), str(e))

    def _save_log(self):
        f = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if f:
            Path(f).write_text(self.txt_log.get("1.0", "end"), encoding="utf-8")

    # ---------- log ----------
    def log(self, s: str):
        # '\r' = riscrivi la riga corrente (contatori di avanzamento dello sweeper);
        #   la riga viene sostituita solo quando arriva altro testo sulla stessa riga
        for i, chunk in enumerate(s.split("\r")):
            if i:
                self._cr_pending = True
            if not chunk:
                continue
            if self._cr_pending and not chunk.startswith("\n"):
                self.txt_log.delete("end-1c linestart", "end-1c")
            self._cr_pending = False
            self.txt_log.insert("end", chunk)
        self.txt_log.see("end")

    def _drain_log(self):
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is RUN_DONE:
                    self._run_finished()
                elif item is DEPS_DONE:
                    self._deps_finished()
                else:
                    self.log(item)
        except queue.Empty:
            pass
        self.after(150, self._drain_log)

    # ---------- dipendenze ----------
    def _check_deps(self):
        self.deps_checking = True
        self._set_status("st_deps")
        self._refresh_buttons()

        def worker():
            try:
                self.deps_ok = deps.ensure_all(log=self.log_queue.put)
            except Exception as e:
                self.log_queue.put(f"[deps] {e}\n")
                self.deps_ok = False
            self.log_queue.put(DEPS_DONE)

        threading.Thread(target=worker, daemon=True).start()

    def _deps_finished(self):
        self.deps_checking = False
        self.deps_ready = self.deps_ok
        if self.deps_ready:
            self.log(f"[gui] {self.t('deps_ok')}\n")
            self._set_status("st_idle")
        else:
            self._set_status("st_deps_fail")
            messagebox.showerror(self.t("error"), self.t("deps_fail"))
        self._refresh_buttons()

    # ---------- run ----------
    def start_run(self):
        if self.running or not self.deps_ready:
            return
        cfg = self._validated_cfg()
        if cfg is None:
            return
        if not cfg["options"]["dry_run"]:
            if not messagebox.askyesno(self.t("confirm_title"), self.t("confirm_msg"), icon="warning"):
                return
        try:
            self._write_cfg(cfg)  # salva config corrente prima di partire
        except Exception as e:
            messagebox.showerror(self.t("save_failed"), str(e))
            return

        STOP_FILE.unlink(missing_ok=True)
        self.running = True
        self._refresh_buttons()
        self._set_status("st_running")
        self.log(f"\n{'=' * 60}\n[gui] {self.t('start_msg', user=cfg['account']['username'], dry=cfg['options']['dry_run'])}"
                 f"\n{'=' * 60}\n")
        finished, error = self.t("finished"), self.t("error").upper()

        def runner():
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = QueueWriter(self.log_queue)
            try:
                from sweeper import Sweeper

                async def _run():
                    self.bot = Sweeper(cfg)
                    await self.bot.start()
                    try:
                        await self.bot.run()
                    finally:
                        await self.bot.close()
                        self.bot = None
                asyncio.run(_run())
                self.log_queue.put(f"\n[gui] {finished}\n")
            except Exception as e:
                import traceback
                self.log_queue.put(f"\n[gui] {error}: {e}\n{traceback.format_exc()}\n")
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                self.log_queue.put(RUN_DONE)  # tkinter non è thread-safe: niente after() dal worker

        self.worker = threading.Thread(target=runner, daemon=True)
        self.worker.start()

    def _run_finished(self):
        self.running = False
        self._refresh_buttons()
        self._set_status("st_idle")

    def stop_run(self):
        # il meccanismo ufficiale dello sweeper: file STOP
        try:
            STOP_FILE.write_text("stop", encoding="utf-8")
        except Exception:
            pass
        # + stop immediato se abbiamo l'istanza
        try:
            bot = self.bot
            if bot is not None and bot._loop is not None:
                bot._loop.call_soon_threadsafe(bot._stop.set)
        except Exception:
            pass
        self.log(f"\n[gui] {self.t('stop_req')}\n")
        self._set_status("st_stopping")

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno(self.t("close_title"), self.t("close_msg")):
                return
            try:
                STOP_FILE.write_text("stop", encoding="utf-8")
            except Exception:
                pass
        self.destroy()


def selftest() -> int:
    """`toksweep.exe --selftest`: dipendenze, calendario e avvio del browser, risultato in selftest.txt."""
    lines = [f"toksweep {__version__}  frozen={FROZEN}  python={sys.version.split()[0]}"]
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            lines.append(f"[ok]   {name}: {fn() or ''}")
        except Exception as e:
            ok = False
            lines.append(f"[FAIL] {name}: {type(e).__name__}: {e}")

    check("dependencies", lambda: "ready" if deps.ensure_all(log=lambda s: lines.append("       " + s.strip()))
          else (_ for _ in ()).throw(RuntimeError("see above")))

    def calendar():
        from babel.dates import format_date
        import tkcalendar  # noqa: F401
        return f"{format_date(date(2026, 8, 8), locale='it_IT')} / {format_date(date(2026, 8, 8), locale='en_US')}"
    check("calendar", calendar)

    def browser():
        async def go():
            from playwright.async_api import async_playwright
            async with async_playwright() as pw:
                b = await pw.chromium.launch(headless=True)
                v = b.version
                await b.close()
                return f"chromium {v}"
        return asyncio.run(go())
    check("browser", browser)
    check("username", lambda: normalize_handle(" https://www.tiktok.com/@Some_User?lang=it "))

    lines.append("RESULT: " + ("OK" if ok else "FAILED"))
    (BASE_DIR / "selftest.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if sys.stdout:  # niente console nell'exe; e la console di Windows può non reggere l'Unicode
        sys.stdout.buffer.write(("\n".join(lines) + "\n").encode(sys.stdout.encoding or "utf-8", "replace"))
        sys.stdout.flush()
    return 0 if ok else 1


def main():
    os.chdir(BASE_DIR)  # sweeper.py usa percorsi relativi (STOP, deleted.csv, debug/)
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG
    try:  # testo nitido su schermi con scaling
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = ToksweepGUI(cfg_path)
    app.mainloop()


if __name__ == "__main__":
    main()
