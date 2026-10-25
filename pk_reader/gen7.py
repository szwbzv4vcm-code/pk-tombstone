"""Gen 7 (.pk7) decoder: Sun/Moon/Ultra Sun/Ultra Moon. 232-byte box or 260-byte party.

UNVERIFIED against a real .pk7 export. Same container as Gen 6 (Encryption Constant seeds the
LCG and drives the 56-byte block shuffle; also accepts already-decrypted exports), and nearly
the same field layout, so the Gen 6 offsets that were verified on real files are reused.
Changes from Gen 6 that are from memory of the PK7 layout: 0xDE is Hyper Training flags
(Gen 6: ground tile), extra ribbon bits past 0x35, species up to 807, Gen 7 origin games and
the Beast Ball. No Gen 7 location table is loaded yet, so met_location_name will be None.
"""
import struct

from .gen4 import NATURES
from .gen5 import BALLS5, GAMES5
from .gen6 import _normalize6, _text, _RIB6, GAMES6
from .memories6 import memory_fields
from .species_data import (
    dex_name, dex_base_stats, growth_rate, level_from_exp,
    calc_hp_stat, calc_other_stat, move_name, ability_name, item_name_gen
)

MAX_DEX = 807
GAMES7 = dict(GAMES6)
GAMES7.update({30: "Sun", 31: "Moon", 32: "Ultra Sun", 33: "Ultra Moon"})   # from memory

BALLS7 = {k: v for k, v in BALLS5.items() if k < 25}
BALLS7.update({25: "Dream Ball", 26: "Beast Ball"})                          # verified with PKHeX-made files

_STAT_KEYS = ["atk", "def", "spe", "spa", "spd"]
_HYPER_BITS = ["HP", "Attack", "Defense", "Sp. Atk", "Sp. Def", "Speed"]      # bit 0..5, verified with a PKHeX-made file


# Gen 7 adds four bits after the Gen 6 table (0x35 bits 6-7, 0x36 bits 0-1). Order inferred from the
# Geodude/Golem complement pair; confirm against the editor's ribbon names.
_RIB7 = _RIB6 + ["Alola Champion", "Battle Royal Master", "Battle Tree Great", "Battle Tree Master"]


def _ribbons7(b):
    """Bits 0-45 reuse the verified Gen 6 table; anything past that is returned as unknown."""
    known, unknown = [], []
    for byte_i, v in enumerate(b):
        for bit in range(8):
            if v >> bit & 1:
                idx = byte_i * 8 + bit
                if idx < len(_RIB7) and _RIB7[idx]:
                    known.append(_RIB7[idx] + " Ribbon")
                else:
                    unknown.append(f"0x{0x30 + byte_i:02X} bit {bit}")
    return known, unknown


def decode_gen7(raw: bytes) -> dict:
    d, encrypted = _normalize6(raw)          # same checksum / encryption / shuffle as Gen 6
    ec, sanity, checksum = struct.unpack_from("<IHH", d, 0)
    species, held, tid, sid, exp = struct.unpack_from("<HHHHI", d, 0x08)
    ability, ability_num = d[0x14], d[0x15]
    pid = struct.unpack_from("<I", d, 0x18)[0]
    nature_id = d[0x1C] if d[0x1C] < 25 else None
    b1d = d[0x1D]
    ev_hp, ev_atk, ev_def, ev_spe, ev_spa, ev_spd = d[0x1E:0x24]
    pokerus = d[0x2B]
    moves = list(struct.unpack_from("<4H", d, 0x5A))
    pp = list(d[0x62:0x66])
    ppups = list(d[0x66:0x6A])
    ivword = struct.unpack_from("<I", d, 0x74)[0]
    iv_hp, iv_atk, iv_def, iv_spe, iv_spa, iv_spd = [(ivword >> (5 * i)) & 31 for i in range(6)]
    egg_y, egg_m, egg_d = d[0xD1:0xD4]
    met_y, met_m, met_d = d[0xD4:0xD7]
    egg_loc, met_loc = struct.unpack_from("<HH", d, 0xD8)
    ball = d[0xDC]
    hyper = d[0xDE]
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
            def _iv(bit, iv):   # a Hyper Trained stat counts as IV 31
                return 31 if hyper >> bit & 1 else iv

            def _mod(k):
                return 1.1 if k == inc and inc != dec else 0.9 if k == dec and inc != dec else 1.0
            stats = {
                "hp_max":   calc_hp_stat(base["hp"], _iv(0, iv_hp), ev_hp, level),
                "stat_atk": calc_other_stat(base["atk"], _iv(1, iv_atk), ev_atk, level, _mod("atk")),
                "stat_def": calc_other_stat(base["def"], _iv(2, iv_def), ev_def, level, _mod("def")),
                "stat_spe": calc_other_stat(base["spe"], _iv(5, iv_spe), ev_spe, level, _mod("spe")),
                "stat_spa": calc_other_stat(base["spa"], _iv(3, iv_spa), ev_spa, level, _mod("spa")),
                "stat_spd": calc_other_stat(base["spd"], _iv(4, iv_spd), ev_spd, level, _mod("spd")),
            }

    if b1d >> 2 & 1:
        gender = "Genderless"
    else:
        gender = "Female" if b1d >> 1 & 1 else "Male"

    ribbons, ribbons_unknown = _ribbons7(d[0x30:0x38])
    if d[0x38]:   # Memory ribbons store a count (max 40 contest wins, 8 battle wins); from Gen 6
        ribbons.append(f"Contest Memory Ribbon ({d[0x38]})")
    if d[0x39]:
        ribbons.append(f"Battle Memory Ribbon ({d[0x39]})")

    result = {
        "generation": 7,
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
        "held_item_name": item_name_gen(7, held) if held else None,
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
        "moves": moves,
        "move_names": [move_name(m) for m in moves],
        "move_pp": pp,
        "ev_hp": ev_hp, "ev_atk": ev_atk, "ev_def": ev_def,
        "ev_spe": ev_spe, "ev_spa": ev_spa, "ev_spd": ev_spd,
        "iv_hp": iv_hp, "iv_atk": iv_atk, "iv_def": iv_def,
        "iv_spe": iv_spe, "iv_spa": iv_spa, "iv_spd": iv_spd,
        "hyper_trained": [n for i, n in enumerate(_HYPER_BITS) if hyper >> i & 1],
        "pokerus_strain": pokerus >> 4,
        "pokerus_days": pokerus & 0xF,
        "met_location": met_loc,
        "egg_location": egg_loc,
        "met_level": d[0xDD] & 0x7F,
        "met_date": (2000 + met_y, met_m, met_d) if met_m else None,
        "egg_date": (2000 + egg_y, egg_m, egg_d) if egg_m else None,
        "origin_version": origin,
        "origin_game": GAMES7.get(origin, f"Unknown ({origin})"),
        "ball": ball,
        "ball_name": BALLS7.get(ball, f"Unknown ({ball})"),
        "ribbons": ribbons,
        "ribbons_unknown_bits": ribbons_unknown,
        "is_shiny": (tid ^ sid ^ (pid >> 16) ^ (pid & 0xFFFF)) < 16,
        "ot_gender": d[0xDD] >> 7,
        "nickname": _text(d[0x40:0x5A]),
        "ot_name": _text(d[0xB0:0xCA]),
        "handler_name": _text(d[0x78:0x92]),
        "current_handler": d[0x93],
        "nicknamed": bool(ivword >> 31 & 1),
    }
    result.update(memory_fields(d, result["nickname"], result["ot_name"], result["handler_name"]))
    result.update(stats)
    if len(d) >= 260:
        result["status_condition"] = d[0xE8]
        result["level_stored"] = d[0xEC]
        hp_cur = struct.unpack_from("<H", d, 0xF0)[0]
        result["hp_current"] = hp_cur if hp_cur > 0 else result.get("hp_max")
    return result
