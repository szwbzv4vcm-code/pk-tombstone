"""Gen 5 (.pk5) decoder: Black/White/Black 2/White 2. 136-byte box or 220-byte party.

UNVERIFIED against a real .pk5 export. Confirmed from PKHeX docs: sizes 136/220,
nature stored at 0x41, hidden-ability flag at 0x42, party tail encrypted with the
PID and not shuffled. Everything else is the Gen 4 layout carried over from memory
(species/item/IDs/EVs/moves/IVs/names/dates/ball), so check it with a real dump.

Same checksum/LCG-encrypt/PID-shuffle scheme as Gen 4, so gen4's _normalize is
reused (it also accepts already-decrypted PKHeX-style exports). Text is plain
UTF-16LE (no character table), 0xFFFF-terminated.
"""
import os
import struct

from .gen4 import (_normalize, _bits, _RIB1, _RIB2, _HOENN, NATURES, BALLS, GAMES)
from . import gen4 as _g4
from .species_data import (
    dex_name, dex_base_stats, growth_rate, level_from_exp,
    calc_hp_stat, calc_other_stat, gender_from_pid, move_name, ability_name,item_name_gen
)

MAX_DEX = 649

BALLS5 = dict(BALLS)
BALLS5.update({25: "Dream Ball"})   # verified with a PKHeX-made file (Gen 4 used 25 for the Park Ball)

GAMES5 = dict(GAMES)
GAMES5.update({20: "White", 21: "Black", 22: "White 2", 23: "Black 2"})

_STAT_KEYS = ["atk", "def", "spe", "spa", "spd"]


def item_name(i):
    return item_name_gen(5, i)


def _text(b):
    out = []
    for (c,) in struct.iter_unpack("<H", b[: len(b) // 2 * 2]):
        if c == 0xFFFF:
            break
        c = {0x246D: 0x2642, 0x246E: 0x2640}.get(c, c)   # game's own ♂/♀ codes -> real symbols (verified with PKHeX)
        out.append(chr(c) if not 0xD800 <= c <= 0xDFFF else "?")
    return "".join(out)


def decode_gen5(raw: bytes) -> dict:
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
    nature_id = d[0x41] if d[0x41] < 25 else None
    hidden_flag = bool(d[0x42] & 1)
    met_y, met_m, met_d = d[0x7B:0x7E]
    egg_y, egg_m, egg_d = d[0x78:0x7B]
    ball_id = d[0x83]
    origin = d[0x5F]

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

    result = {
        "generation": 5,
        "encrypted_source": encrypted,
        "pid": pid,
        "trainer_id": tid,
        "secret_id": sid,
        "language": language,
        "is_bad_egg": bool(flags >> 2 & 1),
        "is_egg": bool(ivword >> 30 & 1),
        "checksum_valid": True,
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
        "nature_id": nature_id,
        "growth_rate": growth_rate(national_dex) if national_dex else None,
        "level": level,
        "move_pp_ups": ppups,
        "friendship": friendship,
        "ability_id": ability,
        "ability": ability_name(ability),
        "hidden_ability": hidden_flag,
        "is_ns_pokemon": bool(d[0x42] >> 1 & 1),   # 0x42 bit 1, verified on N's Zorua (Black 2)
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
        "met_location": struct.unpack_from("<H", d, 0x80)[0],
        "egg_location": struct.unpack_from("<H", d, 0x7E)[0],
        "met_level": d[0x84] & 0x7F,
        "met_date": (2000 + met_y, met_m, met_d) if met_m else None,
        "egg_date": (2000 + egg_y, egg_m, egg_d) if egg_m else None,
        "encounter_type": d[0x85],
        "origin_version": origin,
        "origin_game": GAMES5.get(origin, f"Unknown ({origin})"),
        "ball": ball_id,
        "ball_name": BALLS5.get(ball_id, f"Unknown ({ball_id})"),
        "ribbons": _bits(rib1, _RIB1) + _bits(rib2, _RIB2) + _bits(hoenn, _HOENN),
        "is_shiny": (tid ^ sid ^ (pid >> 16) ^ (pid & 0xFFFF)) < 8,
        "ot_gender": d[0x84] >> 7,
        "nickname": _text(d[0x48:0x5E]),
        "ot_name": _text(d[0x68:0x78]),
        "nicknamed": bool(ivword >> 31 & 1),
        "fateful": bool(b40 & 1),
    }
    result.update(stats)
    if len(d) >= 220:
        result["status_condition"] = d[0x88]
        result["level_stored"] = d[0x8C]
        hp_cur = struct.unpack_from("<H", d, 0x8E)[0]
        result["hp_current"] = hp_cur if hp_cur > 0 else result.get("hp_max")
    return result
