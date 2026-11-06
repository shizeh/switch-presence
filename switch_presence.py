"""
Switch Presence
Affiche le jeu auquel tu joues sur Nintendo Switch / Switch 2 sur ton profil Discord.

Créé par Baptiste Shizeh.
Projet de fan, non affilié à Nintendo ni à Discord.
"""
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import unicodedata
import webbrowser
from tkinter import filedialog, messagebox, ttk

from pypresence import Presence
from pypresence.exceptions import DiscordNotFound, InvalidID
from pypresence.types import ActivityType

# Windows : affichage net et fenêtre correctement placée sur les écrans mis à l'échelle
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# ----------------------------------------------------------------------------
# Identité du logiciel (modifie ces valeurs pour personnaliser l'appli)
# ----------------------------------------------------------------------------
APP_NAME = "Switch Presence"
APP_VERSION = "1.0.0"
APP_AUTHOR = "Baptiste Shizeh"
CONTACT_DISCORD = "Shizeh"   # pseudo Discord affiché dans l'aide
GITHUB_URL = "https://github.com/shizeh/switch-presence"
# Bouton affiché sous l'activité (Discord : 32 caractères maximum). Il mène vers GITHUB_URL.
BUTTON_LABEL = "Get this status"
# Image affichée quand un jeu n'a pas de jaquette (à uploader dans les Art Assets sous ce nom).
DEFAULT_COVER = "default_cover"
# Liste de jeux en ligne : modifie games.json sur GitHub, tout le monde la reçoit au prochain lancement.
REMOTE_GAMES_URL = "https://raw.githubusercontent.com/shizeh/switch-presence/main/games.json"

# Application ID Discord embarqué. C'est un identifiant public (pas un secret).
# Si tu le remplis ici, les utilisateurs n'ont rien à configurer.
# S'il est vide, l'appli le demande au premier lancement.
DEFAULT_CLIENT_ID = "1568268274947457074"

# Consoles disponibles : clé -> (nom affiché, clé de l'icône dans les Art Assets)
CONSOLES = {
    "switch": ("Nintendo Switch", "badge_switch1"),
    "switch2": ("Nintendo Switch 2", "badge_switch2"),
}

# Jeux de secours (utilisés hors-ligne). La liste complète vient de games.json sur GitHub.
# Format : (nom affiché, clé de cover dans les Art Assets Discord). Uniquement des jeux dont la cover est uploadée.
BUILTIN_GAMES = [
    ("The Legend of Zelda: Ocarina of Time", "zelda_ocarina_of_time"),
    ("Nintendo Switch Sports Resort", "switch_sports_resort"),
    ("Splatoon Raiders", "splatoon_raiders"),
    ("Mario Kart World", "mario_kart_world"),
    ("Mario Kart 8 Deluxe", "mario_kart_8_deluxe"),
    ("FINAL FANTASY RESONANCE", "final_fantasy_resonance"),
    ("Donkey Kong Bananza", "donkey_kong_bananza"),
    ("Tomodachi Life: Living the Dream", "tomodachi_life"),
    ("Splatoon 3", "splatoon_3"),
    ("Pokémon Pokopia", "pokemon_pokopia"),
]

# ----------------------------------------------------------------------------
# Thèmes
# ----------------------------------------------------------------------------
THEMES = {
    "dark": {
        "bg": "#1e1f26", "card": "#2a2c36", "fg": "#f2f3f7", "muted": "#9a9db0",
        "field": "#2a2c36", "border": "#3a3d4b", "accent": "#e60012", "accent_fg": "#ffffff",
        "accent_hover": "#ff2335", "select": "#3b3e50",
    },
    "light": {
        "bg": "#f4f5f8", "card": "#ffffff", "fg": "#1d1e24", "muted": "#6b6e80",
        "field": "#ffffff", "border": "#d5d7e0", "accent": "#e60012", "accent_fg": "#ffffff",
        "accent_hover": "#c40010", "select": "#e4e6f0",
    },
}
FONT = "Segoe UI"


# ----------------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------------
def resource_path(relative):
    """Chemin d'un fichier embarqué, que l'appli tourne en .py ou en .exe (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "_", strip_accents(name).lower())
    return s.strip("_")[:30] or "game"


def config_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    folder = os.path.join(base, "SwitchPresence")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def load_config():
    data = {}
    try:
        with open(config_path(), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    defaults = {
        "client_id": "",        # remplace DEFAULT_CLIENT_ID si renseigné
        "console": "switch2",
        "theme": "dark",
        "language": "",         # vide = langue du système
        "show_timer": True,
        "show_console": True,   # nom de la console sous le jeu
        "show_badge": True,     # petit badge de la console sur la jaquette
        "show_button": True,    # bouton « Get Switch Presence » sous l'activité
        "custom": [],           # jeux ajoutés [{name, cover}]
        "overrides": {},        # covers modifiées {nom: cover}
        "hidden": [],           # jeux retirés de la liste
        "favorites": [],
        "remote_games": [],     # dernière liste en ligne reçue (cache hors-ligne)
    }
    for k, v in defaults.items():
        data.setdefault(k, v)
    return data


def save_config(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def parse_version(text):
    nums = [int(x) for x in re.findall(r"\d+", str(text))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def clean_games(raw):
    """Valide une liste de jeux venant d'un fichier ou d'internet (clé d'asset valide ou lien https)."""
    games = []
    for g in (raw or [])[:1000]:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name", "")).strip()[:128]
        cover = str(g.get("cover", "")).strip()[:300]
        if not name:
            continue
        if cover and not (re.fullmatch(r"[a-z0-9_]{1,32}", cover) or cover.startswith("https://")):
            cover = ""
        games.append({"name": name, "cover": cover})
    return games


def load_bundled_games():
    """Liste de jeux embarquée dans l'appli (games.json livré avec le programme)."""
    try:
        with open(resource_path("games.json"), encoding="utf-8") as f:
            return clean_games(json.load(f).get("games", []))
    except Exception:
        return []


def fetch_remote_list():
    """Télécharge games.json (liste de jeux + dernière version). Lève une exception si hors-ligne."""
    import urllib.request
    req = urllib.request.Request(REMOTE_GAMES_URL, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=6) as r:
        data = json.loads(r.read(1_000_000).decode("utf-8"))
    return clean_games(data.get("games", [])), str(data.get("latest_version", "")).strip()


def ui_scale(widget):
    """Facteur d'agrandissement de l'écran (1.0 = 100 %, 1.5 = 150 %...)."""
    try:
        return max(1.0, widget.winfo_fpixels("1i") / 96.0)
    except Exception:
        return 1.0


def fmt_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ----------------------------------------------------------------------------
# Traductions : un fichier .json par langue dans le dossier locales/
# Pour ajouter une langue, copie locales/en.json en locales/xx.json, traduis les textes
# et change la ligne "_name" : la langue apparaît automatiquement dans les paramètres.
# ----------------------------------------------------------------------------
# Langue au premier lancement : "en" pour tout le monde. Mets AUTO_DETECT_LANGUAGE = True pour
# prendre la langue de Windows à la place (français, espagnol ou anglais).
DEFAULT_LANGUAGE = "en"
AUTO_DETECT_LANGUAGE = False
_STRINGS, _FALLBACK = {}, {}


def _read_locale(code):
    try:
        with open(resource_path(os.path.join("locales", code + ".json")), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def available_languages():
    """{code: nom affiché} pour chaque fichier locales/xx.json."""
    langs = {}
    try:
        for fn in sorted(os.listdir(resource_path("locales"))):
            if fn.endswith(".json"):
                langs[fn[:-5]] = str(_read_locale(fn[:-5]).get("_name", fn[:-5]))
    except Exception:
        pass
    return langs or {"en": "English"}


def detect_language():
    """Langue du système si on la propose, sinon l'anglais."""
    code = ""
    try:
        if sys.platform == "win32":
            import ctypes
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF
            code = {0x0C: "fr", 0x0A: "es", 0x09: "en"}.get(primary, "")
        else:
            code = (os.environ.get("LC_ALL") or os.environ.get("LANG") or "")[:2].lower()
    except Exception:
        pass
    return code if code in available_languages() else "en"


def load_language(code):
    global _STRINGS, _FALLBACK
    _FALLBACK = _read_locale("en")
    _STRINGS = _FALLBACK if code == "en" else _read_locale(code)


def tr(key, **kw):
    """Texte traduit (anglais si la clé manque dans la langue choisie)."""
    text = _STRINGS.get(key) or _FALLBACK.get(key) or key
    if not kw:
        return text
    try:
        return text.format(**kw)
    except (KeyError, IndexError, ValueError):
        return text


# ----------------------------------------------------------------------------
# Widgets maison
# ----------------------------------------------------------------------------
class Segmented(tk.Frame):
    """Sélecteur à deux (ou plus) choix, façon interrupteur."""

    def __init__(self, parent, options, value, command):
        super().__init__(parent, bd=0, highlightthickness=1)
        self.options = options          # liste de (clé, texte)
        self.value = value
        self.command = command
        self.labels = {}
        for i, (key, text) in enumerate(options):
            lbl = tk.Label(self, text=text, font=(FONT, 10, "bold"), padx=16, pady=7, cursor="hand2")
            lbl.grid(row=0, column=i, sticky="ew")
            lbl.bind("<Button-1>", lambda _e, k=key: self.select(k))
            self.columnconfigure(i, weight=1, uniform="seg")
            self.labels[key] = lbl

    def select(self, key, notify=True):
        self.value = key
        self.recolor(self.theme)
        if notify:
            self.command(key)

    def recolor(self, theme):
        self.theme = theme
        self.config(bg=theme["card"], highlightbackground=theme["border"], highlightcolor=theme["border"])
        for key, lbl in self.labels.items():
            if key == self.value:
                lbl.config(bg=theme["accent"], fg=theme["accent_fg"])
            else:
                lbl.config(bg=theme["card"], fg=theme["muted"])


class PlaceholderEntry(ttk.Entry):
    def __init__(self, parent, placeholder, textvariable, **kw):
        super().__init__(parent, textvariable=textvariable, **kw)
        self.placeholder = placeholder
        self.var = textvariable
        self.showing = False
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)
        self._focus_out()

    def _focus_in(self, _e=None):
        if self.showing:
            self.showing = False
            self.var.set("")
            self.configure(style="TEntry")

    def _focus_out(self, _e=None):
        if not self.var.get():
            self.showing = True
            self.var.set(self.placeholder)
            self.configure(style="Placeholder.TEntry")

    def real_text(self):
        return "" if self.showing else self.var.get()


# ----------------------------------------------------------------------------
# Boîtes de dialogue
# ----------------------------------------------------------------------------
class BaseDialog(tk.Toplevel):
    def __init__(self, app, title, size):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.min_w, self.min_h = (int(v) for v in size.split("x"))
        self.geometry(f"{int(self.min_w * ui_scale(self))}x{int(self.min_h * ui_scale(self))}")
        self.resizable(False, False)
        self.configure(bg=app.theme["bg"])
        # Volontairement ni transient() ni grab_set() : sous Windows, ils peuvent rendre
        # la fenêtre principale invisible quand on la rouvre depuis la barre des tâches.
        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)
        self.after(20, self._front)
        self.after_idle(self._auto_fit)

    def _auto_fit(self):
        """Adapte la taille au contenu (texte plus grand sous Windows = fenêtre plus grande) et centre."""
        try:
            self.update_idletasks()
            sc = ui_scale(self)
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w = min(max(int(self.min_w * sc), self.body.winfo_reqwidth()), sw - 40)
            h = min(max(int(self.min_h * sc), self.body.winfo_reqheight()), sh - 100)
            x = self.app.winfo_rootx() + (self.app.winfo_width() - w) // 2
            y = self.app.winfo_rooty() + 20
            x = max(0, min(x, sw - w))
            y = max(0, min(y, sh - h - 60))
            self.geometry(f"{w}x{h}+{x}+{y}")
        except tk.TclError:
            pass

    def _front(self):
        try:
            self.lift()
            self.attributes("-topmost", True)
            self.focus_force()
            self.after(300, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass


class GameDialog(BaseDialog):
    """Ajouter un jeu ou modifier sa cover."""

    def __init__(self, app, title, name="", cover="", name_editable=True):
        super().__init__(app, title, "460x330")
        self.result = None
        b = self.body
        ttk.Label(b, text=tr("game_name"), style="Muted.TLabel").pack(anchor="w")
        self.name_var = tk.StringVar(value=name)
        e = ttk.Entry(b, textvariable=self.name_var, state="normal" if name_editable else "disabled")
        e.pack(fill="x", pady=(2, 12))

        ttk.Label(b, text=tr("game_cover"), style="Muted.TLabel").pack(anchor="w")
        self.cover_var = tk.StringVar(value=cover)
        ttk.Entry(b, textvariable=self.cover_var).pack(fill="x", pady=(2, 4))
        self.hint = ttk.Label(b, text="", style="Muted.TLabel", wraplength=410, justify="left")
        self.hint.pack(anchor="w", pady=(0, 14))
        self.name_var.trace_add("write", lambda *_: self._update_hint())
        self._update_hint()

        row = ttk.Frame(b)
        row.pack(side="bottom", fill="x")
        ttk.Button(row, text=tr("cancel"), style="Secondary.TButton", command=self.destroy).pack(side="right")
        ttk.Button(row, text=tr("save"), style="Accent.TButton", command=self._ok).pack(side="right", padx=8)
        if name_editable:
            e.focus_set()
        self.bind("<Return>", lambda _e: self._ok())

    def _update_hint(self):
        self.hint.config(text=tr("game_cover_hint"))

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, tr("err_need_name"), parent=self)
            return
        self.result = (name, self.cover_var.get().strip())
        self.destroy()


class ToggleRow(tk.Frame):
    """Option avec titre, explication et interrupteur (plus lisible qu'une case à cocher)."""

    def __init__(self, parent, theme, title, desc, variable, command=None):
        super().__init__(parent, bg=theme["card"], highlightthickness=1,
                         highlightbackground=theme["border"], highlightcolor=theme["border"])
        self.theme, self.var, self.command = theme, variable, command
        left = tk.Frame(self, bg=theme["card"])
        left.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=6)
        self.t = tk.Label(left, text=title, font=(FONT, 10, "bold"), bg=theme["card"], fg=theme["fg"], anchor="w")
        self.t.pack(fill="x")
        self.d = tk.Label(left, text=desc, font=(FONT, 9), bg=theme["card"], fg=theme["muted"],
                          anchor="w", justify="left", wraplength=int(450 * ui_scale(parent)))
        self.d.pack(fill="x")
        self.canvas = tk.Canvas(self, width=48, height=26, bg=theme["card"], highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="right", padx=12)
        for w in (self, left, self.t, self.d, self.canvas):
            w.bind("<Button-1>", self.toggle)
        self.draw()

    def draw(self):
        c, on = self.canvas, bool(self.var.get())
        c.delete("all")
        track = "#2ecc71" if on else self.theme["muted"]
        c.create_oval(1, 1, 25, 25, fill=track, outline=track)
        c.create_oval(23, 1, 47, 25, fill=track, outline=track)
        c.create_rectangle(13, 1, 35, 25, fill=track, outline=track)
        x = 27 if on else 4
        c.create_oval(x, 4, x + 18, 22, fill="#ffffff", outline="")

    def toggle(self, _e=None):
        self.var.set(not self.var.get())
        self.draw()
        if self.command:
            self.command()


class PresencePreview(tk.Frame):
    """Aperçu approximatif de ce que tes amis verront sur Discord."""
    BG, FG, MUTED = "#2b2d31", "#f2f3f5", "#b5bac1"

    def __init__(self, parent):
        super().__init__(parent, bg=self.BG, highlightthickness=1, highlightbackground="#4a4d55")
        tk.Label(self, text="Playing", font=(FONT, 10, "bold"), bg=self.BG, fg=self.FG,
                 anchor="w").pack(fill="x", padx=16, pady=(12, 8))
        row = tk.Frame(self, bg=self.BG)
        row.pack(fill="x", padx=16, pady=(0, 12))
        self.cover = tk.Canvas(row, width=104, height=104, bg=self.BG, highlightthickness=0)
        self.cover.pack(side="left")
        try:
            img = tk.PhotoImage(file=resource_path(os.path.join("assets", "icon.png")))
            self._img = img.subsample(max(1, img.width() // 88), max(1, img.height() // 88))
        except Exception:
            self._img = None
        col = tk.Frame(row, bg=self.BG)
        col.pack(side="left", fill="x", expand=True, padx=(16, 0))
        mk = lambda size, bold, color: tk.Label(col, font=(FONT, size, "bold" if bold else "normal"),
                                                bg=self.BG, fg=color, anchor="w", justify="left")
        self.l_name, self.l_details = mk(12, True, self.FG), mk(10, False, self.FG)
        self.l_state, self.l_time = mk(10, False, self.FG), mk(10, False, "#23a55a")
        self.btn = tk.Label(self, font=(FONT, 10, "bold"), bg="#4e5058", fg=self.FG, pady=7)

    def show(self, name, console_key, message, show_console, show_badge, show_timer, show_button):
        label = CONSOLES[console_key][0]
        c = self.cover
        c.delete("all")
        c.create_rectangle(0, 0, 92, 92, fill="#1e1f22", outline="")
        if self._img:
            c.create_image(46, 46, image=self._img)
        if show_badge:
            c.create_oval(66, 66, 104, 104, fill="#e60012", outline=self.BG, width=3)
            c.create_text(85, 85, text="2" if console_key == "switch2" else "1", fill="white", font=(FONT, 11, "bold"))
        for lbl in (self.l_name, self.l_details, self.l_state, self.l_time):
            lbl.pack_forget()
        self.l_name.config(text=name)
        self.l_name.pack(fill="x")
        if show_console:
            self.l_details.config(text=label)
            self.l_details.pack(fill="x")
        if message:
            self.l_state.config(text=message)
            self.l_state.pack(fill="x")
        if show_timer:
            self.l_time.config(text="🎮 00:12")
            self.l_time.pack(fill="x")
        self.btn.pack_forget()
        if show_button:
            self.btn.config(text=BUTTON_LABEL)
            self.btn.pack(fill="x", padx=16, pady=(0, 14))


class SettingsDialog(BaseDialog):
    def __init__(self, app, tab="presence"):
        super().__init__(app, tr("settings_title"), "620x560")
        cfg, t = app.cfg, app.theme
        b = self.body
        self.theme_var = tk.StringVar(value=cfg["theme"])
        self.vars = {k: tk.BooleanVar(value=cfg[k]) for k in ("show_timer", "show_console", "show_badge", "show_button")}

        self.tab_seg = Segmented(b, [("presence", tr("tab_presence")), ("general", tr("tab_general"))], tab, self._switch_tab)
        self.tab_seg.recolor(t)
        self.tab_seg.pack(fill="x", pady=(0, 14))

        row = ttk.Frame(b)
        row.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(row, text=tr("cancel"), style="Secondary.TButton", command=self.destroy).pack(side="right")
        ttk.Button(row, text=tr("save"), style="Accent.TButton", command=self._save).pack(side="right", padx=8)

        self.pages = {"presence": ttk.Frame(b), "general": ttk.Frame(b)}
        self._build_presence(self.pages["presence"], t)
        self._build_general(self.pages["general"], t)
        self._start_tab = tab
        self._switch_tab("presence")   # mesure sur l'onglet le plus grand
        self._refresh_preview()

    def _auto_fit(self):
        super()._auto_fit()
        self._switch_tab(self._start_tab)
        self.tab_seg.select(self._start_tab, notify=False)

    def _switch_tab(self, key):
        for f in self.pages.values():
            f.pack_forget()
        self.pages[key].pack(fill="both", expand=True)

    def _build_presence(self, page, t):
        ttk.Label(page, text=tr("preview_label"), style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        self.preview = PresencePreview(page)
        self.preview.pack(fill="x", pady=(0, 14))
        ttk.Label(page, text=tr("settings_label"), style="Section.TLabel").pack(anchor="w", pady=(0, 2))
        options = [
            ("show_timer", tr("opt_timer_title"), tr("opt_timer_desc")),
            ("show_console", tr("opt_console_title"), tr("opt_console_desc")),
            ("show_badge", tr("opt_badge_title"), tr("opt_badge_desc")),
            ("show_button", tr("opt_button_title", button=BUTTON_LABEL), tr("opt_button_desc")),
        ]
        for key, title, desc in options:
            ToggleRow(page, t, title, desc, self.vars[key], self._refresh_preview).pack(fill="x", pady=2)

    def _build_general(self, page, t):
        ttk.Label(page, text=tr("language_label"), style="Section.TLabel").pack(anchor="w")
        self.lang_var = tk.StringVar(value=self.app.cfg["language"])
        lseg = Segmented(page, list(available_languages().items()), self.lang_var.get(),
                         lambda k: self.lang_var.set(k))
        lseg.recolor(t)
        lseg.pack(fill="x", pady=(4, 4))
        ttk.Label(page, text=tr("language_desc"), style="Muted.TLabel").pack(anchor="w", pady=(0, 16))

        ttk.Label(page, text=tr("theme_label"), style="Section.TLabel").pack(anchor="w")
        seg = Segmented(page, [("dark", tr("theme_dark")), ("light", tr("theme_light"))], self.theme_var.get(),
                        lambda k: self.theme_var.set(k))
        seg.recolor(t)
        seg.pack(fill="x", pady=(4, 4))
        ttk.Label(page, text=tr("theme_desc"), style="Muted.TLabel").pack(anchor="w", pady=(0, 16))

        ttk.Label(page, text=tr("cid_label"), style="Section.TLabel").pack(anchor="w")
        self.cid_var = tk.StringVar(value=self.app.cfg["client_id"])
        ttk.Entry(page, textvariable=self.cid_var).pack(fill="x", pady=(4, 4))
        info = tr("cid_info_default") if DEFAULT_CLIENT_ID else tr("cid_info_required")
        ttk.Label(page, text=info, style="Muted.TLabel", wraplength=int(540 * ui_scale(page)),
                  justify="left").pack(anchor="w", pady=(0, 10))
        ttk.Button(page, text=tr("open_portal"), style="Secondary.TButton",
                   command=lambda: webbrowser.open("https://discord.com/developers/applications")).pack(anchor="w")
        ttk.Button(page, text=tr("need_help"), style="Secondary.TButton",
                   command=lambda: self.app.open_help(0)).pack(anchor="w", pady=(16, 0))

    def _refresh_preview(self):
        a = self.app
        try:
            g = a.active_game or a.selected_game()
        except Exception:
            g = None
        v = self.vars
        self.preview.show(g["name"] if g else "Mario Kart World", a.cfg["console"], a.msg_var.get().strip(),
                          v["show_console"].get(), v["show_badge"].get(), v["show_timer"].get(), v["show_button"].get())

    def _save(self):
        cid = self.cid_var.get().strip()
        if cid and not cid.isdigit():
            messagebox.showerror(APP_NAME, tr("err_cid_digits"), parent=self)
            return
        cfg = self.app.cfg
        cfg["client_id"] = cid
        for k, var in self.vars.items():
            cfg[k] = var.get()
        theme_changed = self.theme_var.get() != cfg["theme"]
        cfg["theme"] = self.theme_var.get()
        lang = self.lang_var.get()
        lang_changed = lang != cfg["language"]
        save_config(cfg)
        if theme_changed:
            self.app.apply_theme()
        self.app.refresh_presence_if_active()
        self.destroy()
        if lang_changed:   # l'interface est reconstruite dans la nouvelle langue
            self.app.after(20, lambda: self.app.set_language(lang))


class HelpDialog(BaseDialog):
    """Centre d'aide : une liste de sujets à gauche, l'explication à droite."""

    def __init__(self, app, topic=0):
        super().__init__(app, tr("help_title"), "840x540")
        t = app.theme
        open_issue = lambda: webbrowser.open(GITHUB_URL + "/issues/new")
        fmt = dict(button=BUTTON_LABEL, discord=CONTACT_DISCORD, version=APP_VERSION)
        buttons = [
            [],
            [(tr("help_btn_contact"), lambda: self.show_topic(6))],
            [(tr("help_btn_add_now"), lambda: app.add_game())],
            [(tr("help_btn_settings"), lambda: SettingsDialog(app, "presence"))],
            [(tr("help_btn_request"), open_issue), (tr("help_btn_add"), lambda: app.add_game())],
            [(tr("help_btn_source"), lambda: webbrowser.open(GITHUB_URL))],
            [(tr("help_btn_copy"), self._copy_discord), (tr("help_btn_issue"), open_issue)],
        ]
        self.topics = [(tr(f"help_t{i}_title"), tr(f"help_t{i}_body", **fmt), buttons[i]) for i in range(7)]

        left = ttk.Frame(self.body)
        left.pack(side="left", fill="y")
        self.lb = tk.Listbox(left, width=27, activestyle="none", exportselection=False, font=(FONT, 10),
                             bg=t["card"], fg=t["fg"], selectbackground=t["accent"], selectforeground=t["accent_fg"],
                             highlightthickness=1, highlightbackground=t["border"], relief="flat", bd=0)
        for title, _, _ in self.topics:
            self.lb.insert("end", "  " + title)
        self.lb.pack(fill="y", expand=True)
        self.lb.bind("<<ListboxSelect>>", lambda _e: self.lb.curselection() and self._show(self.lb.curselection()[0]))

        right = ttk.Frame(self.body)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.txt = tk.Text(right, wrap="word", font=(FONT, 10), bg=t["card"], fg=t["fg"], relief="flat",
                           highlightthickness=1, highlightbackground=t["border"], padx=16, pady=14,
                           spacing3=2, cursor="arrow", height=14)
        self.txt.tag_configure("h", font=(FONT, 14, "bold"), spacing3=10)
        self.txt.pack(fill="both", expand=True)
        self.btns = ttk.Frame(right)
        self.btns.pack(fill="x", pady=(10, 0))
        self.status = ttk.Label(right, text="", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(6, 0))
        self.show_topic(topic)

    def show_topic(self, i):
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        self._show(i)

    def _show(self, i):
        title, body, buttons = self.topics[i]
        self.status.config(text="")
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", title + "\n", "h")
        self.txt.insert("end", body)
        self.txt.config(state="disabled")
        for w in self.btns.winfo_children():
            w.destroy()
        for label, fn in buttons:
            ttk.Button(self.btns, text=label, style="Secondary.TButton", command=fn).pack(side="left", padx=(0, 8))

    def _copy_discord(self):
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(CONTACT_DISCORD)
            self.app.update()
            self.status.config(text=tr("help_copied", discord=CONTACT_DISCORD))
        except tk.TclError:
            self.status.config(text=tr("help_discord_fallback", discord=CONTACT_DISCORD))


class AboutDialog(BaseDialog):
    def __init__(self, app):
        super().__init__(app, tr("about_title", name=APP_NAME), "420x400")
        b = self.body
        ttk.Label(b, text=APP_NAME, style="Title.TLabel").pack(pady=(4, 0))
        ttk.Label(b, text=tr("about_version", version=APP_VERSION), style="Muted.TLabel").pack()
        ttk.Label(b, text=tr("about_desc"), justify="center").pack(pady=14)
        ttk.Label(b, text=tr("about_created", author=APP_AUTHOR), font=(FONT, 11, "bold")).pack()
        ttk.Label(b, text=tr("about_discord", discord=CONTACT_DISCORD), style="Muted.TLabel").pack(pady=(2, 0))
        link = ttk.Label(b, text=GITHUB_URL, style="Link.TLabel", cursor="hand2")
        link.pack(pady=(6, 12))
        link.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL))
        ttk.Label(b, text=tr("about_disclaimer"), style="Muted.TLabel", justify="center").pack()
        row = ttk.Frame(b)
        row.pack(side="bottom")
        ttk.Button(row, text=tr("about_contact"), style="Secondary.TButton",
                   command=lambda: app.open_help(6)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text=tr("close"), style="Secondary.TButton", command=self.destroy).pack(side="left")


# ----------------------------------------------------------------------------
# Application principale
# ----------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        sc = ui_scale(self)
        self.geometry(f"{int(540 * sc)}x{int(800 * sc)}")
        self.minsize(int(480 * sc), int(620 * sc))
        self._set_icon()
        self.cfg = load_config()
        if self.cfg.get("language") not in available_languages():
            self.cfg["language"] = detect_language() if AUTO_DETECT_LANGUAGE else DEFAULT_LANGUAGE
            save_config(self.cfg)
        load_language(self.cfg["language"])
        self.title(tr("window_title", name=APP_NAME, author=APP_AUTHOR))
        self.bundled_games = load_bundled_games()
        self.theme = THEMES[self.cfg["theme"]]

        self.rpc = None
        self.rpc_client_id = None
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.active_game = None       # dict du jeu en cours
        self.start_time = None

        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self._build_menu()
        self._build_ui()
        self.apply_theme()
        self.refresh_list()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after_idle(self._fit_main)
        self.after(100, self._poll_events)
        self.after(1000, self._tick)
        self.after(400, self._first_run_check)
        self.after(800, self.refresh_remote)

    # ---------- langue ----------
    def set_language(self, code):
        """Change la langue et reconstruit toute l'interface (sans redémarrer l'appli)."""
        self.cfg["language"] = code
        save_config(self.cfg)
        load_language(code)
        msg = self.msg_var.get()
        for w in list(self.winfo_children()):
            w.destroy()
        self.title(tr("window_title", name=APP_NAME, author=APP_AUTHOR))
        self._build_menu()
        self._build_ui()
        self.apply_theme()
        self.refresh_list()
        self.msg_var.set(msg)
        self._show_update()
        if self.active_game:
            self._update_card()

    # ---------- construction ----------
    def _fit_main(self):
        """Taille de départ adaptée à l'écran : assez grande pour tout voir, jamais hors de l'écran."""
        try:
            self.update_idletasks()
            sc = ui_scale(self)
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w = min(max(int(540 * sc), self.winfo_reqwidth()), sw - 40)
            h = min(max(int(800 * sc), self.winfo_reqheight()), sh - 90)
            self.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - 20)}")
        except tk.TclError:
            pass

    def _set_icon(self):
        try:
            if sys.platform == "win32":
                self.iconbitmap(default=resource_path(os.path.join("assets", "icon.ico")))
            else:
                self._icon_img = tk.PhotoImage(file=resource_path(os.path.join("assets", "icon.png")))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass  # l'icône est un bonus : on ne plante jamais pour ça

    def _build_menu(self):
        fichier = tk.Menu(self, tearoff=0)
        fichier.add_command(label=tr("file_add"), command=self.add_game, accelerator="Ctrl+N")
        fichier.add_separator()
        fichier.add_command(label=tr("file_export"), command=self.export_games)
        fichier.add_command(label=tr("file_import"), command=self.import_games)
        fichier.add_separator()
        fichier.add_command(label=tr("file_quit"), command=self.on_close)

        options = tk.Menu(self, tearoff=0)
        options.add_command(label=tr("opt_refresh"), command=lambda: self.refresh_remote(manual=True))
        options.add_command(label=tr("opt_customize"), command=lambda: SettingsDialog(self, "presence"))
        options.add_command(label=tr("opt_settings"), command=lambda: SettingsDialog(self, "general"))

        aide = tk.Menu(self, tearoff=0)
        aide.add_command(label=tr("help_center"), command=lambda: self.open_help(0), accelerator="F1")
        aide.add_command(label=tr("help_nothing"), command=lambda: self.open_help(1))
        aide.add_command(label=tr("help_cover"), command=lambda: self.open_help(2))
        aide.add_separator()
        aide.add_command(label=tr("help_contact"), command=lambda: self.open_help(6))
        aide.add_command(label=tr("help_request"), command=lambda: webbrowser.open(GITHUB_URL + "/issues/new"))
        aide.add_command(label=tr("help_github"), command=lambda: webbrowser.open(GITHUB_URL))
        aide.add_separator()
        aide.add_command(label=tr("help_about", name=APP_NAME), command=lambda: AboutDialog(self))
        self.menu_defs = [(tr("menu_file"), fichier), (tr("menu_options"), options), (tr("menu_help"), aide)]
        self.menus = [fichier, options, aide]
        self.bind("<Control-n>", lambda _e: self.add_game())
        self.bind("<F1>", lambda _e: self.open_help(0))

    def _popup_menu(self, menu, label):
        try:
            menu.tk_popup(label.winfo_rootx(), label.winfo_rooty() + label.winfo_height())
        finally:
            menu.grab_release()

    def _build_ui(self):
        # Barre de menus maison : sombre, comme le reste (la barre native de Windows reste blanche)
        self.topbar = tk.Frame(self, bd=0)
        self.topbar.pack(side="top", fill="x")
        self.top_labels = []
        for text, menu in self.menu_defs:
            lb = tk.Label(self.topbar, text=text, font=(FONT, 10), padx=14, pady=7, cursor="hand2")
            lb.pack(side="left")
            lb.bind("<Button-1>", lambda _e, m=menu, l=lb: self._popup_menu(m, l))
            lb.bind("<Enter>", lambda _e, l=lb: l.config(bg=self.theme["select"]))
            lb.bind("<Leave>", lambda _e, l=lb: l.config(bg=self.theme["card"]))
            self.top_labels.append(lb)
        root = ttk.Frame(self, padding=(18, 16, 18, 14))
        root.pack(fill="both", expand=True)
        self.root_frame = root

        # En-tête
        ttk.Label(root, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text=tr("tagline"), style="Muted.TLabel").pack(anchor="w", pady=(0, 14))
        # Alerte de nouvelle version (cachée tant qu'il n'y en a pas)
        self.update_lbl = ttk.Label(root, text="", style="Link.TLabel", cursor="hand2")
        self.update_lbl.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL + "/releases/latest"))

        # Console
        ttk.Label(root, text=tr("my_console"), style="Section.TLabel").pack(anchor="w")
        self.console_seg = Segmented(
            root,
            [(k, v[0]) for k, v in CONSOLES.items()],
            self.cfg["console"] if self.cfg["console"] in CONSOLES else "switch2",
            self.on_console_change,
        )
        self.console_seg.theme = self.theme
        self.console_seg.pack(fill="x", pady=(4, 14))

        # Recherche
        ttk.Label(root, text=tr("my_games"), style="Section.TLabel").pack(anchor="w")
        self.search_var = tk.StringVar()
        self.search_entry = PlaceholderEntry(root, tr("search_placeholder"), self.search_var)
        self.search_entry.pack(fill="x", pady=(4, 8))
        self.search_var.trace_add("write", lambda *_: self.refresh_list())

        # Zone du bas (packée avant la liste pour rester toujours visible)
        bottom = ttk.Frame(root)
        bottom.pack(side="bottom", fill="x")

        # Liste
        list_frame = ttk.Frame(root)
        list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_frame, columns=("fav", "name"), show="", selectmode="browse",
                                 style="Games.Treeview", height=5)
        self.tree.column("fav", width=36, stretch=False, anchor="center")
        self.tree.column("name", anchor="w")
        sb = ttk.Scrollbar(list_frame, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Button-3>", self._on_right_click)
        self.tree.bind("<Return>", lambda _e: self.start())

        self.ctx = tk.Menu(self, tearoff=0)
        self.ctx.add_command(label=tr("ctx_show"), command=self.start)
        self.ctx.add_command(label=tr("ctx_fav"), command=self.toggle_favorite)
        self.ctx.add_command(label=tr("ctx_cover"), command=self.edit_cover)
        self.ctx.add_separator()
        self.ctx.add_command(label=tr("ctx_remove"), command=self.delete_game)
        self.menus.append(self.ctx)

        small = ttk.Frame(bottom)
        small.pack(fill="x", pady=(6, 0))
        ttk.Button(small, text=tr("add_game_btn"), style="Secondary.TButton", command=self.add_game).pack(side="left")
        ttk.Label(small, text=tr("right_click_hint"), style="Muted.TLabel").pack(side="right")

        # Message perso
        ttk.Label(bottom, text=tr("msg_label"), style="Section.TLabel").pack(anchor="w", pady=(14, 0))
        self.msg_var = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.msg_var).pack(fill="x", pady=(4, 0))
        ttk.Label(bottom, text=tr("msg_example"), style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        # Carte "en cours"
        self.card = tk.Frame(bottom, bd=0, highlightthickness=1)
        self.card.pack(fill="x", pady=(14, 10))
        self.card_title = tk.Label(self.card, text=tr("card_none_title"), font=(FONT, 11, "bold"), anchor="w")
        self.card_title.pack(fill="x", padx=12, pady=(10, 0))
        self.card_sub = tk.Label(self.card, text=tr("card_none_sub"), font=(FONT, 9), anchor="w", justify="left", wraplength=440)
        self.card_sub.pack(fill="x", padx=12, pady=(0, 10))
        self.card.bind("<Configure>", lambda e: self.card_sub.config(wraplength=max(200, e.width - 30)))

        # Boutons principaux
        btns = ttk.Frame(bottom)
        btns.pack(fill="x")
        custom = ttk.Frame(bottom)
        custom.pack(fill="x", pady=(10, 0))
        ttk.Button(custom, text=tr("btn_customize"), style="Secondary.TButton",
                   command=lambda: SettingsDialog(self, "presence")).pack(side="left", fill="x", expand=True)
        ttk.Button(custom, text=tr("btn_help"), style="Secondary.TButton",
                   command=lambda: self.open_help(0)).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text=tr("btn_stop"), style="Secondary.TButton", command=self.stop).pack(side="right", padx=(8, 0), ipady=6)
        ttk.Button(btns, text=tr("btn_start"), style="Accent.TButton", command=self.start).pack(side="left", fill="x", expand=True, ipady=6)

    # ---------- thème ----------
    def apply_theme(self):
        t = THEMES[self.cfg["theme"]]
        self.theme = t
        s = self.style
        self.configure(bg=t["bg"])
        s.configure(".", background=t["bg"], foreground=t["fg"], font=(FONT, 10), bordercolor=t["border"], focuscolor=t["bg"])
        s.configure("TFrame", background=t["bg"])
        s.configure("TLabel", background=t["bg"], foreground=t["fg"])
        s.configure("Title.TLabel", font=(FONT, 20, "bold"))
        s.configure("Muted.TLabel", foreground=t["muted"], font=(FONT, 9))
        s.configure("Section.TLabel", foreground=t["muted"], font=(FONT, 8, "bold"))
        s.configure("Link.TLabel", foreground=t["accent"], font=(FONT, 10, "underline"))
        s.configure("TEntry", fieldbackground=t["field"], foreground=t["fg"], bordercolor=t["border"],
                    lightcolor=t["border"], darkcolor=t["border"], insertcolor=t["fg"], padding=7)
        s.configure("Placeholder.TEntry", fieldbackground=t["field"], foreground=t["muted"], bordercolor=t["border"],
                    lightcolor=t["border"], darkcolor=t["border"], insertcolor=t["fg"], padding=7)
        s.configure("TCheckbutton", background=t["bg"], foreground=t["fg"])
        s.configure("TRadiobutton", background=t["bg"], foreground=t["fg"])
        s.map("TCheckbutton", background=[("active", t["bg"])])
        s.map("TRadiobutton", background=[("active", t["bg"])])

        s.configure("Accent.TButton", background=t["accent"], foreground=t["accent_fg"], font=(FONT, 11, "bold"),
                    borderwidth=0, padding=(14, 6))
        s.map("Accent.TButton", background=[("active", t["accent_hover"]), ("pressed", t["accent_hover"])])
        s.configure("Secondary.TButton", background=t["card"], foreground=t["fg"], bordercolor=t["border"],
                    borderwidth=1, padding=(12, 6))
        s.map("Secondary.TButton", background=[("active", t["select"])])

        s.configure("Games.Treeview", background=t["card"], fieldbackground=t["card"], foreground=t["fg"],
                    rowheight=34, borderwidth=1, bordercolor=t["border"], font=(FONT, 11))
        s.map("Games.Treeview", background=[("selected", t["select"])], foreground=[("selected", t["fg"])])
        s.configure("Vertical.TScrollbar", background=t["card"], troughcolor=t["bg"], bordercolor=t["bg"],
                    arrowcolor=t["muted"])

        self.console_seg.recolor(t)
        self.topbar.config(bg=t["card"])
        for lb in self.top_labels:
            lb.config(bg=t["card"], fg=t["fg"])
        self.card.config(bg=t["card"], highlightbackground=t["border"], highlightcolor=t["border"])
        self.card_title.config(bg=t["card"], fg=t["fg"])
        self.card_sub.config(bg=t["card"], fg=t["muted"])
        for m in self.menus:
            m.config(bg=t["card"], fg=t["fg"], activebackground=t["accent"], activeforeground=t["accent_fg"], bd=0)
        # Les champs avec placeholder gardent le bon style
        self.search_entry.configure(style="Placeholder.TEntry" if self.search_entry.showing else "TEntry")
        for win in self.winfo_children():
            if isinstance(win, tk.Toplevel):
                win.configure(bg=t["bg"])

    # ---------- liste des jeux ----------
    def all_games(self):
        cfg = self.cfg
        # Ordre de priorité : secours < liste embarquée < liste en ligne < jeux ajoutés par l'utilisateur
        merged = {name: cover for name, cover in BUILTIN_GAMES}
        for g in self.bundled_games:
            merged[g["name"]] = g.get("cover", "")
        for g in cfg.get("remote_games", []):
            merged[g["name"]] = g.get("cover", "")
        for g in cfg["custom"]:
            merged[g["name"]] = g.get("cover", "")
        games = []
        for name, cover in merged.items():
            if name in cfg["hidden"]:
                continue
            cover = cfg["overrides"].get(name, cover) or DEFAULT_COVER
            games.append({"name": name, "cover": cover, "fav": name in cfg["favorites"]})
        return sorted(games, key=lambda g: (not g["fav"], strip_accents(g["name"]).lower()))

    # ---------- liste en ligne ----------
    def refresh_remote(self, manual=False):
        def work():
            try:
                games, latest = fetch_remote_list()
                self.events.put(("remote", games, latest, manual))
            except Exception:
                self.events.put(("remote_fail", manual))
        threading.Thread(target=work, daemon=True).start()

    def visible_games(self):
        q = strip_accents(self.search_entry.real_text()).lower().strip()
        return [g for g in self.all_games() if q in strip_accents(g["name"]).lower()]

    def refresh_list(self):
        if not hasattr(self, "tree"):
            return
        selected = self.selected_name()
        self.tree.delete(*self.tree.get_children())
        self.visible = self.visible_games()
        for i, g in enumerate(self.visible):
            self.tree.insert("", "end", iid=str(i), values=("★" if g["fav"] else "☆", g["name"]))
            if g["name"] == selected:
                self.tree.selection_set(str(i))

    def selected_game(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.visible[int(sel[0])]

    def selected_name(self):
        g = self.selected_game() if self.tree.get_children() else None
        return g["name"] if g else None

    # ---------- interactions liste ----------
    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row and self.tree.identify_column(event.x) == "#1":
            self.tree.selection_set(row)
            self.toggle_favorite()
            return "break"

    def _on_double_click(self, event):
        if self.tree.identify_row(event.y) and self.tree.identify_column(event.x) != "#1":
            self.start()

    def _on_right_click(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.ctx.tk_popup(event.x_root, event.y_root)

    def toggle_favorite(self):
        g = self.selected_game()
        if not g:
            return
        favs = self.cfg["favorites"]
        favs.remove(g["name"]) if g["name"] in favs else favs.append(g["name"])
        save_config(self.cfg)
        self.refresh_list()

    def add_game(self):
        dlg = GameDialog(self, tr("dlg_add_game"))
        self.wait_window(dlg)
        if dlg.result:
            name, cover = dlg.result
            self.cfg["custom"] = [g for g in self.cfg["custom"] if g["name"] != name]
            self.cfg["custom"].append({"name": name, "cover": cover})
            if name in self.cfg["hidden"]:
                self.cfg["hidden"].remove(name)
            save_config(self.cfg)
            self.refresh_list()

    def edit_cover(self):
        g = self.selected_game()
        if not g:
            return
        dlg = GameDialog(self, tr("dlg_edit_cover"), name=g["name"], cover=g["cover"], name_editable=False)
        self.wait_window(dlg)
        if dlg.result:
            self.cfg["overrides"][g["name"]] = dlg.result[1]
            save_config(self.cfg)
            self.refresh_presence_if_active()

    def delete_game(self):
        g = self.selected_game()
        if g and messagebox.askyesno(APP_NAME, tr("remove_confirm", name=g["name"])):
            self.cfg["custom"] = [c for c in self.cfg["custom"] if c["name"] != g["name"]]
            if g["name"] not in self.cfg["hidden"]:
                self.cfg["hidden"].append(g["name"])
            save_config(self.cfg)
            self.refresh_list()

    def export_games(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", initialfile=tr("export_default_file"),
                                            filetypes=[(tr("filetype_games"), "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"custom": self.cfg["custom"], "overrides": self.cfg["overrides"]}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo(APP_NAME, tr("export_done"), parent=self)

    def import_games(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[(tr("filetype_games"), "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            known = {g["name"] for g in self.cfg["custom"]}
            added = 0
            for g in data.get("custom", []):
                if g.get("name") and g["name"] not in known:
                    self.cfg["custom"].append({"name": g["name"], "cover": g.get("cover", "")})
                    added += 1
            self.cfg["overrides"].update(data.get("overrides", {}))
            save_config(self.cfg)
            self.refresh_list()
            messagebox.showinfo(APP_NAME, tr("import_done", n=added), parent=self)
        except Exception as e:
            messagebox.showerror(APP_NAME, tr("import_invalid", err=e), parent=self)

    # ---------- aide ----------
    def open_help(self, topic=0):
        for w in self.winfo_children():
            if isinstance(w, HelpDialog) and w.winfo_exists():
                w.show_topic(topic)
                w._front()
                return
        HelpDialog(self, topic)

    def _first_run_check(self):
        if not self.effective_client_id():
            self._set_card(tr("welcome_title"), tr("welcome_sub"))
            SettingsDialog(self, "general")

    # ---------- Discord ----------
    def effective_client_id(self):
        cid = (self.cfg.get("client_id") or DEFAULT_CLIENT_ID or "").strip()
        return cid if cid.isdigit() else ""

    def on_console_change(self, key):
        self.cfg["console"] = key
        save_config(self.cfg)
        self.refresh_presence_if_active()

    def refresh_presence_if_active(self):
        if self.active_game:
            self._launch(self.active_game, keep_time=True)

    def start(self):
        g = self.selected_game()
        if not g:
            messagebox.showinfo(APP_NAME, tr("select_first"), parent=self)
            return
        if not self.effective_client_id():
            self._first_run_check()
            return
        same = self.active_game and self.active_game["name"] == g["name"]
        self._launch(g, keep_time=bool(same))

    def _launch(self, game, keep_time=False):
        cid = self.effective_client_id()
        if not cid:
            return
        if not keep_time or not self.start_time:
            self.start_time = int(time.time())
        console_label, console_icon = CONSOLES[self.cfg["console"]]
        payload = {
            "game": game,
            "cid": cid,
            "start": self.start_time,
            "console_label": console_label,
            "console_icon": console_icon,
            "message": self.msg_var.get().strip(),
            "timer": self.cfg["show_timer"],
            "button": self.cfg["show_button"],
            "show_console": self.cfg["show_console"],
            "show_badge": self.cfg["show_badge"],
        }
        self.events.put(("status", tr("status_connecting"), game, console_label))
        threading.Thread(target=self._worker, args=(payload,), daemon=True).start()

    def _worker(self, p):
        g = p["game"]
        with self.lock:
            try:
                for attempt in (1, 2):
                    try:
                        if self.rpc is None or self.rpc_client_id != p["cid"]:
                            self._close_rpc()
                            self.rpc = Presence(p["cid"])
                            self.rpc.connect()
                            self.rpc_client_id = p["cid"]
                        kwargs = dict(
                            activity_type=ActivityType.PLAYING,
                            name=g["name"],
                            large_image=g["cover"],
                            large_text=g["name"],
                        )
                        if p["show_console"]:
                            kwargs["details"] = p["console_label"]
                        if p["show_badge"]:
                            kwargs["small_image"] = p["console_icon"]
                            kwargs["small_text"] = p["console_label"]
                        if p["message"]:
                            kwargs["state"] = p["message"]
                        if p["timer"]:
                            kwargs["start"] = p["start"]
                        if p["button"]:
                            kwargs["buttons"] = [{"label": BUTTON_LABEL, "url": GITHUB_URL}]
                        self.rpc.update(**kwargs)
                        break
                    except (DiscordNotFound, InvalidID):
                        raise
                    except Exception:
                        self._close_rpc()   # connexion perdue : on retente une fois
                        if attempt == 2:
                            raise
                self.events.put(("active", g, p["console_label"]))
            except DiscordNotFound:
                self.events.put(("error", tr("err_discord_not_found")))
            except InvalidID:
                self.events.put(("error", tr("err_invalid_id")))
            except Exception as e:
                self.events.put(("error", tr("err_generic", err=e)))

    def _close_rpc(self):
        if self.rpc:
            try:
                self.rpc.clear()
            except Exception:
                pass
            try:
                self.rpc.close()
            except Exception:
                pass
        self.rpc = None
        self.rpc_client_id = None

    def stop(self):
        self.active_game = None
        self.start_time = None
        threading.Thread(target=self._stop_worker, daemon=True).start()
        self._set_card(tr("card_none_title"), tr("card_none_sub"))

    def _stop_worker(self):
        with self.lock:
            self._close_rpc()

    # ---------- événements (thread -> interface) ----------
    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "status":
                    self._set_card(tr("card_connecting", name=ev[2]["name"]), ev[1])
                elif ev[0] == "active":
                    self.active_game = ev[1]
                    self._console_label = ev[2]
                    self._update_card()
                elif ev[0] == "error":
                    self.active_game = None
                    self._set_card(tr("card_failed"), ev[1])
                elif ev[0] == "remote":
                    _, games, latest, manual = ev
                    if games:
                        before = len(self.all_games())
                        self.cfg["remote_games"] = games
                        save_config(self.cfg)
                        self.refresh_list()
                        added = len(self.all_games()) - before
                        if manual:
                            messagebox.showinfo(
                                APP_NAME,
                                tr("remote_ok_new", n=len(games), added=added) if added > 0 else tr("remote_ok", n=len(games)),
                                parent=self)
                    self._latest = latest
                    self._show_update()
                elif ev[0] == "remote_fail" and ev[1]:
                    messagebox.showwarning(APP_NAME, tr("remote_fail"), parent=self)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _show_update(self):
        latest = getattr(self, "_latest", "")
        if latest and parse_version(latest) > parse_version(APP_VERSION):
            self.update_lbl.config(text=tr("update_available", version=latest))
            self.update_lbl.place(relx=1.0, y=6, anchor="ne")

    def _set_card(self, title, sub):
        self.card_title.config(text=title)
        self.card_sub.config(text=sub)

    def _update_card(self):
        if not self.active_game:
            return
        elapsed = fmt_duration(time.time() - self.start_time) if self.start_time else "00:00"
        self._set_card(f"●  {self.active_game['name']}", tr("card_running", console=self._console_label, elapsed=elapsed))
        self.card_title.config(fg="#2ecc71")

    def _tick(self):
        if self.active_game:
            self._update_card()
        else:
            self.card_title.config(fg=self.theme["fg"])
        self.after(1000, self._tick)

    def on_close(self):
        # Nettoie la présence Discord sans jamais bloquer la fermeture (1 s maximum)
        t = threading.Thread(target=self._stop_worker, daemon=True)
        t.start()
        t.join(timeout=1.0)
        try:
            self.destroy()
        finally:
            os._exit(0)  # filet de sécurité : tue tout thread encore en attente


if __name__ == "__main__":
    App().mainloop()
