"""Stage F Level 3 unit, interface, regression and end-to-end tests."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.channel import rayleigh_flat_fading
from src.diversity import mrc_combine
from src.equalization import estimate_flat_channel, mmse_equalize, zf_equalize
from src.metrics import save_metrics
from src.modulation import qpsk_modulate
from src.pipeline import PREAMBLE_SYMBOLS, run_pipeline
from src.synchronization import synchronize_branches


def _symbols():
    return np.asarray(qpsk_modulate([0, 0, 0, 1, 1, 1, 1, 0]))


def _run_text(text, equalizer, diversity_order, snr=40.0, seed=2026):
    directory = tempfile.mkdtemp()
    input_path = Path(directory) / "input.txt"
    output_path = Path(directory) / "output.txt"
    input_path.write_text(text, encoding="utf-8")
    metrics = run_pipeline(
        str(input_path), str(output_path), snr, seed, "qpsk", "rayleigh",
        equalizer, diversity_order,
    )
    recovered = output_path.read_text(encoding="utf-8")
    import shutil
    shutil.rmtree(directory, ignore_errors=True)
    return metrics, recovered


def test_rayleigh_same_seed_is_exactly_reproducible():
    first = rayleigh_flat_fading(_symbols(), 12.0, 2026, 2)
    second = rayleigh_flat_fading(_symbols(), 12.0, 2026, 2)
    assert np.array_equal(first[0], second[0])
    assert np.array_equal(first[1], second[1])
    assert first[2] == second[2]


def test_rayleigh_different_seed_changes_channel():
    first = rayleigh_flat_fading(_symbols(), 12.0, 2026, 1)
    second = rayleigh_flat_fading(_symbols(), 12.0, 2027, 1)
    assert not np.array_equal(first[1], second[1])


def test_rayleigh_branch_shapes_and_empty_input():
    received, channel, variance = rayleigh_flat_fading([], 12.0, 8, 2)
    assert received.shape == (2, 0)
    assert channel.shape == (2,)
    assert variance == 0.0
    assert np.all(np.isfinite(channel))
    with pytest.raises(ValueError, match="1 or 2"):
        rayleigh_flat_fading(_symbols(), 12.0, 8, 3)


def test_rayleigh_channel_average_power_is_near_one():
    coefficients = [
        rayleigh_flat_fading([], 12.0, seed, 1)[1][0]
        for seed in range(1000)
    ]
    assert float(np.mean(np.abs(coefficients) ** 2)) == \
        pytest.approx(1.0, abs=0.10)


def test_zf_recovers_noiseless_symbols():
    symbols = _symbols()
    channel = 0.35 - 0.8j
    assert np.allclose(zf_equalize(channel * symbols, channel), symbols)


def test_mmse_matches_manual_formula():
    received = np.asarray([1 + 2j, -0.5 + 0.25j])
    channel = 0.4 - 0.3j
    variance = 0.2
    expected = np.conj(channel) * received / (abs(channel) ** 2 + variance)
    actual = mmse_equalize(received, channel, variance)
    assert np.allclose(actual, expected)
    assert not np.allclose(actual, zf_equalize(received, channel))


def test_ls_channel_estimate_is_exact_without_noise():
    preamble = np.asarray(PREAMBLE_SYMBOLS)
    channel = -0.25 + 0.9j
    assert estimate_flat_channel(channel * preamble, preamble) == \
        pytest.approx(channel, abs=1e-12)


def test_channel_estimator_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="same length"):
        estimate_flat_channel([1 + 0j], [1 + 0j, 1 - 0j])
    with pytest.raises(ValueError, match="must not be empty"):
        estimate_flat_channel([], [])
    with pytest.raises(ValueError, match="energy"):
        estimate_flat_channel([1 + 0j], [0 + 0j])


def test_mrc_matches_manual_formula():
    received = np.asarray([[1 + 1j, 2 - 1j], [-0.5 + 0.2j, 1 + 0.1j]])
    estimates = np.asarray([0.5 + 0.25j, -0.2 + 0.8j])
    expected = np.sum(np.conj(estimates)[:, None] * received, axis=0)
    expected /= np.sum(np.abs(estimates) ** 2)
    assert np.allclose(mrc_combine(received, estimates), expected)


def test_mrc_recovers_noiseless_symbols():
    symbols = _symbols()
    channels = np.asarray([0.1 + 0.2j, -0.7 + 0.4j])
    received = channels[:, None] * symbols[None, :]
    assert np.allclose(mrc_combine(received, channels), symbols)


def test_deep_fade_handling_never_returns_nonfinite_values():
    with pytest.raises(ValueError, match="near-zero"):
        zf_equalize([1 + 1j], 0j)
    with pytest.raises(ValueError, match="too small"):
        mrc_combine([[1 + 1j], [2 + 2j]], [0j, 0j])
    assert np.all(np.isfinite(
        mmse_equalize([1 + 1j], 0j, noise_variance=0.1)
    ))


def test_multibranch_synchronization_combines_symbol_metrics():
    preamble = np.asarray(PREAMBLE_SYMBOLS)
    prefix = np.asarray(qpsk_modulate([0, 1] * 17))
    transmitted = np.concatenate([prefix, preamble, _symbols()])
    channels = np.asarray([0.4 + 0.6j, -0.2 + 1.1j])
    branches = channels[:, None] * transmitted[None, :]
    start, combined, individual = synchronize_branches(branches, preamble)
    assert start == len(prefix)
    assert len(individual) == 2
    assert len(combined) == len(individual[0])


def test_awgn_old_and_explicit_default_calls_are_identical():
    directory = tempfile.mkdtemp()
    input_path = Path(directory) / "input.txt"
    old_output = Path(directory) / "old.txt"
    new_output = Path(directory) / "new.txt"
    input_path.write_text("AWGN 基线兼容性", encoding="utf-8")
    old = run_pipeline(str(input_path), str(old_output), 12, 2026,
                       "qpsk", "awgn")
    new = run_pipeline(str(input_path), str(new_output), 12, 2026,
                       "qpsk", "awgn", "none", 1)
    assert old_output.read_bytes() == new_output.read_bytes()
    for field in ("ber", "fer", "text_match_rate", "checksum_pass",
                  "sync_start_index"):
        assert old[field] == new[field]
    import shutil
    shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.parametrize("equalizer", ["zf", "mmse"])
def test_single_branch_high_snr_recovers_chinese(equalizer):
    text = "单分支瑞利信道中文恢复"
    metrics, recovered = _run_text(text, equalizer, 1)
    assert recovered == text
    assert metrics["checksum_pass"] is True
    assert metrics["fer"] == 0.0


def test_two_branch_mrc_high_snr_recovers_text():
    text = "二分支 MRC 恢复"
    metrics, recovered = _run_text(text, "none", 2)
    assert recovered == text
    assert metrics["equalizer"] == "mrc"


def test_rayleigh_handles_english_chinese_and_emoji():
    text = "Rayleigh 平坦衰落 😀 QPSK"
    metrics, recovered = _run_text(text, "mmse", 1)
    assert recovered == text
    assert metrics["text_match_rate"] == 1.0


def test_low_snr_rayleigh_does_not_crash():
    metrics, _ = _run_text("低 SNR 安全失败", "zf", 1, snr=0.0)
    assert 0.0 <= metrics["ber"] <= 1.0
    assert metrics["fer"] in (0.0, 1.0)
    assert isinstance(metrics["checksum_pass"], bool)


def test_double_branch_metrics_fields_are_serializable():
    metrics, _ = _run_text("metrics", "mmse", 2)
    directory = tempfile.mkdtemp()
    save_metrics(metrics, directory)
    data = json.loads((Path(directory) / "metrics.json").read_text("utf-8"))
    for field in ("fading_model", "equalizer", "diversity_order",
                  "channel_estimates_real", "channel_estimates_imag",
                  "channel_estimates_magnitude", "channel_estimation_error",
                  "noise_variance", "sync_success"):
        assert field in data
    import shutil
    shutil.rmtree(directory, ignore_errors=True)


def test_single_branch_metrics_include_scalar_estimate_fields():
    metrics, _ = _run_text("scalar metrics", "zf", 1)
    for field in ("channel_estimate_real", "channel_estimate_imag",
                  "channel_estimate_magnitude", "channel_estimate_phase_rad",
                  "channel_estimation_error", "noise_variance"):
        assert field in metrics


def test_rayleigh_end_to_end_metrics_are_reproducible():
    first, first_text = _run_text("可复现", "zf", 1, seed=2030)
    second, second_text = _run_text("可复现", "zf", 1, seed=2030)
    assert first_text == second_text
    keys = [key for key in first if not key.startswith("_")]
    assert {key: first[key] for key in keys} == {
        key: second[key] for key in keys
    }


def test_receiver_uses_estimated_not_simulation_true_channel(monkeypatch):
    import src.pipeline as pipeline

    physical_channel = 0.7 + 0.2j
    wrong_diagnostic = 99.0 - 77.0j

    def fake_channel(symbols, snr_db, seed, diversity_order):
        transmitted = np.asarray(symbols, dtype=np.complex128)
        return ((physical_channel * transmitted)[None, :],
                np.asarray([wrong_diagnostic]), 0.0)

    monkeypatch.setattr(pipeline, "rayleigh_flat_fading", fake_channel)
    metrics, recovered = _run_text("前导估计不能偷用真实 h", "zf", 1)
    assert recovered == "前导估计不能偷用真实 h"
    assert metrics["checksum_pass"] is True
    assert metrics["channel_estimation_error"] > 1.0


def test_fixed_multiseed_mrc_fer_not_worse_than_single_zf():
    directory = tempfile.mkdtemp()
    input_path = Path(directory) / "input.txt"
    input_path.write_text("固定多 seed 性能比较", encoding="utf-8")
    zf_fer, mrc_fer = [], []
    for seed in [101, 102, 103, 104, 105]:
        zf_fer.append(run_pipeline(
            str(input_path), str(Path(directory) / "zf.txt"), 12, seed,
            "qpsk", "rayleigh", "zf", 1)["fer"])
        mrc_fer.append(run_pipeline(
            str(input_path), str(Path(directory) / "mrc.txt"), 12, seed,
            "qpsk", "rayleigh", "none", 2)["fer"])
    assert float(np.mean(mrc_fer)) <= float(np.mean(zf_fer))
    import shutil
    shutil.rmtree(directory, ignore_errors=True)


@pytest.mark.parametrize("arguments", [
    ["--channel", "awgn", "--equalizer", "zf", "--diversity-order", "1"],
    ["--channel", "rayleigh", "--equalizer", "none", "--diversity-order", "1"],
    ["--channel", "rayleigh", "--equalizer", "zf", "--diversity-order", "2"],
])
def test_cli_rejects_invalid_receiver_combinations(arguments):
    command = [sys.executable, "main.py", "--input", "Test.txt", "--output",
               os.path.join(tempfile.gettempdir(), "invalid_level3.txt"),
               "--snr", "12", "--seed", "2026", "--mod", "qpsk"] + arguments
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Error:" in result.stderr
