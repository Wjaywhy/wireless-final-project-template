"""PN-sequence XOR scrambler.

Not intended as cryptographic protection — only prevents long runs of
identical bits that could degrade synchronisation performance.
"""

import numpy as np


def scramble(bits: list[int], seed: int = 2026) -> list[int]:
    """XOR every bit with a reproducible PN sequence.

    Args:
        bits: Input bit list.
        seed: Seed for the NumPy random generator that produces the PN mask.

    Returns:
        Scrambled bit list of the same length.
    """
    if len(bits) == 0:
        return []
    rng = np.random.default_rng(seed)
    mask = rng.integers(0, 2, size=len(bits))
    return [int(b) ^ int(m) for b, m in zip(bits, mask)]


def descramble(bits: list[int], seed: int = 2026) -> list[int]:
    """Reverse the scramble operation (XOR with the same PN sequence).

    Args:
        bits: Scrambled bit list.
        seed: Must match the seed used during scrambling.

    Returns:
        Original bit list.
    """
    return scramble(bits, seed)
