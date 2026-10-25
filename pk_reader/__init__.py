"""
pk_reader: reads raw Pokémon .pk<gen> entity files and returns a plain dict
of decoded fields (species, National Dex number, nickname, OT name, ...).

Built independently from public community documentation (Bulbapedia /
Project Pokémon format-structure pages) rather than ported from any
existing save-editing tool's source code, so it carries no inherited
license obligations and can be used or distributed however you like.

Usage:
    from pk_reader import read_pk_file
    data = read_pk_file("sceptile.pk1")
    print(data["national_dex"], data["nickname"])
"""

import os

from .gen1_2 import decode_gen1
from .gen2 import decode_gen2
from .gen3 import decode_gen3
from .gen4 import decode_gen4
from .gen5 import decode_gen5
from .gen6 import decode_gen6
from .gen7 import decode_gen7


import csv

from .species_data import NATURES, calc_hp_stat, calc_other_stat
from .species_data import met_location_name, egg_location_name, form_info, mega_options, gmax_options, art_options


_EXT_TO_DECODER = {
    ".pk1": decode_gen1,
    ".pk2": decode_gen2,
    ".pk3": decode_gen3,
    ".pk4": decode_gen4,
    ".pk5": decode_gen5,
    ".pk6": decode_gen6,
    ".pk7": decode_gen7,
        
    # .pk4, .pk5, .pk6, .pk7, .pk8, .pk9 -- added one at a time
    # as each generation's algorithm is built and verified against real files.
}


# Held items that change which art the poster uses. Mega Stones and Primal orbs only change
# the art (the species name stays); the Griseous Orb makes Giratina Origin Forme, which
# Gen 4+ files normally already store as form 1, so it only matters if the form says 0.
MEGA_STONES = {
    "Venusaurite": "Mega Venusaur", "Charizardite X": "Mega Charizard X",
    "Charizardite Y": "Mega Charizard Y", "Blastoisinite": "Mega Blastoise",
    "Beedrillite": "Mega Beedrill", "Pidgeotite": "Mega Pidgeot", "Alakazite": "Mega Alakazam",
    "Slowbronite": "Mega Slowbro", "Gengarite": "Mega Gengar", "Kangaskhanite": "Mega Kangaskhan",
    "Pinsirite": "Mega Pinsir", "Gyaradosite": "Mega Gyarados", "Aerodactylite": "Mega Aerodactyl",
    "Mewtwonite X": "Mega Mewtwo X", "Mewtwonite Y": "Mega Mewtwo Y",
    "Ampharosite": "Mega Ampharos", "Steelixite": "Mega Steelix", "Scizorite": "Mega Scizor",
    "Heracronite": "Mega Heracross", "Houndoominite": "Mega Houndoom",
    "Tyranitarite": "Mega Tyranitar", "Sceptilite": "Mega Sceptile", "Blazikenite": "Mega Blaziken",
    "Swampertite": "Mega Swampert", "Gardevoirite": "Mega Gardevoir", "Sablenite": "Mega Sableye",
    "Mawilite": "Mega Mawile", "Aggronite": "Mega Aggron", "Medichamite": "Mega Medicham",
    "Manectite": "Mega Manectric", "Sharpedonite": "Mega Sharpedo", "Cameruptite": "Mega Camerupt",
    "Altarianite": "Mega Altaria", "Banettite": "Mega Banette", "Absolite": "Mega Absol",
    "Glalitite": "Mega Glalie", "Salamencite": "Mega Salamence", "Metagrossite": "Mega Metagross",
    "Latiasite": "Mega Latias", "Latiosite": "Mega Latios", "Lopunnite": "Mega Lopunny",
    "Garchompite": "Mega Garchomp", "Lucarionite": "Mega Lucario", "Abomasite": "Mega Abomasnow",
    "Galladite": "Mega Gallade", "Audinite": "Mega Audino", "Diancite": "Mega Diancie",
    "Blue Orb": "Primal Kyogre", "Red Orb": "Primal Groudon",
}


def _held_item_art(data):
    """Art option picked by the held item (Mega Stone, Primal orb), or None."""
    want = MEGA_STONES.get(data.get("held_item_name") or "")
    for o in data.get("mega_options") or []:
        if o["name"] == want:
            return o
    return None


# Base stats for forms whose stats differ from the base form (pokedex_stats.csv only has one
# row per species). Normal Forme and other unlisted forms keep the stats the decoder worked out.
_FORM_STATS_PATH = os.path.join(os.path.dirname(__file__), "form_stats.csv")
FORM_STATS = {}   # (dex, form) -> {"hp": .., "atk": .., "def": .., "spa": .., "spd": .., "spe": ..}
with open(_FORM_STATS_PATH, newline="", encoding="utf-8-sig") as _f:
    for _row in csv.DictReader(_f):
        FORM_STATS[(int(_row["national_number"]), int(_row["form"]))] = {
            "hp": int(_row["hp"]), "atk": int(_row["attack"]), "def": int(_row["defense"]),
            "spa": int(_row["sp_attack"]), "spd": int(_row["sp_defense"]), "spe": int(_row["speed"])}

_HYPER_NAMES = {"hp": "HP", "atk": "Attack", "def": "Defense", "spa": "Sp. Atk", "spd": "Sp. Def", "spe": "Speed"}


def _apply_form_stats(data):
    """Recomputes the stats with the form's own base stats (same formulas the decoders use)."""
    base = FORM_STATS.get((data.get("national_dex"), data.get("form") or 0))
    level = data.get("level")
    if not base or not level or "stat_atk" not in data:
        return
    inc = dec = None
    for name, up, down in NATURES:
        if name == data.get("nature") and up != down:
            inc, dec = up, down
    hyper = data.get("hyper_trained") or []

    def iv(k):
        return 31 if _HYPER_NAMES[k] in hyper else data[f"iv_{k}"]

    data["hp_max"] = calc_hp_stat(base["hp"], iv("hp"), data["ev_hp"], level)
    for k in ("atk", "def", "spa", "spd", "spe"):
        mod = 1.1 if k == inc else 0.9 if k == dec else 1.0
        data[f"stat_{k}"] = calc_other_stat(base[k], iv(k), data[f"ev_{k}"], level, mod)


_GEN3_DEOXYS_FORM = {4: 1, 5: 2, 3: 3}   # Gen 3 origin version -> Deoxys form


def read_pk_file(path: str) -> dict:
    """Reads a .pk<gen> file from disk and returns its decoded fields."""
    ext = os.path.splitext(path)[1].lower()
    decoder = _EXT_TO_DECODER.get(ext)
    if decoder is None:
        supported = ", ".join(sorted(_EXT_TO_DECODER))
        raise ValueError(f"No decoder yet for '{ext}' files (supported so far: {supported})")
    with open(path, "rb") as f:
        raw = f.read()
        data = decoder(raw)
    if data.get("generation") == 3 and data.get("national_dex") == 386 and not data.get("form"):
        # Gen 3 files have no form field: Deoxys takes the form of the game it is in, so use the
        # origin game (FireRed = Attack, LeafGreen = Defense, Emerald = Speed, others Normal).
        data["form"] = _GEN3_DEOXYS_FORM.get(data.get("origin_version"), 0)
        data["form_from_origin_game"] = True
    info = form_info(data)
    if info:
        data["species_name"] = info["display_name"]
        data["form_art_key"] = info["art_key"]
        data["is_alternate_form"] = info["is_alternate_form"]
    _apply_form_stats(data)
    data["met_location_name"] = met_location_name(data)
    data["egg_location_name"] = egg_location_name(data)
    data["mega_options"] = mega_options(data)
    data["gmax_options"] = gmax_options(data)
    data["art_options"] = art_options(data)
    if data.get("national_dex") == 487 and not data.get("form") and data.get("held_item_name") == "Griseous Orb":
        origin = dict(data, form=1)   # the file's own form number is left as stored
        info = form_info(origin)
        data["species_name"] = info["display_name"]
        data["form_art_key"] = info["art_key"]
        data["is_alternate_form"] = True
        data["art_options"] = art_options(origin)
    item_art = _held_item_art(data)
    if item_art:
        data["form_art_key"] = item_art["art_key"]
        data["held_item_art"] = item_art["name"]
        data["art_options"] = [o for o in data["art_options"] if o["art_key"] == item_art["art_key"]] + \
                              [o for o in data["art_options"] if o["art_key"] != item_art["art_key"]]
    return data
