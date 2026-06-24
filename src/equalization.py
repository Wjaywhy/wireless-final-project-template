"""Preamble-aided flat-channel estimation and scalar equalisation."""

import numpy as np


#: Default numerical threshold for near-zero denominator guards.
#: Shared by LS estimation, ZF, and MMSE equalisation.
_EPSILON = 1e-12


def estimate_flat_channel(
        received_preamble: list[complex] | np.ndarray,
        known_preamble: list[complex] | np.ndarray,
        epsilon: float = _EPSILON) -> complex:
    r"""Estimate one flat channel coefficient by preamble least squares.

    Computes:

    .. math::
        \hat{h} = \frac{\sum_k y_p[k] \cdot p^*[k]}{\sum_k |p[k]|^2}

    where :math:`y_p` is the received preamble and :math:`p` is the known
    transmitted preamble.  Rejects empty, mismatched-length, or zero-energy
    preambles.

    Args:
        received_preamble: Received preamble symbols after synchronisation.
        known_preamble: Known transmitted preamble template symbols.
        epsilon: Threshold below which the denominator is considered zero.

    Returns:
        Complex channel estimate :math:`\hat{h}`.

    Raises:
        ValueError: If preambles have different lengths, are empty, or the
            known preamble energy is below *epsilon*.
    """
    received = np.asarray(received_preamble, dtype=np.complex128).reshape(-1)
    known = np.asarray(known_preamble, dtype=np.complex128).reshape(-1)
    if received.size != known.size:
        raise ValueError("received and known preambles must have the same length")
    if received.size == 0:
        raise ValueError("preamble must not be empty")
    denominator = float(np.sum(np.abs(known) ** 2))
    if not np.isfinite(denominator) or denominator <= epsilon:
        raise ValueError("known preamble energy is too small for estimation")
    estimate = np.sum(received * np.conj(known)) / denominator
    if not np.isfinite(estimate.real) or not np.isfinite(estimate.imag):
        raise ValueError("channel estimate is not finite")
    return complex(estimate)


def zf_equalize(received: list[complex] | np.ndarray, h_est: complex,
                epsilon: float = _EPSILON) -> np.ndarray:
    r"""Zero-force equalisation for a flat-fading channel.

    Applies:

    .. math::
        \hat{x}[k] = \frac{y[k]}{\hat{h}}

    This perfectly inverts the channel gain but amplifies noise when
    :math:`|\hat{h}|` is small.

    Args:
        received: Received symbol sequence after synchronisation.
        h_est: Estimated complex channel coefficient.
        epsilon: Threshold below which :math:`|\hat{h}|` is considered zero.

    Returns:
        Equalised symbol array, same length as *received*.

    Raises:
        ValueError: If the channel estimate is near-zero or non-finite.
    """
    samples = np.asarray(received, dtype=np.complex128).reshape(-1)
    h = complex(h_est)
    if not np.isfinite(h.real) or not np.isfinite(h.imag):
        raise ValueError("channel estimate must be finite")
    if abs(h) <= epsilon:
        raise ValueError("ZF equalization rejected a near-zero channel estimate")
    equalized = samples / h
    if not np.all(np.isfinite(equalized)):
        raise ValueError("ZF equalization produced non-finite samples")
    return equalized


def mmse_equalize(
        received: list[complex] | np.ndarray, h_est: complex,
        noise_variance: float, symbol_power: float = 1.0,
        epsilon: float = _EPSILON) -> np.ndarray:
    r"""Scalar MMSE equalisation for a flat-fading channel.

    Applies the minimum mean-square error estimator:

    .. math::
        \hat{x}[k] = \frac{\hat{h}^*}{|\hat{h}|^2 + N_0/E_s} \cdot y[k]

    The regularisation term :math:`N_0/E_s` prevents noise enhancement when
    :math:`|\hat{h}|` is small.  When :math:`N_0 = 0`, MMSE reduces to ZF.

    Args:
        received: Received symbol sequence after synchronisation.
        h_est: Estimated complex channel coefficient.
        noise_variance: Linear noise power :math:`N_0`.
        symbol_power: Average transmitted symbol power :math:`E_s` (default 1.0
            for unit-average-power constellations).
        epsilon: Threshold below which the denominator is considered zero.

    Returns:
        Equalised symbol array, same length as *received*.

    Raises:
        ValueError: If the channel estimate is non-finite, noise_variance is
            negative, symbol_power is non-positive, or the denominator is
            below *epsilon*.
    """
    samples = np.asarray(received, dtype=np.complex128).reshape(-1)
    h = complex(h_est)
    if not np.isfinite(h.real) or not np.isfinite(h.imag):
        raise ValueError("channel estimate must be finite")
    if not np.isfinite(noise_variance) or noise_variance < 0:
        raise ValueError("noise_variance must be finite and non-negative")
    if not np.isfinite(symbol_power) or symbol_power <= 0:
        raise ValueError("symbol_power must be finite and positive")
    denominator = abs(h) ** 2 + float(noise_variance) / float(symbol_power)
    if not np.isfinite(denominator) or denominator <= epsilon:
        raise ValueError("MMSE denominator is too small")
    equalized = (np.conj(h) / denominator) * samples
    if not np.all(np.isfinite(equalized)):
        raise ValueError("MMSE equalization produced non-finite samples")
    return equalized
