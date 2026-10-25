"""Gen 4 (.pk4 / .pt4-style) decoder. 136- or 236-byte files.

Handles both plain (PKHeX/PKMDS-style) and encrypted+shuffled data:
if the stored checksum doesn't match the raw bytes, it decrypts and unshuffles.
"""
import csv
import itertools
import os
import struct

from .species_data import (
    dex_name, dex_base_stats, growth_rate, level_from_exp,
    calc_hp_stat, calc_other_stat, nature_from_pid, gender_from_pid, move_name, ability_name, item_name_gen
)

_DIR = os.path.dirname(__file__)
_ORDERS = ["".join(p) for p in itertools.permutations("ABCD")]  # index = shift value

NATURES = ["Hardy", "Lonely", "Brave", "Adamant", "Naughty", "Bold", "Docile",
           "Relaxed", "Impish", "Lax", "Timid", "Hasty", "Serious", "Jolly",
           "Naive", "Modest", "Mild", "Quiet", "Bashful", "Rash", "Calm",
           "Gentle", "Sassy", "Careful", "Quirky"]

BALLS = {1: "Master Ball", 2: "Ultra Ball", 3: "Great Ball", 4: "Poke Ball",
         5: "Safari Ball", 6: "Net Ball", 7: "Dive Ball", 8: "Nest Ball",
         9: "Repeat Ball", 10: "Timer Ball", 11: "Luxury Ball", 12: "Premier Ball",
         13: "Dusk Ball", 14: "Heal Ball", 15: "Quick Ball", 16: "Cherish Ball",
         17: "Fast Ball", 18: "Level Ball", 19: "Lure Ball", 20: "Heavy Ball",
         21: "Love Ball", 22: "Friend Ball", 23: "Moon Ball", 24: "Sport Ball"}

GAMES = {1: "Sapphire", 2: "Ruby", 3: "Emerald", 4: "FireRed", 5: "LeafGreen",
         7: "HeartGold", 8: "SoulSilver", 10: "Diamond", 11: "Pearl",
         12: "Platinum", 15: "Colosseum/XD"}

_RIB1 = ["Gen4 Champion", "Ability", "Great Ability", "Double Ability", "Multi Ability",
         "Pair Ability", "World Ability", "Alert", "Shock", "Downcast", "Careless",
         "Relax", "Snooze", "Smile", "Gorgeous", "Royal", "Gorgeous Royal",
         "Footprint", "Record", "History", "Legend", "Red", "Green", "Blue",
         "Festival", "Carnival", "Classic", "Premier"]
_CONTEST = ["Cool", "Beauty", "Cute", "Smart", "Tough"]
_RIB2 = [f"Sinnoh {c} {r}".strip() for c in _CONTEST for r in ("", "Great", "Ultra", "Master")]
_HOENN = ([f"Hoenn {c} {r}".strip() for c in _CONTEST for r in ("", "Super", "Hyper", "Master")]
          + ["Gen 3 Champion", "Winning", "Victory", "Artist", "Effort", "Marine", "Land",
             "Sky", "Country", "National", "Earth", "World"])


def _load_chars():
    path = os.path.join(_DIR, "character_table_gen4.csv")
    table = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    # Row labels in the CSV are mangled; rely on position: data row k = codes (k-1)*16..
    for k, row in enumerate(rows[1:]):
        for col, ch in enumerate(row[1:17]):
            if ch and ch != "\u2400":
                table[k * 16 + col] = ch
    return table


_CHARS = _load_chars()


def item_name(i):
    return item_name_gen(4, i)


def _text(b):
    out = []
    for (c,) in struct.iter_unpack("<H", b[: len(b) // 2 * 2]):
        if c == 0xFFFF:
            break
        out.append(_CHARS.get(c, "?"))
    return "".join(out)


def _checksum(d):
    return sum(struct.unpack_from("<64H", d, 8)) & 0xFFFF


def _xor_stream(buf, seed):
    out = bytearray(buf)
    x = seed
    for i in range(0, len(out) - 1, 2):
        x = (0x41C64E6D * x + 0x6073) & 0xFFFFFFFF
        w = int.from_bytes(out[i:i + 2], "little") ^ (x >> 16)
        out[i:i + 2] = w.to_bytes(2, "little")
    return out


def _normalize(raw):
    """Return (plain bytes, was_encrypted). Raises ValueError if checksum can't be satisfied."""
    if len(raw) < 136:
        raise ValueError(f"Gen 4 file too short: {len(raw)} bytes")
    pid = struct.unpack_from("<I", raw, 0)[0]
    stored = struct.unpack_from("<H", raw, 6)[0]
    if _checksum(raw) == stored:
        return bytes(raw), False
    body = _xor_stream(raw[8:136], stored)
    order = _ORDERS[((pid & 0x3E000) >> 13) % 24]
    plain = bytearray(raw)
    for pos, letter in enumerate(order):  # stored block `pos` holds block `letter`
        dst = 8 + "ABCD".index(letter) * 32
        plain[dst:dst + 32] = body[pos * 32:(pos + 1) * 32]
    if _checksum(plain) != stored:
        raise ValueError("Gen 4 checksum mismatch (not plain, not decryptable)")
    if len(raw) > 136:
        plain[136:] = _xor_stream(raw[136:], pid)
    return bytes(plain), True


def _bits(value, names):
    return [n + " Ribbon" for i, n in enumerate(names) if value >> i & 1]


def decode_gen4(raw: bytes) -> dict:
    d, encrypted = _normalize(raw)
    pid, flags, checksum = struct.unpack_from("<IHH", d, 0)
    species, held = struct.unpack_from("<HH", d, 0x08)
    tid, sid, exp = struct.unpack_from("<HHI", d, 0x0C)
    friendship, ability, markings, language = d[0x14:0x18]
    ev_hp, ev_atk, ev_def, ev_spe, ev_spa, ev_spd = d[0x18:0x1E]
    moves = list(struct.unpack_from("<4H", d, 0x28))
    pp = list(d[0x30:0x34])
    ppups = list(d[0x34:0x38])
    ivword = struct.unpack_from("<I", d, 0x38)[0]
    iv_hp, iv_atk, iv_def, iv_spe, iv_spa, iv_spd = [(ivword >> (5 * i)) & 31 for i in range(6)]
    rib1 = struct.unpack_from("<I", d, 0x24)[0]
    hoenn = struct.unpack_from("<I", d, 0x3C)[0]
    rib2 = struct.unpack_from("<I", d, 0x60)[0]
    b40 = d[0x40]
    met_y, met_m, met_d = d[0x7B:0x7E]
    egg_y, egg_m, egg_d = d[0x78:0x7B]
    ball_id = d[0x86] or d[0x83]
    origin = d[0x5F]

    national_dex = species if 1 <= species <= 493 else None
    nature_name, nature_inc, nature_dec = nature_from_pid(pid)
    level = None
    stats = {}
    if national_dex is not None:
        level = level_from_exp(national_dex, exp)
        base = dex_base_stats(national_dex)
        if base and level:
            def _mod(k):
                return 1.1 if k == nature_inc else 0.9 if k == nature_dec else 1.0
            stats = {
                "hp_max":   calc_hp_stat(base["hp"], iv_hp, ev_hp, level),
                "stat_atk": calc_other_stat(base["atk"], iv_atk, ev_atk, level, _mod("atk")),
                "stat_def": calc_other_stat(base["def"], iv_def, ev_def, level, _mod("def")),
                "stat_spe": calc_other_stat(base["spe"], iv_spe, ev_spe, level, _mod("spe")),
                "stat_spa": calc_other_stat(base["spa"], iv_spa, ev_spa, level, _mod("spa")),
                "stat_spd": calc_other_stat(base["spd"], iv_spd, ev_spd, level, _mod("spd")),
            }

    result = {
        "generation": 4,
        "encrypted_source": encrypted,
        "pid": pid,
        "trainer_id": tid,
        "secret_id": sid,
        "language": language,
        "is_bad_egg": bool(flags >> 2 & 1),
        "is_egg": bool(ivword >> 30 & 1),
        "checksum_valid": True,   # _normalize raises if it can't be satisfied
        "internal_index": species,
        "national_dex": national_dex,
        "species_known": national_dex is not None,
        "species_confident": national_dex is not None,
        "species_name": dex_name(national_dex) if national_dex else None,
        "gender": gender_from_pid(national_dex, pid) if national_dex else None,
        "gender_flag_female": bool(b40 >> 1 & 1),
        "gender_flag_unknown": bool(b40 >> 2 & 1),
        "form": b40 >> 3,
        "held_item": held,
        "held_item_name": item_name(held) if held else None,
        "experience": exp,
        "nature": nature_name,
        "growth_rate": growth_rate(national_dex) if national_dex else None,
        "level": level,
        "move_pp_ups": ppups,
        "friendship": friendship,
        "ability_id": ability,
        "ability": ability_name(ability),
        "markings": markings,
        "moves": moves,
        "move_names": [move_name(m) for m in moves],
        "move_pp": pp,
        "ev_hp": ev_hp, "ev_atk": ev_atk, "ev_def": ev_def,
        "ev_spe": ev_spe, "ev_spa": ev_spa, "ev_spd": ev_spd,
        "iv_hp": iv_hp, "iv_atk": iv_atk, "iv_def": iv_def,
        "iv_spe": iv_spe, "iv_spa": iv_spa, "iv_spd": iv_spd,
        "pokerus_strain": d[0x82] >> 4,
        "pokerus_days": d[0x82] & 0xF,
        "met_location": struct.unpack_from("<H", d, 0x46)[0] or struct.unpack_from("<H", d, 0x80)[0],
        "met_location_dp": struct.unpack_from("<H", d, 0x80)[0],
        "met_loc_source": "0x46" if struct.unpack_from("<H", d, 0x46)[0] else "0x80",
        "egg_location": struct.unpack_from("<H", d, 0x44)[0] or struct.unpack_from("<H", d, 0x7E)[0],
        "met_level": d[0x84] & 0x7F,
        "met_date": (2000 + met_y, met_m, met_d) if met_m else None,
        "egg_date": (2000 + egg_y, egg_m, egg_d) if egg_m else None,
        "encounter_type": d[0x85],
        "origin_version": origin,
        "origin_game": GAMES.get(origin, f"Unknown ({origin})"),
        "ball": ball_id,
        "ball_name": BALLS.get(ball_id, f"Unknown ({ball_id})"),
        "ribbons": _bits(rib1, _RIB1) + _bits(rib2, _RIB2) + _bits(hoenn, _HOENN),
        "is_shiny": (tid ^ sid ^ (pid >> 16) ^ (pid & 0xFFFF)) < 8,
        "ot_gender": d[0x84] >> 7,
        "nickname": _text(d[0x48:0x5E]),
        "ot_name": _text(d[0x68:0x78]),
        "nicknamed": bool(ivword >> 31 & 1),
        "fateful": bool(b40 & 1),
    }
    result.update(stats)
    if len(d) >= 236:
        result["status_condition"] = d[0x88]
        hp_cur = struct.unpack_from("<H", d, 0x8E)[0]
        result["hp_current"] = hp_cur if hp_cur > 0 else result.get("hp_max")
    return result
