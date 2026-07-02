"""Wireless final project — CLI entry point.

Usage::

    python main.py --input Test.txt --output results/received.txt \\
                   --snr 12 --seed 2026 --mod qpsk --channel awgn
"""

import argparse
import math
import sys
import time
from pathlib import Path

from src.pipeline import run_pipeline
from src.metrics import save_metrics
from src.plotting import generate_all_plots, plot_constellation, plot_sync_peak
from src.manifest import build_run_manifest, write_run_manifest


def _expected_plot_names(channel: str) -> list[str]:
    """Return plot files promised by this CLI mode."""
    if channel == "awgn":
        return ["constellation.png", "ber_curve.png", "sync_peak.png"]
    return ["constellation.png", "sync_peak.png"]


def _clear_expected_plots(output_dir: Path, names: list[str]) -> None:
    """Remove stale plot files before generating this run's artefacts."""
    for name in names:
        path = output_dir / name
        if path.exists():
            path.unlink()


def _valid_files(output_dir: Path, names: list[str]) -> tuple[list[str], list[str]]:
    """Split expected files into valid and missing-or-empty names."""
    valid = []
    invalid = []
    for name in names:
        path = output_dir / name
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            valid.append(name)
        else:
            invalid.append(name)
    return valid, invalid


def _print_plot_failure(
        expected: list[str],
        valid: list[str],
        invalid: list[str],
        plot_error: Exception | None) -> None:
    """Print a clear plot-delivery error for CLI users and tests."""
    print("Error: plot delivery failed.", file=sys.stderr)
    print(f"  Expected plots: {expected}", file=sys.stderr)
    print(f"  Valid generated plots: {valid}", file=sys.stderr)
    print(f"  Missing or invalid plots: {invalid}", file=sys.stderr)
    if plot_error is not None:
        print(f"  Plot exception: {plot_error}", file=sys.stderr)


def main() -> int:
    """Parse CLI arguments, run the pipeline, and write all output artefacts.

    Returns:
        0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Wireless communication baseband simulation"
    )
    parser.add_argument("--input", required=True, help="Input UTF-8 text file")
    parser.add_argument("--output", required=True, help="Output recovered text file")
    parser.add_argument("--snr", type=float, required=True, help="Symbol SNR (dB)")
    parser.add_argument("--seed", type=int, required=True, help="Random seed")
    parser.add_argument("--mod", required=True, help="Modulation (qpsk)")
    parser.add_argument(
        "--channel", required=True, choices=("awgn", "rayleigh"),
        help="Channel type",
    )
    parser.add_argument(
        "--equalizer", choices=("none", "zf", "mmse"), default="none",
        help="Receiver equalizer (default: none)",
    )
    parser.add_argument(
        "--diversity-order", type=int, choices=(1, 2), default=1,
        help="Number of receive branches (default: 1)",
    )

    args = parser.parse_args()

    if not math.isfinite(args.snr):
        print(
            f"Error: SNR must be a finite number, got {args.snr}",
            file=sys.stderr,
        )
        return 1

    if args.mod not in ("qpsk",):
        print(
            f"Error: unsupported modulation '{args.mod}'."
            " Only 'qpsk' is supported.",
            file=sys.stderr,
        )
        return 1
    if args.channel == "awgn" and (
            args.equalizer != "none" or args.diversity_order != 1):
        print(
            "Error: AWGN requires --equalizer none --diversity-order 1.",
            file=sys.stderr,
        )
        return 1
    if args.channel == "rayleigh" and args.diversity_order == 1 \
            and args.equalizer not in ("zf", "mmse"):
        print(
            "Error: single-branch Rayleigh requires --equalizer zf or mmse.",
            file=sys.stderr,
        )
        return 1
    if args.channel == "rayleigh" and args.diversity_order == 2 \
            and args.equalizer not in ("none", "mmse"):
        print(
            "Error: two-branch Rayleigh uses MRC; use --equalizer none "
            "or the compatibility token mmse.",
            file=sys.stderr,
        )
        return 1

    argv = sys.argv[:]
    output_dir_path = Path(args.output).parent
    output_dir = str(output_dir_path)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    expected_plots = _expected_plot_names(args.channel)
    min_valid_plots = 2

    t0 = time.perf_counter()

    try:
        metrics = run_pipeline(
            input_path=args.input,
            output_path=args.output,
            snr_db=args.snr,
            seed=args.seed,
            modulation=args.mod,
            channel=args.channel,
            equalizer=args.equalizer,
            diversity_order=args.diversity_order,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: pipeline failed — {e}", file=sys.stderr)
        return 1

    try:
        save_metrics(metrics, output_dir)
    except Exception as e:
        print(f"Error: metrics writing failed - {e}", file=sys.stderr)
        return 1

    plot_error = None
    try:
        _clear_expected_plots(output_dir_path, expected_plots)
        if args.channel == "awgn":
            generate_all_plots(
                metrics=metrics,
                output_dir=output_dir,
                input_path=args.input,
                seed=args.seed,
                modulation=args.mod,
                channel=args.channel,
            )
        else:
            plot_constellation(metrics["_equalized_symbols"], output_dir)
            plot_sync_peak(
                metrics["_corr_values"], metrics["_sync_start"], output_dir
            )
    except Exception as e:
        plot_error = e

    valid_plots, invalid_plots = _valid_files(output_dir_path, expected_plots)
    if plot_error is not None or len(valid_plots) < min_valid_plots:
        _print_plot_failure(expected_plots, valid_plots, invalid_plots, plot_error)
        return 1

    elapsed = time.perf_counter() - t0
    generated_files = [Path(args.output).name, "metrics.json", *valid_plots]
    try:
        manifest = build_run_manifest(
            argv=argv,
            input_path=args.input,
            output_path=args.output,
            output_dir=output_dir,
            runtime_seconds=elapsed,
            seed=args.seed,
            snr_db=args.snr,
            modulation=args.mod,
            channel=args.channel,
            generated_files=generated_files,
            cwd=Path.cwd(),
        )
        manifest_path = write_run_manifest(manifest, output_dir)
    except Exception as e:
        print(f"Error: run manifest generation failed - {e}", file=sys.stderr)
        return 1

    print(f"Pipeline complete in {elapsed:.2f}s")
    print(f"  SNR: {args.snr} dB, Seed: {args.seed}")
    print(f"  BER: {metrics['ber']:.6f}, FER: {metrics['fer']:.1f}")
    print(f"  Predecode BER: {metrics['predecode_ber']:.6f}")
    print(f"  Payload BER: {metrics['payload_ber']:.6f}")
    print(f"  Frame error indicator: {metrics['frame_error_indicator']}")
    print(f"  Text match: {metrics['text_match_rate']:.4f}")
    print(f"  CRC pass: {metrics['checksum_pass']}")
    print(f"  Sync start: {metrics['sync_start_index']}")
    print(f"  True prefix symbols: {metrics['true_prefix_symbols']}")
    print(f"  Sync error symbols: {metrics['sync_error_symbols']}")
    print(f"  Sync success: {metrics['sync_success']}")
    if args.channel == "rayleigh":
        print(
            f"  Receiver: {metrics['equalizer']}, "
            f"diversity order: {metrics['diversity_order']}"
        )
        print(
            "  Channel estimation error: "
            f"{metrics['channel_estimation_error']}"
        )
    print(f"  Output: {args.output}")
    print(f"  Metrics: {Path(output_dir) / 'metrics.json'}")
    print(f"  Manifest: {manifest_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
