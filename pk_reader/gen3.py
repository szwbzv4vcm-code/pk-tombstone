"""
Generation III .pk3 reader (Ruby/Sapphire/Emerald/FireRed/LeafGreen),
for files exported by PKHeX.

IMPORTANT CORRECTION: Gen 3's real in-game/cartridge format DOES use
real encryption (a PID-derived XOR seed) and shuffles its four 12-byte
blocks into one of 24 orders based on PID%24 -- this is well documented
and was our first working hypothesis. But PKHeX's own "loose file"
export skips BOTH of those steps entirely: it writes the four blocks
in plain, natural A-B-C-D order with no XOR applied at all. Confirmed
directly against two real files (a Corphish and an Electrode):
  - The stored checksum matches an exact sum over the completely raw,
    undecrypted bytes -- essentially impossible by coincidence.
  - Electrode's species (101) read correctly straight from block A's
    first two bytes with zero shuffling.
  - Both files' nicknames decoded to their species name in caps
    ("CORPHISH", "ELECTRODE") exactly matching Gen 1's own "no nickname
    set" default convention, confirming the character table below too.
If a future sample ever needs the "real" encrypted/shuffled format
(e.g. a file sourced from an actual save rather than a PKHeX loose
export), that's a distinct code path we'd need to add back, not this
one -- don't assume this module handles that case.

STRUCTURE (100-byte party format; box format omits the last 20 bytes):
  0x00-0x03  PID (personality value)
  0x04-0x05  TID16
  0x06-0x07  SID16
  0x08-0x11  Nickname (10 bytes, Gen 3 character table, 0xFF-terminated)
  0x12       Language
  0x13       Flags (bit0=bad egg, bit1=has species, bit2=is egg)
  0x14-0x1A  OT name (7 bytes, same character table)
  0x1B       Marking value
  0x1C-0x1D  Checksum (sum of all 16-bit words in the 0x20-0x4F region)
  0x1E-0x1F  "Sanity" -- unused padding
  0x20-0x2B  Block A: species (internal index, see below) / held item /
             EXP (4 bytes) / PP-Ups (packed) / friendship
  0x2C-0x37  Block B: 4 moves, then their PP
  0x38-0x43  Block C: 5 EVs, then 6 contest stats
  0x44-0x4F  Block D: pokérus / met info / packed IVs (4 bytes) / ribbons
  --- party-only fields below ---
  0x50-0x53  Status condition
  0x54       Level
  0x55       Held Mail ID
  0x56-0x63  Current/Max HP, Attack, Defense, Speed, Sp.Atk, Sp.Def stats

CHARACTER TABLE (confirmed against both real samples above):
  0xBB-0xD4  A-Z
  0xD5-0xEE  a-z
  0xFF       terminator
  Digits/punctuation are best-effort from general Gen 3+ documentation,
  not yet confirmed against a real sample containing any.

SPECIES: internal index is confirmed identical to the National Dex
number for every Gen 1/2-originated species (indices 1-251, verified
directly against Bulbapedia's Gen 3 index-number table). For species
introduced IN Gen 3 itself (dex 252+), this does NOT reliably hold --
Corphish (National Dex #341) read as raw internal index 326, not 341,
proving the naive "index = dex number" assumption is wrong for at least
some Hoenn natives. We don't have PKHeX's real conversion table for
this range yet, so national_dex is only reported with confidence for
1-251; beyond that, internal_index is accurate but national_dex is a
best-effort (possibly wrong) identity-mapped guess, flagged as such.
"""

from struct import unpack_from

from .species_data import (
    dex_name, dex_base_stats, growth_rate,
    level_from_exp, calc_hp_stat, calc_other_stat, nature_from_pid,
    gen3_index_to_national_dex,gen3_index_to_national_dex, gender_from_pid, move_name, item_name, gen3_ability
)

CHIMECHO_INTERNAL_INDEX = 387
CHIMECHO_NATIONAL_DEX = 358
CONFIRMED_IDENTITY_MAX = 251  # Confirmed 1:1 for indices up to here

TERMINATOR = 0xFF

BALL_NAMES = {
    1: "Master Ball", 2: "Ultra Ball", 3: "Great Ball", 4: "Poké Ball",
    5: "Safari Ball", 6: "Net Ball", 7: "Dive Ball", 8: "Nest Ball",
    9: "Repeat Ball", 10: "Timer Ball", 11: "Luxury Ball", 12: "Premier Ball",
}

CONTEST_CATEGORIES = [("Cool", 0), ("Beauty", 3), ("Cute", 6), ("Smart", 9), ("Tough", 12)]
CONTEST_RANKS = ["", "Normal", "Super", "Hyper", "Master"]
SINGLE_RIBBONS = {
    15: "Champion", 16: "Winning", 17: "Victory", 18: "Artist", 19: "Effort",
    20: "Battle Champion", 21: "Regional Champion", 22: "National Champion",
    23: "Country", 24: "National", 25: "Earth", 26: "World",
}


def _decode_ribbons(value):
    ribbons = []
    for name, shift in CONTEST_CATEGORIES:
        rank = (value >> shift) & 0x7
        if rank:
            label = CONTEST_RANKS[rank] if rank < len(CONTEST_RANKS) else f"rank {rank}"
            ribbons.append(f"{name} ({label})")
    for bit, name in SINGLE_RIBBONS.items():
        if (value >> bit) & 1:
            ribbons.append(name)
    return ribbons

GAME_NAMES = {
    1: "Sapphire", 2: "Ruby", 3: "Emerald",
    4: "FireRed", 5: "LeafGreen", 15: "Colosseum / XD",
}

CHAR_MAP = {}
for _i in range(26):
    CHAR_MAP[0xBB + _i] = chr(ord('A') + _i)
    CHAR_MAP[0xD5 + _i] = chr(ord('a') + _i)
for _i in range(10):
    CHAR_MAP[0xA1 + _i] = str(_i)  # best-effort, not yet confirmed
CHAR_MAP[0x00] = " "
CHAR_MAP[0xB5] = "♂"  # verified with PKHeX-made Nidoran files
CHAR_MAP[0xB6] = "♀"


def _decode_gen3_string(data: bytes) -> str:
    out = []
    for b in data:
        if b == TERMINATOR:
            break
        out.append(CHAR_MAP.get(b, "?"))
    return "".join(out)


def _species_from_internal(index_number: int):
    """Returns (national_dex, confident: bool)."""
    if index_number == CHIMECHO_INTERNAL_INDEX:
        return CHIMECHO_NATIONAL_DEX, True
    if 1 <= index_number <= CONFIRMED_IDENTITY_MAX:
        return index_number, True
    if CONFIRMED_IDENTITY_MAX < index_number <= 386:
        return index_number, False  # unconfirmed guess -- see module docstring
    return None, False


def decode_gen3(raw: bytes) -> dict:
    if len(raw) < 0x50:
        raise ValueError(f"File too short to be a Gen 3 Pokémon ({len(raw)} bytes)")

    pid = unpack_from("<I", raw, 0x00)[0]
    tid16 = unpack_from("<H", raw, 0x04)[0]
    sid16 = unpack_from("<H", raw, 0x06)[0]
    language = raw[0x12]
    flags = raw[0x13]

    stored_checksum = unpack_from("<H", raw, 0x1C)[0]
    block_region = raw[0x20:0x50]  # plain, no XOR, no shuffle -- confirmed above
    calc_checksum = 0
    for i in range(0, 48, 2):
        calc_checksum = (calc_checksum + unpack_from("<H", block_region, i)[0]) & 0xFFFF
    checksum_valid = calc_checksum == stored_checksum

    # --- Block A: species/item/EXP/PP-Ups/friendship, absolute 0x20-0x2B ---
    species_internal = unpack_from("<H", raw, 0x20)[0]
    national_dex, species_confident = gen3_index_to_national_dex(species_internal)
    held_item = unpack_from("<H", raw, 0x22)[0]
    experience = unpack_from("<I", raw, 0x24)[0]
    pp_ups_byte = raw[0x28]
    friendship = raw[0x29]

    # --- Block B: moves/PP, absolute 0x2C-0x37 ---
    moves = [unpack_from("<H", raw, 0x2C + 2 * i)[0] for i in range(4)]
    move_pp_raw = [raw[0x34 + i] for i in range(4)]

    # --- Block C: EVs/contest, absolute 0x38-0x43 ---
    ev_hp, ev_atk, ev_def, ev_spe, ev_spa, ev_spd = raw[0x38:0x3E]

    # --- Block D: pokerus/met info/IVs/ribbons, absolute 0x44-0x4F ---
    pokerus = raw[0x44]
    met_location = raw[0x45]
    origins = unpack_from("<H", raw, 0x46)[0]
    met_level = origins & 0x7F
    origin_version = (origins >> 7) & 0xF
    ball = (origins >> 11) & 0xF
    ot_gender = (origins >> 15) & 1
    iv32 = unpack_from("<I", raw, 0x48)[0]
    iv_hp = iv32 & 0x1F
    iv_atk = (iv32 >> 5) & 0x1F
    iv_def = (iv32 >> 10) & 0x1F
    iv_spe = (iv32 >> 15) & 0x1F
    iv_spa = (iv32 >> 20) & 0x1F
    iv_spd = (iv32 >> 25) & 0x1F
    is_egg_bit = (iv32 >> 30) & 1 == 1
    ability_slot = (iv32 >> 31) & 1

    nickname_raw = raw[0x08:0x12]
    ot_name_raw = raw[0x14:0x1B]

    # Compute Level, Nature, and stats from stored EXP/IVs/EVs + species data.
    # These are never stored as raw bytes in PKHeX's loose-file export -- the
    # game (and PKHeX) recalculates them on demand using the same formulas below.
    # Only compute if species_confident is True -- an unconfirmed index would
    # mean the growth rate and base stats belong to the wrong species entirely.
    nature_name, nature_inc, nature_dec = nature_from_pid(pid)
    computed_level = None
    computed_stats = {}
    if national_dex is not None and species_confident:
        computed_level = level_from_exp(national_dex, experience)
        base = dex_base_stats(national_dex)
        if base and computed_level:
            lvl = computed_level

            def _mod(stat_key):
                if stat_key == nature_inc:
                    return 1.1
                if stat_key == nature_dec:
                    return 0.9
                return 1.0

            computed_stats = {
                "hp_max":   calc_hp_stat(base["hp"],  iv_hp,  ev_hp,  lvl),
                "stat_atk": calc_other_stat(base["atk"], iv_atk, ev_atk, lvl, _mod("atk")),
                "stat_def": calc_other_stat(base["def"], iv_def, ev_def, lvl, _mod("def")),
                "stat_spe": calc_other_stat(base["spe"], iv_spe, ev_spe, lvl, _mod("spe")),
                "stat_spa": calc_other_stat(base["spa"], iv_spa, ev_spa, lvl, _mod("spa")),
                "stat_spd": calc_other_stat(base["spd"], iv_spd, ev_spd, lvl, _mod("spd")),
            }

    result = {
        "generation": 3,
        "pid": pid,
        "trainer_id": tid16,
        "secret_id": sid16,
        "language": language,
        "is_bad_egg": bool(flags & 1),
        "has_species_flag": bool(flags & 2),
        "is_egg": bool(flags & 4) or is_egg_bit,
        "checksum_valid": checksum_valid,
        "internal_index": species_internal,
        "national_dex": national_dex,
        "species_known": national_dex is not None,
        "species_confident": species_confident,
        "species_name": dex_name(national_dex) if species_confident else None,
        "gender": gender_from_pid(national_dex, pid) if national_dex else None,
        "held_item": held_item,
        "held_item_name": item_name(held_item, 3),
        "experience": experience,
        "nature": nature_name,
        "growth_rate": growth_rate(national_dex) if (national_dex and species_confident) else None,
        "level": computed_level,
        "move_pp_ups": [(pp_ups_byte >> (2 * i)) & 3 for i in range(4)],
        "friendship": friendship,
        "moves": moves,
        "move_names": [move_name(m) for m in moves],
        "move_pp": move_pp_raw,
        "ev_hp": ev_hp, "ev_atk": ev_atk, "ev_def": ev_def,
        "ev_spe": ev_spe, "ev_spa": ev_spa, "ev_spd": ev_spd,
        "pokerus_strain": pokerus >> 4,
        "pokerus_days": pokerus & 0xF,
        "met_location": met_location,
        "met_level": met_level,
        "origin_version": origin_version,
        "ball": ball,
        "origin_game": GAME_NAMES.get(origin_version, f"Unknown ({origin_version})"),
        "ball_name": BALL_NAMES.get(ball, f"Unknown ({ball})"),
        "ribbons": _decode_ribbons(unpack_from("<I", raw, 0x4C)[0]),
        "is_shiny": (tid16 ^ sid16 ^ (pid >> 16) ^ (pid & 0xFFFF)) < 8,
        "ot_gender": ot_gender,
        "iv_hp": iv_hp, "iv_atk": iv_atk, "iv_def": iv_def,
        "iv_spe": iv_spe, "iv_spa": iv_spa, "iv_spd": iv_spd,
        "ability_slot": ability_slot,
        "ability": gen3_ability(national_dex, ability_slot) if (national_dex and species_confident) else None,
        "nickname": _decode_gen3_string(nickname_raw),
        "ot_name": _decode_gen3_string(ot_name_raw),
    }
    result.update(computed_stats)  # hp_max, stat_atk, etc. (empty dict if unavailable)

    if len(raw) >= 0x64:
        # Only read status_condition and hp_current from the raw party bytes --
        # everything else (level, max HP, stats) is zeroed in PKHeX loose exports
        # and is already computed correctly above from EXP/IVs/EVs/base stats.
        result["status_condition"] = unpack_from("<I", raw, 0x50)[0]
        result["held_mail_id"] = raw[0x55]
        raw_hp_current = unpack_from("<H", raw, 0x56)[0]
        # hp_current from raw is only meaningful if it's non-zero (i.e. party data
        # was actually filled in); otherwise fall back to hp_max (full health).
        result["hp_current"] = raw_hp_current if raw_hp_current > 0 else result.get("hp_max")

    return result
