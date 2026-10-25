import os
import sys
import csv
import json
import colorsys
import subprocess
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser, font as tkfont
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".pk_binary_art_config.json")
# PokeAPI item sprites (30x30), used for the ball and held item icons in the bottom strip
# (where the README's download commands put them; any other folder can be picked with Browse)
ITEM_SPRITE_DIR = os.path.expanduser("~/pokeapi-sprites/sprites/items")

try:
    from pk_reader import read_pk_file
except ImportError:
    read_pk_file = None

def six_stats(d, keys):
    """'HP 17 Atk 18 Def 0 SpA 19 SpD 5 Spe 7' from six reader keys, or '' if any is missing."""
    if not all(d.get(k) is not None for k in keys):
        return ""
    return " ".join(f"{a} {d[k]}" for a, k in zip(("HP", "Atk", "Def", "SpA", "SpD", "Spe"), keys))


def nice_date(t):
    """(2022, 9, 8) -> 'Sep 8, 2022'."""
    try:
        y, m, day = t
        return f"{'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()[m - 1]} {day}, {y}"
    except Exception:
        return ""


# (key, label shown in GUI, how to turn the pk_reader dict into text)
INFO_FIELDS = [
    ("species", "Species", lambda d: (("Shiny " if d.get("is_shiny") else "") + (d.get("species_name") or "")).strip()),
    ("nickname", "Nickname", lambda d: d.get("nickname") or ""),
    ("moves", "Moves", lambda d: " / ".join(m for m in (d.get("move_names") or []) if m)),
    ("ability", "Ability", lambda d: d.get("ability") or ""),
    ("nature", "Nature", lambda d: d.get("nature") or ""),
    ("level", "Level", lambda d: str(d["level"]) if d.get("level") is not None else ""),
    ("met_location", "Met Location", lambda d: next(
        (v for k, v in d.items() if k.startswith("met_location") and isinstance(v, str) and v.strip()),
        f"Location #{d['met_location']}" if d.get("met_location") is not None else "")),
    ("origin_game", "Original Game", lambda d: d.get("origin_game") or ""),
    ("ot", "OT", lambda d: d.get("ot_name") or ""),
    ("pid", "PID", lambda d: f"0x{d['pid']:08X}" if d.get("pid") is not None else ""),
    ("ivs", "IVs", lambda d: six_stats(d, ("iv_hp", "iv_atk", "iv_def", "iv_spa", "iv_spd", "iv_spe"))),
    ("ball", "Ball", lambda d: d.get("ball_name") or ""),
    ("gender", "Gender", lambda d: d.get("gender") or ""),
    ("held_item", "Held Item", lambda d: d.get("held_item_name") or ""),
    ("met_date", "Met Date", lambda d: nice_date(d.get("met_date"))),
    ("met_level", "Met Level", lambda d: str(d["met_level"]) if d.get("met_level") is not None else ""),
    ("hatched", "Hatched", lambda d: (nice_date(d.get("egg_date")) + (f" at {d['egg_location_name']}"
                                      if d.get("egg_location_name") else "")) if d.get("egg_date") else ""),
    ("tid", "TID / SID", lambda d: "" if d.get("trainer_id") is None else
        f"{d['trainer_id']} / {d['secret_id']}" if d.get("secret_id") is not None else str(d["trainer_id"])),
    ("ribbons", "Ribbons", lambda d: ", ".join(r.replace(" Ribbon", "") for r in (d.get("ribbons") or []))),
    ("memory", "Memory", lambda d: d.get("ot_memory") or ""),
    ("home", "Home", lambda d: d.get("home_location") or ""),
    ("evs", "EVs", lambda d: six_stats(d, ("ev_hp", "ev_atk", "ev_def", "ev_spa", "ev_spd", "ev_spe"))),
    ("stats", "Stats", lambda d: six_stats(d, ("hp_max", "stat_atk", "stat_def", "stat_spa", "stat_spd", "stat_spe"))),
    ("friendship", "Friendship", lambda d: str(d["friendship"]) if d.get("friendship") is not None else ""),
]
INFO_LABELS = {k: label for k, label, _ in INFO_FIELDS}
# Default layout ("layout 18" from the mockups): field order down each column, and column widths.
# Ball, gender and held item go last; they only print as text when there's no sprite (or in Text mode).
DEFAULT_LAYOUT = {
    1: ["species", "nickname", "level", "nature", "ability", "friendship", "ot"],
    2: ["moves", "origin_game", "met_location", "met_date", "met_level", "hatched", "tid", "pid"],
    3: ["memory", "ribbons", "stats", "ivs", "evs", "home", "ball", "gender", "held_item"],
}
DEFAULT_COL_WIDTHS = (1.0, 1.0, 1.8)
DEFAULT_STRIP_IN = 1.5
DEFAULT_ORDER = [k for c in (1, 2, 3) for k in DEFAULT_LAYOUT[c]]
DEFAULT_COLUMN = {k: c for c in (1, 2, 3) for k in DEFAULT_LAYOUT[c]}
# Windows font file names (Pillow needs the file, not the family name). Helvetica isn't on Windows, so it uses Arial.
WINDOWS_FONT_FILES = {
    "helvetica": "arial.ttf", "arial": "arial.ttf", "courier": "cour.ttf", "courier new": "cour.ttf",
    "times new roman": "times.ttf", "georgia": "georgia.ttf", "verdana": "verdana.ttf", "impact": "impact.ttf",
    "trebuchet ms": "trebuc.ttf", "consolas": "consola.ttf", "lucida console": "lucon.ttf",
    "calibri": "calibri.ttf", "cambria": "cambria.ttc", "segoe ui": "segoeui.ttf", "comic sans ms": "comic.ttf",
}
WINDOWS_FONT_DIRS = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
                     os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts")]


def find_windows_font(font_name):
    """Path of a Windows font file for a family name, or None (also None on a Mac)."""
    wanted = [WINDOWS_FONT_FILES.get(font_name.lower(), "")]
    wanted += [font_name.replace(" ", "").lower() + ext for ext in (".ttf", ".ttc", ".otf")]
    for folder in WINDOWS_FONT_DIRS:
        try:
            files = {f.lower(): f for f in os.listdir(folder)}
        except OSError:
            continue
        for w in wanted:
            if w and w in files:
                return os.path.join(folder, files[w])
    return None


# Where the red shiny star (the phone app's sparkle icon) goes on shiny Pokémon
SHINY_STAR_CHOICES = [
    "None (just \"Shiny\" in the Species line)",
    "A: Beside the name in the title",
    "B: Above the ball / gender / item icons",
    "D: In front of the Species line",
]
SHINY_RED = "#FF5252"

NB = "\u00a0"   # Non-breaking space: words joined by it never wrap apart
ICON_KEYS = ("ball", "gender", "held_item")  # Fields that can show as a sprite next to the QR instead of text

# Pokémon colors: 6 hex colors per official-artwork image (color_1 = biggest area), made by make_palette_table.py.
# Looked up by the template's file name (254.png -> "254", 423-east.png -> "423-east").
PALETTE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pk_reader", "palette_table.csv")
PALETTE_ART_CONTRAST = 3.0    # Binary art vs page: the main color is darkened (lightened on a dark page) to this
PALETTE_TEXT_CONTRAST = 4.5   # Title text vs title background (the usual "easy to read" level)


def load_palette_table():
    """{(art_key, "normal" or "shiny"): [hex colors]} from palette_table.csv, or {} if it can't be read."""
    table = {}
    try:
        with open(PALETTE_PATH, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                colors = [row[f"color_{i}"] for i in range(1, 7) if row.get(f"color_{i}")]
                if colors:
                    table[(row["art_key"].lower(), row["version"])] = colors
    except Exception:
        print(f"Palette table not loaded ({PALETTE_PATH}):\n{traceback.format_exc()}")
    return table


def _luminance(hex_color):
    """How bright a '#RRGGBB' color looks, 0 (black) to 1 (white)."""
    channels = []
    for i in (1, 3, 5):
        c = int(hex_color[i:i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a, b):
    """1 = same brightness, 21 = black on white."""
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def shade_for_contrast(hex_color, bg, ratio):
    """Same hue, made darker (or lighter on a dark page) until it stands out from bg by `ratio`."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    step = -0.02 if _luminance(bg) > 0.18 else 0.02
    color = hex_color.upper()
    while contrast_ratio(color, bg) < ratio and 0.0 < l < 1.0:
        l = min(1.0, max(0.0, l + step))
        color = "#%02X%02X%02X" % tuple(int(round(v * 255)) for v in colorsys.hls_to_rgb(h, l, s))
    return color

# Settings that get saved/restored as part of a "style" (profiles + auto-remembered last-used).
# File paths and the title text are per-run inputs, not part of a reusable look, so they're excluded.
SETTINGS_FIELDS = [
    "title_font_var", "title_size_var", "title_gap_var",
    "title_separator_thickness_var", "title_separator_color_var",
    "art_font_var", "density_var", "manual_art_font_size_var", "thin_lines_var", "auto_crop_var",
    "include_qr_var", "icon_style_var", "strip_height_var", "shiny_star_var",
    "col_width1_var", "col_width2_var", "col_width3_var", "open_after_var", "output_mode_var", "output_dir_var",
    "canvas_bg_color_var", "title_bg_color_var",
    "art_font_color_var", "title_font_color_var",
    "use_palette_var", "palette_art_var", "palette_title_text_var", "palette_title_bg_var", "palette_separator_var",
]


class BinaryArtGUI:
    # Fixed US Letter page at 300 DPI. The canvas is always exactly this size,
    # so the exported PDF prints as one true 8.5x11 page with no "fit to page"
    # guesswork needed at print time.
    PAGE_DPI = 300
    PAGE_W = 2550
    PAGE_H = 3300
    PAGE_MARGIN = 60      # Print-safe outer margin
    TITLE_TOP_PADDING = 80    # Space between the very top edge and the title text, at scale 1.0
    TITLE_BOTTOM_PADDING = 50  # Space between the title text and the bottom of its colored band, at scale 1.0
    QR_GAP = 40             # Space between the items in the bottom strip (QR, icons, info columns)
    QR_SIZE = 363           # QR target width (~1.2 in). Fixed: never shrinks with the art
    STRIP_H = 450           # Largest QR allowed (the shortest strip, 1.5 in). Strip height itself is a setting
    COL_GAP = 70            # Space between the info columns
    WRAP_INDENT = 0.8       # Wrapped lines are indented by this many font sizes, so each field's start is clear
    GLUE_MAX = 24           # Short values (e.g. "Omega Ruby") never break across lines
    RIBBON_MAX_LINES = 5    # Longer ribbon lists end with "and N more"
    STRIP_BUFFER = 60       # Minimum space between the art and the bottom strip
    TITLE_GAP_MIN = 40      # When things don't fit, the title gap shrinks to this before anything else
    ICON_SLOT = 120         # Max size of each ball / gender / held item icon
    MIN_SCALE = 0.2         # Floor for the auto-shrink fallback
    SCALE_STEP = 0.05

    def __init__(self, root):
        self.root = root
        self.root.title("Binary Pokémon Art & QR Generator")
        self.root.geometry("980x960")
        self.root.resizable(True, True)

        # File & Input Variables
        self.pk_path_var = tk.StringVar()
        self.img_path_var = tk.StringVar()
        self.title_text_var = tk.StringVar()

        # Title Formatting Variables
        self.title_font_var = tk.StringVar()
        self.title_size_var = tk.IntVar(value=100)
        self.title_gap_var = tk.IntVar(value=400)  # Whitespace between title banner and art, at scale 1.0
        self.title_separator_thickness_var = tk.IntVar(value=4)  # px; 0 = no separator line, at scale 1.0

        # Binary Art Grid Formatting Variables
        self.art_font_var = tk.StringVar()
        self.density_var = tk.IntVar(value=200)
        self.manual_art_font_size_var = tk.IntVar(value=16)  # 0 = Auto-calculate
        self.thin_lines_var = tk.BooleanVar(value=True)  # Darkest pixel per cell, so thin lines survive
        self.auto_crop_var = tk.BooleanVar(value=True)   # Trim white margins around the outline
        self.alt_form_var = tk.BooleanVar(value=False)   # Single posters only: use the art picked below
        self.art_choice_var = tk.StringVar()
        self.art_choices = []   # pk_reader's art_options for the loaded file

        # QR / Output Options
        self.include_qr_var = tk.BooleanVar(value=True)
        self.strip_height_var = tk.DoubleVar(value=DEFAULT_STRIP_IN)  # Bottom strip height, inches
        self.col_width1_var = tk.DoubleVar(value=DEFAULT_COL_WIDTHS[0])  # Relative column widths
        self.col_width2_var = tk.DoubleVar(value=DEFAULT_COL_WIDTHS[1])
        self.col_width3_var = tk.DoubleVar(value=DEFAULT_COL_WIDTHS[2])
        self.shiny_star_var = tk.StringVar(value=SHINY_STAR_CHOICES[2])  # Shiny star spot, see SHINY_STAR_CHOICES
        self.icon_style_var = tk.StringVar(value="sprite")  # Ball / gender / held item: "sprite" or "text"
        self.open_after_var = tk.BooleanVar(value=True)
        self.output_mode_var = tk.StringVar(value="auto")  # "auto" = name_1, name_2, ... / "prompt" = Save As dialog
        self.output_dir_var = tk.StringVar()  # Blank = save next to the .pk file

        # Color Variables (hex strings, from the full color picker)
        self.canvas_bg_color_var = tk.StringVar(value="#FFFFFF")
        self.title_bg_color_var = tk.StringVar(value="#FFFFFF")
        self.art_font_color_var = tk.StringVar(value="#000000")
        self.title_font_color_var = tk.StringVar(value="#000000")
        self.title_separator_color_var = tk.StringVar(value="#000000")

        # Pokémon colors from palette_table.csv: when ticked they replace the colors above for each poster
        self.palette_table = load_palette_table()
        self.use_palette_var = tk.BooleanVar(value=False)
        self.palette_art_var = tk.BooleanVar(value=True)
        self.palette_title_text_var = tk.BooleanVar(value=True)
        self.palette_title_bg_var = tk.BooleanVar(value=True)
        self.palette_separator_var = tk.BooleanVar(value=True)
        self.palette_swatches = []
        self.palette_note = None   # Set by render_poster when the art has no palette

        self.color_swatch_buttons = {}
        self.profile_select_var = tk.StringVar()

        self.pk_info = None
        self.info_order = list(DEFAULT_ORDER)
        self.info_row_widgets = {}
        self.info_fields = {}
        for key, _label, _get in INFO_FIELDS:
            self.info_fields[key] = {
                "text": tk.StringVar(),
                "show": tk.BooleanVar(value=True),
                "font": tk.StringVar(value="Helvetica"),
                "size": tk.IntVar(value=40),
                "color": tk.StringVar(value="#000000"),
                "column": tk.IntVar(value=DEFAULT_COLUMN.get(key, 3)),
            }

        self.config_data = self.load_config()

        # Fixed folder holding the outline images (later: auto-pick by Pokédex number)
        # Default to the outline templates bundled with the app when no saved folder exists
        saved_dir = self.config_data.get("img_dir", "")
        bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        if not os.path.isdir(saved_dir) and os.path.isdir(bundled):
            saved_dir = bundled
        self.img_dir_var = tk.StringVar(value=saved_dir)
        self.img_dir_var.trace_add("write", lambda *_: self._save_img_dir())
        # Folder with PokeAPI item sprites (sprites/items); missing pictures print as text
        self.item_dir_var = tk.StringVar(value=self.config_data.get("item_dir") or
                                         (ITEM_SPRITE_DIR if os.path.isdir(ITEM_SPRITE_DIR) else ""))
        self.item_dir_var.trace_add("write", lambda *_: self._save_item_dir())

        self.setup_ui()

        # Restore whatever was last used, so tweaked settings persist across launches.
        self.apply_settings(self.config_data.get("last_used", {}))
        self.refresh_color_swatches()
        self.refresh_profile_list()
        self.img_path_var.trace_add("write", lambda *_: self.refresh_palette_preview())
        self.refresh_palette_preview()

    # ------------------------------------------------------------------
    # Settings persistence (profiles + auto-remembered last-used settings)
    # ------------------------------------------------------------------
    def load_config(self):
        default = {"profiles": {}, "last_used": {}}
        if not os.path.exists(CONFIG_PATH):
            return default
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            data.setdefault("profiles", {})
            data.setdefault("last_used", {})
            return data
        except Exception:
            print(f"Config load error (using defaults):\n{traceback.format_exc()}")
            return default

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.config_data, f, indent=2)
        except Exception:
            print(f"Config save error:\n{traceback.format_exc()}")

    def get_current_settings(self):
        settings = {}
        for var_name in SETTINGS_FIELDS:
            var = getattr(self, var_name)
            key = var_name[:-4]  # strip "_var"
            settings[key] = var.get()
        settings["info_order"] = list(self.info_order)
        settings["info_fields"] = {
            k: {s: f[s].get() for s in ("show", "font", "size", "color", "column")}
            for k, f in self.info_fields.items()
        }
        return settings

    def apply_settings(self, settings):
        """Applies a settings dict (from a profile or last_used) to the current UI vars.
        Missing keys are left untouched, so older saved profiles still work if new
        fields get added later."""
        for var_name in SETTINGS_FIELDS:
            key = var_name[:-4]
            if key in settings:
                try:
                    getattr(self, var_name).set(settings[key])
                except Exception:
                    pass
        if "info_order" in settings:
            saved_order = [k for k in settings["info_order"] if k in self.info_fields]
            self.info_order = saved_order + [k for k in self.info_fields if k not in saved_order]
            if self.info_row_widgets:
                self.regrid_info_rows()
        for k, saved in settings.get("info_fields", {}).items():
            f = self.info_fields.get(k)
            if f:
                for s, v in saved.items():
                    if s in f and s != "text":
                        try:
                            f[s].set(v)
                        except Exception:
                            pass

    def refresh_color_swatches(self):
        mapping = {
            "canvas_bg_color": self.canvas_bg_color_var,
            "title_bg_color": self.title_bg_color_var,
            "art_font_color": self.art_font_color_var,
            "title_font_color": self.title_font_color_var,
            "title_separator_color": self.title_separator_color_var,
        }
        for k, f in self.info_fields.items():
            mapping[f"info_{k}"] = f["color"]
        for key, var in mapping.items():
            btn = self.color_swatch_buttons.get(key)
            if btn is not None:
                try:
                    btn.configure(bg=var.get())
                except Exception:
                    pass

    def refresh_profile_list(self):
        names = sorted(self.config_data.get("profiles", {}).keys())
        self.profile_combo["values"] = names
        if names and self.profile_select_var.get() not in names:
            self.profile_select_var.set(names[0])

    def on_save_profile(self):
        name = simpledialog.askstring("Save Style Profile", "Name this style profile:", parent=self.root)
        if not name:
            return
        self.config_data.setdefault("profiles", {})[name] = self.get_current_settings()
        self.save_config()
        self.refresh_profile_list()
        self.profile_select_var.set(name)
        messagebox.showinfo("Saved", f"Style profile \"{name}\" saved.")

    def on_load_profile(self):
        name = self.profile_select_var.get()
        profile = self.config_data.get("profiles", {}).get(name)
        if not profile:
            messagebox.showwarning("No Profile Selected", "Choose a saved profile first.")
            return
        self.apply_settings(profile)
        self.refresh_color_swatches()

    def on_delete_profile(self):
        name = self.profile_select_var.get()
        if name in self.config_data.get("profiles", {}):
            if messagebox.askyesno("Delete Profile", f"Delete style profile \"{name}\"?"):
                del self.config_data["profiles"][name]
                self.save_config()
                self.refresh_profile_list()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------
    def setup_ui(self):
        padding = {'padx': 12, 'pady': 8}

        btn_row = ttk.Frame(self.root)
        btn_row.pack(side="bottom", fill="x", padx=15, pady=15)
        ttk.Button(btn_row, text="Generate Poster (Letter, 300 DPI PDF)", command=self.generate_art).pack(side="left", fill="x", expand=True)
        ttk.Button(btn_row, text="Generate All in Folder...", command=self.generate_all).pack(side="left", fill="x", expand=True, padx=(8, 0))

        scroll_container = ttk.Frame(self.root)
        scroll_container.pack(side="top", fill="both", expand=True)

        canvas = tk.Canvas(scroll_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        h_scrollbar = ttk.Scrollbar(scroll_container, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=h_scrollbar.set)
        h_scrollbar.pack(side="bottom", fill="x")
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        canvas.configure(yscrollincrement=1, xscrollincrement=1)  # 1 unit == 1 pixel for smooth trackpad scrolling

        pending = {"dx": 0, "dy": 0, "job": None}

        def _flush_scroll():
            pending["job"] = None
            if pending["dy"]:
                canvas.yview_scroll(pending["dy"], "units")
            if pending["dx"]:
                canvas.xview_scroll(pending["dx"], "units")
            pending["dx"] = pending["dy"] = 0

        def _queue(dx, dy):
            # Batch rapid scroll events into one redraw (~60 fps) instead of one per event
            pending["dx"] += dx
            pending["dy"] += dy
            if pending["job"] is None:
                pending["job"] = canvas.after(16, _flush_scroll)

        def _on_mousewheel(event):
            # Physical mouse wheel only (macOS: small notch counts; Windows: multiples of 120)
            notches = event.delta if sys.platform == "darwin" else event.delta / 120
            if event.state & 0x1:  # Shift held: scroll sideways
                _queue(int(-1 * notches * 20), 0)
            else:
                _queue(0, int(-1 * notches * 20))

        def _on_touchpad_scroll(event):
            # Tk 9's dedicated trackpad event. %D packs two signed 16-bit deltas
            # into one int: X in the high 16 bits, Y in the low 16 bits.
            raw = event.delta
            y_delta = raw & 0xFFFF
            if y_delta >= 0x8000:
                y_delta -= 0x10000
            x_delta = (raw >> 16) & 0xFFFF
            if x_delta >= 0x8000:
                x_delta -= 0x10000
            if abs(x_delta) > abs(y_delta):
                _queue(-x_delta, 0)  # Mostly sideways swipe
            else:
                _queue(0, -y_delta)  # Mostly vertical swipe

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        try:  # <TouchpadScroll> only exists in Tk 9; older Tk just uses <MouseWheel>
            canvas.bind_all("<TouchpadScroll>", _on_touchpad_scroll)
            has_touchpad = True
        except tk.TclError:
            has_touchpad = False
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-20, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(20, "units"))
        

        def _bind_mousewheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            if has_touchpad:
                widget.bind("<TouchpadScroll>", _on_touchpad_scroll)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)


        # ------------------- 1. FILE SELECTION & TITLE -------------------
        file_frame = ttk.LabelFrame(scroll_frame, text=" 1. File Selection & Title ")
        file_frame.pack(fill="x", **padding)
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="PK File:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.pk_path_var).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_pk, width=12).grid(row=0, column=2, padx=(5, 10), pady=5)

        ttk.Label(file_frame, text="Template Img:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.img_path_var).grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_img, width=12).grid(row=1, column=2, padx=(5, 10), pady=5)

        ttk.Label(file_frame, text="Image Title:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.title_text_var).grid(row=2, column=1, columnspan=2, sticky="ew", padx=5, pady=5)

        ttk.Label(file_frame, text="Save To:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.output_dir_var).grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_output_dir, width=12).grid(row=3, column=2, padx=(5, 10), pady=5)

        ttk.Label(file_frame, text="Template Folder:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.img_dir_var).grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_img_dir, width=12).grid(row=4, column=2, padx=(5, 10), pady=5)

        ttk.Label(file_frame, text="Template Art:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        art_row = ttk.Frame(file_frame)
        art_row.grid(row=5, column=1, columnspan=2, sticky="w", padx=5, pady=5)
        ttk.Checkbutton(art_row, text="Alternate form", variable=self.alt_form_var,
                        command=self.on_alt_form_toggle).pack(side="left")
        self.art_combo = ttk.Combobox(art_row, textvariable=self.art_choice_var, width=30, state="disabled")
        self.art_combo.pack(side="left", padx=(8, 0))
        self.art_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_art_choice())

        ttk.Label(file_frame, text="Item Sprites Folder:").grid(row=6, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.item_dir_var).grid(row=6, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(file_frame, text="Browse...", command=self.browse_item_dir, width=12).grid(row=6, column=2, padx=(5, 10), pady=5)

        # ------------------- 1b. POKÉMON INFO FIELDS -------------------
        info_frame = ttk.LabelFrame(scroll_frame, text=" Pokémon Info (auto-filled from .pk, editable) ")
        info_frame.pack(fill="x", **padding)
        info_frame.columnconfigure(2, weight=1)
        info_fonts = self.get_available_title_fonts()
        for col, header in enumerate(["Show", "Field", "Text", "Font", "Size", "Color", "Col", "Order"]):
            ttk.Label(info_frame, text=header, foreground="#666666").grid(row=0, column=col, sticky="w", padx=4, pady=(4, 0))
        for key, label, _get in INFO_FIELDS:
            f = self.info_fields[key]
            swatch_key = f"info_{key}"
            color_box = ttk.Frame(info_frame)
            swatch = tk.Label(color_box, width=3, bg=f["color"].get(), relief="solid", bd=1, cursor="hand2")
            swatch.bind("<Button-1>", lambda e, k=swatch_key, v=f["color"]: self.pick_color(k, v))
            swatch.pack(side="left")
            self.add_hex_entry(color_box, f["color"], swatch).pack(side="left", padx=(4, 0))
            self.color_swatch_buttons[swatch_key] = swatch
            order_box = ttk.Frame(info_frame)
            ttk.Button(order_box, text="▲", width=2, command=lambda k=key: self.move_info_field(k, -1)).pack(side="left")
            ttk.Button(order_box, text="▼", width=2, command=lambda k=key: self.move_info_field(k, 1)).pack(side="left")
            self.info_row_widgets[key] = [
                ttk.Checkbutton(info_frame, variable=f["show"]),
                ttk.Label(info_frame, text=label),
                ttk.Entry(info_frame, textvariable=f["text"]),
                ttk.Combobox(info_frame, textvariable=f["font"], values=info_fonts, width=14, state="readonly"),
                ttk.Spinbox(info_frame, from_=8, to=200, increment=2, textvariable=f["size"], width=5),
                color_box,
                ttk.Combobox(info_frame, textvariable=f["column"], values=[1, 2, 3], width=2, state="readonly"),
                order_box,
            ]
        self.regrid_info_rows()

        all_size_var = tk.IntVar(value=40)
        all_row = ttk.Frame(info_frame)
        all_row.grid(row=len(INFO_FIELDS) + 1, column=0, columnspan=8, sticky="w", padx=4, pady=(6, 4))
        ttk.Label(all_row, text="Set all sizes:").pack(side="left")
        ttk.Spinbox(all_row, from_=8, to=200, increment=2, textvariable=all_size_var, width=5).pack(side="left", padx=4)
        ttk.Button(all_row, text="Apply to All",
                   command=lambda: [f["size"].set(all_size_var.get()) for f in self.info_fields.values()]).pack(side="left")
        all_font_var = tk.StringVar(value="Helvetica")
        ttk.Label(all_row, text="   Set all fonts:").pack(side="left")
        ttk.Combobox(all_row, textvariable=all_font_var, values=info_fonts, width=14,
                     state="readonly").pack(side="left", padx=4)
        ttk.Button(all_row, text="Apply to All",
                   command=lambda: [f["font"].set(all_font_var.get()) for f in self.info_fields.values()]).pack(side="left")
        ttk.Label(all_row, text="   Column widths:").pack(side="left")
        for var in (self.col_width1_var, self.col_width2_var, self.col_width3_var):
            ttk.Spinbox(all_row, from_=0.3, to=4, increment=0.1, textvariable=var, width=4).pack(side="left", padx=2)
        ttk.Button(all_row, text="Reset to default layout",
                   command=self.reset_default_layout).pack(side="left", padx=(12, 0))

        # ------------------- 2. TITLE STYLING OPTIONS -------------------
        title_style_frame = ttk.LabelFrame(scroll_frame, text=" 2. Title Header Settings ")
        title_style_frame.pack(fill="x", **padding)

        title_fonts = self.get_available_title_fonts()
        art_fonts = self.get_available_art_fonts()

        ttk.Label(title_style_frame, text="Title Font:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        title_font_dropdown = ttk.Combobox(title_style_frame, textvariable=self.title_font_var, values=title_fonts, width=25, state="readonly")
        title_font_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        if title_fonts:
            title_font_dropdown.current(0)

        ttk.Label(title_style_frame, text="Title Size (pt):").grid(row=0, column=2, sticky="w", padx=(15, 5), pady=5)
        title_size_spinbox = ttk.Spinbox(title_style_frame, from_=12, to=200, increment=2, textvariable=self.title_size_var, width=8)
        title_size_spinbox.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        ttk.Label(title_style_frame, text="Space Below Title (px, shrinks first):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        title_gap_spinbox = ttk.Spinbox(title_style_frame, from_=0, to=1000, increment=10, textvariable=self.title_gap_var, width=8)
        title_gap_spinbox.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Label(title_style_frame, text="Separator Thickness (px):").grid(row=1, column=2, sticky="w", padx=(15, 5), pady=5)
        title_sep_spinbox = ttk.Spinbox(title_style_frame, from_=0, to=50, increment=1, textvariable=self.title_separator_thickness_var, width=8)
        title_sep_spinbox.grid(row=1, column=3, padx=5, pady=5, sticky="w")

        # ------------------- 3. BINARY ART GRID OPTIONS -------------------
        art_style_frame = ttk.LabelFrame(scroll_frame, text=" 3. Binary Art Settings ")
        art_style_frame.pack(fill="x", **padding)

        ttk.Label(art_style_frame, text="Art Font:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        art_font_dropdown = ttk.Combobox(art_style_frame, textvariable=self.art_font_var, values=art_fonts, width=25, state="readonly")
        art_font_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        if art_fonts:
            art_font_dropdown.set("Courier New" if "Courier New" in art_fonts else art_fonts[0])

        ttk.Label(art_style_frame, text="Grid Columns (Density):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        density_spinbox = ttk.Spinbox(art_style_frame, from_=20, to=400, increment=10, textvariable=self.density_var, width=10)
        density_spinbox.grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(art_style_frame, text="Art Size (0 = Auto-fit):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        art_size_spinbox = ttk.Spinbox(art_style_frame, from_=0, to=72, increment=1, textvariable=self.manual_art_font_size_var, width=10)
        art_size_spinbox.grid(row=2, column=1, padx=5, pady=5, sticky="w")

        ttk.Checkbutton(art_style_frame, text="Keep thin lines (fill a cell if any part of it is dark)",
                        variable=self.thin_lines_var).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))
        ttk.Checkbutton(art_style_frame, text="Auto-crop white margins around the outline",
                        variable=self.auto_crop_var).grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 5))

        # ------------------- 4. COLORS -------------------
        color_frame = ttk.LabelFrame(scroll_frame, text=" 4. Colors ")
        color_frame.pack(fill="x", **padding)

        self.add_color_row(color_frame, 0, "Page Background:", "canvas_bg_color", self.canvas_bg_color_var)
        self.add_color_row(color_frame, 1, "Title Background:", "title_bg_color", self.title_bg_color_var)
        self.add_color_row(color_frame, 2, "Binary Art Color:", "art_font_color", self.art_font_color_var)
        self.add_color_row(color_frame, 3, "Title Text Color:", "title_font_color", self.title_font_color_var)
        self.add_color_row(color_frame, 4, "Title Separator Color:", "title_separator_color", self.title_separator_color_var)
        note = ttk.Label(
            color_frame,
            text="Note: the QR code itself always renders as standard black-on-white to stay reliably scannable.",
            foreground="#666666", wraplength=560, justify="left"
        )
        note.grid(row=8, column=0, columnspan=3, sticky="w", padx=5, pady=(6, 2))

        ttk.Checkbutton(color_frame, text="Use the Pokémon's own colors (from palette_table.csv) for:",
                        variable=self.use_palette_var).grid(row=5, column=0, columnspan=3, sticky="w", padx=5, pady=(10, 0))
        palette_parts = ttk.Frame(color_frame)
        palette_parts.grid(row=6, column=0, columnspan=3, sticky="w", padx=25)
        for text, var in (("Binary art", self.palette_art_var), ("Title text", self.palette_title_text_var),
                          ("Title background", self.palette_title_bg_var), ("Title separator", self.palette_separator_var)):
            ttk.Checkbutton(palette_parts, text=text, variable=var).pack(side="left", padx=(0, 12))
        palette_row = ttk.Frame(color_frame)
        palette_row.grid(row=7, column=0, columnspan=3, sticky="w", padx=25, pady=(4, 0))
        ttk.Label(palette_row, text="This Pokémon's colors:").pack(side="left", anchor="n")
        for _ in range(6):
            cell = ttk.Frame(palette_row)
            cell.pack(side="left", padx=3)
            swatch = tk.Label(cell, width=3, bg="#DDDDDD", relief="solid", bd=1, cursor="hand2")
            swatch.pack()
            hex_var = tk.StringVar()
            hex_box = ttk.Entry(cell, textvariable=hex_var, width=8, state="readonly", justify="center")
            hex_box.pack(pady=(2, 0))
            swatch.bind("<Button-1>", lambda e, v=hex_var: self.copy_palette_color(v.get()))
            swatch.hex_var = hex_var
            self.palette_swatches.append(swatch)
        self.palette_key_label = ttk.Label(palette_row, text="", foreground="#666666")
        self.palette_key_label.pack(side="left", padx=(8, 0))

        # ------------------- 5. EXPORT OPTIONS -------------------
        export_frame = ttk.LabelFrame(scroll_frame, text=" 5. Layout & Extras ")
        export_frame.pack(fill="x", **padding)

        ttk.Checkbutton(
            export_frame,
            text="Embed Printable Binary QR Code in Bottom-Left Corner",
            variable=self.include_qr_var
        ).pack(anchor="w", padx=10, pady=(8, 2))

        ttk.Label(export_frame, text="Ball, Gender and Held Item show as:").pack(anchor="w", padx=10, pady=(6, 0))
        ttk.Radiobutton(
            export_frame, text="Sprites next to the QR code (text if there's no sprite)",
            variable=self.icon_style_var, value="sprite"
        ).pack(anchor="w", padx=25)
        ttk.Radiobutton(
            export_frame, text="Text in the info columns",
            variable=self.icon_style_var, value="text"
        ).pack(anchor="w", padx=25, pady=(0, 4))

        strip_row = ttk.Frame(export_frame)
        strip_row.pack(anchor="w", padx=10, pady=(2, 6))
        ttk.Label(strip_row, text="Bottom strip height (inches; taller = more room for info, smaller art):").pack(side="left")
        ttk.Combobox(strip_row, textvariable=self.strip_height_var, values=[1.5, 1.75, 2.0, 2.25],
                     width=5, state="readonly").pack(side="left", padx=5)

        star_row = ttk.Frame(export_frame)
        star_row.pack(anchor="w", padx=10, pady=(0, 6))
        ttk.Label(star_row, text="Shiny star (shiny Pokémon only):").pack(side="left")
        ttk.Combobox(star_row, textvariable=self.shiny_star_var, values=SHINY_STAR_CHOICES,
                     width=40, state="readonly").pack(side="left", padx=5)

        ttk.Checkbutton(
            export_frame,
            text="Open the PDF automatically after generating (for a quick visual check)",
            variable=self.open_after_var
        ).pack(anchor="w", padx=10, pady=(2, 8))

        ttk.Separator(export_frame, orient="horizontal").pack(fill="x", padx=10, pady=(4, 8))

        ttk.Label(export_frame, text="Output filename, when generating:").pack(anchor="w", padx=10)
        ttk.Radiobutton(
            export_frame, text="Auto-number so nothing gets overwritten (e.g. sceptile_1, sceptile_2, ...)",
            variable=self.output_mode_var, value="auto"
        ).pack(anchor="w", padx=25, pady=(2, 0))
        ttk.Radiobutton(
            export_frame, text="Ask me each time (Save As dialog)",
            variable=self.output_mode_var, value="prompt"
        ).pack(anchor="w", padx=25, pady=(0, 8))

        # ------------------- 6. STYLE PROFILES -------------------
        profile_frame = ttk.LabelFrame(scroll_frame, text=" 6. Style Profiles ")
        profile_frame.pack(fill="x", **padding)

        ttk.Label(profile_frame, text="Saved profile:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.profile_combo = ttk.Combobox(profile_frame, textvariable=self.profile_select_var, width=25, state="readonly")
        self.profile_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Button(profile_frame, text="Load", command=self.on_load_profile, width=10).grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(profile_frame, text="Save As...", command=self.on_save_profile, width=10).grid(row=0, column=3, padx=5, pady=5)
        ttk.Button(profile_frame, text="Delete", command=self.on_delete_profile, width=10).grid(row=0, column=4, padx=5, pady=5)

        note2 = ttk.Label(
            profile_frame,
            text="Your current settings are also remembered automatically each time you generate a poster.",
            foreground="#666666", wraplength=560, justify="left"
        )
        note2.grid(row=1, column=0, columnspan=5, sticky="w", padx=5, pady=(2, 6))




    def add_color_row(self, parent, row, label_text, key, var):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", padx=5, pady=4)
        swatch = tk.Label(parent, width=4, bg=var.get(), relief="solid", bd=1, cursor="hand2")
        swatch.bind("<Button-1>", lambda e: self.pick_color(key, var))
        swatch.grid(row=row, column=1, sticky="w", padx=5, pady=4)
        self.color_swatch_buttons[key] = swatch
        self.add_hex_entry(parent, var, swatch, width=9).grid(row=row, column=2, sticky="w", padx=5, pady=4)

    def add_hex_entry(self, parent, var, swatch, width=8):
        """Editable hex box tied to a color variable and its swatch. Returns the Entry."""
        hex_var = tk.StringVar(value=var.get())
        entry = ttk.Entry(parent, textvariable=hex_var, width=width)

        def commit(_event=None):
            text = hex_var.get().strip().lstrip("#")
            if len(text) == 6 and all(c in "0123456789abcdefABCDEF" for c in text):
                var.set("#" + text.upper())
            else:
                hex_var.set(var.get())  # Invalid: put the current color back
        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        # Keep box and swatch in sync when the color changes any other way (picker, profile load)
        var.trace_add("write", lambda *_: (hex_var.set(var.get()), swatch.configure(bg=var.get())))
        return entry

    def pick_color(self, key, var):
        _, hex_color = colorchooser.askcolor(color=var.get(), title="Choose a color", parent=self.root)
        if hex_color:
            var.set(hex_color)
            self.color_swatch_buttons[key].configure(bg=hex_color)

    def palette_colors_for(self, img_path, info=None):
        """The template's palette (shiny colors for a shiny Pokémon) and the name it was found under,
        or (None, name) if palette_table.csv has no row for it."""
        stem = os.path.splitext(os.path.basename(img_path or ""))[0].lower()
        digits = ""
        for ch in stem:
            if not ch.isdigit():
                break
            digits += ch
        keys = [stem] + ([str(int(digits))] if digits and str(int(digits)) != stem else [])  # 0254_x.png -> 254
        versions = ["shiny", "normal"] if (info or {}).get("is_shiny") else ["normal"]
        for key in keys:
            for version in versions:
                colors = self.palette_table.get((key, version))
                if colors:
                    return colors, f"{key} ({version})"
        return None, stem

    def refresh_palette_preview(self):
        """Shows the loaded Pokémon's 6 colors under the color settings."""
        if not self.palette_swatches:
            return
        img_path = self.img_path_var.get().strip()
        colors, key = self.palette_colors_for(img_path, self.pk_info) if img_path else (None, "")
        for i, swatch in enumerate(self.palette_swatches):
            color = colors[i] if colors and i < len(colors) else ""
            swatch.configure(bg=color or "#DDDDDD")
            swatch.hex_var.set(color)
        self.palette_key_label.configure(text=key if colors else (f"none found for {key}" if key else ""))

    def copy_palette_color(self, color):
        """Clicking a palette swatch copies its hex code, ready to paste into any color box."""
        if not color:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(color)
        self.palette_key_label.configure(text=f"Copied {color}")

    def get_available_title_fonts(self):
        """Curates an expanded list of display, serif, sans-serif, and decorative fonts on macOS."""
        mac_title_fonts = [
            "Helvetica", "Arial", "Avenir", "Avenir Next",
            "Baskerville", "Bodoni 72", "Chalkduster", "Copperplate",
            "Didot", "Futura", "Georgia", "Gill Sans",
            "Impact", "Marker Felt", "Optima", "Palatino",
            "Papyrus", "Times New Roman", "Trebuchet MS", "Verdana",
            "Courier New", "Menlo", "Monaco", "SF Mono",
            "Calibri", "Cambria", "Segoe UI", "Comic Sans MS", "Consolas"   # Windows
        ]
        system_fonts = set(tkfont.families())
        found = [f for f in mac_title_fonts if f in system_fonts]
        return found if found else ["Helvetica", "Arial"]

    def get_available_art_fonts(self):
        """Curates monospaced fonts best suited for grid binary stencil alignment."""
        mac_mono_fonts = [
            "Courier New", "Menlo", "Monaco",
            "SF Mono", "Andale Mono", "PT Mono",
            "Consolas", "Lucida Console"   # Windows
        ]
        system_fonts = set(tkfont.families())
        found = [f for f in mac_mono_fonts if f in system_fonts]
        return found if found else ["Courier New", "Courier"]

    def browse_pk(self):
        filename = filedialog.askopenfilename(
            title="Select PK File",
            initialdir=self.config_data.get("last_pk_dir") or None,
            filetypes=[("Pokémon PK Files", " ".join(f"*.pk{n}" for n in range(1, 10))), ("All Files", "*.*")]
        )
        if filename:
            self.pk_path_var.set(filename)
            self.config_data["last_pk_dir"] = os.path.dirname(filename)
            self.save_config()
            base_name = os.path.splitext(os.path.basename(filename))[0]
            self.title_text_var.set(base_name)
            self.load_pk_info(filename)

    def reset_default_layout(self):
        """Puts every info field back to the default layout: order, column, shown, size 40, column widths, strip height."""
        self.info_order = list(DEFAULT_ORDER)
        for key, f in self.info_fields.items():
            f["column"].set(DEFAULT_COLUMN.get(key, 3))
            f["show"].set(True)
            f["size"].set(40)
        for var, w in zip((self.col_width1_var, self.col_width2_var, self.col_width3_var), DEFAULT_COL_WIDTHS):
            var.set(w)
        self.strip_height_var.set(DEFAULT_STRIP_IN)
        self.icon_style_var.set("sprite")
        self.shiny_star_var.set(SHINY_STAR_CHOICES[2])   # B: above the icons
        if self.info_row_widgets:
            self.regrid_info_rows()

    def regrid_info_rows(self):
        stickies = ["", "w", "ew", "", "", "", "", ""]
        for row, key in enumerate(self.info_order, start=1):
            for col, widget in enumerate(self.info_row_widgets[key]):
                widget.grid(row=row, column=col, sticky=stickies[col], padx=4, pady=2)

    def move_info_field(self, key, step):
        i = self.info_order.index(key)
        j = i + step
        if 0 <= j < len(self.info_order):
            self.info_order[i], self.info_order[j] = self.info_order[j], self.info_order[i]
            self.regrid_info_rows()

    def find_template(self, dex):
        """Returns the outline image in the Template Folder whose name starts with this
        Pokédex number (531.png, 0531.png, 0531_audino.png all match), or None."""
        folder = self.img_dir_var.get().strip()
        if isinstance(dex, str) and dex and not dex.isdigit():
            # Named art such as "423-east" (PokeAPI official-artwork names): exact file name match
            if not folder or not os.path.isdir(folder):
                return None
            for name in sorted(os.listdir(folder)):
                stem, ext = os.path.splitext(name)
                if stem.lower() == dex.lower() and ext.lower() in (".png", ".jpg", ".jpeg", ".bmp"):
                    return os.path.join(folder, name)
            return None
        try:
            dex = int(dex)
        except (TypeError, ValueError):
            return None
        if dex <= 0 or not folder or not os.path.isdir(folder):
            return None
        matches = []
        for name in os.listdir(folder):
            stem, ext = os.path.splitext(name)
            if name.startswith(".") or ext.lower() not in (".png", ".jpg", ".jpeg", ".bmp"):
                continue
            digits = ""
            for ch in stem:
                if not ch.isdigit():
                    break
                digits += ch
            if digits and int(digits) == dex:
                matches.append(name)
        if not matches:
            return None
        matches.sort(key=lambda n: (len(n), n))  # Plain "0531.png" wins over "0531_alt.png"
        return os.path.join(folder, matches[0])

    def load_pk_info(self, path):
        """Decodes the .pk file and fills the info fields + title. Everything stays editable."""
        self.pk_info = None
        self.refresh_art_choices()
        if read_pk_file is None:
            print("pk_reader not found; info fields left blank.")
            return
        try:
            self.pk_info = read_pk_file(path)
        except Exception:
            print(f"pk_reader error:\n{traceback.format_exc()}")
            return
        for key, _label, get in INFO_FIELDS:
            try:
                self.info_fields[key]["text"].set(get(self.pk_info))
            except Exception:
                self.info_fields[key]["text"].set("")
        name = self.pk_info.get("nickname") or self.pk_info.get("species_name")
        if name:
            self.title_text_var.set(name)
        self.refresh_art_choices()
        template = self.own_template(self.pk_info)
        if template:
            self.img_path_var.set(template)

    def own_template(self, info):
        """Template for the file's own form (e.g. Alolan art), else the base Pokédex art."""
        info = info or {}
        return self.find_template(info.get("form_art_key")) or self.find_template(info.get("national_dex"))

    def refresh_art_choices(self):
        """Fills the Alternate form list from pk_reader's art_options and turns the box off."""
        self.art_choices = (self.pk_info or {}).get("art_options") or []
        self.art_combo["values"] = [o["name"] for o in self.art_choices]
        self.art_choice_var.set(self.art_choices[0]["name"] if self.art_choices else "")
        self.alt_form_var.set(False)
        self.art_combo.configure(state="disabled")

    def on_alt_form_toggle(self):
        if self.alt_form_var.get() and self.art_choices:
            self.art_combo.configure(state="readonly")
            self.apply_art_choice()
        else:
            self.art_combo.configure(state="disabled")
            template = self.own_template(self.pk_info)
            if template:
                self.img_path_var.set(template)

    def apply_art_choice(self):
        """Switches the Template Img to the chosen art, if its image is in the Template Folder."""
        if not self.alt_form_var.get():
            return
        for o in self.art_choices:
            if o["name"] == self.art_choice_var.get():
                if o["kind"] in ("own", "form"):   # a different form is a different species name
                    shiny = "Shiny " if (self.pk_info or {}).get("is_shiny") else ""
                    self.info_fields["species"]["text"].set(shiny + o["name"])
                template = self.find_template(o["art_key"])
                if template:
                    self.img_path_var.set(template)
                else:
                    messagebox.showwarning("Template not found",
                                           f"No image named {o['art_key']} in the Template Folder.")
                return

    def browse_output_dir(self):
        folder = filedialog.askdirectory(title="Choose Where Posters Are Saved",
                                         initialdir=self.output_dir_var.get() or None)
        if folder:
            self.output_dir_var.set(folder)

    def browse_img_dir(self):
        folder = filedialog.askdirectory(title="Choose Template Image Folder",
                                         initialdir=self.img_dir_var.get() or None)
        if folder:
            self.img_dir_var.set(folder)

    def _save_img_dir(self):
        self.config_data["img_dir"] = self.img_dir_var.get().strip()
        self.save_config()

    def browse_item_dir(self):
        folder = filedialog.askdirectory(title="Choose Item Sprites Folder (PokeAPI sprites/items)",
                                         initialdir=self.item_dir_var.get() or None)
        if folder:
            self.item_dir_var.set(folder)

    def _save_item_dir(self):
        self.config_data["item_dir"] = self.item_dir_var.get().strip()
        self.save_config()

    def browse_img(self):
        filename = filedialog.askopenfilename(
            title="Select Template Image",
            initialdir=self.img_dir_var.get() or None,
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp"), ("All Files", "*.*")]
        )
        if filename:
            self.img_path_var.set(filename)

    def get_pil_font(self, font_name, size):
        """Attempts to load TTF/TTC system fonts across common macOS font directories."""
        size = max(1, int(size))
        clean_name = font_name.replace(" ", "")
        possible_paths = [
            f"/System/Library/Fonts/Supplemental/{clean_name}.ttc",
            f"/System/Library/Fonts/Supplemental/{font_name}.ttf",
            f"/System/Library/Fonts/Supplemental/{clean_name}.ttf",
            f"/Library/Fonts/{clean_name}.ttc",
            f"/Library/Fonts/{font_name}.ttf",
            f"/System/Library/Fonts/{clean_name}.ttf",
            f"/System/Library/Fonts/{font_name}.ttc",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass

        win_path = find_windows_font(font_name) or find_windows_font("Arial")  # Windows only
        if win_path:
            try:
                return ImageFont.truetype(win_path, size)
            except Exception:
                pass

        try:
            return ImageFont.truetype(font_name, size)
        except IOError:
            pass

        try:
            return ImageFont.truetype("Helvetica", size)
        except IOError:
            return ImageFont.load_default()

    def generate_qr_image_element(self, raw_bytes, target_width=220, border=2):
        """
        Renders the raw save-file bytes as a QR code using segno's 8-bit byte
        mode, at an integer module scale computed to land near target_width.
        Never resamples the rendered pixels, so modules stay crisp and scannable.
        Returns None (and logs the traceback) if generation fails.
        """
        try:
            import io
            import segno

            qr = segno.make(raw_bytes, error='m')
            module_count = qr.symbol_size(scale=1, border=border)[0]
            scale = max(1, round(target_width / module_count))  # Whole pixels per dot, so it stays sharp
            while scale > 1 and module_count * scale > self.STRIP_H:  # Must fit in the bottom strip
                scale -= 1

            buffer = io.BytesIO()
            qr.save(buffer, kind='png', scale=scale, border=border)
            buffer.seek(0)

            return Image.open(buffer).convert("RGB")
        except Exception:
            print(f"QR Error:\n{traceback.format_exc()}")
            return None

    # ------------------------------------------------------------------
    # Layout: compute sizes at a given scale factor without drawing yet,
    # so the fit-check loop can try progressively smaller scales.
    # ------------------------------------------------------------------
    def attempt_layout(self, scale, columns, img_aspect,
                        title_text, title_font_name, base_title_pt,
                        art_font_name, manual_art_size, title_gap, strip_h):
        title_font = None
        title_h = 0
        title_band_height = 0
        title_top_padding_eff = 0
        if title_text:
            title_pt_eff = max(6, int(round(base_title_pt * scale)))
            title_font = self.get_pil_font(title_font_name, title_pt_eff)
            tb = title_font.getbbox(title_text)
            title_h = tb[3] - tb[1]
            title_top_padding_eff = int(round(self.TITLE_TOP_PADDING * scale))
            title_bottom_padding_eff = int(round(self.TITLE_BOTTOM_PADDING * scale))
            # The colored band hugs the title text snugly...
            title_band_height = title_top_padding_eff + title_h + title_bottom_padding_eff

        content_area_w = self.PAGE_W - 2 * self.PAGE_MARGIN
        target_char_w = (content_area_w * scale) / columns

        if manual_art_size > 0:
            art_pt_eff = max(1, int(round(manual_art_size * scale)))
        else:
            art_pt_eff = max(4, int(round(target_char_w / 0.6)))

        art_font = self.get_pil_font(art_font_name, art_pt_eff)
        art_bbox = art_font.getbbox("0")
        char_w = max(1, art_bbox[2] - art_bbox[0])
        char_h = max(1, art_bbox[3] - art_bbox[1])

        font_aspect = char_w / char_h
        rows = max(1, int(columns * img_aspect * font_aspect))

        art_width = columns * char_w
        art_height = rows * char_h

        # The art lives between the title gap (or top margin) and the bottom strip.
        # The title gap is not scaled: it was already shrunk first if needed.
        art_top = title_band_height + title_gap if title_text else self.PAGE_MARGIN
        art_bottom = self.PAGE_H - self.PAGE_MARGIN - (strip_h + self.STRIP_BUFFER if strip_h else 0)
        overflow_h = art_top + art_height - art_bottom
        fits = overflow_h <= 0 and art_width + 2 * self.PAGE_MARGIN <= self.PAGE_W

        return {
            'scale': scale, 'title_font': title_font, 'title_h': title_h,
            'title_top_padding': title_top_padding_eff,
            'title_band_height': title_band_height, 'art_top_gap': title_gap if title_text else 0,
            'art_font': art_font,
            'char_w': char_w, 'char_h': char_h, 'rows': rows, 'columns': columns,
            'art_width': art_width, 'art_height': art_height,
            'art_top': art_top, 'art_bottom': art_bottom,
            'overflow_h': overflow_h, 'fits': fits,
        }

    @staticmethod
    def sprite_name(name):
        """'Poke Ball' -> 'poke-ball.png', matching PokeAPI item sprite file names."""
        import re
        import unicodedata
        name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
        name = re.sub(r"[^a-z0-9 -]", "", name).strip()
        return re.sub(r" +", "-", name) + ".png"

    def item_icon(self, item_name):
        """Item sprite cropped to its pixels and enlarged in whole steps (stays crisp). None if missing."""
        folder = self.item_dir_var.get().strip()
        if not item_name or not folder:
            return None
        path = os.path.join(folder, self.sprite_name(item_name))
        if not os.path.exists(path):
            return None
        img = Image.open(path).convert("RGBA")
        box = img.getchannel("A").getbbox()
        if box:
            img = img.crop(box)
        k = max(1, self.ICON_SLOT // max(img.size))
        return img.resize((img.width * k, img.height * k), Image.NEAREST)

    def gender_icon(self, gender):
        """Draws a blue male or pink female symbol. None for genderless or unknown."""
        if gender not in ("Male", "Female"):
            return None
        big = self.ICON_SLOT * 4  # Draw large, then shrink, for smooth edges
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        w = big // 10
        if gender == "Male":
            color = "#3B7DD8"
            r = big * 0.3
            cx, cy = big * 0.4, big * 0.6
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
            tip = big * 0.92
            start = cx + r * 0.7
            d.line([start, big - start, tip, big - tip], fill=color, width=w)
            d.line([tip - big * 0.3, big - tip, tip + w / 2, big - tip], fill=color, width=w)
            d.line([tip, big - tip - w / 2, tip, big - tip + big * 0.3], fill=color, width=w)
        else:
            color = "#E8578F"
            r = big * 0.27
            cx, cy = big * 0.5, big * 0.33
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=w)
            d.line([cx, cy + r, cx, big * 0.98], fill=color, width=w)
            d.line([cx - big * 0.17, big * 0.8, cx + big * 0.17, big * 0.8], fill=color, width=w)
        return img.resize((self.ICON_SLOT, self.ICON_SLOT), Image.LANCZOS)

    def shiny_star_spot(self):
        """'A', 'B' or 'D' when this Pokémon is shiny and a star spot is picked, otherwise None."""
        spot = (self.shiny_star_var.get() or "")[:1]
        is_shiny = self.info_fields["species"]["text"].get().strip().lower().startswith("shiny")
        return spot if is_shiny and spot in ("A", "B", "D") else None

    @staticmethod
    def shiny_star_icon(size, color=SHINY_RED):
        """Three four-pointed sparkles (like the phone app's shiny icon), size x size, transparent."""
        import math
        big = size * 4  # Draw large, then shrink, for smooth edges
        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for cx, cy, r in ((0.36, 0.5, 0.34), (0.78, 0.22, 0.17), (0.78, 0.78, 0.17)):
            points = []
            for i in range(8):
                radius = r * big if i % 2 == 0 else r * big * 0.28
                angle = -math.pi / 2 + i * math.pi / 4
                points.append((cx * big + radius * math.cos(angle), cy * big + radius * math.sin(angle)))
            d.polygon(points, fill=color)
        return img.resize((size, size), Image.LANCZOS)

    def strip_icons(self):
        """Sprites for the shown Ball / Gender / Held Item fields. Returns (icons, text_keys):
        text_keys are the fields that print as text instead (Text mode, or no sprite found)."""
        icons, text_keys = [], set()
        for key in ICON_KEYS:
            f = self.info_fields[key]
            text = f["text"].get().strip()
            if not (f["show"].get() and text):
                continue
            icon = None
            if self.icon_style_var.get() == "sprite":
                icon = self.gender_icon(text) if key == "gender" else self.item_icon(text)
            if icon is None:
                text_keys.add(key)
            else:
                icons.append(icon)
        return icons, text_keys

    def generate_art(self):
        pk_path = self.pk_path_var.get()
        img_path = self.img_path_var.get()
        title_text = self.title_text_var.get().strip()

        title_font_name = self.title_font_var.get()
        base_title_pt = self.title_size_var.get()

        art_font_name = self.art_font_var.get()
        columns = self.density_var.get()
        manual_art_size = self.manual_art_font_size_var.get()

        qr_requested = self.include_qr_var.get()

        if not os.path.exists(pk_path) or not os.path.exists(img_path):
            messagebox.showerror("Error", "Please select valid file paths for both the PK file and template image.")
            return

        # Resolve the output path up front (and before any heavy rendering), so a
        # cancelled Save As dialog doesn't waste work, and auto-numbering never
        # overwrites a previous version.
        chosen_dir = self.output_dir_var.get().strip()
        if chosen_dir and not os.path.isdir(chosen_dir):
            messagebox.showerror("Error", f"The Save To folder doesn't exist:\n{chosen_dir}")
            return
        output_dir = chosen_dir or os.path.dirname(pk_path) or "."
        base_name = self.sanitize_filename(title_text if title_text else os.path.splitext(os.path.basename(pk_path))[0])

        if self.output_mode_var.get() == "prompt":
            chosen_path = filedialog.asksaveasfilename(
                title="Save Poster As",
                initialdir=output_dir,
                initialfile=f"{base_name}.pdf",
                defaultextension=".pdf",
                filetypes=[("PDF Files", "*.pdf")]
            )
            if not chosen_path:
                return  # User cancelled
            output_path = chosen_path
        else:
            output_path = self.get_next_available_path(output_dir, base_name)

        try:
            scale, qr_generated, still_overflowing = self.render_poster(pk_path, img_path, title_text, output_path)

            # 10. Remember these settings for next time
            self.config_data["last_used"] = self.get_current_settings()
            self.save_config()

            # 11. Open for a quick visual check
            if self.open_after_var.get():
                self.open_file(output_path)

            # 12. Report results
            notes = []
            if qr_requested and not qr_generated:
                notes.append("the QR code could not be generated (the save file may be too large for one QR symbol) — see the console for details")
            if scale < 1.0:
                notes.append(f"your settings were automatically scaled to {int(scale * 100)}% to fit one Letter page")
            if still_overflowing:
                notes.append("content still slightly exceeds the page even at minimum scale — consider lowering density or title size")
            if self.palette_note:
                notes.append(self.palette_note)

            if notes:
                messagebox.showwarning("Saved with notes", f"Poster saved to:\n{output_path}\n\n" + "\n".join(f"- {n}" for n in notes))
            else:
                messagebox.showinfo("Success!", f"Poster saved successfully!\nPath: {output_path}")

        except Exception:
            print(f"Rendering Error:\n{traceback.format_exc()}")
            messagebox.showerror("Rendering Error", traceback.format_exc(limit=1))

    def load_template_gray(self, img_path):
        """Opens the outline as grayscale. Transparent areas become white, and (if
        Auto-crop is on) the white margins are trimmed to the dark pixels plus 2%."""
        with Image.open(img_path) as img:
            img = img.convert("RGBA")
            white = Image.new("RGBA", img.size, (255, 255, 255, 255))
            gray = Image.alpha_composite(white, img).convert("L")
        if self.auto_crop_var.get():
            dark = np.array(gray) < 128
            ys, xs = np.nonzero(dark)
            if len(xs):
                pad = int(round(0.02 * max(gray.size)))
                box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
                       min(gray.width, xs.max() + 1 + pad), min(gray.height, ys.max() + 1 + pad))
                gray = gray.crop(box)
        return gray

    def sample_grid(self, gray, columns, rows):
        """Shrinks the outline to columns x rows. With 'Keep thin lines' on, each cell takes
        the DARKEST pixel in its block, so a thin line still fills the cell; otherwise
        it uses the usual smooth average."""
        if not self.thin_lines_var.get():
            resample_mode = getattr(Image, 'Resampling', Image).LANCZOS
            return np.array(gray.resize((columns, rows), resample_mode))
        a = np.array(gray)
        h, w = a.shape
        ys = np.linspace(0, h, rows + 1).astype(int)[:-1]
        xs = np.linspace(0, w, columns + 1).astype(int)[:-1]
        return np.minimum.reduceat(np.minimum.reduceat(a, ys, axis=0), xs, axis=1)

    def render_poster(self, pk_path, img_path, title_text, output_path):
        """Renders one poster to output_path using the current GUI settings.
        No dialogs, so it can be called in a loop (Generate All). Raises on failure.
        Returns (scale, qr_generated, still_overflowing)."""
        title_font_name = self.title_font_var.get()
        base_title_pt = self.title_size_var.get()
        art_font_name = self.art_font_var.get()
        columns = self.density_var.get()
        manual_art_size = self.manual_art_font_size_var.get()
        qr_requested = self.include_qr_var.get()

        # 1. Read binary stream from PK file
        with open(pk_path, "rb") as f:
            raw_bytes = f.read()
        binary_stream = "".join(f"{b:08b}" for b in raw_bytes)
        stream_len = len(binary_stream)

        # 2. Template image aspect ratio
        img_gray_full = self.load_template_gray(img_path)
        img_orig_w, img_orig_h = img_gray_full.size
        img_aspect = img_orig_h / img_orig_w

        # 3. The bottom strip (QR, icons, info) is a fixed size and never shrinks.
        qr_img = self.generate_qr_image_element(raw_bytes, target_width=self.QR_SIZE) if qr_requested else None
        qr_generated = qr_img is not None
        icons, icon_text_keys = self.strip_icons()
        star_spot = self.shiny_star_spot()
        if star_spot == "B":
            icons.insert(0, self.shiny_star_icon(int(self.ICON_SLOT * 0.8)))

        # Info fields block: right of the QR and icons, centered in the strip. Each column
        # gets its share of the width (Column widths); long fields wrap inside their column.
        # If a column is still taller than the strip, all fonts shrink together.
        try:
            strip_px = int(round(float(self.strip_height_var.get()) * self.PAGE_DPI))
        except Exception:
            strip_px = int(round(DEFAULT_STRIP_IN * self.PAGE_DPI))
        strip_px = max(self.STRIP_H, strip_px)
        try:
            col_weights = [max(0.1, float(v.get())) for v in (self.col_width1_var, self.col_width2_var, self.col_width3_var)]
        except Exception:
            col_weights = list(DEFAULT_COL_WIDTHS)

        def glue(key, text):
            """Joins words that shouldn't be split across lines with non-breaking spaces."""
            if key in ("ivs", "evs", "stats"):   # Only break between Def and SpA (3 + 3)
                return text.replace(" ", NB).replace(NB + "SpA", " SpA")
            if key == "ribbons":
                return ", ".join(r.replace(" ", NB) for r in text.split(", "))
            if key not in ("memory", "moves") and len(text) <= self.GLUE_MAX:
                return text.replace(" ", NB)
            return text

        def wrap(text, font, width):
            indent = font.size * self.WRAP_INDENT
            def fits(t, first):
                return font.getlength(t.replace(NB, " ")) <= width - (0 if first else indent)
            units = []
            for u in text.split(" "):   # A joined group too wide for any line may break after all
                units += u.split(NB) if not fits(u, False) else [u]
            lines, cur = [], ""
            for u in units:
                t = (cur + " " + u).strip()
                if cur and not fits(t, not lines):
                    lines.append(cur)
                    cur = u
                else:
                    cur = t
            if cur:
                lines.append(cur)
            # Don't leave one word alone on the last line if the line above can spare a word
            if len(lines) > 1 and " " not in lines[-1].replace(NB, " ") and lines[-2].count(" ") >= 2:
                head, last = lines[-2].rsplit(" ", 1)
                if fits(last + " " + lines[-1], False):
                    lines[-2], lines[-1] = head, last + " " + lines[-1]
            return [line.replace(NB, " ") for line in lines]

        def build_info(k):
            fields = {1: [], 2: [], 3: []}
            for key in self.info_order:
                f = self.info_fields[key]
                text = f["text"].get().strip()
                if key in ICON_KEYS and key not in icon_text_keys:
                    continue  # Shown as a sprite instead
                if f["show"].get() and text:
                    label = INFO_LABELS[key]
                    if key == "ribbons":
                        label = f"Ribbons ({text.count(', ') + 1})"
                    size = max(6, int(round(f["size"].get() * k)))
                    font = self.get_pil_font(f["font"].get(), size)
                    try:
                        col = int(f["column"].get())
                    except Exception:
                        col = 1
                    fields[col if col in fields else 1].append((key, f"{label}: {glue(key, text)}", font, f["color"].get()))
            gap = int(round(12 * k))
            used = [c for c in fields if fields[c]]
            avail = info_max_w - self.COL_GAP * max(0, len(used) - 1)
            total_weight = sum(col_weights[c - 1] for c in used) or 1
            widths = {c: int(avail * col_weights[c - 1] / total_weight) for c in used}
            cols = {c: [] for c in fields}
            heights = []
            for c in used:
                h = 0
                for key, text, font, color in fields[c]:
                    star_w = int(font.size * 1.15) + 10 if (key == "species" and star_spot == "D") else 0
                    lines = wrap(text, font, widths[c] - star_w)
                    if key == "ribbons" and len(lines) > self.RIBBON_MAX_LINES:
                        # Lots of ribbons: list as many as fit, then "and N more"
                        label, names = text.split(": ", 1)
                        names = names.split(", ")
                        n = len(names)
                        while n > 1 and len(lines) > self.RIBBON_MAX_LINES:
                            n -= 1
                            lines = wrap(f"{label}: {', '.join(names[:n])}, and{NB}{len(names) - n}{NB}more", font, widths[c])
                    cols[c].append((lines, font, color, star_w))
                    h += len(lines) * sum(font.getmetrics())
                h += gap * (len(fields[c]) - 1)
                heights.append(h)
            return cols, gap, widths, max(heights, default=0)

        side_gap = self.QR_GAP
        icon_w = max((i.width for i in icons), default=0)
        info_x = self.PAGE_MARGIN
        if qr_generated:
            info_x += qr_img.width + side_gap
        if icons:
            icon_x = info_x
            info_x += icon_w + side_gap
        info_max_w = self.PAGE_W - self.PAGE_MARGIN - info_x

        k = 1.0
        info_cols, line_gap, info_widths, info_h = build_info(k)
        while any(info_cols.values()) and info_h > strip_px and k > 0.2:
            k *= 0.97
            info_cols, line_gap, info_widths, info_h = build_info(k)

        strip_h = strip_px if (qr_generated or icons or any(info_cols.values())) else 0
        strip_top = self.PAGE_H - self.PAGE_MARGIN - strip_h

        # 4. Fit the art above the strip: first shrink the title gap (down to
        # TITLE_GAP_MIN), and only then shrink the art and title together.
        def attempt(scale, title_gap):
            return self.attempt_layout(scale, columns, img_aspect, title_text, title_font_name, base_title_pt,
                                       art_font_name, manual_art_size, title_gap, strip_h)

        scale = 1.0
        title_gap = self.title_gap_var.get()
        layout = attempt(scale, title_gap)
        if title_text and layout['overflow_h'] > 0:
            title_gap = max(min(title_gap, self.TITLE_GAP_MIN), title_gap - layout['overflow_h'])
            layout = attempt(scale, title_gap)
        while not layout['fits'] and scale > self.MIN_SCALE:
            scale = max(self.MIN_SCALE, round(scale - self.SCALE_STEP, 2))
            layout = attempt(scale, title_gap)

        still_overflowing = not layout['fits']

        # Resize the template image to the final grid dimensions
        img_np = self.sample_grid(img_gray_full, layout['columns'], layout['rows'])

        # 5. Build the fixed Letter-size page
        canvas_bg = self.canvas_bg_color_var.get()
        title_bg = self.title_bg_color_var.get()
        art_color = self.art_font_color_var.get()
        title_color = self.title_font_color_var.get()
        sep_color = self.title_separator_color_var.get()

        # Pokémon colors: art and separator get the main color, darkened just enough to show up on the
        # page; the title band gets the main color as-is, and the title text the first palette color
        # that's easy to read on that band (black or white if none is).
        self.palette_note = None
        if self.use_palette_var.get():
            colors, key = self.palette_colors_for(img_path, self.pk_info)
            if colors:
                main = colors[0]
                if self.palette_title_bg_var.get():
                    title_bg = main
                art_shade = shade_for_contrast(main, canvas_bg, PALETTE_ART_CONTRAST)
                if self.palette_art_var.get():
                    art_color = art_shade
                if self.palette_separator_var.get():
                    sep_color = art_shade
                if self.palette_title_text_var.get():
                    readable = [c for c in colors if contrast_ratio(c, title_bg) >= PALETTE_TEXT_CONTRAST]
                    title_color = readable[0] if readable else max(
                        ("#000000", "#FFFFFF"), key=lambda c: contrast_ratio(c, title_bg))
            else:
                self.palette_note = f"no Pokémon colors for {key or 'this template'}, so your own colors were used"

        canvas = Image.new("RGB", (self.PAGE_W, self.PAGE_H), canvas_bg)
        draw = ImageDraw.Draw(canvas)

        art_x_offset = max(0, (self.PAGE_W - layout['art_width']) // 2)

        # 6. Title band + text — the band is flush with the very top edge of the
        # page (y=0, full width) so no page-background color shows above it, and
        # the text sits near the top of that snug band (not vertically centered
        # in a tall band) so it reads high on the page. A separate, adjustable
        # whitespace gap (page-background colored) then separates the band from
        # the art, so the artwork doesn't look like it's touching the banner.
        if title_text:
            band_top = 0
            band_bottom = layout['title_band_height']
            if title_bg.lower() != canvas_bg.lower():
                draw.rectangle([0, band_top, self.PAGE_W, band_bottom], fill=title_bg)

            title_bbox = layout['title_font'].getbbox(title_text)
            title_w = title_bbox[2] - title_bbox[0]
            title_x = (self.PAGE_W - title_w) // 2
            title_y = band_top + layout['title_top_padding']
            draw.text((title_x, title_y), title_text, fill=title_color, font=layout['title_font'])
            if star_spot == "A":   # Shiny star just right of the title, centred on the letters
                star = self.shiny_star_icon(int((title_bbox[3] - title_bbox[1]) * 1.6))
                star_y = title_y + (title_bbox[1] + title_bbox[3]) // 2 - star.height // 2
                canvas.paste(star, (title_x + title_bbox[2] + star.width // 4, star_y), star)

            sep_thickness = min(
                layout['art_top_gap'],
                int(round(self.title_separator_thickness_var.get() * layout['scale']))
            )
            if sep_thickness > 0:
                draw.rectangle(
                    [0, band_bottom, self.PAGE_W, band_bottom + sep_thickness],
                    fill=sep_color
                )

        # Center the art in its space (between the title gap and the strip), so
        # any spare room splits evenly above and below it.
        spare = layout['art_bottom'] - layout['art_top'] - layout['art_height']
        art_start_y = layout['art_top'] + max(0, spare // 2)

        bit_idx = 0
        char_w, char_h = layout['char_w'], layout['char_h']

        for r in range(layout['rows']):
            for c in range(layout['columns']):
                if img_np[r, c] < 128:
                    char = binary_stream[bit_idx % stream_len]
                    bit_idx += 1
                    x_pos = art_x_offset + (c * char_w)
                    y_pos = art_start_y + (r * char_h)
                    # Only happens if the art still overflows: keep the strip clear
                    if strip_h and y_pos + char_h > strip_top:
                        continue
                    draw.text((x_pos, y_pos), char, fill=art_color, font=layout['art_font'])

        # 8. Bottom strip: QR, then icons, then info columns, each centered vertically
        if qr_generated:
            canvas.paste(qr_img, (self.PAGE_MARGIN, strip_top + (strip_h - qr_img.height) // 2))

        if icons:
            icons_h = sum(i.height for i in icons) + 20 * (len(icons) - 1)
            if icons_h > strip_h:   # e.g. shiny star + 3 icons on a short strip: shrink them to fit
                k_icons = (strip_h - 20 * (len(icons) - 1)) / sum(i.height for i in icons)
                icons = [i.resize((max(1, int(i.width * k_icons)), max(1, int(i.height * k_icons))), Image.NEAREST)
                         for i in icons]
                icons_h = sum(i.height for i in icons) + 20 * (len(icons) - 1)
            y = strip_top + (strip_h - icons_h) // 2
            for icon in icons:
                canvas.paste(icon, (icon_x + (icon_w - icon.width) // 2, y), icon)
                y += icon.height + 20

        info_y = strip_top + (strip_h - info_h) // 2
        col_x = info_x
        for c, col_fields in info_cols.items():
            if not col_fields:
                continue
            y = info_y
            for lines, font, color, star_w in col_fields:
                if star_w:   # Shiny star in front of the Species line
                    star = self.shiny_star_icon(star_w - 10)
                    ascent = font.getmetrics()[0]
                    canvas.paste(star, (col_x, y + max(0, (ascent - star.height) // 2 + font.size // 8)), star)
                for j, line in enumerate(lines):
                    indent = int(round(font.size * self.WRAP_INDENT)) if j else star_w
                    draw.text((col_x + indent, y), line, fill=color, font=font)
                    y += sum(font.getmetrics())
                y += line_gap
            col_x += info_widths[c] + self.COL_GAP

        # 9. Save as a single Letter-size PDF page
        canvas.save(output_path, "PDF", resolution=float(self.PAGE_DPI))

        return scale, qr_generated, still_overflowing

    def generate_all(self):
        """Makes one poster per .pk1-.pk9 file in a chosen folder, then shows a summary."""
        folder = filedialog.askdirectory(title="Choose a Folder of .pk Files",
                                         initialdir=self.config_data.get("last_pk_dir") or None)
        if not folder:
            return
        exts = tuple(f".pk{n}" for n in range(1, 10))
        pk_files = sorted(os.path.join(folder, n) for n in os.listdir(folder)
                          if n.lower().endswith(exts) and not n.startswith("."))
        if not pk_files:
            messagebox.showwarning("No Files", f"No .pk1-.pk9 files found in:\n{folder}")
            return

        fallback_img = self.img_path_var.get()
        if not os.path.exists(fallback_img) and not os.path.isdir(self.img_dir_var.get().strip()):
            messagebox.showerror("Error", "Set a Template Folder (for auto-pick), or pick a template image "
                                          "(used when no match is found).")
            return
        chosen_dir = self.output_dir_var.get().strip()
        if chosen_dir and not os.path.isdir(chosen_dir):
            messagebox.showerror("Error", f"The Save To folder doesn't exist:\n{chosen_dir}")
            return
        output_dir = chosen_dir or folder

        self.config_data["last_pk_dir"] = folder
        window_title = self.root.title()
        saved, failed, warned = [], [], []

        for i, pk_path in enumerate(pk_files, start=1):
            name = os.path.basename(pk_path)
            self.root.title(f"Generating {i} of {len(pk_files)}: {name}")
            self.root.update()
            try:
                # Fresh fields for each file, so nothing carries over from the previous one
                for f in self.info_fields.values():
                    f["text"].set("")
                base = os.path.splitext(name)[0]
                self.pk_path_var.set(pk_path)
                self.title_text_var.set(base)
                self.load_pk_info(pk_path)
                if read_pk_file is not None and self.pk_info is None:
                    warned.append(f"{name}: reader couldn't decode it, so info fields are blank")

                auto_img = self.own_template(self.pk_info)
                if auto_img:
                    img_path = auto_img
                elif os.path.exists(fallback_img):
                    img_path = fallback_img
                    warned.append(f"{name}: no matching template, used {os.path.basename(fallback_img)}")
                else:
                    raise FileNotFoundError("no matching template in the Template Folder, and no fallback image selected")

                title_text = self.title_text_var.get().strip()
                output_path = self.get_next_available_path(output_dir, self.sanitize_filename(title_text or base))
                scale, qr_generated, still_overflowing = self.render_poster(pk_path, img_path, title_text, output_path)
                saved.append(output_path)
                if self.include_qr_var.get() and not qr_generated:
                    warned.append(f"{name}: no QR code (file may be too large)")
                if still_overflowing:
                    warned.append(f"{name}: content still overflows the page")
                if self.palette_note:
                    warned.append(f"{name}: {self.palette_note}")
            except Exception:
                print(f"Generate All error on {name}:\n{traceback.format_exc()}")
                failed.append(f"{name}: {traceback.format_exc(limit=1).strip().splitlines()[-1]}")

        self.root.title(window_title)
        self.img_path_var.set(fallback_img)
        self.config_data["last_used"] = self.get_current_settings()
        self.save_config()

        msg = f"Saved {len(saved)} of {len(pk_files)} posters to:\n{output_dir}"
        if failed:
            msg += "\n\nFailed:\n" + "\n".join(f"- {x}" for x in failed)
        if warned:
            msg += "\n\nNotes:\n" + "\n".join(f"- {x}" for x in warned)
        (messagebox.showwarning if (failed or warned) else messagebox.showinfo)("Generate All", msg)
        if saved and self.open_after_var.get():
            self.open_file(output_dir)

    @staticmethod
    def sanitize_filename(name):
        invalid = '<>:"/\\|?*'
        cleaned = "".join(c for c in name if c not in invalid).strip()
        return cleaned if cleaned else "poster"

    @staticmethod
    def get_next_available_path(directory, base_name, ext=".pdf"):
        n = 1
        while True:
            candidate = os.path.join(directory, f"{base_name}_{n}{ext}")
            if not os.path.exists(candidate):
                return candidate
            n += 1

    @staticmethod
    def open_file(path):
        try:
            if sys.platform.startswith("darwin"):
                subprocess.call(["open", path])
            elif sys.platform.startswith("win"):
                os.startfile(path)  # noqa: PLW1514
            else:
                subprocess.call(["xdg-open", path])
        except Exception:
            print(f"Could not auto-open the file:\n{traceback.format_exc()}")


if __name__ == "__main__":
    root = tk.Tk()
    app = BinaryArtGUI(root)
    root.mainloop()
