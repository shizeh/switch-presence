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
GITHUB_URL = "https://github.com/shizeh/switch-presence"  # <- à remplacer

# Application ID Discord embarqué. C'est un identifiant public (pas un secret).
# Si tu le remplis ici, les utilisateurs n'ont rien à configurer.
# S'il est vide, l'appli le demande au premier lancement.
DEFAULT_CLIENT_ID = ""

# Consoles disponibles : clé -> (nom affiché, clé de l'icône dans les Art Assets)
CONSOLES = {
    "switch": ("Nintendo Switch", "switch1"),
    "switch2": ("Nintendo Switch 2", "switch2"),
}

# Jeux intégrés : (nom affiché, clé de cover dans les Art Assets Discord)
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
    ("Pokémon Violet", "pokemon_violet"),
    ("Nintendo Switch Sports", "switch_sports"),
    ("Pokémon Pokopia", "pokemon_pokopia"),
    ("Hello Kitty Island Adventure", "hello_kitty_island_adventure"),
    ("Kirby and the Forgotten Land", "kirby_forgotten_land"),
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
        "custom": [],           # jeux ajoutés [{name, cover}]
        "overrides": {},        # covers modifiées {nom: cover}
        "hidden": [],           # jeux retirés de la liste
        "favorites": [],
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
        self.geometry(size)
        self.resizable(False, False)
        self.configure(bg=app.theme["bg"])
        # Volontairement ni transient() ni grab_set() : sous Windows, ils peuvent rendre
        # la fenêtre principale invisible quand on la rouvre depuis la barre des tâches.
        self.body = ttk.Frame(self, padding=20)
        self.body.pack(fill="both", expand=True)
        self.after(20, self._front)

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

        ttk.Label(b, text="Cover (clé d'image Discord ou lien https://…)", style="Muted.TLabel").pack(anchor="w")
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
        key = slugify(self.name_var.get() or "mon jeu")
        self.hint.config(
            text=f"Laisse vide pour utiliser la clé automatique : {key}\n"
                 "Upload ton image dans Discord Developer Portal > Rich Presence > Art Assets."
        )

    def _ok(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning(APP_NAME, "Donne un nom au jeu.", parent=self)
            return
        self.result = (name, self.cover_var.get().strip())
        self.destroy()


class SettingsDialog(BaseDialog):
    def __init__(self, app):
        super().__init__(app, "Paramètres", "480x440")
        cfg = app.cfg
        b = self.body

        ttk.Label(b, text="Thème", style="Muted.TLabel").pack(anchor="w")
        self.theme_var = tk.StringVar(value=cfg["theme"])
        row = ttk.Frame(b)
        row.pack(anchor="w", pady=(2, 12))
        ttk.Radiobutton(row, text="Sombre", value="dark", variable=self.theme_var).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(row, text="Clair", value="light", variable=self.theme_var).pack(side="left")

        self.timer_var = tk.BooleanVar(value=cfg["show_timer"])
        ttk.Checkbutton(b, text="Afficher le temps de jeu sur Discord", variable=self.timer_var).pack(anchor="w", pady=(0, 14))

        ttk.Label(b, text="Application ID Discord (avancé)", style="Muted.TLabel").pack(anchor="w")
        self.cid_var = tk.StringVar(value=cfg["client_id"])
        ttk.Entry(b, textvariable=self.cid_var).pack(fill="x", pady=(2, 4))
        info = (
            "Laisse vide pour utiliser l'ID intégré à l'appli."
            if DEFAULT_CLIENT_ID else
            "Obligatoire : crée une application sur discord.com/developers/applications "
            "et colle ici son « Application ID »."
        )
        ttk.Label(b, text=info, style="Muted.TLabel", wraplength=430, justify="left").pack(anchor="w", pady=(0, 12))
        ttk.Button(b, text="Ouvrir le Developer Portal", style="Secondary.TButton",
                   command=lambda: webbrowser.open("https://discord.com/developers/applications")).pack(anchor="w")

        row = ttk.Frame(b)
        row.pack(side="bottom", fill="x")
        ttk.Button(row, text="Annuler", style="Secondary.TButton", command=self.destroy).pack(side="right")
        ttk.Button(row, text="Enregistrer", style="Accent.TButton", command=self._save).pack(side="right", padx=8)

    def _save(self):
        cid = self.cid_var.get().strip()
        if cid and not cid.isdigit():
            messagebox.showerror(APP_NAME, "L'Application ID ne contient que des chiffres.", parent=self)
            return
        self.app.cfg["client_id"] = cid
        self.app.cfg["show_timer"] = self.timer_var.get()
        theme_changed = self.theme_var.get() != self.app.cfg["theme"]
        self.app.cfg["theme"] = self.theme_var.get()
        save_config(self.app.cfg)
        if theme_changed:
            self.app.apply_theme()
        self.app.refresh_presence_if_active()
        self.destroy()


class AboutDialog(BaseDialog):
    def __init__(self, app):
        super().__init__(app, f"À propos de {APP_NAME}", "420x330")
        b = self.body
        ttk.Label(b, text=APP_NAME, style="Title.TLabel").pack(pady=(4, 0))
        ttk.Label(b, text=f"Version {APP_VERSION}", style="Muted.TLabel").pack()
        ttk.Label(b, text="Affiche le jeu auquel tu joues sur Nintendo Switch\net Switch 2 directement sur ton profil Discord.",
                  justify="center").pack(pady=14)
        ttk.Label(b, text=f"Créé par {APP_AUTHOR}", font=(FONT, 11, "bold")).pack()
        link = ttk.Label(b, text=GITHUB_URL, style="Link.TLabel", cursor="hand2")
        link.pack(pady=(6, 14))
        link.bind("<Button-1>", lambda _e: webbrowser.open(GITHUB_URL))
        ttk.Label(b, text="Projet de fan, non affilié à Nintendo ni à Discord.\n"
                          "Nintendo Switch est une marque de Nintendo.",
                  style="Muted.TLabel", justify="center").pack()
        ttk.Button(b, text="Fermer", style="Secondary.TButton", command=self.destroy).pack(side="bottom")


# ----------------------------------------------------------------------------
# Application principale
# ----------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  -  par {APP_AUTHOR}")
        self.geometry("520x720")
        self.minsize(460, 600)
        self._set_icon()
        self.cfg = load_config()
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
        self.after(100, self._poll_events)
        self.after(1000, self._tick)
        self.after(400, self._first_run_check)

    # ---------- construction ----------
    def _set_icon(self):
        try:
            if sys.platform == "win32":
                self.iconbitmap(resource_path(os.path.join("assets", "icon.ico")))
            else:
                self._icon_img = tk.PhotoImage(file=resource_path(os.path.join("assets", "icon.png")))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass  # l'icône est un bonus : on ne plante jamais pour ça

    def _build_menu(self):
        self.menubar = tk.Menu(self)
        fichier = tk.Menu(self.menubar, tearoff=0)
        fichier.add_command(label="Ajouter un jeu…", command=self.add_game, accelerator="Ctrl+N")
        fichier.add_separator()
        fichier.add_command(label="Exporter mes jeux ajoutés…", command=self.export_games)
        fichier.add_command(label="Importer des jeux…", command=self.import_games)
        fichier.add_separator()
        fichier.add_command(label="Quitter", command=self.on_close)
        self.menubar.add_cascade(label="Fichier", menu=fichier)

        options = tk.Menu(self.menubar, tearoff=0)
        options.add_command(label="Paramètres…", command=lambda: SettingsDialog(self))
        self.menubar.add_cascade(label="Options", menu=options)

        aide = tk.Menu(self.menubar, tearoff=0)
        aide.add_command(label="Guide de démarrage", command=self.show_guide)
        aide.add_command(label="Page GitHub", command=lambda: webbrowser.open(GITHUB_URL))
        aide.add_separator()
        aide.add_command(label=f"À propos de {APP_NAME}", command=lambda: AboutDialog(self))
        self.menubar.add_cascade(label="Aide", menu=aide)
        self.config(menu=self.menubar)
        self.menus = [fichier, options, aide, self.menubar]
        self.bind("<Control-n>", lambda _e: self.add_game())

    def _build_ui(self):
        root = ttk.Frame(self, padding=(18, 16, 18, 14))
        root.pack(fill="both", expand=True)
        self.root_frame = root

        # En-tête
        ttk.Label(root, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Montre à tes amis ce que tu joues sur Switch", style="Muted.TLabel").pack(anchor="w", pady=(0, 14))

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

        # Boutons principaux
        btns = ttk.Frame(bottom)
        btns.pack(fill="x")
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
        games = []
        for name, cover in BUILTIN_GAMES + [(g["name"], g.get("cover", "")) for g in cfg["custom"]]:
            if name in cfg["hidden"]:
                continue
            cover = cfg["overrides"].get(name, cover) or slugify(name)
            games.append({"name": name, "cover": cover, "fav": name in cfg["favorites"]})
        return sorted(games, key=lambda g: (not g["fav"], strip_accents(g["name"]).lower()))

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
    def show_guide(self):
        messagebox.showinfo(
            "Guide de démarrage",
            "1. Ouvre l'application Discord sur ton PC (pas le navigateur).\n\n"
            "2. Choisis ta console : Nintendo Switch ou Switch 2.\n\n"
            "3. Double-clique sur un jeu (ou sélectionne-le puis clique sur « Afficher sur Discord »).\n\n"
            "4. Pour arrêter, clique sur « Arrêter ». La présence disparaît aussi quand tu fermes l'appli.\n\n"
            "Rien n'apparaît ? Dans Discord, va dans Paramètres > Confidentialité des activités "
            "et active « Partager mon activité détectée ».",
            parent=self,
        )

    def _first_run_check(self):
        if not self.effective_client_id():
            self._set_card("Bienvenue !", "Renseigne ton Application ID Discord dans la fenêtre des paramètres pour commencer.")
            SettingsDialog(self)

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
                            details=p["console_label"],
                            large_image=g["cover"],
                            large_text=g["name"],
                            small_image=p["console_icon"],
                            small_text=p["console_label"],
                        )
                        if p["message"]:
                            kwargs["state"] = p["message"]
                        if p["timer"]:
                            kwargs["start"] = p["start"]
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
