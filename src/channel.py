"""AWGN channel — complex baseband additive white Gaussian noise.

Noise is generated independently for the real and imaginary components.
A fixed seed produces bit-exact reproducible noise for grading.

The optional Level 3 model is narrowband flat block Rayleigh fading: one
independent complex coefficient per receive branch remains constant for the
entire transmitted frame.
"""

import numpy as np


def awgn(symbols: list[complex], snr_db: float, seed: int = 2026) -> list[complex]:
    """Add circularly-symmetric complex AWGN to a symbol sequence.

    The noise power is derived from the *symbol* SNR::

        N_0 = E_s / 10^(SNR_dB / 10)
        noise variance per real dimension = N_0 / 2

    Args:
        symbols: Transmitted complex baseband symbols.
        snr_db: Symbol SNR (E_s / N_0) in dB.
        seed: Seed for the NumPy random generator.

    Returns:
        Noisy symbols, same length as the input.
    """
    if len(symbols) == 0:
        return []
    syms = np.array([complex(s) for s in symbols])
    E_s = np.mean(np.abs(syms) ** 2)
    if E_s == 0:
        return list(syms)
    N0 = E_s / (10.0 ** (snr_db / 10.0))
    noise_std = np.sqrt(N0 / 2.0)
    rng = np.random.default_rng(seed)
    noise = (rng.normal(0.0, noise_std, len(syms))
             + 1j * rng.normal(0.0, noise_std, len(syms)))
    return [complex(x) for x in (syms + noise)]


def rayleigh_flat_fading(
        symbols: list[complex], snr_db: float, seed=2026,
        diversity_order: int = 1) -> tuple[np.ndarray, np.ndarray, float]:
    """Apply flat block Rayleigh fading and independent branch AWGN.

    The channel model for branch *l* and symbol index *k* is::

        y_l[k] = h_l · x[k] + n_l[k]

    where:
        * ``h_l ~ CN(0, 1)`` — complex Gaussian, constant for the entire frame
        * ``n_l[k] ~ CN(0, N_0)`` — circularly-symmetric complex AWGN
        * ``N_0 = E_s / 10^(SNR_dB / 10)`` — noise power from symbol SNR

    Each branch's fading coefficient is independent.  Random sub-streams are
    derived deterministically via ``SeedSequence.spawn()`` so that prefix,
    fading, and per-branch noise streams never couple.

    Args:
        symbols: Transmitted complex baseband symbols.
        snr_db: Symbol SNR :math:`E_s/N_0` in dB (must be finite).
        seed: Integer seed or ``SeedSequence`` for reproducible randomness.
        diversity_order: Number of independent receive branches (1 or 2).

    Returns:
        ``(received_branches, true_channel, noise_variance)`` where:
            * *received_branches* — ``ndarray`` of shape ``(L, N)``
            * *true_channel* — ``ndarray`` of *L* complex gains (diagnostic
              only; must not be used by the receiver equaliser)
            * *noise_variance* — linear :math:`N_0` (float)

    Raises:
        ValueError: If *diversity_order* is not 1 or 2, or *snr_db* is
            non-finite.
    """
    if diversity_order not in (1, 2):
        raise ValueError(
            f"diversity_order must be 1 or 2, got {diversity_order}"
        )
    if not np.isfinite(snr_db):
        raise ValueError(f"snr_db must be finite, got {snr_db}")

    syms = np.asarray(symbols, dtype=np.complex128).reshape(-1)
    root = seed if isinstance(seed, np.random.SeedSequence) else \
        np.random.SeedSequence(seed)
    child_streams = root.spawn(1 + diversity_order)

    fading_rng = np.random.default_rng(child_streams[0])
    true_channel = (
        fading_rng.normal(size=diversity_order)
        + 1j * fading_rng.normal(size=diversity_order)
    ) / np.sqrt(2.0)

    if syms.size == 0:
        return (
            np.empty((diversity_order, 0), dtype=np.complex128),
            true_channel.astype(np.complex128),
            0.0,
        )

    symbol_power = float(np.mean(np.abs(syms) ** 2))
    if not np.isfinite(symbol_power) or symbol_power < 0:
        raise ValueError("transmitted symbol power must be finite and non-negative")
    noise_variance = symbol_power / (10.0 ** (float(snr_db) / 10.0))
    noise_std = np.sqrt(noise_variance / 2.0)

    received = np.empty(
        (diversity_order, syms.size), dtype=np.complex128
    )
    for branch in range(diversity_order):
        noise_rng = np.random.default_rng(child_streams[branch + 1])
        noise = noise_std * (
            noise_rng.normal(size=syms.size)
            + 1j * noise_rng.normal(size=syms.size)
        )
        received[branch] = true_channel[branch] * syms + noise

    return received, true_channel.astype(np.complex128), float(noise_variance)
