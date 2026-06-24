"""Stage C mathematical prototypes for Level 3 design validation.

These local helpers intentionally do not import or implement the production
Rayleigh pipeline.  They validate the LS, ZF, MMSE and ordinary MRC formulas
before the production interfaces are created.
"""

import numpy as np
import pytest

from src.modulation import qpsk_modulate
from src.pipeline import PREAMBLE_SYMBOLS


def _ls_estimate(received_preamble, known_preamble, epsilon=1e-12):
    """Minimal least-squares flat-channel estimate."""
    received = np.asarray(received_preamble, dtype=np.complex128)
    known = np.asarray(known_preamble, dtype=np.complex128)
    if received.shape != known.shape or received.size == 0:
        raise ValueError("preamble shape must be equal and non-empty")
    denominator = float(np.sum(np.abs(known) ** 2))
    if denominator <= epsilon:
        raise ValueError("preamble energy is too small")
    return np.sum(received * np.conj(known)) / denominator


def _zf(received, channel_estimate, epsilon=1e-12):
    """Minimal scalar zero-forcing equalizer."""
    if abs(channel_estimate) <= epsilon:
        raise ValueError("ZF channel estimate is too small")
    return np.asarray(received, dtype=np.complex128) / channel_estimate


def _mmse(received, channel_estimate, noise_variance,
          symbol_power=1.0, epsilon=1e-12):
    """Minimal scalar MMSE equalizer using linear noise variance."""
    if noise_variance < 0 or symbol_power <= 0:
        raise ValueError("invalid MMSE power parameter")
    denominator = (
        abs(channel_estimate) ** 2 + noise_variance / symbol_power
    )
    if denominator <= epsilon:
        raise ValueError("MMSE denominator is too small")
    return (
        np.conj(channel_estimate) / denominator
        * np.asarray(received, dtype=np.complex128)
    )


def _mrc(received_branches, channel_estimates, epsilon=1e-12):
    """Minimal ordinary equal-noise MRC combiner."""
    received = np.asarray(received_branches, dtype=np.complex128)
    estimates = np.asarray(channel_estimates, dtype=np.complex128)
    if received.ndim != 2 or received.shape[0] != estimates.size:
        raise ValueError("branch and estimate shapes do not match")
    denominator = float(np.sum(np.abs(estimates) ** 2))
    if denominator <= epsilon:
        raise ValueError("MRC denominator is too small")
    return (
        np.sum(np.conj(estimates)[:, None] * received, axis=0)
        / denominator
    )


def test_l3_mt_001_known_channel_zf_and_mmse():
    symbols = np.asarray(qpsk_modulate([0, 0, 0, 1, 1, 1, 1, 0]))
    channel = 0.35 - 0.8j
    received = channel * symbols

    assert np.allclose(_zf(received, channel), symbols, atol=1e-12)

    noise_variance = 0.2
    expected_mmse = (
        np.conj(channel) / (abs(channel) ** 2 + noise_variance)
        * received
    )
    actual_mmse = _mmse(received, channel, noise_variance)
    assert np.allclose(actual_mmse, expected_mmse, atol=1e-12)
    assert not np.allclose(actual_mmse, _zf(received, channel))


def test_l3_mt_002_noiseless_ls_estimate():
    preamble = np.asarray(PREAMBLE_SYMBOLS)
    channel = -0.25 + 0.9j
    estimate = _ls_estimate(channel * preamble, preamble)
    assert estimate == pytest.approx(channel, abs=1e-12)


def test_l3_mt_003_noiseless_two_branch_mrc():
    symbols = np.asarray(qpsk_modulate([0, 0, 0, 1, 1, 1, 1, 0]))
    channels = np.asarray([0.1 + 0.2j, -0.7 + 0.4j])
    received = channels[:, None] * symbols[None, :]
    assert np.allclose(_mrc(received, channels), symbols, atol=1e-12)


def test_l3_mt_004_deep_fade_is_explicitly_rejected():
    with pytest.raises(ValueError, match="too small"):
        _zf([1 + 1j], 0j)
    with pytest.raises(ValueError, match="too small"):
        _mmse([1 + 1j], 0j, noise_variance=0.0)
    with pytest.raises(ValueError, match="too small"):
        _mrc([[1 + 1j], [2 + 2j]], [0j, 0j])
