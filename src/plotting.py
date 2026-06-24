"""Plot generation: constellation, BER curve, and sync correlation peak.

All plotting uses the non-interactive ``Agg`` backend so that figures can be
saved to disk in headless environments (e.g. CI runners).
"""

import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import erfc

from src.pipeline import run_pipeline


def plot_constellation(rx_symbols: list[complex], output_dir: str):
    """Scatter plot of received symbols with ideal QPSK constellation markers.

    Args:
        rx_symbols: Noisy received complex symbols.
        output_dir: Directory to write ``constellation.png``.
    """
    syms = np.array([complex(s) for s in rx_symbols])
    if len(syms) == 0:
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(syms.real, syms.imag, s=2, alpha=0.4, color="steelblue")
    ideal = np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j]) / np.sqrt(2)
    ax.scatter(ideal.real, ideal.imag, s=80, marker="x", color="red", linewidths=2)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.set_xlabel("In-phase (I)")
    ax.set_ylabel("Quadrature (Q)")
    ax.set_title("Received QPSK Constellation")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)

    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / "constellation.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_ber_curve(input_path: str, output_dir: str, seed: int,
                   modulation: str, channel: str):
    """Simulated end-to-end BER vs SNR with an ideal uncoded QPSK reference.

    Evaluates seven SNR points ``[0, 2, 4, 6, 8, 10, 12] dB``, running one
    light-weight pipeline pass per point (no Monte-Carlo averaging).

    The simulated curve includes preamble detection, triple repetition
    coding, CRC verification and safe failure modes, so it is NOT directly
    comparable to the ideal uncoded QPSK reference line.

    Zero-BER points use the detection floor ``0.5 / payload_bits`` on the
    log-scale axes and are annotated *"0 errors observed"*.
    """
    # Fixed SNR sweep: 7 points from 0 to 12 dB (DESIGN.md §R10)
    snr_range = [0, 2, 4, 6, 8, 10, 12]
    ber_values = []
    payload_bits = 0

    for snr in snr_range:
        tmp_output = str(Path(output_dir) / "_tmp_received.txt")
        metrics = run_pipeline(
            input_path=input_path,
            output_path=tmp_output,
            snr_db=float(snr),
            seed=seed,
            modulation=modulation,
            channel=channel,
        )
        ber_values.append(metrics["ber"])
        if payload_bits == 0:
            payload_bits = metrics["payload_bits"]

    # Clean up temporary file
    tmp = Path(output_dir) / "_tmp_received.txt"
    if tmp.exists():
        tmp.unlink()

    # Replace exact zeros with detection floor for log-scale visibility.
    # Floor = 0.5 / payload_bits: one-half bit error relative to total bits.
    detection_floor = 0.5 / max(payload_bits, 1)
    plot_ber = []
    zero_mask = []
    for b in ber_values:
        if b == 0.0:
            plot_ber.append(detection_floor)
            zero_mask.append(True)
        else:
            plot_ber.append(b)
            zero_mask.append(False)

    # Ideal uncoded QPSK theoretical BER reference:
    #   P_b = 0.5 * erfc(√(E_s/N_0 / 2))
    # where E_s/N_0 (linear) = 10^(SNR_dB / 10).
    # This is for reference only — the simulated curve additionally includes
    # triple-repetition coding, preamble detection, and CRC verification.
    snr_linear = 10.0 ** (np.array(snr_range) / 10.0)
    reference_ber = 0.5 * erfc(np.sqrt(snr_linear / 2.0))

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.semilogy(snr_range, plot_ber, "o-", color="steelblue",
                label="Simulated (triple-repetition + QPSK + AWGN)")
    ax.semilogy(snr_range, reference_ber, "--", color="darkorange",
                label="Ideal uncoded QPSK reference")
    # Mark zero-error points
    for i, is_zero in enumerate(zero_mask):
        if is_zero:
            ax.annotate("0 errors\nobserved", (snr_range[i], plot_ber[i]),
                        textcoords="offset points", xytext=(0, -18),
                        ha="center", fontsize=7, color="steelblue",
                        arrowprops=dict(arrowstyle="->", color="steelblue",
                                        lw=0.8))
    ax.set_xlabel("SNR $E_s/N_0$ (dB)")
    ax.set_ylabel("BER")
    ax.set_title("BER vs SNR (Triple Repetition Code, QPSK, AWGN)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / "ber_curve.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_sync_peak(corr_values: list[float], sync_start: int,
                   output_dir: str):
    """Normalised cross-correlation trace with the detected peak highlighted.

    Args:
        corr_values: Correlation magnitude per window position.
        sync_start: Index where the synchroniser declared the frame start.
        output_dir: Directory to write ``sync_peak.png``.
    """
    if len(corr_values) == 0:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    x = list(range(len(corr_values)))
    ax.plot(x, corr_values, color="steelblue", linewidth=0.8)
    ax.axvline(sync_start, color="red", linestyle="--", linewidth=1.2,
               label=f"Detected peak at {sync_start}")
    ax.set_xlabel("Symbol offset")
    ax.set_ylabel("Normalized correlation")
    ax.set_title("Synchronization Correlation")
    ax.legend()
    ax.grid(True, alpha=0.3)

    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / "sync_peak.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_all_plots(metrics: dict, output_dir: str,
                       input_path: str, seed: int,
                       modulation: str, channel: str):
    """Generate all three required plots from a single pipeline run.

    Args:
        metrics: Full metrics dict from :func:`pipeline.run_pipeline`.
        output_dir: Directory to write the PNG files.
        input_path: Original text file (needed for BER sweep).
        seed: Random seed (forwarded to BER sweep).
        modulation: ``"qpsk"``.
        channel: ``"awgn"``.
    """
    plot_constellation(metrics["_rx_symbols"], output_dir)
    plot_ber_curve(input_path, output_dir, seed, modulation, channel)
    plot_sync_peak(metrics["_corr_values"], metrics["_sync_start"], output_dir)
