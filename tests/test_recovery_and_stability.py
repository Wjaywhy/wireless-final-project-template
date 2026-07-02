"""文本恢复、同步随机性和稳定性回归测试。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.pipeline import run_pipeline


def _run_bytes_case(tmp_path: Path, payload: bytes,
                    snr_db: float = 12.0, seed: int = 2026) -> dict:
    input_path = tmp_path / "input.txt"
    output_path = tmp_path / "received.txt"
    input_path.write_bytes(payload)
    metrics = run_pipeline(
        str(input_path), str(output_path), snr_db, seed, "qpsk", "awgn"
    )
    assert output_path.read_bytes() == payload
    assert metrics["checksum_pass"] is True
    assert metrics["frame_error_indicator"] == 0
    assert metrics["payload_ber"] == 0.0
    return metrics


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        "A".encode("utf-8"),
        "hello wireless".encode("utf-8"),
        "纯中文文本".encode("utf-8"),
        "English 与中文混合".encode("utf-8"),
        "emoji 🙂🚀".encode("utf-8"),
        b"\xef\xbb\xbfUTF-8 BOM",
        "第一行\n第二行\t制表符".encode("utf-8"),
        b"null\x00byte",
        ("长文本" * 80).encode("utf-8"),
        b"A" * 31,
        b"B" * 32,
    ],
)
def test_awgn_text_recovery_matches_original_bytes(tmp_path, payload):
    _run_bytes_case(tmp_path, payload)


def test_dynamic_inputs_are_not_hardcoded(tmp_path):
    rng = np.random.default_rng(7070)
    alphabet = np.array(list("abcdefghijklmnopqrstuvwxyz0123456789"))
    text1 = "随机文本-" + "".join(rng.choice(alphabet, size=48).tolist())
    text2 = "随机文本-" + "".join(rng.choice(alphabet, size=48).tolist())
    assert text1 != text2

    first_in = tmp_path / "first.txt"
    first_out = tmp_path / "first_received.txt"
    second_in = tmp_path / "second.txt"
    second_out = tmp_path / "second_received.txt"
    first_in.write_text(text1, encoding="utf-8")
    second_in.write_text(text2, encoding="utf-8")

    first_metrics = run_pipeline(
        str(first_in), str(first_out), 12.0, 2026, "qpsk", "awgn"
    )
    second_metrics = run_pipeline(
        str(second_in), str(second_out), 12.0, 2026, "qpsk", "awgn"
    )

    assert first_metrics["checksum_pass"] is True
    assert second_metrics["checksum_pass"] is True
    assert first_out.read_text(encoding="utf-8") == text1
    assert second_out.read_text(encoding="utf-8") == text2
    assert first_out.read_bytes() != second_out.read_bytes()


@pytest.mark.parametrize(
    ("channel", "equalizer", "diversity_order"),
    [
        ("awgn", "none", 1),
        ("rayleigh", "zf", 1),
        ("rayleigh", "mmse", 1),
        ("rayleigh", "none", 2),
    ],
)
def test_sync_and_metrics_fields_across_supported_modes(
        tmp_path, channel, equalizer, diversity_order):
    input_path = tmp_path / f"{channel}_{equalizer}.txt"
    output_path = tmp_path / f"{channel}_{equalizer}_received.txt"
    input_path.write_text("同步字段回归 Sync 123", encoding="utf-8")

    metrics = run_pipeline(
        str(input_path),
        str(output_path),
        20.0,
        2031,
        "qpsk",
        channel,
        equalizer,
        diversity_order,
    )

    for field in [
        "sync_start_index", "true_prefix_symbols", "sync_error_symbols",
        "sync_success", "checksum_pass", "fer", "payload_ber",
        "predecode_ber", "text_match_rate", "frame_parse_strategy",
    ]:
        assert field in metrics
    assert metrics["sync_error_symbols"] == (
        metrics["sync_start_index"] - metrics["true_prefix_symbols"]
    )
    assert isinstance(metrics["sync_success"], bool)
    assert 0.0 <= metrics["predecode_ber"] <= 1.0
    assert 0.0 <= metrics["payload_ber"] <= 1.0
    assert 0.0 <= metrics["text_match_rate"] <= 1.0


def test_12db_awgn_stability_across_text_classes(tmp_path):
    official = Path("Test.txt").read_text(encoding="utf-8")
    cases = {
        "short_english": "Short wireless test.",
        "short_chinese": "短中文测试",
        "mixed_emoji": "Hello 无线通信🙂🚀 QPSK",
        "official": official,
    }
    report = {}

    for name, text in cases.items():
        input_path = tmp_path / f"{name}.txt"
        output_path = tmp_path / f"{name}_received.txt"
        input_path.write_text(text, encoding="utf-8")
        failures = []
        sync_success = 0
        crc_success = 0
        full_recovery = 0
        predecode_values = []
        max_sync_error = 0
        for seed in range(2026, 2126):
            metrics = run_pipeline(
                str(input_path), str(output_path), 12.0, seed, "qpsk", "awgn"
            )
            recovered = output_path.read_text(encoding="utf-8")
            sync_success += int(metrics["sync_success"])
            crc_success += int(metrics["checksum_pass"])
            full_recovery += int(recovered == text)
            predecode_values.append(float(metrics["predecode_ber"]))
            max_sync_error = max(
                max_sync_error, abs(int(metrics["sync_error_symbols"]))
            )
            if recovered != text or not metrics["checksum_pass"]:
                failures.append({
                    "seed": seed,
                    "sync_error_symbols": metrics["sync_error_symbols"],
                    "predecode_ber": metrics["predecode_ber"],
                    "payload_ber": metrics["payload_ber"],
                    "frame_parse_strategy": metrics["frame_parse_strategy"],
                    "header_bit_errors": metrics["header_bit_errors"],
                    "crc_bit_errors": metrics["crc_bit_errors"],
                })

        report[name] = {
            "trial_count": 100,
            "sync_success_count": sync_success,
            "crc_success_count": crc_success,
            "full_recovery_count": full_recovery,
            "failure_seeds": failures,
            "mean_predecode_ber": sum(predecode_values) / len(predecode_values),
            "max_sync_error_symbols": max_sync_error,
        }

    assert all(item["sync_success_count"] == 100 for item in report.values()), (
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    assert all(item["crc_success_count"] == 100 for item in report.values()), (
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    assert all(item["full_recovery_count"] == 100 for item in report.values()), (
        json.dumps(report, ensure_ascii=False, indent=2)
    )
