"""Gen 6 (.pk6) decoder: X/Y/Omega Ruby/Alpha Sapphire. 232-byte box or 260-byte party.

UNVERIFIED against a real .pk6 export -- check with a hex dump of a known Pokemon.
Anchors from sources: sizes 232/260; four 56-byte blocks (A 0x08-0x3F, B 0x40-0x77,
C 0x78-0xAF, D 0xB0-0xE7); Encryption Constant (EC) at 0x00 seeds the LCG and drives
the shuffle (not PID, not checksum); party stats use the same EC seed and aren't
shuffled; fateful flag 0x1D, ability 0x14, ability number 0x15, OT friendship 0xCA,
OT gender 0xDD, party Speed 0xF8. Everything else is from memory of the PK6 layout.
Also accepts already-decrypted exports (checksum matches the raw bytes).

Memories, geolocations, country and handler friendship/affection come from memories6.py.
"""
import os
import struct

from .gen4 import _xor_stream, _ORDERS, NATURES
from .gen5 import BALLS5, GAMES5
from .memories6 import memory_fields
from .species_data import (
    dex_name, dex_base_stats, growth_rate, level_from_exp,
    calc_hp_stat, calc_other_stat, move_name, ability_name,item_name_gen
)

MAX_DEX = 721
GAMES6 = dict(GAMES5)
GAMES6.update({24: "X", 25: "Y", 26: "Alpha Sapphire", 27: "Omega Ruby"})  # from memory
_STAT_KEYS = ["atk", "def", "spe", "spa", "spd"]


def item_name(i):
    return item_name_gen(6, i)


def _text(b):
    out = []
    for (c,) in struct.iter_unpack("<H", b[: len(b) // 2 * 2]):
        if c in (0x0000, 0xFFFF):
            break
        c = {0xE08E: 0x2642, 0xE08F: 0x2640}.get(c, c)   # game's own ♂/♀ codes -> real symbols (verified with PKHeX)
        out.append(chr(c) if not 0xD800 <= c <= 0xDFFF else "?")
    return "".join(out)


def _checksum6(d):
    return sum(struct.unpack_from("<112H", d, 8)) & 0xFFFF


def _normalize6(raw):
    if len(raw) < 232:
        raise ValueError(f"Gen 6 file too short: {len(raw)} bytes")
    ec = struct.unpack_from("<I", raw, 0)[0]
    stored = struct.unpack_from("<H", raw, 6)[0]
    if _checksum6(raw) == stored:
        return bytes(raw), False
    body = _xor_stream(raw[8:232], ec)
    order = _ORDERS[((ec >> 13) & 31) % 24]
    plain = bytearray(raw)
    for pos, letter in enumerate(order):          # stored block `pos` holds block `letter`
        dst = 8 + "ABCD".index(letter) * 56
        plain[dst:dst + 56] = body[pos * 56:(pos + 1) * 56]
    if _checksum6(plain) != stored:
        raise ValueError("Gen 6 checksum mismatch (not plain, not decryptable)")
    if len(raw) > 232:
        plain[232:] = _xor_stream(raw[232:], ec)
    return bytes(plain), True

# Gen 6 ribbon bits, bytes 0x30-0x35 (bit 0 of each byte first). Checked against real files
# (Surskit, Beautifly, Illumise, Wurmple, Seedot). 0x34 bits 5-6 and 0x35 bits 6-7 are unused.
# The order of the six contest ribbons within 0x35 is inferred (the set of six is confirmed).
_RIB6 = [
    "Kalos Champion", "Gen 3 Champion", "Gen 4 Champion", "Best Friends",
    "Training", "Skillful Battler", "Expert Battler", "Effort",
    "Alert", "Shock", "Downcast", "Careless", "Relax", "Snooze", "Smile", "Gorgeous",
    "Royal", "Gorgeous Royal", "Artist", "Footprint", "Record", "Legend", "Country", "National",
    "Earth", "World", "Classic", "Premier", "Event", "Birthday", "Special", "Souvenir",
    "Wishing", "Battle Champion", "Regional Champion", "National Champion", "World Champion",
    None, None, "Hoenn Champion (ORAS)",
    "Contest Star", "Coolness Master", "Beauty Master", "Cuteness Master", "Cleverness Master", "Toughness Master",
]


def _ribbons6(b):
    out = []
    for byte_i, v in enumerate(b):
        for bit in range(8):
            if v >> bit & 1:
                idx = byte_i * 8 + bit
                name = _RIB6[idx] if idx < len(_RIB6) and _RIB6[idx] else f"Unknown Gen 6 ribbon (0x{0x30 + byte_i:02X} bit {bit})"
                out.append(name if name.startswith("Unknown") else name + " Ribbon")
    return out

def decode_gen6(raw: bytes) -> dict:
    d, encrypted = _normalize6(raw)
    ec, sanity, checksum = struct.unpack_from("<IHH", d, 0)
    species, held, tid, sid, exp = struct.unpack_from("<HHHHI", d, 0x08)
    ability, ability_num = d[0x14], d[0x15]
    pid = struct.unpack_from("<I", d, 0x18)[0]
    nature_id = d[0x1C] if d[0x1C] < 25 else None
    b1d = d[0x1D]
    ev_hp, ev_atk, ev_def, ev_spe, ev_spa, ev_spd = d[0x1E:0x24]
    markings, pokerus = d[0x2A], d[0x2B]
    moves = list(struct.unpack_from("<4H", d, 0x5A))
    pp = list(d[0x62:0x66])
    ppups = list(d[0x66:0x6A])
    ivword = struct.unpack_from("<I", d, 0x74)[0]
    iv_hp, iv_atk, iv_def, iv_spe, iv_spa, iv_spd = [(ivword >> (5 * i)) & 31 for i in range(6)]
    egg_y, egg_m, egg_d = d[0xD1:0xD4]
    met_y, met_m, met_d = d[0xD4:0xD7]
    egg_loc, met_loc = struct.unpack_from("<HH", d, 0xD8)
    ball = d[0xDC]
    origin = d[0xDF]

    nature_name = NATURES[nature_id] if nature_id is not None else None
    inc = dec = None
    if nature_id is not None:
        inc, dec = _STAT_KEYS[nature_id // 5], _STAT_KEYS[nature_id % 5]

    national_dex = species if 1 <= species <= MAX_DEX else None
    level = None
    stats = {}
    if national_dex is not None:
        level = level_from_exp(national_dex, exp)
        base = dex_base_stats(national_dex)
        if base and level and nature_id is not None:
            def _mod(k):
                return 1.1 if k == inc and inc != dec else 0.9 if k == dec and inc != dec else 1.0
            stats = {
                "hp_max":   calc_hp_stat(base["hp"], iv_hp, ev_hp, level),
                "stat_atk": calc_other_stat(base["atk"], iv_atk, ev_atk, level, _mod("atk")),
                "stat_def": calc_other_stat(base["def"], iv_def, ev_def, level, _mod("def")),
                "stat_spe": calc_other_stat(base["spe"], iv_spe, ev_spe, level, _mod("spe")),
                "stat_spa": calc_other_stat(base["spa"], iv_spa, ev_spa, level, _mod("spa")),
                "stat_spd": calc_other_stat(base["spd"], iv_spd, ev_spd, level, _mod("spd")),
            }

    if b1d >> 2 & 1:
        gender = "Genderless"
    else:
        gender = "Female" if b1d >> 1 & 1 else "Male"

    result = {
        "generation": 6,
        "encrypted_source": encrypted,
        "encryption_constant": ec,
        "pid": pid,
        "trainer_id": tid,
        "secret_id": sid,
        "language": d[0xE3],
        "is_bad_egg": bool(sanity >> 2 & 1),
        "is_egg": bool(ivword >> 30 & 1),
        "checksum_valid": True,
        "internal_index": species,
        "national_dex": national_dex,
        "species_known": national_dex is not None,
        "species_confident": national_dex is not None,
        "species_name": dex_name(national_dex) if national_dex else None,
        "gender": gender,
        "form": b1d >> 3,
        "fateful": bool(b1d & 1),
        "held_item": held,
        "held_item_name": item_name(held) if held else None,
        "experience": exp,
        "nature": nature_name,
        "nature_id": nature_id,
        "growth_rate": growth_rate(national_dex) if national_dex else None,
        "level": level,
        "move_pp_ups": ppups,
        "friendship": d[0xCA],
        "ability_id": ability,
        "ability": ability_name(ability),
        "ability_number": ability_num,
        "hidden_ability": bool(ability_num & 4),
        "markings": markings,
        "moves": moves,
        "move_names": [move_name(m) for m in moves],
        "move_pp": pp,
        "ev_hp": ev_hp, "ev_atk": ev_atk, "ev_def": ev_def,
        "ev_spe": ev_spe, "ev_spa": ev_spa, "ev_spd": ev_spd,
        "iv_hp": iv_hp, "iv_atk": iv_atk, "iv_def": iv_def,
        "iv_spe": iv_spe, "iv_spa": iv_spa, "iv_spd": iv_spd,
        "pokerus_strain": pokerus >> 4,
        "pokerus_days": pokerus & 0xF,
        "met_location": met_loc,
        "egg_location": egg_loc,
        "met_level": d[0xDD] & 0x7F,
        "met_date": (2000 + met_y, met_m, met_d) if met_m else None,
        "egg_date": (2000 + egg_y, egg_m, egg_d) if egg_m else None,
        "origin_version": origin,
        "origin_game": GAMES6.get(origin, f"Unknown ({origin})"),
        "ball": ball,
        "ball_name": BALLS5.get(ball, f"Unknown ({ball})"),
        "ribbons_raw": d[0x30:0x38].hex(),
        "is_shiny": (tid ^ sid ^ (pid >> 16) ^ (pid & 0xFFFF)) < 16,
        "ot_gender": d[0xDD] >> 7,
        "nickname": _text(d[0x40:0x5A]),
        "ot_name": _text(d[0xB0:0xCA]),
        "handler_name": _text(d[0x78:0x92]),
        "current_handler": d[0x93],
        "nicknamed": bool(ivword >> 31 & 1),
    }

    result.update(memory_fields(d, result["nickname"], result["ot_name"], result["handler_name"]))
    _rib = _ribbons6(d[0x30:0x36])
    result["ribbons"] = [r for r in _rib if not r.startswith("Unknown")]
    result["ribbons_unknown_bits"] = [r for r in _rib if r.startswith("Unknown")]
    if d[0x38]:   # Memory ribbons store a count (max 40 contest wins, 8 battle wins)
        result["ribbons"].append(f"Contest Memory Ribbon ({d[0x38]})")
    if d[0x39]:
        result["ribbons"].append(f"Battle Memory Ribbon ({d[0x39]})")

    result.update(stats)
    if len(d) >= 260:
        result["status_condition"] = d[0xE8]
        result["level_stored"] = d[0xEC]
        if result["level_stored"]:   # party files carry the game's own stats: prefer them
            (result["hp_max"], result["stat_atk"], result["stat_def"],
             result["stat_spe"], result["stat_spa"], result["stat_spd"]) = struct.unpack_from("<6H", d, 0xF2)
            result["level"] = result["level_stored"]
        hp_cur = struct.unpack_from("<H", d, 0xF0)[0]
        result["hp_current"] = hp_cur if hp_cur > 0 else result.get("hp_max")
    return result
