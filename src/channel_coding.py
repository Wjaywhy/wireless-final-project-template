"""Triple repetition code.

Each information bit is repeated three times.  The decoder uses hard-decision
majority voting: a group of three bits decodes to 1 when at least two of them
are 1, otherwise 0.

Code rate: 1/3.  Corrects any single-bit error per 3-bit group.
"""


def channel_encode(bits: list[int]) -> list[int]:
    """Triple each bit.

    Args:
        bits: Information bit list.

    Returns:
        Encoded bit list whose length is ``3 * len(bits)``.
    """
    result = []
    for b in bits:
        v = int(b)
        result.extend([v, v, v])
    return result


def channel_decode(bits: list[int]) -> list[int]:
    """Majority-vote decoder.

    Groups the input into blocks of three and outputs 1 when the sum of the
    block is >= 2, otherwise 0.  Incomplete trailing groups are rejected
    because they indicate truncation or an invalid coded-length field.

    Args:
        bits: Received (possibly noisy) encoded bit list.

    Returns:
        Decoded bit list.  Length is exactly ``len(bits) / 3``.

    Raises:
        ValueError: If the encoded bitstream length is not divisible by 3.
    """
    if len(bits) % 3 != 0:
        raise ValueError(
            "Triple-repetition decoder requires a bitstream length "
            f"divisible by 3, got {len(bits)}"
        )

    result = []
    for i in range(0, len(bits), 3):
        group = [int(x) for x in bits[i : i + 3]]
        result.append(1 if sum(group) >= 2 else 0)
    return result
