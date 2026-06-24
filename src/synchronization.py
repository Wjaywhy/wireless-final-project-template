"""Frame synchronisation via normalised sliding cross-correlation.

The receiver correlates a known preamble template against the incoming
symbol stream.  The index with the highest normalised correlation magnitude
is declared the frame start.

Correlation formula (normalised cross-correlation):

    C[k] = |Σ r[k+m]·p*[m]| / √(Σ|r[k+m]|² · Σ|p[m]|²)

where *r* is the received sequence, *p* is the preamble template, and *L*
is the number of preamble symbols.
"""

import numpy as np


def synchronize(received_symbols: list[complex],
                preamble: list[complex]) -> int:
    """Return the best frame-start index using normalised cross-correlation.

    Args:
        received_symbols: Received symbol sequence (preamble + payload + noise).
        preamble: Complex preamble template (QPSK-modulated preamble bits).

    Returns:
        Sample index where the correlation peaks.
    """
    r = np.array([complex(s) for s in received_symbols])
    p = np.array([complex(s) for s in preamble])
    L = len(p)
    N = len(r)

    if N < L:
        return 0

    p_power = np.sum(np.abs(p) ** 2)
    if p_power == 0:
        return 0

    best_idx = 0
    best_corr = -1.0

    for k in range(N - L + 1):
        window = r[k:k + L]
        num = np.abs(np.sum(window * np.conj(p)))
        den = np.sqrt(np.sum(np.abs(window) ** 2) * p_power)
        corr = num / den if den > 0 else 0.0
        if corr > best_corr:
            best_corr = corr
            best_idx = k

    return best_idx


def synchronize_with_correlation(
        received_symbols: list[complex],
        preamble: list[complex]) -> tuple[int, list[float]]:
    """Like :func:`synchronize`, but also returns the full correlation trace.

    Args:
        received_symbols: Received symbol sequence.
        preamble: Complex preamble template.

    Returns:
        ``(best_index, correlation_values)`` where *correlation_values* is a
        list of normalised correlation magnitudes (one per window position).
    """
    r = np.array([complex(s) for s in received_symbols])
    p = np.array([complex(s) for s in preamble])
    L = len(p)
    N = len(r)

    if N < L:
        return 0, []

    p_power = float(np.sum(np.abs(p) ** 2))
    if p_power == 0:
        return 0, []

    best_idx = 0
    best_corr = -1.0
    corr_values = []

    for k in range(N - L + 1):
        window = r[k:k + L]
        num = float(np.abs(np.sum(window * np.conj(p))))
        den = np.sqrt(float(np.sum(np.abs(window) ** 2)) * p_power)
        corr = num / den if den > 0 else 0.0
        corr_values.append(corr)
        if corr > best_corr:
            best_corr = corr
            best_idx = k

    return best_idx, corr_values


def synchronize_branches(
        received_branches: np.ndarray, preamble: list[complex]
        ) -> tuple[int, list[float], list[list[float]]]:
    """Estimate one frame start from summed normalised branch metrics.

    Each branch is correlated independently; the per-branch correlation
    magnitudes are summed element-wise and the combined peak is selected.
    This avoids the circular dependency of requiring channel estimates
    before synchronisation.

    Args:
        received_branches: Array of shape ``(L, N)`` where *L* is the number
            of receive branches and *N* is the symbol sequence length.
        preamble: Complex preamble template symbols.

    Returns:
        ``(start_index, combined_correlation, branch_correlations)`` where
        *combined_correlation* is the element-wise sum of the per-branch
        correlation magnitude traces and *branch_correlations* is a list
        containing each branch's individual trace.

    Raises:
        ValueError: If the branch array is not 2-D, is empty, or branches
            produce correlation traces of differing lengths.
    """
    branches = np.asarray(received_branches, dtype=np.complex128)
    if branches.ndim != 2:
        raise ValueError("received_branches must have shape (branches, symbols)")
    if branches.shape[0] == 0:
        raise ValueError("at least one receive branch is required")

    individual = []
    for branch in branches:
        _, correlation = synchronize_with_correlation(branch, preamble)
        individual.append(correlation)

    lengths = {len(values) for values in individual}
    if len(lengths) != 1:
        raise ValueError("all branch correlation traces must have equal length")
    if not individual or len(individual[0]) == 0:
        return 0, [], individual

    combined = np.sum(np.asarray(individual, dtype=float), axis=0)
    start = int(np.argmax(combined))
    return start, combined.tolist(), individual
