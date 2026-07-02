"""Standalone reproducible Level 3 multi-seed comparison.

The default CLI never invokes this script.  Reported curves are finite-sample
simulation averages, not theoretical performance guarantees.
"""

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.pipeline import run_pipeline


SNR_POINTS = [0, 4, 8, 12, 16, 20]
SCHEMES = {
    "awgn_baseline": ("AWGN baseline", "awgn", "none", 1),
    "rayleigh_zf": ("Rayleigh + ZF (1 branch)", "rayleigh", "zf", 1),
    "rayleigh_mmse": ("Rayleigh + MMSE (1 branch)", "rayleigh", "mmse", 1),
    "rayleigh_mrc": ("Rayleigh + MRC (2 branches)", "rayleigh", "none", 2),
}


def _experiment_seeds(root_seed: int, count: int = 5) -> list[int]:
    """Derive deterministic independent simulation seeds from one root."""
    if count <= 0:
        raise ValueError("seed count must be a positive integer")
    children = np.random.SeedSequence(root_seed).spawn(count)
    return [int(child.generate_state(1, dtype=np.uint32)[0]) for child in children]


def _aggregate(records: list[dict]) -> dict:
    """Aggregate one SNR point without hiding per-seed failures."""
    if not records:
        return {
            "trial_count": 0,
            "mean_ber": None,
            "std_ber": None,
            "mean_fer": None,
            "frame_error_count": 0,
            "complete_recovery_rate": None,
            "text_complete_recovery_rate": None,
            "sync_success_rate": None,
            "mean_channel_estimation_error": None,
        }
    ber_values = [float(record["ber"]) for record in records]
    frame_errors = [int(record["frame_error_indicator"]) for record in records]
    text_complete = [bool(record["text_complete"]) for record in records]
    sync_success = [bool(record["sync_success"]) for record in records]
    errors = [record["channel_estimation_error"] for record in records
              if record["channel_estimation_error"] is not None]
    complete_recovery_rate = float(np.mean(text_complete))
    return {
        "trial_count": int(len(records)),
        "mean_ber": float(np.mean(ber_values)),
        "std_ber": float(np.std(ber_values, ddof=0)),
        "mean_fer": float(np.mean(frame_errors)),
        "frame_error_count": int(sum(frame_errors)),
        "complete_recovery_rate": complete_recovery_rate,
        "text_complete_recovery_rate": complete_recovery_rate,
        "sync_success_rate": float(np.mean(sync_success)),
        "mean_channel_estimation_error": (
            float(np.mean(errors)) if errors else None
        ),
    }


def run_experiments(
        input_path: str, output_dir: str, root_seed: int,
        seed_count: int = 5) -> dict:
    """Run fixed scheme/SNR/seed combinations and write metrics and plots."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    seeds = _experiment_seeds(root_seed, seed_count)
    started = time.perf_counter()
    results = {}

    with tempfile.TemporaryDirectory() as temporary:
        for name, (label, channel, equalizer, diversity) in SCHEMES.items():
            points = []
            for snr in SNR_POINTS:
                records = []
                for seed in seeds:
                    metrics = run_pipeline(
                        input_path,
                        os.path.join(temporary, f"{name}_{snr}_{seed}.txt"),
                        float(snr), seed, "qpsk", channel, equalizer, diversity,
                    )
                    sync_success = metrics.get("sync_success")
                    if sync_success is None:
                        sync_success = (
                            abs(metrics["sync_start_index"]
                                - metrics["_prefix_count"]) <= 1
                        )
                    records.append({
                        "seed": int(seed),
                        "ber": float(metrics["ber"]),
                        "payload_ber": float(metrics["payload_ber"]),
                        "predecode_ber": float(metrics["predecode_ber"]),
                        "fer": float(metrics["fer"]),
                        "frame_error_indicator": int(
                            metrics["frame_error_indicator"]
                        ),
                        "text_match_rate": float(metrics["text_match_rate"]),
                        "text_complete": bool(
                            metrics["checksum_pass"]
                            and metrics["text_match_rate"] == 1.0
                        ),
                        "sync_success": bool(sync_success),
                        "true_prefix_symbols": int(
                            metrics["true_prefix_symbols"]
                        ),
                        "sync_start_index": int(metrics["sync_start_index"]),
                        "sync_error_symbols": int(
                            metrics["sync_error_symbols"]
                        ),
                        "channel_estimation_error": metrics.get(
                            "channel_estimation_error"
                        ),
                    })
                points.append({
                    "snr_db": int(snr), **_aggregate(records),
                    "per_seed": records,
                })
            results[name] = {
                "label": label,
                "configuration": {
                    "channel": channel,
                    "equalizer": "mrc" if diversity == 2 else equalizer,
                    "diversity_order": diversity,
                },
                "points": points,
            }

        representative = {}
        for name in ("rayleigh_zf", "rayleigh_mmse", "rayleigh_mrc"):
            _, channel, equalizer, diversity = SCHEMES[name]
            representative[name] = run_pipeline(
                input_path, os.path.join(temporary, f"{name}_const.txt"),
                16, seeds[0], "qpsk", channel, equalizer, diversity,
            )

    summary = {
        "model": "single-carrier narrowband flat block Rayleigh fading",
        "root_seed": int(root_seed),
        "seed_count": int(seed_count),
        "experiment_seeds": seeds,
        "snr_db_points": SNR_POINTS,
        "schemes": results,
        "runtime_seconds": float(time.perf_counter() - started),
        "finite_sample_notice": (
            "Fixed finite-seed averages; not strict theoretical curves."
        ),
    }
    (output / "level3_metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8"
    )
    _plot_ber(results, output, input_path, len(seeds))
    _plot_fer(results, output)
    _plot_estimation_error(results, output)
    _plot_constellations(representative, output)
    return summary


def _plot_ber(results, output, input_path, seed_count):
    """Plot mean BER with an explicit finite-observation zero floor."""
    bits = max(1, len(Path(input_path).read_bytes()) * 8)
    floor = 0.5 / (bits * max(seed_count, 1))
    figure, axis = plt.subplots(figsize=(8, 5.5))
    for scheme in results.values():
        x = [point["snr_db"] for point in scheme["points"]]
        raw = [point["mean_ber"] for point in scheme["points"]]
        axis.semilogy(x, [value if value > 0 else floor for value in raw],
                      "o-", label=scheme["label"])
    axis.set(xlabel="Symbol SNR $E_s/N_0$ (dB)", ylabel="Mean BER",
             title="Finite-seed BER comparison")
    axis.grid(True, which="both", alpha=0.3)
    axis.legend()
    axis.text(0.01, 0.01, f"Zero-error floor: {floor:.2e}",
              transform=axis.transAxes, fontsize=8)
    figure.savefig(output / "level3_ber_comparison.png", dpi=150,
                   bbox_inches="tight")
    plt.close(figure)


def _plot_fer(results, output):
    """Plot mean frame-error rate for every receiver configuration."""
    figure, axis = plt.subplots(figsize=(8, 5.5))
    for scheme in results.values():
        axis.plot([point["snr_db"] for point in scheme["points"]],
                  [point["mean_fer"] for point in scheme["points"]],
                  "o-", label=scheme["label"])
    axis.set(xlabel="Symbol SNR $E_s/N_0$ (dB)", ylabel="Mean FER",
             title="Finite-seed frame error comparison", ylim=(-0.03, 1.03))
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.savefig(output / "level3_fer_comparison.png", dpi=150,
                   bbox_inches="tight")
    plt.close(figure)


def _plot_estimation_error(results, output):
    """Plot mean absolute LS estimation error for Rayleigh modes."""
    figure, axis = plt.subplots(figsize=(8, 5.5))
    for key in ("rayleigh_zf", "rayleigh_mmse", "rayleigh_mrc"):
        scheme = results[key]
        values = []
        for point in scheme["points"]:
            value = point["mean_channel_estimation_error"]
            values.append(max(value if value is not None else 1e-12, 1e-12))
        axis.semilogy(
            [point["snr_db"] for point in scheme["points"]],
            values, "o-", label=scheme["label"])
    axis.set(xlabel="Symbol SNR $E_s/N_0$ (dB)",
             ylabel=r"Mean $|\hat{h}-h|$",
             title="Preamble LS channel-estimation error")
    axis.grid(True, which="both", alpha=0.3)
    axis.legend()
    figure.savefig(output / "channel_estimation_error.png", dpi=150,
                   bbox_inches="tight")
    plt.close(figure)


def _scatter(axis, samples, title):
    """Render a bounded constellation sample on an existing axis."""
    values = np.asarray(samples).reshape(-1)[:2500]
    axis.scatter(values.real, values.imag, s=2, alpha=0.35)
    axis.axhline(0, color="gray", linewidth=0.5)
    axis.axvline(0, color="gray", linewidth=0.5)
    axis.set(title=title, xlabel="I", ylabel="Q")
    axis.grid(True, alpha=0.25)
    axis.set_aspect("equal", adjustable="box")


def _plot_constellations(representative, output):
    """Compare raw Rayleigh, ZF, MMSE and MRC symbol clouds."""
    figure, axes = plt.subplots(2, 2, figsize=(10, 9))
    zf = representative["rayleigh_zf"]
    _scatter(axes[0, 0], zf["_raw_aligned_symbols"], "Before equalization")
    _scatter(axes[0, 1], zf["_equalized_symbols"], "ZF output")
    _scatter(axes[1, 0], representative["rayleigh_mmse"]["_equalized_symbols"],
             "MMSE output")
    _scatter(axes[1, 1], representative["rayleigh_mrc"]["_equalized_symbols"],
             "Two-branch MRC output")
    figure.suptitle("Representative constellations at 16 dB")
    figure.tight_layout()
    figure.savefig(output / "level3_constellation_comparison.png", dpi=150,
                   bbox_inches="tight")
    plt.close(figure)


def main() -> int:
    """Parse the experiment CLI and return a process status."""
    parser = argparse.ArgumentParser(description="Run Level 3 comparisons")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument(
        "--seed-count", type=int, default=5,
        help="Number of deterministic trial seeds (positive integer)",
    )
    args = parser.parse_args()
    if args.seed_count <= 0:
        parser.error("--seed-count must be a positive integer")
    summary = run_experiments(
        args.input, args.output_dir, args.seed, args.seed_count
    )
    print(f"Level 3 experiments complete in {summary['runtime_seconds']:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
