"""
Generation I .pk1 reader, for files exported by PKSM (a 3DS save manager).

IMPORTANT: this does NOT match the classic Game Boy cartridge/hardware
33-byte (box) / 44-byte (party) LIST structure documented on Bulbapedia --
that documentation describes how a whole box/party of Pokémon is packed
together in a save file, not how PKSM serializes a single exported entity.
PKHeX's own standalone .pk1 format differs from PKSM's too (PKHeX wraps a
single entry using the same list format via PokeList1). PKSM's format,
confirmed below, is its own simpler, flatter layout.

CONFIRMED origin of "OT trash bytes" (previously called an
"unidentified field"): this is a real, documented Gen 1 quirk, not
meaningful game data. When a player selects a name from the game's
quick-pick default-name menu (rather than typing one manually), the
save's name buffer is reused from prior menu-navigation state and isn't
fully cleared -- so trailing bytes from OTHER menu options that were
sitting in that buffer get copied in after the real name. PKHeX's own
developer (Kaphotics) confirmed this directly, citing the actual
Pokémon Yellow disassembly: selecting "ASH" from the default-name menu
leaves the OT buffer holding "ASH\0JACK\0" as trailing trash
(https://projectpokemon.org/home/forums/topic/41764). This matches our
data exactly: manually-typed names ("RED", "TIM", "MANIA") show no
trailing trash at all, while menu-picked names ("YELLOW", "JACK") do,
and the specific trash differs by game version since each game's
default-name menu offers different presets.

CONFIRMED against four real files (Ditto and two Mankeys from a Yellow
save, a Charmander from a Red save):
  - Byte 0: unidentified constant (0x01 in every sample so far).
  - Byte 1: species internal index number, a "preview" duplicate of byte 3.
  - Byte 2: unidentified constant (0xFF in every sample so far).
  - Bytes 3-46 (44 bytes): a VERBATIM copy of the classic Gen 1 PARTY
    Pokémon structure. Confirmed field-for-field against PKHeX's own
    PK1.cs source and a real Mankey's known values (species, current/max
    HP, level, type, catch rate, and both known moves all matched
    exactly). A generated (not caught) Ditto sample had a catch rate of
    0 under this same mapping -- not a mapping error, just a real data
    quirk of PKSM's Pokémon generator not setting that field.
  - Byte 47 onward: a run of terminated text strings, no fixed-width
    padding. Two different bytes can terminate a field: 0x50 (the
    standard Gen 1/2 string terminator) and, at least once, 0x00.
  - Two real text fields: OT (trainer) name, then nickname. Either one
    may be immediately followed by leftover "trash" bytes (see above)
    when that name came from the default-name menu.
  - Any strings found beyond the real name + its trash are NOT reliable
    text -- more than one sample had a spurious trailing "string" that
    was almost certainly leftover binary data (e.g. a checksum)
    coincidentally containing bytes in a printable range before hitting
    a terminator.
"""

from .char_tables import decode_gen1_2_string
from .gen1_index import GEN1_INDEX_TO_DEX
from .species_data import dex_name,move_name

SPECIES_PREVIEW_OFFSET = 1  # Duplicate "preview" copy of species
DATA_START = 3               # Start of the verbatim 44-byte party structure
DATA_SIZE = 44
FIXED_REGION_SIZE = DATA_START + DATA_SIZE  # 47; confirmed start of text strings
MIN_FILE_SIZE = FIXED_REGION_SIZE + 1  # at least one terminator byte

GEN1_TYPE_NAMES = {
    0x00: "Normal", 0x01: "Fighting", 0x02: "Flying", 0x03: "Poison",
    0x04: "Ground", 0x05: "Rock", 0x07: "Bug", 0x08: "Ghost",
    0x14: "Fire", 0x15: "Water", 0x16: "Grass", 0x17: "Electric",
    0x18: "Psychic", 0x19: "Ice", 0x1A: "Dragon",
}


def _u16(data: bytes, offset: int) -> int:
    """Big-endian 2-byte read, matching Gen 1's byte order."""
    return (data[offset] << 8) | data[offset + 1]


def _read_terminated_strings(data: bytes) -> list:
    """Reads consecutive terminated strings back-to-back until the data
    runs out (used for the variable-length text region at the end of a
    PKSM .pk1 export). Both 0x50 (the game's native string terminator)
    and 0x00 (confirmed acting as a second field separator on a real
    in-game-trade sample) end a string. Trailing all-terminator padding
    yields no extra empty strings."""
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
    """Decodes the 44-byte Gen 1 party structure (already sliced out, so
    offsets here match PKHeX's PK1.cs field definitions directly)."""
    move_ids = [d[0x08], d[0x09], d[0x0A], d[0x0B]]
    pp_bytes = [d[0x1D], d[0x1E], d[0x1F], d[0x20]]

    # Gen 1 IV packing: Attack/Defense in the high byte of DV16, Speed/
    # Special in the low byte, 4 bits each; HP IV is derived from the
    # low bit of each of the other four.
    dv16 = _u16(d, 0x1B)
    atk_iv = (dv16 >> 12) & 0xF
    def_iv = (dv16 >> 8) & 0xF
    spe_iv = (dv16 >> 4) & 0xF
    spc_iv = dv16 & 0xF
    hp_iv = ((atk_iv & 1) << 3) | ((def_iv & 1) << 2) | ((spe_iv & 1) << 1) | (spc_iv & 1)

    return {
        "hp_current": _u16(d, 0x01),
        "level": d[0x03],
        "status_condition": d[0x04],
        "type1": d[0x05],
        "type2": d[0x06],
        "type1_name": GEN1_TYPE_NAMES.get(d[0x05]),
        "type2_name": GEN1_TYPE_NAMES.get(d[0x06]),
        "catch_rate": d[0x07],
        "moves": move_ids,
        "move_names": [move_name(m) for m in move_ids],
        "move_pp": [b & 0x3F for b in pp_bytes],
        "move_pp_ups": [(b & 0xC0) >> 6 for b in pp_bytes],
        "trainer_id": _u16(d, 0x0C),
        "experience": (d[0x0E] << 16) | (d[0x0F] << 8) | d[0x10],
        "ev_hp": _u16(d, 0x11),
        "ev_atk": _u16(d, 0x13),
        "ev_def": _u16(d, 0x15),
        "ev_spe": _u16(d, 0x17),
        "ev_spc": _u16(d, 0x19),
        "iv_hp": hp_iv, "iv_atk": atk_iv, "iv_def": def_iv,
        "iv_spe": spe_iv, "iv_spc": spc_iv,
        "party_level": d[0x21],
        "hp_max": _u16(d, 0x22),
        "stat_atk": _u16(d, 0x24),
        "stat_def": _u16(d, 0x26),
        "stat_spe": _u16(d, 0x28),
        "stat_spc": _u16(d, 0x2A),
    }


def decode_gen1(raw: bytes) -> dict:
    if len(raw) < MIN_FILE_SIZE:
        raise ValueError(f"File too short to be a PKSM Gen 1 export ({len(raw)} bytes)")

    index_number = raw[SPECIES_PREVIEW_OFFSET]
    national_dex = GEN1_INDEX_TO_DEX.get(index_number)

    party = _decode_party_block(raw[DATA_START:DATA_START + DATA_SIZE])

    text_strings = _read_terminated_strings(raw[FIXED_REGION_SIZE:])
    if len(text_strings) >= 3:
        ot_name, ot_trash, nickname = text_strings[0], text_strings[1], text_strings[2]
        trailing_noise = text_strings[3:]
    elif len(text_strings) == 2:
        ot_name, ot_trash, nickname = text_strings[0], None, text_strings[1]
        trailing_noise = []
    elif len(text_strings) == 1:
        ot_name, ot_trash, nickname = text_strings[0], None, None
        trailing_noise = []
    else:
        ot_name, ot_trash, nickname = None, None, None
        trailing_noise = []

    result = {
        "generation": 1,
        "internal_index": index_number,
        "national_dex": national_dex,
        "species_known": national_dex is not None,
        "species_name": dex_name(national_dex),
        "raw_size": len(raw),
        "text_strings": text_strings,
        "ot_name": ot_name,
        "ot_trash": ot_trash,
        "nickname": nickname,
        "trailing_noise": trailing_noise,
    }
    result.update(party)
    return result
