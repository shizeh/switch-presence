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
        ttk.Label(b, text="Nom du jeu", style="Muted.TLabel").pack(anchor="w")
        self.name_var = tk.StringVar(value=name)
        e = ttk.Entry(b, textvariable=self.name_var, state="normal" if name_editable else "disabled")
        e.pack(fill="x", pady=(2, 12))

        ttk.Label(b, text="Cover (lien https:// vers une image, facultatif)", style="Muted.TLabel").pack(anchor="w")
        self.cover_var = tk.StringVar(value=cover)
        ttk.Entry(b, textvariable=self.cover_var).pack(fill="x", pady=(2, 4))
        self.hint = ttk.Label(b, text="", style="Muted.TLabel", wraplength=410, justify="left")
        self.hint.pack(anchor="w", pady=(0, 14))
        self.name_var.trace_add("write", lambda *_: self._update_hint())
        self._update_hint()

        row = ttk.Frame(b)
        row.pack(side="bottom", fill="x")
        ttk.Button(row, text="Annuler", style="Secondary.TButton", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Enregistrer", style="Accent.TButton", command=self._ok).pack(side="right", padx=8)
        if name_editable:
            e.focus_set()
        self.bind("<Return>", lambda _e: self._ok())

    def _update_hint(self):
        self.hint.config(
            text="Laisse vide pour afficher l'image par défaut. Pour une jaquette, colle un lien https "
                 "direct vers une image (finissant par .png ou .jpg)."
        )

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Donne un nom au jeu.", parent=self)
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
        super().__init__(app, "Paramètres", "620x560")
        cfg, t = app.cfg, app.theme
        b = self.body
        self.theme_var = tk.StringVar(value=cfg["theme"])
        self.vars = {k: tk.BooleanVar(value=cfg[k]) for k in ("show_timer", "show_console", "show_badge", "show_button")}

        self.tab_seg = Segmented(b, [("presence", "Ma présence Discord"), ("general", "Général")], tab, self._switch_tab)
        self.tab_seg.recolor(t)
        self.tab_seg.pack(fill="x", pady=(0, 14))

        row = ttk.Frame(b)
        row.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Button(row, text="Annuler", style="Secondary.TButton", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Enregistrer", style="Accent.TButton", command=self._save).pack(side="right", padx=8)

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
        ttk.Label(page, text="APERÇU : ce que tes amis voient sur ton profil", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        self.preview = PresencePreview(page)
        self.preview.pack(fill="x", pady=(0, 14))
        ttk.Label(page, text="RÉGLAGES : clique sur un interrupteur", style="Section.TLabel").pack(anchor="w", pady=(0, 2))
        options = [
            ("show_timer", "Temps de jeu", "Un chrono qui montre depuis combien de temps tu joues."),
            ("show_console", "Nom de la console", "Écrit « Nintendo Switch » ou « Switch 2 » sous le nom du jeu."),
            ("show_badge", "Badge de la console", "Le petit logo dans le coin de la jaquette."),
            ("show_button", f"Bouton « {BUTTON_LABEL} »",
             "Un bouton cliquable sous ton activité (tu ne le vois pas toi-même)."),
        ]
        for key, title, desc in options:
            ToggleRow(page, t, title, desc, self.vars[key], self._refresh_preview).pack(fill="x", pady=2)

    def _build_general(self, page, t):
        ttk.Label(page, text="THÈME", style="Section.TLabel").pack(anchor="w")
        seg = Segmented(page, [("dark", "Sombre"), ("light", "Clair")], self.theme_var.get(),
                        lambda k: self.theme_var.set(k))
        seg.recolor(t)
        seg.pack(fill="x", pady=(4, 4))
        ttk.Label(page, text="Change l'apparence de l'application.", style="Muted.TLabel").pack(anchor="w", pady=(0, 18))

        ttk.Label(page, text="APPLICATION ID DISCORD (AVANCÉ)", style="Section.TLabel").pack(anchor="w")
        self.cid_var = tk.StringVar(value=self.app.cfg["client_id"])
        ttk.Entry(page, textvariable=self.cid_var).pack(fill="x", pady=(4, 4))
        info = (
            "Tu n'as rien à remplir : l'application utilise déjà l'ID prévu pour elle. "
            "Ce champ sert uniquement si tu veux utiliser ta propre application Discord."
            if DEFAULT_CLIENT_ID else
            "Obligatoire : crée une application sur discord.com/developers/applications "
            "et colle ici son « Application ID »."
        )
        ttk.Label(page, text=info, style="Muted.TLabel", wraplength=500, justify="left").pack(anchor="w", pady=(0, 10))
        ttk.Button(page, text="Ouvrir le Developer Portal", style="Secondary.TButton",
                   command=lambda: webbrowser.open("https://discord.com/developers/applications")).pack(anchor="w")
        ttk.Button(page, text="Besoin d'aide ?", style="Secondary.TButton",
                   command=lambda: self.app.open_help(0)).pack(anchor="w", pady=(18, 0))

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
            messagebox.showerror(APP_NAME, "L'Application ID ne contient que des chiffres.", parent=self)
            return
        cfg = self.app.cfg
        cfg["client_id"] = cid
        for k, var in self.vars.items():
            cfg[k] = var.get()
        theme_changed = self.theme_var.get() != cfg["theme"]
        cfg["theme"] = self.theme_var.get()
        save_config(cfg)
        if theme_changed:
            self.app.apply_theme()
        self.app.refresh_presence_if_active()
        self.destroy()


class HelpDialog(BaseDialog):
    """Centre d'aide : une liste de sujets à gauche, l'explication à droite."""

    def __init__(self, app, topic=0):
        super().__init__(app, "Centre d'aide", "840x540")
        t = app.theme
        open_issue = lambda: webbrowser.open(GITHUB_URL + "/issues/new")
        self.topics = [
            ("Démarrer en 30 secondes",
             "1. Ouvre l'application Discord sur ton PC (pas le navigateur).\n\n"
             "2. En haut de la fenêtre, choisis ta console : Nintendo Switch ou Switch 2.\n\n"
             "3. Double-clique sur le jeu auquel tu joues.\n\n"
             "C'est tout : ton profil Discord affiche le jeu, la console et le temps de jeu.\n\n"
             "Pour arrêter, clique sur « Arrêter » (ou ferme l'application). Tu peux aussi écrire un "
             "message perso (par exemple « Niveau 12 ») dans la fenêtre principale.",
             []),
            ("Rien ne s'affiche sur Discord",
             "Vérifie ces points, dans l'ordre :\n\n"
             "1. Utilise l'application Discord installée sur ton PC, pas le site dans le navigateur.\n\n"
             "2. Dans Discord, va dans Paramètres > Confidentialité des activités et active le partage de "
             "ton activité (« Partager mon activité détectée »).\n\n"
             "3. Regarde ton profil depuis un autre compte, ou demande à un ami : Discord n'affiche pas "
             "toujours ton activité comme les autres la voient (le bouton, par exemple, ne t'est jamais montré).\n\n"
             "4. Si la jaquette reste un « ? », patiente quelques secondes, puis clique sur « Arrêter » "
             "et de nouveau sur « Afficher sur Discord ».\n\n"
             "5. Toujours rien ? Ferme complètement Discord (clic droit sur son icône près de l'horloge, "
             "puis « Quitter »), relance-le et réessaie.",
             [("Contacter le créateur", lambda: self.show_topic(6))]),
            ("Ajouter un jeu avec sa jaquette",
             "1. Clique sur « + Ajouter un jeu ».\n\n"
             "2. Écris le nom du jeu : c'est lui qui s'affiche en gros sur ton profil.\n\n"
             "3. Pour la jaquette, cherche l'image du jeu sur Google Images, fais un clic droit dessus puis "
             "« Copier l'adresse de l'image », et colle ce lien dans le champ « Cover ».\n\n"
             "Astuces :\n"
             "• Le lien doit commencer par https:// et mener directement à une image (.png, .jpg).\n"
             "• Les images de Wikipédia (upload.wikimedia.org) ou de SteamGridDB marchent très bien.\n"
             "• Si une image ne s'affiche pas, essaie un autre lien.\n"
             "• Sans cover, une image par défaut s'affiche : le nom du jeu reste correct.\n\n"
             "Tu peux changer la jaquette plus tard : clic droit sur le jeu > « Modifier la cover ».",
             [("+ Ajouter un jeu maintenant", lambda: app.add_game())]),
            ("Personnaliser ma présence",
             "Clique sur « Personnaliser ma présence » en bas de la fenêtre principale (ou sur "
             "Options > Paramètres). Chaque réglage a son explication et un aperçu te montre le résultat en direct.\n\n"
             "Tu peux afficher ou masquer :\n"
             "• le temps de jeu,\n"
             "• le nom de la console sous le jeu,\n"
             "• le petit badge Switch / Switch 2 sur la jaquette,\n"
             f"• le bouton « {BUTTON_LABEL} ».\n\n"
             "Tu peux aussi écrire un message perso dans la fenêtre principale. "
             "Les changements s'appliquent tout de suite si un jeu est déjà affiché.",
             [("Ouvrir les paramètres", lambda: SettingsDialog(app, "presence"))]),
            ("Mon jeu n'est pas dans la liste",
             "Deux solutions :\n\n"
             "• Ajoute-le toi-même avec « + Ajouter un jeu » (voir « Ajouter un jeu avec sa jaquette »).\n\n"
             "• Demande son ajout : je l'ajoute avec sa vraie jaquette et tout le monde l'aura au prochain "
             "lancement de l'application (ou via Options > Actualiser la liste des jeux).",
             [("Demander l'ajout (GitHub)", open_issue), ("+ Ajouter un jeu", lambda: app.add_game())]),
            ("Windows affiche un avertissement",
             "Au premier lancement, Windows peut afficher « Windows a protégé votre ordinateur » ou "
             "« Éditeur inconnu ». C'est normal : l'application n'est pas signée numériquement "
             "(une signature coûte cher).\n\n"
             "Clique sur « Informations complémentaires », puis « Exécuter quand même ».\n\n"
             "Le code source est public sur GitHub : tu peux le vérifier, ou compiler l'application toi-même. "
             "Si ton antivirus la bloque à tort, ajoute-la en exception.",
             [("Voir le code source", lambda: webbrowser.open(GITHUB_URL))]),
            ("Contacter le créateur",
             "Un bug, une idée, un jeu à ajouter ? Écris-moi !\n\n"
             f"• Discord : {CONTACT_DISCORD}\n"
             "• GitHub : ouvre une demande (il faut un compte GitHub, c'est gratuit).\n\n"
             "Pour un bug, dis-moi ce que tu faisais, le message d'erreur éventuel et la version de "
             f"l'application ({APP_VERSION}).",
             [("Copier mon pseudo Discord", self._copy_discord), ("Ouvrir une demande GitHub", open_issue)]),
        ]

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
            self.status.config(text=f"Pseudo « {CONTACT_DISCORD} » copié. Colle-le dans la recherche de Discord.")
        except tk.TclError:
            self.status.config(text=f"Mon pseudo Discord : {CONTACT_DISCORD}")


class AboutDialog(BaseDialog):
    def __init__(self, app):
        super().__init__(app, f"À propos de {APP_NAME}", "420x400")
        b = self.body
        ttk.Label(b, text=APP_NAME, style="Title.TLabel").pack(pady=(4, 0))
        ttk.Label(b, text=f"Version {APP_VERSION}", style="Muted.TLabel").pack()
        ttk.Label(b, text="Affiche le jeu auquel tu joues sur Nintendo Switch\net Switch 2 directement sur ton profil Discord.",
                  justify="center").pack(pady=14)
        ttk.Label(b, text=f"Créé par {APP_AUTHOR}", font=(FONT, 11, "bold")).pack()
        ttk.Label(b, text=f"Discord : {CONTACT_DISCORD}", style="Muted.TLabel").pack(pady=(2, 0))
        link = ttk.Label(b, text=GITHUB_URL, style="Link.TLabel", cursor="hand2")
        link.pack(pady=(6, 12))
        link.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL))
        ttk.Label(b, text="Projet de fan, non affilié à Nintendo ni à Discord.\n"
                          "Nintendo Switch est une marque de Nintendo.",
                  style="Muted.TLabel", justify="center").pack()
        row = ttk.Frame(b)
        row.pack(side="bottom")
        ttk.Button(row, text="Me contacter", style="Secondary.TButton",
                   command=lambda: app.open_help(6)).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Fermer", style="Secondary.TButton", command=self.destroy).pack(side="left")


# ----------------------------------------------------------------------------
# Application principale
# ----------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  -  par {APP_AUTHOR}")
        sc = ui_scale(self)
        self.geometry(f"{int(540 * sc)}x{int(800 * sc)}")
        self.minsize(int(480 * sc), int(620 * sc))
        self._set_icon()
        self.cfg = load_config()
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
        fichier.add_command(label="Ajouter un jeu…", command=self.add_game, accelerator="Ctrl+N")
        fichier.add_separator()
        fichier.add_command(label="Exporter mes jeux ajoutés…", command=self.export_games)
        fichier.add_command(label="Importer des jeux…", command=self.import_games)
        fichier.add_separator()
        fichier.add_command(label="Quitter", command=self.on_close)

        options = tk.Menu(self, tearoff=0)
        options.add_command(label="Actualiser la liste des jeux", command=lambda: self.refresh_remote(manual=True))
        options.add_command(label="Personnaliser ma présence…", command=lambda: SettingsDialog(self, "presence"))
        options.add_command(label="Paramètres…", command=lambda: SettingsDialog(self, "general"))

        aide = tk.Menu(self, tearoff=0)
        aide.add_command(label="Centre d'aide", command=lambda: self.open_help(0), accelerator="F1")
        aide.add_command(label="Rien ne s'affiche sur Discord ?", command=lambda: self.open_help(1))
        aide.add_command(label="Ajouter un jeu avec sa jaquette", command=lambda: self.open_help(2))
        aide.add_separator()
        aide.add_command(label="Contacter le créateur", command=lambda: self.open_help(6))
        aide.add_command(label="Demander l'ajout d'un jeu…", command=lambda: webbrowser.open(GITHUB_URL + "/issues/new"))
        aide.add_command(label="Page GitHub", command=lambda: webbrowser.open(GITHUB_URL))
        aide.add_separator()
        aide.add_command(label=f"À propos de {APP_NAME}", command=lambda: AboutDialog(self))
        self.menu_defs = [("Fichier", fichier), ("Options", options), ("Aide", aide)]
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
        ttk.Label(root, text="Montre à tes amis ce que tu joues sur Switch", style="Muted.TLabel").pack(anchor="w", pady=(0, 14))
        # Alerte de nouvelle version (cachée tant qu'il n'y en a pas)
        self.update_lbl = ttk.Label(root, text="", style="Link.TLabel", cursor="hand2")
        self.update_lbl.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL + "/releases/latest"))

        # Console
        ttk.Label(root, text="MA CONSOLE", style="Section.TLabel").pack(anchor="w")
        self.console_seg = Segmented(
            root,
            [(k, v[0]) for k, v in CONSOLES.items()],
            self.cfg["console"] if self.cfg["console"] in CONSOLES else "switch2",
            self.on_console_change,
        )
        self.console_seg.theme = self.theme
        self.console_seg.pack(fill="x", pady=(4, 14))

        # Recherche
        ttk.Label(root, text="MES JEUX", style="Section.TLabel").pack(anchor="w")
        self.search_var = tk.StringVar()
        self.search_entry = PlaceholderEntry(root, "Rechercher un jeu…", self.search_var)
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
        self.ctx.add_command(label="Afficher sur Discord", command=self.start)
        self.ctx.add_command(label="Ajouter / retirer des favoris", command=self.toggle_favorite)
        self.ctx.add_command(label="Modifier la cover…", command=self.edit_cover)
        self.ctx.add_separator()
        self.ctx.add_command(label="Retirer de la liste", command=self.delete_game)
        self.menus.append(self.ctx)

        small = ttk.Frame(bottom)
        small.pack(fill="x", pady=(6, 0))
        ttk.Button(small, text="+ Ajouter un jeu", style="Secondary.TButton", command=self.add_game).pack(side="left")
        ttk.Label(small, text="Clic droit sur un jeu pour plus d'options", style="Muted.TLabel").pack(side="right")

        # Message perso
        ttk.Label(bottom, text="MESSAGE PERSO (OPTIONNEL)", style="Section.TLabel").pack(anchor="w", pady=(14, 0))
        self.msg_var = tk.StringVar()
        ttk.Entry(bottom, textvariable=self.msg_var).pack(fill="x", pady=(4, 0))
        ttk.Label(bottom, text="Ex : Niveau 12, Chasse aux Pokémon, En ligne avec des potes…", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        # Carte "en cours"
        self.card = tk.Frame(bottom, bd=0, highlightthickness=1)
        self.card.pack(fill="x", pady=(14, 10))
        self.card_title = tk.Label(self.card, text="Aucune présence active", font=(FONT, 11, "bold"), anchor="w")
        self.card_title.pack(fill="x", padx=12, pady=(10, 0))
        self.card_sub = tk.Label(self.card, text="Choisis un jeu puis clique sur « Afficher sur Discord ».", font=(FONT, 9), anchor="w", justify="left", wraplength=440)
        self.card_sub.pack(fill="x", padx=12, pady=(0, 10))
        self.card.bind("<Configure>", lambda e: self.card_sub.config(wraplength=max(200, e.width - 30)))

        # Boutons principaux
        btns = ttk.Frame(bottom)
        btns.pack(fill="x")
        custom = ttk.Frame(bottom)
        custom.pack(fill="x", pady=(10, 0))
        ttk.Button(custom, text="Personnaliser ma présence", style="Secondary.TButton",
                   command=lambda: SettingsDialog(self, "presence")).pack(side="left", fill="x", expand=True)
        ttk.Button(custom, text="Aide", style="Secondary.TButton",
                   command=lambda: self.open_help(0)).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="■  Arrêter", style="Secondary.TButton", command=self.stop).pack(side="right", padx=(8, 0), ipady=6)
        ttk.Button(btns, text="▶  Afficher sur Discord", style="Accent.TButton", command=self.start).pack(side="left", fill="x", expand=True, ipady=6)

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
        dlg = GameDialog(self, "Ajouter un jeu")
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
        dlg = GameDialog(self, "Modifier la cover", name=g["name"], cover=g["cover"], name_editable=False)
        self.wait_window(dlg)
        if dlg.result:
            self.cfg["overrides"][g["name"]] = dlg.result[1]
            save_config(self.cfg)
            self.refresh_presence_if_active()

    def delete_game(self):
        g = self.selected_game()
        if g and messagebox.askyesno(APP_NAME, f"Retirer « {g['name']} » de la liste ?"):
            self.cfg["custom"] = [c for c in self.cfg["custom"] if c["name"] != g["name"]]
            if g["name"] not in self.cfg["hidden"]:
                self.cfg["hidden"].append(g["name"])
            save_config(self.cfg)
            self.refresh_list()

    def export_games(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", initialfile="mes_jeux.json",
                                            filetypes=[("Liste de jeux", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"custom": self.cfg["custom"], "overrides": self.cfg["overrides"]}, f, ensure_ascii=False, indent=2)
            messagebox.showinfo(APP_NAME, "Liste exportée.", parent=self)

    def import_games(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Liste de jeux", "*.json")])
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
            messagebox.showinfo(APP_NAME, f"{added} jeu(x) importé(s).", parent=self)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Fichier invalide : {e}", parent=self)

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
            self._set_card("Bienvenue !", "Renseigne ton Application ID Discord dans la fenêtre des paramètres pour commencer.")
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
            messagebox.showinfo(APP_NAME, "Sélectionne d'abord un jeu dans la liste.", parent=self)
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
        self.events.put(("status", "Connexion à Discord…", game, console_label))
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
                self.events.put(("error", "Discord est introuvable. Ouvre l'application Discord sur ton PC (pas le navigateur) puis réessaie."))
            except InvalidID:
                self.events.put(("error", "L'Application ID Discord est invalide. Vérifie-le dans Options > Paramètres."))
            except Exception as e:
                self.events.put(("error", f"Impossible de communiquer avec Discord : {e}"))

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
        self._set_card("Aucune présence active", "Choisis un jeu puis clique sur « Afficher sur Discord ».")

    def _stop_worker(self):
        with self.lock:
            self._close_rpc()

    # ---------- événements (thread -> interface) ----------
    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "status":
                    self._set_card(f"Connexion… {ev[2]['name']}", ev[1])
                elif ev[0] == "active":
                    self.active_game = ev[1]
                    self._console_label = ev[2]
                    self._update_card()
                elif ev[0] == "error":
                    self.active_game = None
                    self._set_card("Échec de la connexion", ev[1])
                elif ev[0] == "remote":
                    _, games, latest, manual = ev
                    if games:
                        before = len(self.all_games())
                        self.cfg["remote_games"] = games
                        save_config(self.cfg)
                        self.refresh_list()
                        added = len(self.all_games()) - before
                        if manual:
                            messagebox.showinfo(APP_NAME, f"Liste à jour : {len(games)} jeux en ligne"
                                                          + (f" ({added} nouveau(x))." if added > 0 else "."), parent=self)
                    if latest and parse_version(latest) > parse_version(APP_VERSION):
                        self.update_lbl.config(text=f"Version {latest} disponible")
                        self.update_lbl.place(relx=1.0, y=6, anchor="ne")
                elif ev[0] == "remote_fail" and ev[1]:
                    messagebox.showwarning(APP_NAME, "Impossible de récupérer la liste en ligne. Vérifie ta connexion internet.", parent=self)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _set_card(self, title, sub):
        self.card_title.config(text=title)
        self.card_sub.config(text=sub)

    def _update_card(self):
        if not self.active_game:
            return
        elapsed = fmt_duration(time.time() - self.start_time) if self.start_time else "00:00"
        self._set_card(f"●  {self.active_game['name']}", f"{self._console_label}   ·   en cours depuis {elapsed}")
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
