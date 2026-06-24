"""Complex-symbol receive diversity combiners."""

import numpy as np


def mrc_combine(received_branches: np.ndarray,
                channel_estimates: np.ndarray,
                noise_variance: float | None = None,
                epsilon: float = 1e-12) -> np.ndarray:
    r"""Combine equal-noise receive branches using ordinary coherent MRC.

    Applies the maximal-ratio combining rule:

    .. math::
        \hat{x}[k] = \frac{\sum_l \hat{h}_l^* \cdot y_l[k]}
                           {\sum_l |\hat{h}_l|^2}

    For equal-noise branches the common noise variance cancels from the
    normalised weights; the optional *noise_variance* parameter is validated
    for diagnostic consistency but not used as an unnamed MMSE regulariser.

    Args:
        received_branches: Array of shape ``(L, N)`` where *L* is the number
            of branches and *N* is the symbol count.
        channel_estimates: Array of *L* complex channel estimates.
        noise_variance: Optional common noise variance (validated if provided).
        epsilon: Threshold below which the denominator is considered zero.

    Returns:
        Combined symbol array of length *N*.

    Raises:
        ValueError: If branch count mismatches estimate count, *noise_variance*
            is negative, or the MRC denominator is below *epsilon*.
    """
    received = np.asarray(received_branches, dtype=np.complex128)
    estimates = np.asarray(channel_estimates, dtype=np.complex128).reshape(-1)
    if received.ndim != 2:
        raise ValueError("received_branches must have shape (branches, symbols)")
    if received.shape[0] != estimates.size:
        raise ValueError("branch count must match channel-estimate count")
    if received.shape[0] == 0:
        raise ValueError("at least one receive branch is required")
    if noise_variance is not None and (
            not np.isfinite(noise_variance) or noise_variance < 0):
        raise ValueError("noise_variance must be finite and non-negative")
    if not np.all(np.isfinite(estimates)):
        raise ValueError("channel estimates must be finite")
    denominator = float(np.sum(np.abs(estimates) ** 2))
    if not np.isfinite(denominator) or denominator <= epsilon:
        raise ValueError("MRC denominator is too small")
    combined = np.sum(np.conj(estimates)[:, None] * received, axis=0)
    combined = combined / denominator
    if not np.all(np.isfinite(combined)):
        raise ValueError("MRC produced non-finite samples")
    return combined
