"""Gray-coded QPSK modulation and hard-decision demodulation.

Constellation (normalised to unit average power)::

    (b0, b1)  |  symbol           |  I (real)  |  Q (imag)
    -------------------------------------------------------
    0 0        |  (1 + j) / sqrt(2) |  +         |  +
    0 1        |  (-1 + j) / sqrt(2)|  -         |  +
    1 1        |  (-1 - j) / sqrt(2)|  -         |  -
    1 0        |  (1 - j) / sqrt(2) |  +         |  -

Bit-to-symbol rule: **b1 controls I (real), b0 controls Q (imag).**
"""

import numpy as np


def qpsk_modulate(bits: list[int]) -> list[complex]:
    """Map a bitstream to unit-average-power QPSK symbols.

    If the number of input bits is odd a single 0 is appended so that every
    pair of bits maps to one symbol.

    Args:
        bits: List of ints (0 or 1).

    Returns:
        Complex baseband symbols; ``len(result) == ceil(len(bits) / 2)``.
    """
    bit_list = [int(b) for b in bits]
    if len(bit_list) % 2 != 0:
        bit_list.append(0)

    symbols = []
    inv_sqrt2 = 1.0 / np.sqrt(2)
    for i in range(0, len(bit_list), 2):
        b0, b1 = bit_list[i], bit_list[i + 1]
        real = 1.0 if b1 == 0 else -1.0
        imag = 1.0 if b0 == 0 else -1.0
        symbols.append(complex(real * inv_sqrt2, imag * inv_sqrt2))
    return symbols


def qpsk_demodulate(symbols: list[complex]) -> list[int]:
    """Hard-decision QPSK demodulator.

    Decision rule:
        ``b1 = 0`` when ``real >= 0``, else ``1``;
        ``b0 = 0`` when ``imag >= 0``, else ``1``.

    Args:
        symbols: Received (possibly noisy) complex symbols.

    Returns:
        Recovered bit list.  Length is ``2 * len(symbols)``.
    """
    bits = []
    for s in symbols:
        b1 = 0 if s.real >= 0 else 1
        b0 = 0 if s.imag >= 0 else 1
        bits.append(b0)
        bits.append(b1)
    return bits
