"""绘图模块：星座图、BER 曲线和同步相关峰值图。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import erfc

from src.channel import awgn
from src.channel_coding import channel_encode
from src.framing import build_frame
from src.metrics import calculate_ber
from src.modulation import qpsk_demodulate, qpsk_modulate
from src.pipeline import (
    PREAMBLE_SYMBOLS,
    _generate_prefix_symbols,
    _recover_frame_fields,
)
from src.scramble import scramble
from src.source import source_decode, source_encode
from src.synchronization import synchronize_with_correlation

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

BER_CURVE_SNR_POINTS = [0, 2, 4, 6, 8, 10, 12]
BER_CURVE_TRIALS_PER_SNR = 20


def plot_constellation(rx_symbols: list[complex], output_dir: str) -> None:
    """绘制接收符号星座图，并标出理想 QPSK 星座点。"""
    syms = np.array([complex(s) for s in rx_symbols])
    if len(syms) == 0:
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(syms.real, syms.imag, s=2, alpha=0.4, color="steelblue")
    ideal = np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j]) / np.sqrt(2)
    ax.scatter(ideal.real, ideal.imag, s=80, marker="x", color="red", linewidths=2)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.set_xlabel("同相分量 I")
    ax.set_ylabel("正交分量 Q")
    ax.set_title("接收 QPSK 星座图")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)

    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / "constellation.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _trial_seed(base_seed: int, snr_index: int, trial_index: int) -> int:
    """从基准 seed 派生 BER 曲线试验 seed。"""
    return int(base_seed) + 1000 * int(snr_index) + int(trial_index)


def _text_match_rate(original_text: str, recovered_text: str) -> float:
    """按字符位置计算文本一致率。"""
    max_chars = max(len(original_text), len(recovered_text))
    if max_chars == 0:
        return 1.0
    matches = sum(
        (original_text[index] if index < len(original_text) else "")
        == (recovered_text[index] if index < len(recovered_text) else "")
        for index in range(max_chars)
    )
    return matches / max_chars


def _run_awgn_curve_trial(frame_bits: list[int],
                          frame_symbols: list[complex],
                          original_bits: list[int],
                          original_text: str,
                          snr_db: float,
                          seed: int) -> dict:
    """运行一次轻量 AWGN 试验，用于 BER 曲线统计。

    该函数不写临时文件，但保留实际物理层链路和接收端候选帧恢复逻辑。
    """
    rng = np.random.default_rng(seed)
    n_prefix = int(rng.integers(0, 129))
    tx_symbols = _generate_prefix_symbols(n_prefix, seed) + frame_symbols
    rx_symbols = awgn(tx_symbols, snr_db=snr_db, seed=seed)
    sync_start, _corr_values = synchronize_with_correlation(
        rx_symbols, PREAMBLE_SYMBOLS
    )
    demod_bits = qpsk_demodulate(np.asarray(rx_symbols[sync_start:]))
    predecode_ber = calculate_ber(frame_bits, demod_bits[:len(frame_bits)])
    recovery = _recover_frame_fields(demod_bits, seed)
    descrambled = recovery["descrambled"]
    checksum_pass = bool(recovery["checksum_pass"])

    recovered_text = ""
    if recovery["length_ok"] and len(descrambled) % 8 == 0:
        try:
            recovered_text = source_decode(descrambled)
        except (ValueError, UnicodeDecodeError):
            recovered_text = ""

    text_match_rate = _text_match_rate(original_text, recovered_text)
    return {
        "payload_bits": int(len(original_bits)),
        "predecode_ber": float(predecode_ber),
        "payload_ber": float(calculate_ber(original_bits, descrambled)),
        "frame_error_indicator": 0 if checksum_pass else 1,
        "checksum_pass": checksum_pass,
        "text_match_rate": float(text_match_rate),
        "sync_error_symbols": int(sync_start) - int(n_prefix),
        "sync_success": bool(abs(int(sync_start) - int(n_prefix)) <= 1),
    }


def plot_ber_curve(input_path: str, output_dir: str, seed: int,
                   modulation: str, channel: str) -> None:
    """绘制物理层 BER 均值曲线，并保存逐 SNR 统计数据。

    曲线使用同步后、信道译码前的 ``predecode_ber``，因此可以与同口径的
    未编码 Gray QPSK 理论硬判决 BER 作参考比较。端到端失败率另外以 FER
    曲线展示，不再混入物理层 BER。
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    if channel != "awgn":
        raise ValueError("BER 曲线统计当前只用于 AWGN 默认模式")
    with open(input_path, "r", encoding="utf-8", newline="") as file:
        original_text = file.read()
    original_bits = source_encode(original_text)

    stats = []
    mean_predecode = []
    std_predecode = []
    fer_mean = []
    payload_bits = 0

    for snr_index, snr in enumerate(BER_CURVE_SNR_POINTS):
        trial_metrics = []
        trial_seeds = [
            _trial_seed(seed, snr_index, trial_index)
            for trial_index in range(BER_CURVE_TRIALS_PER_SNR)
        ]
        for trial_seed in trial_seeds:
            trial_scrambled = scramble(original_bits, trial_seed)
            trial_coded = channel_encode(trial_scrambled)
            trial_frame_bits = build_frame(
                original_bits, trial_coded, seed=trial_seed
            )
            trial_frame_symbols = qpsk_modulate(trial_frame_bits)
            metrics = _run_awgn_curve_trial(
                frame_bits=trial_frame_bits,
                frame_symbols=trial_frame_symbols,
                original_bits=original_bits,
                original_text=original_text,
                snr_db=float(snr),
                seed=trial_seed,
            )
            trial_metrics.append(metrics)
            if payload_bits == 0:
                payload_bits = int(metrics["payload_bits"])

        predecode_values = np.array(
            [float(item["predecode_ber"]) for item in trial_metrics],
            dtype=float,
        )
        frame_errors = np.array(
            [int(item["frame_error_indicator"]) for item in trial_metrics],
            dtype=float,
        )
        checksum_pass = np.array(
            [1.0 if bool(item["checksum_pass"]) else 0.0 for item in trial_metrics],
            dtype=float,
        )
        text_match = np.array(
            [float(item["text_match_rate"]) for item in trial_metrics],
            dtype=float,
        )
        complete_recovery = np.array(
            [
                1.0 if bool(item["checksum_pass"])
                and float(item["text_match_rate"]) == 1.0 else 0.0
                for item in trial_metrics
            ],
            dtype=float,
        )

        point = {
            "snr_db": float(snr),
            "num_trials": int(BER_CURVE_TRIALS_PER_SNR),
            "predecode_ber_mean": float(np.mean(predecode_values)),
            "predecode_ber_std": float(np.std(predecode_values, ddof=0)),
            "predecode_ber_min": float(np.min(predecode_values)),
            "predecode_ber_max": float(np.max(predecode_values)),
            "fer_mean": float(np.mean(frame_errors)),
            "checksum_pass_rate": float(np.mean(checksum_pass)),
            "complete_recovery_rate": float(np.mean(complete_recovery)),
            "text_match_rate_mean": float(np.mean(text_match)),
            "trial_seeds": [int(value) for value in trial_seeds],
        }
        stats.append(point)
        mean_predecode.append(point["predecode_ber_mean"])
        std_predecode.append(point["predecode_ber_std"])
        fer_mean.append(point["fer_mean"])

    with open(output_path / "ber_curve_data.json", "w", encoding="utf-8") as file:
        json.dump(stats, file, indent=2, ensure_ascii=False, allow_nan=False)

    frame_bit_count = max(160 + 3 * payload_bits, 1)
    detection_floor = 0.5 / max(frame_bit_count * BER_CURVE_TRIALS_PER_SNR, 1)
    plot_ber = [value if value > 0.0 else detection_floor for value in mean_predecode]
    zero_mask = [value == 0.0 for value in mean_predecode]

    # 未编码 Gray QPSK 理论 BER，SNR 按 E_s/N_0 解释。
    snr_linear = 10.0 ** (np.array(BER_CURVE_SNR_POINTS) / 10.0)
    reference_ber = 0.5 * erfc(np.sqrt(snr_linear / 2.0))

    fig, ax = plt.subplots(figsize=(7, 5))
    lower = np.maximum(
        np.array(plot_ber) - np.array(std_predecode), detection_floor
    )
    upper = np.maximum(
        np.array(plot_ber) + np.array(std_predecode), detection_floor
    )
    ax.semilogy(
        BER_CURVE_SNR_POINTS,
        plot_ber,
        "o-",
        color="steelblue",
        label="物理层 predecode_ber 均值",
    )
    ax.fill_between(
        BER_CURVE_SNR_POINTS,
        lower,
        upper,
        color="steelblue",
        alpha=0.15,
        label="predecode_ber 标准差范围",
    )
    ax.semilogy(
        BER_CURVE_SNR_POINTS,
        reference_ber,
        "--",
        color="darkorange",
        label="理想未编码 Gray QPSK BER",
    )
    for index, is_zero in enumerate(zero_mask):
        if is_zero:
            ax.annotate(
                "未观察到误码",
                (BER_CURVE_SNR_POINTS[index], plot_ber[index]),
                textcoords="offset points",
                xytext=(0, -18),
                ha="center",
                fontsize=7,
                color="steelblue",
                arrowprops=dict(arrowstyle="->", color="steelblue", lw=0.8),
            )

    ax2 = ax.twinx()
    ax2.plot(
        BER_CURVE_SNR_POINTS,
        fer_mean,
        "s--",
        color="crimson",
        label="端到端 FER 均值",
    )
    ax2.set_ylim(-0.02, 1.02)
    ax2.set_ylabel("FER")

    ax.set_xlabel("SNR $E_s/N_0$ (dB)")
    ax.set_ylabel("物理层 BER")
    ax.set_title("物理层 BER 与端到端 FER 随 SNR 变化")
    lines, labels = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines + lines2, labels + labels2, loc="best")
    ax.grid(True, alpha=0.3)

    path = output_path / "ber_curve.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_sync_peak(corr_values: list[float], sync_start: int,
                   output_dir: str) -> None:
    """绘制归一化互相关曲线，并标出同步峰值位置。"""
    if len(corr_values) == 0:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    x = list(range(len(corr_values)))
    ax.plot(x, corr_values, color="steelblue", linewidth=0.8)
    ax.axvline(sync_start, color="red", linestyle="--", linewidth=1.2,
               label=f"检测峰值: {sync_start}")
    ax.set_xlabel("符号偏移")
    ax.set_ylabel("归一化相关值")
    ax.set_title("同步相关峰值")
    ax.legend()
    ax.grid(True, alpha=0.3)

    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / "sync_peak.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_all_plots(metrics: dict, output_dir: str,
                       input_path: str, seed: int,
                       modulation: str, channel: str) -> None:
    """生成 AWGN 默认模式需要的三张图。"""
    plot_constellation(metrics["_rx_symbols"], output_dir)
    plot_ber_curve(input_path, output_dir, seed, modulation, channel)
    plot_sync_peak(metrics["_corr_values"], metrics["_sync_start"], output_dir)
