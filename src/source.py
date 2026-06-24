"""UTF-8 text to bitstream conversion and back.

Bits are packed MSB-first per byte. The bitstream length is always a multiple
of 8 since every UTF-8 code unit is exactly one byte.
"""


def source_encode(text: str) -> list[int]:
    """Encode a UTF-8 string into a list of bits (MSB first per byte).

    Args:
        text: Arbitrary UTF-8 string.

    Returns:
        Flat list of ints (0 or 1).  Length is always 8 * len(text.encode('utf-8')).
    """
    data = text.encode("utf-8")
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def source_decode(bits: list[int]) -> str:
    """Decode a bit list back into a UTF-8 string (MSB first per byte).

    Args:
        bits: List of ints (0 or 1).  Length must be a multiple of 8.

    Returns:
        The original UTF-8 string.

    Raises:
        ValueError: If ``len(bits)`` is not divisible by 8.
        UnicodeDecodeError: If the bytes do not form valid UTF-8.
    """
    bit_ints = [int(b) for b in bits]
    if len(bit_ints) % 8 != 0:
        raise ValueError(
            f"Bitstream length {len(bit_ints)} is not divisible by 8"
        )
    data = bytearray()
    for i in range(0, len(bit_ints), 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bit_ints[i + j]
        data.append(byte_val)
    return data.decode("utf-8")
