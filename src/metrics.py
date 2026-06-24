"""Metric computation and JSON serialisation.

The public metric fields always use Python native types so that
``json.dump`` never encounters a NumPy scalar.
"""

import json
import os
from pathlib import Path


def calculate_ber(sent_bits: list[int], received_bits: list[int]) -> float:
    """Bit error rate with length-difference counted as errors.

    Matches the DESIGN.md specification::

        BER = N_err / max(L_sent, L_received)

    * Bits in the common length range are compared position-by-position.
    * Every missing bit (sent longer than received) is an error.
    * Every extra bit (received longer than sent) is an error.
    * When both are empty, BER = 0.0.

    Args:
        sent_bits: Transmitted information bit list.
        received_bits: Recovered bit list after the full receive chain.

    Returns:
        BER in [0.0, 1.0].
    """
    sent = [int(b) for b in sent_bits]
    received = [int(b) for b in received_bits]

    common = min(len(sent), len(received))
    bit_errors = sum(1 for i in range(common) if sent[i] != received[i])
    bit_errors += abs(len(sent) - len(received))

    denominator = max(len(sent), len(received))
    return bit_errors / denominator if denominator else 0.0


def _convert_for_json(obj):
    """Recursively replace NumPy scalars with Python builtins."""
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _convert_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert_for_json(x) for x in obj]
    return obj


def save_metrics(metrics: dict, output_dir: str):
    """Write ``metrics.json`` into *output_dir*.

    Level 2 fields are preserved exactly.  Optional Level 3 fields are
    persisted only when present; internal keys prefixed with ``_`` are not.
    """
    public_fields = [
        "snr_db", "seed", "modulation", "channel", "payload_bits",
        "ber", "fer", "text_match_rate", "checksum_pass", "sync_start_index",
        "fading_model", "equalizer", "requested_equalizer",
        "diversity_order", "channel_estimate_real", "channel_estimate_imag",
        "channel_estimate_magnitude", "channel_estimate_phase_rad",
        "channel_estimates_real", "channel_estimates_imag",
        "channel_estimates_magnitude", "channel_estimation_error",
        "noise_variance", "sync_success", "failure_reason",
        "simulation_only_true_channel_real",
        "simulation_only_true_channel_imag",
        "simulation_only_true_channels_real",
        "simulation_only_true_channels_imag",
    ]
    public_metrics = {k: metrics[k] for k in public_fields if k in metrics}
    public_metrics = _convert_for_json(public_metrics)

    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / "metrics.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(public_metrics, f, indent=2, ensure_ascii=False)
