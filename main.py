"""无线通信期末项目统一 CLI 入口。

示例::

    python main.py --input Test.txt --output results/received.txt \
                   --snr 12 --seed 2026 --mod qpsk --channel awgn
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from src.config import MIN_SNR_DB, MAX_SNR_DB, validate_snr_db
from src.manifest import build_run_manifest, write_run_manifest
from src.metrics import save_metrics
from src.pipeline import run_pipeline
from src.plotting import generate_all_plots, plot_constellation, plot_sync_peak


def _expected_plot_names(channel: str) -> list[str]:
    """返回当前 CLI 模式承诺生成的图像文件。"""
    if channel == "awgn":
        return ["constellation.png", "ber_curve.png", "sync_peak.png"]
    return ["constellation.png", "sync_peak.png"]


def _clear_expected_plots(output_dir: Path, names: list[str]) -> None:
    """生成本次图像前清理旧图，避免把历史文件误判为新结果。"""
    for name in names:
        path = output_dir / name
        if path.exists():
            path.unlink()


def _valid_files(output_dir: Path, names: list[str]) -> tuple[list[str], list[str]]:
    """区分有效文件和缺失或空文件。"""
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
    """向 CLI 用户输出可复查的图像交付错误。"""
    print("Error: 图像交付失败。", file=sys.stderr)
    print(f"  预期图像: {expected}", file=sys.stderr)
    print(f"  有效生成图像: {valid}", file=sys.stderr)
    print(f"  缺失或无效图像: {invalid}", file=sys.stderr)
    if plot_error is not None:
        print(f"  绘图异常: {plot_error}", file=sys.stderr)


def _validate_io_paths(input_path: Path, output_path: Path) -> tuple[bool, str | None]:
    """在主流程运行前校验输入和输出路径，避免留下半生成结果。"""
    if not input_path.exists():
        return False, f"Error: 输入文件不存在: {input_path}"
    if not input_path.is_file():
        return False, f"Error: 输入路径不是普通文件: {input_path}"
    if output_path.exists() and output_path.is_dir():
        return False, f"Error: 输出路径不能是目录: {output_path}"

    output_dir = output_path.parent if output_path.parent != Path("") else Path(".")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, PermissionError, OSError) as error:
        return False, (
            f"Error: 无法创建输出目录 '{output_dir}': {error}。"
            " 请检查父路径是否为目录以及是否具备写入权限。"
        )
    if not output_dir.is_dir():
        return False, f"Error: 输出父路径不是目录: {output_dir}"

    probe = output_dir / f".write_probe_{os.getpid()}"
    try:
        with open(probe, "wb"):
            pass
    except (PermissionError, OSError) as error:
        return False, (
            f"Error: 输出目录不可写 '{output_dir}': {error}。"
            " 请更换 --output 或修复目录权限。"
        )
    finally:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
    return True, None


def _normalize_argv_for_argparse(argv: list[str]) -> list[str]:
    """兼容 ``--snr -inf`` 这类会被 argparse 误判为选项的取值。"""
    normalized = []
    index = 0
    while index < len(argv):
        if index + 1 < len(argv) and argv[index] == "--snr" \
                and argv[index + 1].lower() in ("-inf", "-infinity"):
            normalized.append(f"--snr={argv[index + 1]}")
            index += 2
            continue
        normalized.append(argv[index])
        index += 1
    return normalized


def main() -> int:
    """解析 CLI 参数、运行通信链路并写出交付文件。"""
    parser = argparse.ArgumentParser(description="无线通信基带仿真")
    parser.add_argument("--input", required=True, help="输入 UTF-8 文本文件")
    parser.add_argument("--output", required=True, help="恢复文本输出路径")
    parser.add_argument("--snr", type=float, required=True, help="符号 SNR(dB)")
    parser.add_argument("--seed", type=int, required=True, help="随机种子")
    parser.add_argument("--mod", required=True, help="调制方式: qpsk")
    parser.add_argument("--channel", required=True, help="信道类型: awgn 或 rayleigh")
    parser.add_argument(
        "--equalizer",
        default="none",
        help="接收端均衡器: none、zf 或 mmse",
    )
    parser.add_argument(
        "--diversity-order",
        type=int,
        default=1,
        help="接收分支数: 1 或 2",
    )

    args = parser.parse_args(_normalize_argv_for_argparse(sys.argv[1:]))

    try:
        args.snr = validate_snr_db(args.snr)
    except ValueError:
        print(
            "Error: --snr 必须是有限数，并位于 "
            f"[{MIN_SNR_DB:g}, {MAX_SNR_DB:g}] dB 范围内；"
            f"当前值为 {args.snr}。",
            file=sys.stderr,
        )
        return 1

    if args.mod not in ("qpsk",):
        print(f"Error: 不支持的 --mod '{args.mod}'；合法值为 qpsk。", file=sys.stderr)
        return 1
    if args.channel not in ("awgn", "rayleigh"):
        print(
            f"Error: 不支持的 --channel '{args.channel}'；合法值为 awgn 或 rayleigh。",
            file=sys.stderr,
        )
        return 1
    if args.equalizer not in ("none", "zf", "mmse"):
        print(
            f"Error: 不支持的 --equalizer '{args.equalizer}'；"
            "合法值为 none、zf 或 mmse。",
            file=sys.stderr,
        )
        return 1
    if args.diversity_order not in (1, 2):
        print(
            f"Error: 不支持的 --diversity-order {args.diversity_order}；"
            "合法值为 1 或 2。",
            file=sys.stderr,
        )
        return 1
    if args.channel == "awgn" and (
            args.equalizer != "none" or args.diversity_order != 1):
        print(
            "Error: AWGN 模式要求 --equalizer none 且 --diversity-order 1。",
            file=sys.stderr,
        )
        return 1
    if args.channel == "rayleigh" and args.diversity_order == 1 \
            and args.equalizer not in ("zf", "mmse"):
        print("Error: 单分支 Rayleigh 要求 --equalizer zf 或 mmse。", file=sys.stderr)
        return 1
    if args.channel == "rayleigh" and args.diversity_order == 2 \
            and args.equalizer not in ("none", "mmse"):
        print(
            "Error: 双分支 Rayleigh 使用 MRC；请使用 --equalizer none，"
            "或使用兼容参数 mmse。",
            file=sys.stderr,
        )
        return 1

    argv = sys.argv[:]
    input_path = Path(args.input)
    output_path = Path(args.output)
    ok, path_error = _validate_io_paths(input_path, output_path)
    if not ok:
        print(path_error, file=sys.stderr)
        return 1

    output_dir_path = output_path.parent
    output_dir = str(output_dir_path)
    expected_plots = _expected_plot_names(args.channel)
    min_valid_plots = len(expected_plots)

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
    except (FileNotFoundError, PermissionError, OSError) as error:
        print(f"Error: 文件处理失败: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Error: 通信链路执行失败: {error}", file=sys.stderr)
        return 1

    try:
        save_metrics(metrics, output_dir)
    except (PermissionError, OSError, TypeError, ValueError) as error:
        print(f"Error: metrics.json 写入失败: {error}", file=sys.stderr)
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
    except Exception as error:
        plot_error = error

    valid_plots, invalid_plots = _valid_files(output_dir_path, expected_plots)
    if plot_error is not None or len(valid_plots) < min_valid_plots:
        _print_plot_failure(expected_plots, valid_plots, invalid_plots, plot_error)
        return 1

    elapsed = time.perf_counter() - t0
    generated_files = [Path(args.output).name, "metrics.json", *valid_plots]
    ber_data_path = output_dir_path / "ber_curve_data.json"
    if ber_data_path.exists() and ber_data_path.is_file():
        generated_files.append("ber_curve_data.json")
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
    except Exception as error:
        print(f"Error: run_manifest.json 生成失败: {error}", file=sys.stderr)
        return 1

    print(f"通信链路完成，用时 {elapsed:.2f}s")
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
