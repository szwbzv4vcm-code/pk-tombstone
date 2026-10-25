"""
Static species-level reference data: NOT decoded from any .pk file's bytes.

This is the other half of the answer to "does the hex contain everything":
a species' name, type, and base stats are properties of the SPECIES, not
the individual Pokémon, so the games never store them in an individual's
save data at all (Gen 1 is a partial exception -- see gen1_2.py, which
stores type directly per-individual and needs no lookup here). Everything
below is the same kind of fixed table the games themselves keep in ROM.

Source: names, types, and base stats are loaded from pokedex_stats.csv
(bundled alongside this file), a user-provided reference sheet covering
National Dex #1-1025, cross-checked and confirmed accurate against a real
Breloom sample (base stats matched exactly). IMPORTANT CORRECTION
APPLIED: that sheet reflects current (post-Generation VI) types, which
introduced the Fairy type retroactively. For Gen 1/2 purposes we want the
ORIGINAL type those species actually had in-game at the time -- so
Clefairy/Clefable/Jigglypuff/Wigglytuff/Togepi/Togetic/Cleffa/Igglybuff/
Snubbull/Granbull/Marill/Azumarill are restored to Normal (or Water for
the Marill line), and Mr. Mime to pure Psychic, matching how these games
actually typed them. No other generation-specific type differences (e.g.
the Steel type not existing pre-Gen 2) are corrected yet.

COVERAGE:
  - Names, types, base stats: National Dex #1-1025 (whatever the CSV
    covers), via dex_name() / dex_type() / dex_base_stats().
  - Gender ratio: a curated set of known exceptions (single-gender
    species, genderless species, and 7:1 starter lines); every other
    species defaults to a standard 50/50 ratio, which is correct for
    the large majority but could be wrong for a non-standard ratio we
    haven't catalogued yet (ask to have a specific species checked).
  - Growth rate: covered for Gen 1-3 species by name-based lookup tables
    sourced from Bulbapedia category pages (Erratic, Fluctuating, Slow,
    Fast, Medium-Slow all explicitly assigned; everything else defaults to
    Medium-Fast which is the largest group at ~402 species). Validated
    against Breloom (confirmed Fluctuating, level 24 at EXP 11155).
    May be incomplete for some Gen 3 species not yet in the confirmed lists.
"""

import csv
import os

_CSV_PATH = os.path.join(os.path.dirname(__file__), "pokedex_stats.csv")

SPECIES_NAMES = {}
SPECIES_TYPES = {}
BASE_STATS = {}
PERCENT_MALE = {}   # dex -> float, or None for genderless


def _load_csv():
    with open(_CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                dex = int(row["national_number"])
            except (KeyError, ValueError):
                continue
            SPECIES_NAMES[dex] = row["english_name"]
            type1 = (row.get("primary_type") or "").strip().capitalize() or None
            type2 = (row.get("secondary_type") or "").strip().capitalize() or None
            pm = (row.get("percent_male") or "").strip()
            PERCENT_MALE[dex] = float(pm) if pm else None
            SPECIES_TYPES[dex] = (type1, type2)
            try:
                BASE_STATS[dex] = {
                    "hp": int(row["hp"]), "atk": int(row["attack"]),
                    "def": int(row["defense"]), "spa": int(row["sp_attack"]),
                    "spd": int(row["sp_defense"]), "spe": int(row["speed"]),
                }
            except (KeyError, ValueError):
                pass


_load_csv()

# Historical correction: restore pre-Fairy-type (Gen 1-5) typing for
# species the CSV lists with the retroactive Fairy type -- see module
# docstring for the full reasoning.
_PRE_FAIRY_TYPES = {
    35: ("Normal", None), 36: ("Normal", None),    # Clefairy/Clefable
    39: ("Normal", None), 40: ("Normal", None),    # Jigglypuff/Wigglytuff
    122: ("Psychic", None),                        # Mr. Mime
    173: ("Normal", None), 174: ("Normal", None),  # Cleffa/Igglybuff
    175: ("Normal", None), 176: ("Normal", "Flying"),  # Togepi/Togetic
    183: ("Water", None), 184: ("Water", None),    # Marill/Azumarill
    209: ("Normal", None), 210: ("Normal", None),  # Snubbull/Granbull
}
SPECIES_TYPES.update(_PRE_FAIRY_TYPES)

# Attack-IV threshold (0-15 scale). Female if Attack IV <= threshold.
# "M" / "F" = always that gender (formula not used); "U" = genderless.
# Anything NOT listed here defaults to a standard 50/50 ratio (threshold=7)
# in gender_from_attack_iv() below -- the overwhelming majority of species
# really are 50/50, so this table only needs to catalog the exceptions.
# A small number of non-standard-but-not-50/50 ratios beyond what's listed
# here may still exist and would incorrectly fall back to 50/50; flag it
# if a specific species' gender looks wrong and we'll add it.
GENDER_RATIO = {
    # Genderless
    81: "U", 82: "U",    # Magnemite/Magneton
    100: "U", 101: "U",  # Voltorb/Electrode
    120: "U", 121: "U",  # Staryu/Starmie
    132: "U",            # Ditto
    137: "U", 233: "U",  # Porygon/Porygon2
    150: "U", 151: "U",  # Mewtwo/Mew
    144: "U", 145: "U", 146: "U",  # Legendary birds
    243: "U", 244: "U", 245: "U",  # Legendary beasts
    249: "U", 250: "U", 251: "U",  # Lugia/Ho-Oh/Celebi
    201: "U",            # Unown
    # Always male
    32: "M", 33: "M", 34: "M",   # Nidoran-M family (evolved from the male-only Nidoran♂)
    106: "M", 107: "M", 237: "M", 236: "M",  # Hitmonlee/Hitmonchan/Hitmontop + baby Tyrogue
    128: "M",            # Tauros
    # Always female
    29: "F", 30: "F", 31: "F",   # Nidoran-F family (evolved from the female-only Nidoran♀)
    113: "F", 242: "F",  # Chansey/Blissey
    115: "F",            # Kangaskhan
    124: "F", 238: "F",  # Jynx + baby Smoochum
    241: "F",            # Miltank
    # 7:1 male:female (threshold=1) -- the Kanto/Johto starter lines
    4: 1, 5: 1, 6: 1, 7: 1, 8: 1, 9: 1, 1: 1, 2: 1, 3: 1,
    152: 1, 153: 1, 154: 1, 155: 1, 156: 1, 157: 1, 158: 1, 159: 1, 160: 1,
}

DEFAULT_GENDER_THRESHOLD = 7  # Standard 50/50 ratio

# The 25 natures, indexed by (PID % 25) -- the standard, well-documented
# formula. Each nature raises one stat by 10% and lowers a different one
# by 10%, except the 5 "neutral" natures (where increased == decreased),
# which have no effect at all. Order and stat keys match BASE_STATS'
# "atk"/"def"/"spa"/"spd"/"spe".
NATURES = [
    ("Hardy", "atk", "atk"), ("Lonely", "atk", "def"), ("Brave", "atk", "spe"),
    ("Adamant", "atk", "spa"), ("Naughty", "atk", "spd"),
    ("Bold", "def", "atk"), ("Docile", "def", "def"), ("Relaxed", "def", "spe"),
    ("Impish", "def", "spa"), ("Lax", "def", "spd"),
    ("Timid", "spe", "atk"), ("Hasty", "spe", "def"), ("Serious", "spe", "spe"),
    ("Jolly", "spe", "spa"), ("Naive", "spe", "spd"),
    ("Modest", "spa", "atk"), ("Mild", "spa", "def"), ("Quiet", "spa", "spe"),
    ("Bashful", "spa", "spa"), ("Rash", "spa", "spd"),
    ("Calm", "spd", "atk"), ("Gentle", "spd", "def"), ("Sassy", "spd", "spe"),
    ("Careful", "spd", "spa"), ("Quirky", "spd", "spd"),
]


def dex_name(national_dex):
    return SPECIES_NAMES.get(national_dex)


def dex_type(national_dex):
    """Returns (type1, type2_or_None), or (None, None) if this dex number
    isn't in the reference sheet."""
    return SPECIES_TYPES.get(national_dex, (None, None))


def dex_base_stats(national_dex):
    """Returns a dict with keys hp/atk/def/spa/spd/spe, or None if this
    dex number isn't in the reference sheet."""
    return BASE_STATS.get(national_dex)


def gender_from_attack_iv(national_dex, atk_iv):
    """Gen 2's real gender formula: female if Attack IV <= the species'
    gender-ratio threshold, else male; fixed-gender/genderless species
    skip the formula entirely. Species not in our exceptions table use
    the standard 50/50 threshold, which is correct for the large
    majority of species -- see GENDER_RATIO's comment for the caveat."""
    ratio = GENDER_RATIO.get(national_dex, DEFAULT_GENDER_THRESHOLD)
    if ratio == "M":
        return "Male"
    if ratio == "F":
        return "Female"
    if ratio == "U":
        return "Genderless"
    return "Female" if atk_iv <= ratio else "Male"

def gender_from_pid(national_dex, pid):
    """Gen 3+ gender from the PID's lowest byte, using percent_male
    from the CSV. Blank = genderless."""
    if national_dex not in PERCENT_MALE:
        return None
    pm = PERCENT_MALE[national_dex]
    if pm is None:
        return "Genderless"
    if pm == 100:
        return "Male"
    if pm == 0:
        return "Female"
    # Female threshold on the 0-255 scale: 87.5% male -> 31, 50% -> 127, etc.
    threshold = int((100 - pm) / 100 * 256) - 1
    return "Female" if (pid & 0xFF) < threshold else "Male"


def nature_from_pid(pid: int):
    """Returns (name, increased_stat_key_or_None, decreased_stat_key_or_None).
    The two keys are None for the 5 neutral natures (no effect)."""
    name, inc, dec = NATURES[pid % 25]
    if inc == dec:
        return name, None, None
    return name, inc, dec


def calc_hp_stat(base: int, iv: int, ev: int, level: int) -> int:
    """Standard Gen 3+ HP formula. Verified against a real Breloom
    (base 60, IV 5, EV 0, level 24 -> 64), confirmed correct."""
    return ((2 * base + iv + ev // 4) * level) // 100 + level + 10


def calc_other_stat(base: int, iv: int, ev: int, level: int, nature_mod: float = 1.0) -> int:
    """Standard Gen 3+ non-HP stat formula (Attack/Defense/Sp.Atk/Sp.Def/
    Speed). nature_mod should be 1.1 if this stat is the nature's
    increased stat, 0.9 if decreased, 1.0 otherwise. NOT YET cross-checked
    against a real non-HP stat value -- see module docstring."""
    raw = ((2 * base + iv + ev // 4) * level) // 100 + 5
    return int(raw * nature_mod)


def _min_exp_for_level(level: int, curve: str) -> int:
    """Minimum EXP required to be at `level` for a given growth curve."""
    if level <= 1:
        return 0
    n = level
    if curve == 'medium-fast':
        return n ** 3
    if curve == 'fast':
        return (4 * n ** 3) // 5
    if curve == 'slow':
        return (5 * n ** 3) // 4
    if curve == 'medium-slow':
        return max(0, int(6 / 5 * n ** 3 - 15 * n ** 2 + 100 * n - 140))
    if curve == 'erratic':
        if n <= 50:
            return int(n ** 3 * (100 - n) / 50)
        if n <= 68:
            return int(n ** 3 * (150 - n) / 100)
        if n <= 98:
            return int(n ** 3 * int((1911 - 10 * n) / 3) / 500)
        return int(n ** 3 * (160 - n) / 100)
    if curve == 'fluctuating':
        if n <= 15:
            return int(n ** 3 * (int((n + 1) / 3) + 24) / 50)
        if n <= 35:
            return int(n ** 3 * (n + 14) / 50)
        return int(n ** 3 * (int(n / 2) + 32) / 50)
    return n ** 3  # fallback to medium-fast


# Growth rate per species, from experience_speed_byspecies.csv (dex -> curve name).
_GROWTH_CSV_PATH = os.path.join(os.path.dirname(__file__), "experience_speed_byspecies.csv")
_GROWTH_NAMES = {
    "medium fast": "medium-fast", "medium slow": "medium-slow", "slow": "slow",
    "fast": "fast", "erratic": "erratic", "fluctuating": "fluctuating",
}
GROWTH_BY_DEX = {}


def _load_growth():
    with open(_GROWTH_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                dex = int(row["National Dex#"])
            except (KeyError, ValueError):
                continue
            name = _GROWTH_NAMES.get(row["Experience type"].strip().lower())
            if name:
                GROWTH_BY_DEX[dex] = name


_load_growth()


def growth_rate(national_dex: int) -> str:
    """Returns the growth rate curve name for a species. A dex number missing
    from the CSV falls back to 'medium-fast' (so level_from_exp still works)."""
    return GROWTH_BY_DEX.get(national_dex, "medium-fast")


def level_from_exp(national_dex: int, exp: int) -> int:
    """Derives the current level from stored EXP, using the species'
    growth rate curve. Returns level 1 if exp is 0 or very small."""
    curve = growth_rate(national_dex)
    for lvl in range(100, 0, -1):
        if _min_exp_for_level(lvl, curve) <= exp:
            return lvl
    return 1


GEN3_INDEX_TO_DEX = {
    1: 1,  # Bulbasaur
    2: 2,  # Ivysaur
    3: 3,  # Venusaur
    4: 4,  # Charmander
    5: 5,  # Charmeleon
    6: 6,  # Charizard
    7: 7,  # Squirtle
    8: 8,  # Wartortle
    9: 9,  # Blastoise
    10: 10,  # Caterpie
    11: 11,  # Metapod
    12: 12,  # Butterfree
    13: 13,  # Weedle
    14: 14,  # Kakuna
    15: 15,  # Beedrill
    16: 16,  # Pidgey
    17: 17,  # Pidgeotto
    18: 18,  # Pidgeot
    19: 19,  # Rattata
    20: 20,  # Raticate
    21: 21,  # Spearow
    22: 22,  # Fearow
    23: 23,  # Ekans
    24: 24,  # Arbok
    25: 25,  # Pikachu
    26: 26,  # Raichu
    27: 27,  # Sandshrew
    28: 28,  # Sandslash
    29: 29,  # Nidoran♀
    30: 30,  # Nidorina
    31: 31,  # Nidoqueen
    32: 32,  # Nidoran♂
    33: 33,  # Nidorino
    34: 34,  # Nidoking
    35: 35,  # Clefairy
    36: 36,  # Clefable
    37: 37,  # Vulpix
    38: 38,  # Ninetales
    39: 39,  # Jigglypuff
    40: 40,  # Wigglytuff
    41: 41,  # Zubat
    42: 42,  # Golbat
    43: 43,  # Oddish
    44: 44,  # Gloom
    45: 45,  # Vileplume
    46: 46,  # Paras
    47: 47,  # Parasect
    48: 48,  # Venonat
    49: 49,  # Venomoth
    50: 50,  # Diglett
    51: 51,  # Dugtrio
    52: 52,  # Meowth
    53: 53,  # Persian
    54: 54,  # Psyduck
    55: 55,  # Golduck
    56: 56,  # Mankey
    57: 57,  # Primeape
    58: 58,  # Growlithe
    59: 59,  # Arcanine
    60: 60,  # Poliwag
    61: 61,  # Poliwhirl
    62: 62,  # Poliwrath
    63: 63,  # Abra
    64: 64,  # Kadabra
    65: 65,  # Alakazam
    66: 66,  # Machop
    67: 67,  # Machoke
    68: 68,  # Machamp
    69: 69,  # Bellsprout
    70: 70,  # Weepinbell
    71: 71,  # Victreebel
    72: 72,  # Tentacool
    73: 73,  # Tentacruel
    74: 74,  # Geodude
    75: 75,  # Graveler
    76: 76,  # Golem
    77: 77,  # Ponyta
    78: 78,  # Rapidash
    79: 79,  # Slowpoke
    80: 80,  # Slowbro
    81: 81,  # Magnemite
    82: 82,  # Magneton
    83: 83,  # Farfetch'd
    84: 84,  # Doduo
    85: 85,  # Dodrio
    86: 86,  # Seel
    87: 87,  # Dewgong
    88: 88,  # Grimer
    89: 89,  # Muk
    90: 90,  # Shellder
    91: 91,  # Cloyster
    92: 92,  # Gastly
    93: 93,  # Haunter
    94: 94,  # Gengar
    95: 95,  # Onix
    96: 96,  # Drowzee
    97: 97,  # Hypno
    98: 98,  # Krabby
    99: 99,  # Kingler
    100: 100,  # Voltorb
    101: 101,  # Electrode
    102: 102,  # Exeggcute
    103: 103,  # Exeggutor
    104: 104,  # Cubone
    105: 105,  # Marowak
    106: 106,  # Hitmonlee
    107: 107,  # Hitmonchan
    108: 108,  # Lickitung
    109: 109,  # Koffing
    110: 110,  # Weezing
    111: 111,  # Rhyhorn
    112: 112,  # Rhydon
    113: 113,  # Chansey
    114: 114,  # Tangela
    115: 115,  # Kangaskhan
    116: 116,  # Horsea
    117: 117,  # Seadra
    118: 118,  # Goldeen
    119: 119,  # Seaking
    120: 120,  # Staryu
    121: 121,  # Starmie
    122: 122,  # Mr. Mime
    123: 123,  # Scyther
    124: 124,  # Jynx
    125: 125,  # Electabuzz
    126: 126,  # Magmar
    127: 127,  # Pinsir
    128: 128,  # Tauros
    129: 129,  # Magikarp
    130: 130,  # Gyarados
    131: 131,  # Lapras
    132: 132,  # Ditto
    133: 133,  # Eevee
    134: 134,  # Vaporeon
    135: 135,  # Jolteon
    136: 136,  # Flareon
    137: 137,  # Porygon
    138: 138,  # Omanyte
    139: 139,  # Omastar
    140: 140,  # Kabuto
    141: 141,  # Kabutops
    142: 142,  # Aerodactyl
    143: 143,  # Snorlax
    144: 144,  # Articuno
    145: 145,  # Zapdos
    146: 146,  # Moltres
    147: 147,  # Dratini
    148: 148,  # Dragonair
    149: 149,  # Dragonite
    150: 150,  # Mewtwo
    151: 151,  # Mew
    152: 152,  # Chikorita
    153: 153,  # Bayleef
    154: 154,  # Meganium
    155: 155,  # Cyndaquil
    156: 156,  # Quilava
    157: 157,  # Typhlosion
    158: 158,  # Totodile
    159: 159,  # Croconaw
    160: 160,  # Feraligatr
    161: 161,  # Sentret
    162: 162,  # Furret
    163: 163,  # Hoothoot
    164: 164,  # Noctowl
    165: 165,  # Ledyba
    166: 166,  # Ledian
    167: 167,  # Spinarak
    168: 168,  # Ariados
    169: 169,  # Crobat
    170: 170,  # Chinchou
    171: 171,  # Lanturn
    172: 172,  # Pichu
    173: 173,  # Cleffa
    174: 174,  # Igglybuff
    175: 175,  # Togepi
    176: 176,  # Togetic
    177: 177,  # Natu
    178: 178,  # Xatu
    179: 179,  # Mareep
    180: 180,  # Flaaffy
    181: 181,  # Ampharos
    182: 182,  # Bellossom
    183: 183,  # Marill
    184: 184,  # Azumarill
    185: 185,  # Sudowoodo
    186: 186,  # Politoed
    187: 187,  # Hoppip
    188: 188,  # Skiploom
    189: 189,  # Jumpluff
    190: 190,  # Aipom
    191: 191,  # Sunkern
    192: 192,  # Sunflora
    193: 193,  # Yanma
    194: 194,  # Wooper
    195: 195,  # Quagsire
    196: 196,  # Espeon
    197: 197,  # Umbreon
    198: 198,  # Murkrow
    199: 199,  # Slowking
    200: 200,  # Misdreavus
    201: 201,  # Unown
    202: 202,  # Wobbuffet
    203: 203,  # Girafarig
    204: 204,  # Pineco
    205: 205,  # Forretress
    206: 206,  # Dunsparce
    207: 207,  # Gligar
    208: 208,  # Steelix
    209: 209,  # Snubbull
    210: 210,  # Granbull
    211: 211,  # Qwilfish
    212: 212,  # Scizor
    213: 213,  # Shuckle
    214: 214,  # Heracross
    215: 215,  # Sneasel
    216: 216,  # Teddiursa
    217: 217,  # Ursaring
    218: 218,  # Slugma
    219: 219,  # Magcargo
    220: 220,  # Swinub
    221: 221,  # Piloswine
    222: 222,  # Corsola
    223: 223,  # Remoraid
    224: 224,  # Octillery
    225: 225,  # Delibird
    226: 226,  # Mantine
    227: 227,  # Skarmory
    228: 228,  # Houndour
    229: 229,  # Houndoom
    230: 230,  # Kingdra
    231: 231,  # Phanpy
    232: 232,  # Donphan
    233: 233,  # Porygon2
    234: 234,  # Stantler
    235: 235,  # Smeargle
    236: 236,  # Tyrogue
    237: 237,  # Hitmontop
    238: 238,  # Smoochum
    239: 239,  # Elekid
    240: 240,  # Magby
    241: 241,  # Miltank
    242: 242,  # Blissey
    243: 243,  # Raikou
    244: 244,  # Entei
    245: 245,  # Suicune
    246: 246,  # Larvitar
    247: 247,  # Pupitar
    248: 248,  # Tyranitar
    249: 249,  # Lugia
    250: 250,  # Ho-Oh
    251: 251,  # Celebi
    277: 252,  # Treecko
    278: 253,  # Grovyle
    279: 254,  # Sceptile
    280: 255,  # Torchic
    281: 256,  # Combusken
    282: 257,  # Blaziken
    283: 258,  # Mudkip
    284: 259,  # Marshtomp
    285: 260,  # Swampert
    286: 261,  # Poochyena
    287: 262,  # Mightyena
    288: 263,  # Zigzagoon
    289: 264,  # Linoone
    290: 265,  # Wurmple
    291: 266,  # Silcoon
    292: 267,  # Beautifly
    293: 268,  # Cascoon
    294: 269,  # Dustox
    295: 270,  # Lotad
    296: 271,  # Lombre
    297: 272,  # Ludicolo
    298: 273,  # Seedot
    299: 274,  # Nuzleaf
    300: 275,  # Shiftry
    301: 290,  # Nincada
    302: 291,  # Ninjask
    303: 292,  # Shedinja
    304: 276,  # Taillow
    305: 277,  # Swellow
    306: 285,  # Shroomish
    307: 286,  # Breloom
    308: 327,  # Spinda
    309: 278,  # Wingull
    310: 279,  # Pelipper
    311: 283,  # Surskit
    312: 284,  # Masquerain
    313: 320,  # Wailmer
    314: 321,  # Wailord
    315: 300,  # Skitty
    316: 301,  # Delcatty
    317: 352,  # Kecleon
    318: 343,  # Baltoy
    319: 344,  # Claydol
    320: 299,  # Nosepass
    321: 324,  # Torkoal
    322: 302,  # Sableye
    323: 339,  # Barboach
    324: 340,  # Whiscash
    325: 370,  # Luvdisc
    326: 341,  # Corphish
    327: 342,  # Crawdaunt
    328: 349,  # Feebas
    329: 350,  # Milotic
    330: 318,  # Carvanha
    331: 319,  # Sharpedo
    332: 328,  # Trapinch
    333: 329,  # Vibrava
    334: 330,  # Flygon
    335: 296,  # Makuhita
    336: 297,  # Hariyama
    337: 309,  # Electrike
    338: 310,  # Manectric
    339: 322,  # Numel
    340: 323,  # Camerupt
    341: 363,  # Spheal
    342: 364,  # Sealeo
    343: 365,  # Walrein
    344: 331,  # Cacnea
    345: 332,  # Cacturne
    346: 361,  # Snorunt
    347: 362,  # Glalie
    348: 337,  # Lunatone
    349: 338,  # Solrock
    350: 298,  # Azurill
    351: 325,  # Spoink
    352: 326,  # Grumpig
    353: 311,  # Plusle
    354: 312,  # Minun
    355: 303,  # Mawile
    356: 307,  # Meditite
    357: 308,  # Medicham
    358: 333,  # Swablu
    359: 334,  # Altaria
    360: 360,  # Wynaut
    361: 355,  # Duskull
    362: 356,  # Dusclops
    363: 315,  # Roselia
    364: 287,  # Slakoth
    365: 288,  # Vigoroth
    366: 289,  # Slaking
    367: 316,  # Gulpin
    368: 317,  # Swalot
    369: 357,  # Tropius
    370: 293,  # Whismur
    371: 294,  # Loudred
    372: 295,  # Exploud
    373: 366,  # Clamperl
    374: 367,  # Huntail
    375: 368,  # Gorebyss
    376: 359,  # Absol
    377: 353,  # Shuppet
    378: 354,  # Banette
    379: 336,  # Seviper
    380: 335,  # Zangoose
    381: 369,  # Relicanth
    382: 304,  # Aron
    383: 305,  # Lairon
    384: 306,  # Aggron
    385: 351,  # Castform
    386: 313,  # Volbeat
    387: 314,  # Illumise
    388: 345,  # Lileep
    389: 346,  # Cradily
    390: 347,  # Anorith
    391: 348,  # Armaldo
    392: 280,  # Ralts
    393: 281,  # Kirlia
    394: 282,  # Gardevoir
    395: 371,  # Bagon
    396: 372,  # Shelgon
    397: 373,  # Salamence
    398: 374,  # Beldum
    399: 375,  # Metang
    400: 376,  # Metagross
    401: 377,  # Regirock
    402: 378,  # Regice
    403: 379,  # Registeel
    404: 382,  # Kyogre
    405: 383,  # Groudon
    406: 384,  # Rayquaza
    407: 380,  # Latias
    408: 381,  # Latios
    409: 385,  # Jirachi
    410: 386,  # Deoxys
    411: 358,  # Chimecho
    413: 201,  # Unown
    414: 201,  # Unown
    415: 201,  # Unown
    416: 201,  # Unown
    417: 201,  # Unown
    418: 201,  # Unown
    419: 201,  # Unown
    420: 201,  # Unown
    421: 201,  # Unown
    422: 201,  # Unown
    423: 201,  # Unown
    424: 201,  # Unown
    425: 201,  # Unown
    426: 201,  # Unown
    427: 201,  # Unown
    428: 201,  # Unown
    429: 201,  # Unown
    430: 201,  # Unown
    431: 201,  # Unown
    432: 201,  # Unown
    433: 201,  # Unown
    434: 201,  # Unown
    435: 201,  # Unown
    436: 201,  # Unown
    437: 201,  # Unown
    438: 201,  # Unown
    439: 201,  # Unown
}


def gen3_index_to_national_dex(internal_index: int):
    """Converts a Gen 3 internal species index to National Dex number.
    Returns (national_dex, confident) where confident is True if the
    index is in the confirmed Bulbapedia table, False otherwise."""
    dex = GEN3_INDEX_TO_DEX.get(internal_index)
    return dex, (dex is not None)


_MOVES_CSV_PATH = os.path.join(os.path.dirname(__file__), "move_index_values_gen1-9.csv")
MOVE_NAMES = {}

def _load_moves():
    with open(_MOVES_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                MOVE_NAMES[int(row["#"])] = row["Name"]
            except (KeyError, ValueError):
                continue

_load_moves()


def move_name(move_id):
    if move_id == 0:
        return None  # empty move slot
    return MOVE_NAMES.get(move_id, f"Unknown ({move_id})")

# Ability index -> name (same numbering across generations; list only grows).
_ABILITIES_CSV_PATH = os.path.join(os.path.dirname(__file__), "index_numbers_abilities_gen3-9.csv")
ABILITY_NAMES = {}

def _load_abilities():
    with open(_ABILITIES_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) > 1 and row[0].strip().isdigit() and row[1].strip():
                ABILITY_NAMES[int(row[0])] = row[1].strip()

_load_abilities()


def ability_name(ability_id):
    if not ability_id:
        return None
    return ABILITY_NAMES.get(ability_id, f"Unknown ({ability_id})")

# Gen 3 abilities per species, from abilities_by_species_gen3.csv.
# NOTE: no official Gen 3 per-species ability table was ever found. This file was
# derived from the Bulbapedia ability-by-species sheet (abilities_by_species.csv) by
# dropping abilities tagged Gen IV or later and ignoring Hidden abilities, then adding
# manual overrides (see the "note" column) where an ability was replaced in a later
# generation (Gengar, Shiftry). Fix wrong species by editing that CSV.
_GEN3_ABILITIES_CSV_PATH = os.path.join(os.path.dirname(__file__), "abilities_by_species_gen3.csv")
GEN3_ABILITIES = {}   # dex -> (ability_1, ability_2 or None)


def _load_gen3_abilities():
    with open(_GEN3_ABILITIES_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                dex = int(row["national_number"])
            except (KeyError, ValueError):
                continue
            GEN3_ABILITIES[dex] = ((row["ability_1"] or "").strip() or None,
                                   (row["ability_2"] or "").strip() or None)


_load_gen3_abilities()


def gen3_ability(national_dex, slot):
    """Gen 3 stores only a slot bit (0/1). Slot 1 gives ability_2 when the species has
    one; otherwise ability_1. Dex numbers above 386 return None."""
    a1, a2 = GEN3_ABILITIES.get(national_dex, (None, None))
    return a2 if (slot == 1 and a2) else a1


# --- Met location names: location_index_values_gen2-7.csv (side-by-side blocks) ---
_LOCATIONS_CSV_PATH = os.path.join(os.path.dirname(__file__), "location_index_values_gen2-7.csv")
_LOC_COLUMNS = {2: (0, 2), 3: (4, 6), 4: (8, 10), 5: (12, 14), 6: (17, 19), 7: (21, 23)}  # gen: (id col, name col)
LOCATION_NAMES = {g: {} for g in _LOC_COLUMNS}
_REGION_BY_ORIGIN = {1: "Hoenn", 2: "Hoenn", 3: "Hoenn", 4: "Kanto", 5: "Kanto",
                     7: "Johto", 8: "Johto", 10: "Sinnoh", 11: "Sinnoh", 12: "Sinnoh",
                     15: "Distant land"}


def _load_locations():
    import re
    with open(_LOCATIONS_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))[2:]          # skip the two header rows
    for row in rows:
        for gen, (ic, nc) in _LOC_COLUMNS.items():
            if len(row) > nc and row[ic].strip().isdigit() and row[nc].strip():
                name = re.sub(r"\[[^\]]*\]", "", row[nc]).strip().rstrip("*").strip()
                LOCATION_NAMES[gen][int(row[ic])] = name


_load_locations()

def egg_location_name(data):
    """Name of the egg-received location from data['egg_location'], or None."""
    gen = data.get("generation")
    code = data.get("egg_location")
    if gen not in LOCATION_NAMES or not code:
        return None
    return LOCATION_NAMES[gen].get(code)

def met_location_name(data):
    """Name for a decoded dict's met location, or None. Uses data['generation'],
    'met_location', 'origin_version' (and 'met_location_dp' for Gen 4)."""
    gen = data.get("generation")
    code = data.get("met_location")
    origin = data.get("origin_version")
    if gen == 4 and not code:
        code = data.get("met_location_dp")
    if gen not in LOCATION_NAMES or code is None:
        return None
    if gen == 2 and code == 0:
        return None
    # Pal Park (Gen 4) / Poke Transfer (Gen 5): displayed as a region from the origin game.
    if (gen == 4 and code == 0x37 and origin in _REGION_BY_ORIGIN) or \
       (gen == 5 and code == 30001 and origin in _REGION_BY_ORIGIN):
        return _REGION_BY_ORIGIN[origin]
    return LOCATION_NAMES[gen].get(code)


# --- Item names for Gen 2-9: item_index_values_gen2-9.csv (side-by-side blocks) ---
_ITEMS_ALL_CSV_PATH = os.path.join(os.path.dirname(__file__), "item_index_values_gen2-9.csv")
_ITEM_COLUMNS = {2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28}   # gen: first column of block
ITEM_NAMES = {g: {} for g in _ITEM_COLUMNS}


def _load_item_names():
    with open(_ITEMS_ALL_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))[3:]          # skip the three header rows
    for row in rows:
        for gen, c in _ITEM_COLUMNS.items():
            if len(row) > c + 2 and row[c].strip().isdigit() and row[c + 2].strip():
                idx = int(row[c])
                if idx not in ITEM_NAMES[gen]:   # first row wins when games share an index
                    ITEM_NAMES[gen][idx] = row[c + 2].strip().rstrip("*").strip()


_load_item_names()


def item_name_gen(gen, item_id):
    return ITEM_NAMES.get(gen, {}).get(item_id, f"Item {item_id}")

# Regional forms: (dex, form number) -> adjective used in the display name. Form numbers differ
# by species and generation, so each one is listed explicitly. Gen 7 Alolan forms are form 1.
# Galarian, Hisuian and Paldean entries get added here when those decoders exist.
# --- Alternate forms and extra art: form_table.csv -------------------------------------
# One table for every PokeAPI art id 10001-10326. kind = "form" (a form a .pk file can store),
# or battle-only art the poster can offer: "mega", "primal", "gmax", "special" (Eternamax).
# "form" is the stored form number (blank = any), "gender" is M or F (blank = either),
# gen_from/gen_to limit a form row to some generations (blank = all), "priority" orders
# species with more than one Mega (X before Y). art_id is the template image name.
_FORMS_CSV_PATH = os.path.join(os.path.dirname(__file__), "form_table.csv")
FORM_TABLE = {}   # (dex, form or None, gender) -> list of (gen_from, gen_to, name, art_id)
EXTRA_ART = {}    # dex -> list of (kind, priority, form or None, gender, name, art_id)


def _load_forms():
    with open(_FORMS_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                dex = int(row["national_number"])
            except (KeyError, ValueError):
                continue
            form = row["form"].strip()
            form = int(form) if form.isdigit() else None
            gender = (row["gender"] or "").strip().upper()[:1]
            name, art_id = row["display_name"].strip(), row["art_id"].strip()
            kind = row["kind"].strip() or "form"
            if kind == "form":
                g_from = int(row["gen_from"]) if row["gen_from"].strip().isdigit() else 0
                g_to = int(row["gen_to"]) if row["gen_to"].strip().isdigit() else 99
                FORM_TABLE.setdefault((dex, form, gender), []).append((g_from, g_to, name, art_id))
            else:
                prio = int(row["priority"]) if row["priority"].strip().isdigit() else 1
                EXTRA_ART.setdefault(dex, []).append((kind, prio, form, gender, name, art_id))


_load_forms()


def form_info(data):
    """Display name, template art id and an is_alternate_form flag for a decoded dict.
    Lookup order: exact form + gender, exact form any gender, any form + gender.
    Base forms use the national dex number as the art id."""
    dex = data.get("national_dex")
    if not dex:
        return None
    form = data.get("form") or 0
    gen = data.get("generation") or 0
    g = (data.get("gender") or "")[:1].upper()
    for key in ((dex, form, g), (dex, form, ""), (dex, None, g)):
        for g_from, g_to, name, art_id in FORM_TABLE.get(key, []):
            if g_from <= gen <= g_to:
                return {"display_name": name, "art_key": art_id, "is_alternate_form": True}
    return {"display_name": dex_name(dex), "art_key": str(dex), "is_alternate_form": False}


def _extra_art(data, kinds):
    dex = data.get("national_dex")
    form = data.get("form") or 0
    g = (data.get("gender") or "")[:1].upper()
    hits = [m for m in EXTRA_ART.get(dex, [])
            if m[0] in kinds and (m[2] is None or m[2] == form) and (not m[3] or m[3] == g)]
    return [{"name": m[4], "art_key": m[5], "kind": m[0]} for m in sorted(hits, key=lambda m: m[1])]


def mega_options(data):
    """Mega/Primal art this Pokemon could use (matching species, form, gender), best first."""
    return _extra_art(data, ("mega", "primal"))


def gmax_options(data):
    """Gigantamax art this Pokemon could use (matching species and form)."""
    return _extra_art(data, ("gmax",))


def art_options(data):
    """Every template for this species, for an 'alternate form' picker: this Pokemon's own art
    first, then the base form, other forms, and Mega/Primal/Gigantamax/special art."""
    dex = data.get("national_dex")
    if not dex:
        return []
    own = form_info(data)
    opts = [{"name": own["display_name"], "art_key": own["art_key"], "kind": "own"},
            {"name": dex_name(dex), "art_key": str(dex), "kind": "form"}]
    forms = [{"name": r[2], "art_key": r[3], "kind": "form"}
             for (d, _form, _g), rows in FORM_TABLE.items() if d == dex for r in rows]
    opts += sorted(forms, key=lambda o: (not o["art_key"].isdigit(), int(o["art_key"]) if o["art_key"].isdigit() else 0, o["art_key"]))
    opts += [{"name": m[4], "art_key": m[5], "kind": m[0]}
             for m in sorted(EXTRA_ART.get(dex, []),
                             key=lambda m: ({"mega": 0, "primal": 0, "gmax": 1}.get(m[0], 2), m[1]))]
    seen, out = set(), []
    for o in opts:
        if o["art_key"] not in seen:
            seen.add(o["art_key"])
            out.append(o)
    return out

#Imports the csv for the held item name conversion from index numbers
_ITEMS_CSV_PATH = os.path.join(os.path.dirname(__file__), "item_index_values_gen2_3.csv")
ITEM_NAMES_GEN2 = {}
ITEM_NAMES_GEN3 = {}

def _load_items():
    with open(_ITEMS_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for row in list(csv.reader(f))[2:]:  # skip the two header rows
            if len(row) > 2 and row[0].strip().isdigit() and row[2].strip():
                ITEM_NAMES_GEN3[int(row[0])] = row[2].strip()
            if len(row) > 6 and row[4].strip().isdigit() and row[6].strip():
                ITEM_NAMES_GEN2[int(row[4])] = row[6].strip()

_load_items()


def item_name(item_id, generation):
    if item_id == 0:
        return None  # no held item
    if generation == 2:
        if item_id in (195, 220):  # dummy TM04/TM28 display as Berry when held
            return "Berry"
        return ITEM_NAMES_GEN2.get(item_id, f"Unknown ({item_id})")
    return ITEM_NAMES_GEN3.get(item_id, f"Unknown ({item_id})")