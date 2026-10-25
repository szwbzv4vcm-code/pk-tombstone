"""
Generation II .pk2 reader, for files exported by PKSM (a 3DS save manager).

CONFIRMED against a real file (a shiny Red Gyarados from Pokémon Crystal's
main-story event, caught at Lake of Rage): every field below matched
exactly on the first try, with no adjustments needed -- species, level,
current/max HP, all 5 stats, all 4 moves, all 4 move PP values, OT name,
and nickname. The decoded IVs also independently satisfy Gen 2's actual
shininess formula (Speed/Defense/Special DVs all 10, Attack DV one of the
8 valid values) -- confirming both the DV16 offset and that this really
is a shiny Pokémon, without being told so up front.

Ground truth for the 48-byte party structure comes directly from PKHeX's
PK2.cs (field offsets only -- this is our own independent implementation,
not ported code, so no license obligation is inherited from PKHeX):
  0x00        Species (National Dex number directly -- Gen 2 has no
              internal-index quirk like Gen 1; no lookup table needed)
  0x01        Held item
  0x02-0x05   Move 1-4
  0x06-0x07   Trainer ID (2 bytes, big-endian)
  0x08-0x0A   Experience (3 bytes, big-endian)
  0x0B-0x0C   EV HP
  0x0D-0x0E   EV Attack
  0x0F-0x10   EV Defense
  0x11-0x12   EV Speed
  0x13-0x14   EV Special
  0x15-0x16   Packed IVs (DV16 -- same packing as Gen 1)
  0x17-0x1A   Move 1-4 PP (low 6 bits) + PP Ups (high 2 bits)
  0x1B        Current friendship
  0x1C        Pokérus (strain in high nibble, days in low nibble)
  0x1D-0x1E   Caught Data (Crystal only): time of day / met level /
              OT gender / met location, all bit-packed
  0x1F        Level (box/stored copy)
  --- party-only fields below ---
  0x20        Status condition
  0x21        (gap; unused/unmapped in PKHeX's own model)
  0x22-0x23   Current HP
  0x24-0x25   Max HP
  0x26-0x27   Attack stat
  0x28-0x29   Defense stat
  0x2A-0x2B   Speed stat
  0x2C-0x2D   Sp. Attack stat
  0x2E-0x2F   Sp. Defense stat
(48 bytes total, 0x00-0x2F)

CONFIRMED file layout: a 3-byte header identical in shape to Gen 1's
(0x01, a duplicate "preview" byte of species, 0xFF), then this 48-byte
party structure verbatim (bytes 3-50), then the text region (byte 51
onward: OT name, then nickname -- this sample had no third/unidentified
field, unlike some Gen 1 samples).

Shininess (Gen 2): a Pokémon is shiny when its Speed, Defense, and
Special DVs are all exactly 10, and its Attack DV is one of
{2, 3, 6, 7, 10, 11, 14, 15}. This is the real in-game algorithm, not a
guess -- and it's what identified the sample above as shiny purely from
its bytes, matching what its owner separately confirmed.

STILL UNCONFIRMED:
  - Whether the unidentified middle text field Gen 1 sometimes showed
    ("ASH", "NEW N") ever appears in Gen 2 files, or under what
    conditions -- only one sample so far, with just OT + nickname.
  - The Caught Data (met time/level/location) fields -- computed per
    PKHeX's bit layout but not cross-checked against known ground truth
    yet.
  - The character table is assumed identical to Gen 1's (Bulbapedia
    documents them as very similar) -- holds for the plain names tested so far,
    both plain Western text, but not yet tested on anything using
    characters outside the plain A-Z/a-z range.
"""

from .char_tables import decode_gen1_2_string
from .species_data import dex_name, dex_type, gender_from_attack_iv, move_name, item_name

# Confirmed against a real Gyarados sample.
SPECIES_PREVIEW_OFFSET = 1
DATA_START = 3
DATA_SIZE = 48
FIXED_REGION_SIZE = DATA_START + DATA_SIZE  # 51, confirmed
MIN_FILE_SIZE = FIXED_REGION_SIZE + 1

GEN2_TYPE_NAMES = {
    0x00: "Normal", 0x01: "Fighting", 0x02: "Flying", 0x03: "Poison",
    0x04: "Ground", 0x05: "Rock", 0x07: "Bug", 0x08: "Ghost",
    0x09: "Steel", 0x14: "Fire", 0x15: "Water", 0x16: "Grass",
    0x17: "Electric", 0x18: "Psychic", 0x19: "Ice", 0x1A: "Dragon",
    0x1B: "Dark",
}

SHINY_VALID_ATTACK_IVS = {2, 3, 6, 7, 10, 11, 14, 15}


def _u16(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def _read_terminated_strings(data: bytes) -> list:
    """Same approach as the confirmed Gen 1 reader -- see its docstring
    for why both 0x50 and 0x00 are treated as terminators."""
    TERMINATORS = (0x00, 0x50)
    strings = []
    start = 0
    for i, b in enumerate(data):
        if b in TERMINATORS:
            if i > start:
                strings.append(decode_gen1_2_string(data[start:i]))
            start = i + 1
    return strings


def _decode_party_block(d: bytes) -> dict:
    """Decodes the confirmed 48-byte Gen 2 party structure -- offsets
    match PKHeX's PK2.cs field definitions directly."""
    move_ids = [d[0x02], d[0x03], d[0x04], d[0x05]]
    pp_bytes = [d[0x17], d[0x18], d[0x19], d[0x1A]]

    dv16 = _u16(d, 0x15)
    atk_iv = (dv16 >> 12) & 0xF
    def_iv = (dv16 >> 8) & 0xF
    spe_iv = (dv16 >> 4) & 0xF
    spc_iv = dv16 & 0xF
    hp_iv = ((atk_iv & 1) << 3) | ((def_iv & 1) << 2) | ((spe_iv & 1) << 1) | (spc_iv & 1)

    is_shiny = (
        spe_iv == 10 and def_iv == 10 and spc_iv == 10
        and atk_iv in SHINY_VALID_ATTACK_IVS
    )

    species = d[0x00]
    type1, type2 = dex_type(species)
    gender = gender_from_attack_iv(species, atk_iv)

    pokerus = d[0x1C]
    caught_data = _u16(d, 0x1D)

    return {
        "species": species,  # National Dex number directly, no lookup needed
        "species_name": dex_name(species),
        "type1": type1, "type2": type2,
        "gender": gender,
        "held_item": d[0x01],
        "held_item_name": item_name(d[0x01], 2),
        "moves": move_ids,
        "move_names": [move_name(m) for m in move_ids],
        "move_pp": [b & 0x3F for b in pp_bytes],
        "move_pp_ups": [(b & 0xC0) >> 6 for b in pp_bytes],
        "trainer_id": _u16(d, 0x06),
        "experience": (d[0x08] << 16) | (d[0x09] << 8) | d[0x0A],
        "ev_hp": _u16(d, 0x0B),
        "ev_atk": _u16(d, 0x0D),
        "ev_def": _u16(d, 0x0F),
        "ev_spe": _u16(d, 0x11),
        "ev_spc": _u16(d, 0x13),
        "iv_hp": hp_iv, "iv_atk": atk_iv, "iv_def": def_iv,
        "iv_spe": spe_iv, "iv_spc": spc_iv,
        "is_shiny": is_shiny,
        "friendship": d[0x1B],
        "pokerus_strain": pokerus >> 4,
        "pokerus_days": pokerus & 0xF,
        "met_time_of_day": (caught_data >> 14) & 0x3,
        # 1/2/3 = Morning/Day/Night, 0 = not recorded (non-Crystal); checked against PKHeX
        "met_time_of_day_name": {1: "Morning", 2: "Day", 3: "Night"}.get((caught_data >> 14) & 0x3),
        "met_level": (caught_data >> 8) & 0x3F,
        "ot_gender": (caught_data >> 7) & 1,
        "met_location": caught_data & 0x7F,
        "level": d[0x1F],
        "status_condition": d[0x20],
        "hp_current": _u16(d, 0x22),
        "hp_max": _u16(d, 0x24),
        "stat_atk": _u16(d, 0x26),
        "stat_def": _u16(d, 0x28),
        "stat_spe": _u16(d, 0x2A),
        "stat_spa": _u16(d, 0x2C),
        "stat_spd": _u16(d, 0x2E),
    }


def decode_gen2(raw: bytes) -> dict:
    if len(raw) < MIN_FILE_SIZE:
        raise ValueError(f"File too short to be a PKSM Gen 2 export ({len(raw)} bytes)")

    party = _decode_party_block(raw[DATA_START:DATA_START + DATA_SIZE])
    national_dex = party["species"]

    text_strings = _read_terminated_strings(raw[FIXED_REGION_SIZE:])
    if len(text_strings) >= 3:
        ot_name, unidentified_field, nickname = text_strings[0], text_strings[1], text_strings[2]
        trailing_noise = text_strings[3:]
    elif len(text_strings) == 2:
        ot_name, unidentified_field, nickname = text_strings[0], None, text_strings[1]
        trailing_noise = []
    elif len(text_strings) == 1:
        ot_name, unidentified_field, nickname = text_strings[0], None, None
        trailing_noise = []
    else:
        ot_name, unidentified_field, nickname = None, None, None
        trailing_noise = []

    result = {
        "generation": 2,
        "national_dex": national_dex,
        "species_known": 1 <= national_dex <= 251,
        "raw_size": len(raw),
        "text_strings": text_strings,
        "ot_name": ot_name,
        "unidentified_field": unidentified_field,
        "nickname": nickname,
        "trailing_noise": trailing_noise,
    }
    result.update(party)
    return result
