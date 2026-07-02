"""BER 曲线统计口径测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.plotting as plotting


def test_ber_curve_uses_predecode_ber_statistics(monkeypatch, tmp_path):
    input_path = tmp_path / "input.txt"
    input_path.write_text("plot statistics", encoding="utf-8")
    calls = []

    def fake_curve_trial(**kwargs):
        calls.append(kwargs)
        snr = float(kwargs["snr_db"])
        seed = int(kwargs["seed"])
        return {
            "payload_bits": 128,
            "ber": 0.99,
            "payload_ber": 0.99,
            "predecode_ber": snr / 1000.0 + (seed % 5) / 100000.0,
            "frame_error_indicator": int(seed % 2),
            "checksum_pass": seed % 2 == 0,
            "text_match_rate": 1.0 if seed % 2 == 0 else 0.0,
        }

    monkeypatch.setattr(plotting, "_run_awgn_curve_trial", fake_curve_trial)

    plotting.plot_ber_curve(str(input_path), str(tmp_path), 2026, "qpsk", "awgn")

    data = json.loads((tmp_path / "ber_curve_data.json").read_text(encoding="utf-8"))
    assert len(data) == len(plotting.BER_CURVE_SNR_POINTS)
    assert plotting.BER_CURVE_TRIALS_PER_SNR >= 20
    assert len(calls) == len(plotting.BER_CURVE_SNR_POINTS) * plotting.BER_CURVE_TRIALS_PER_SNR
    for point in data:
        assert point["num_trials"] == plotting.BER_CURVE_TRIALS_PER_SNR
        assert point["predecode_ber_mean"] != pytest.approx(0.99)
        assert "predecode_ber_std" in point
        assert "predecode_ber_min" in point
        assert "predecode_ber_max" in point
        assert "fer_mean" in point
        assert "checksum_pass_rate" in point
        assert "complete_recovery_rate" in point
    assert (tmp_path / "ber_curve.png").exists()
    assert (tmp_path / "ber_curve.png").stat().st_size > 0
