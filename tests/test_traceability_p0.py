"""Traceability, layered metrics, manifest, and CLI artefact tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import main as cli_main
from src.manifest import build_run_manifest, file_sha256, write_run_manifest
from src.metrics import save_metrics
from src.pipeline import run_pipeline


def _write_input(tmp_path: Path, text: str = "traceability test") -> Path:
    path = tmp_path / "input.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_manifest_writes_hashes_when_git_is_unavailable(monkeypatch, tmp_path):
    input_path = _write_input(tmp_path, "manifest")
    output_path = tmp_path / "received.txt"
    output_path.write_text("manifest", encoding="utf-8")

    def no_git(*_args, **_kwargs):
        raise OSError("git unavailable")

    monkeypatch.setattr("src.manifest._run_git", no_git)
    manifest = build_run_manifest(
        argv=["main.py", "--input", str(input_path)],
        input_path=input_path,
        output_path=output_path,
        output_dir=tmp_path,
        runtime_seconds=0.25,
        seed=2026,
        snr_db=12.0,
        modulation="qpsk",
        channel="awgn",
        generated_files=["received.txt", "metrics.json"],
        cwd=tmp_path,
    )
    manifest_path = write_run_manifest(manifest, tmp_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert data["git_commit"] is None
    assert data["git_dirty"] is None
    assert data["input_sha256"] == file_sha256(input_path)
    assert data["output_sha256"] == file_sha256(output_path)
    assert data["runtime_seconds"] == pytest.approx(0.25)


def test_sync_truth_and_error_are_public_metrics(tmp_path):
    input_path = _write_input(tmp_path, "sync public")
    output_path = tmp_path / "received.txt"
    metrics = run_pipeline(
        str(input_path), str(output_path), 12.0, 2026, "qpsk", "awgn"
    )
    save_metrics(metrics, str(tmp_path))
    data = json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8"))

    assert data["sync_error_symbols"] == (
        data["sync_start_index"] - data["true_prefix_symbols"]
    )
    assert data["sync_success"] is (abs(data["sync_error_symbols"]) <= 1)


def test_12db_layered_ber_fields_are_zero_on_recovery(tmp_path):
    input_path = _write_input(tmp_path, "layered ber")
    output_path = tmp_path / "received.txt"
    metrics = run_pipeline(
        str(input_path), str(output_path), 12.0, 2026, "qpsk", "awgn"
    )

    assert metrics["predecode_ber"] == 0.0
    assert metrics["payload_ber"] == 0.0
    assert metrics["ber"] == metrics["payload_ber"]
    assert metrics["frame_error_indicator"] == 0


def test_low_snr_predecode_and_payload_ber_can_differ(tmp_path):
    input_path = _write_input(tmp_path, "low snr check")
    output_path = tmp_path / "received.txt"
    metrics = run_pipeline(
        str(input_path), str(output_path), 0.0, 2026, "qpsk", "awgn"
    )

    assert 0.0 <= metrics["predecode_ber"] <= 1.0
    assert 0.0 <= metrics["payload_ber"] <= 1.0
    assert metrics["predecode_ber"] != metrics["payload_ber"]
    assert metrics["ber"] == metrics["payload_ber"]


def test_frame_parse_failure_keeps_predecode_ber(monkeypatch, tmp_path):
    input_path = _write_input(tmp_path, "parse failure")
    output_path = tmp_path / "received.txt"

    def fail_parse(*_args, **_kwargs):
        raise ValueError("forced parse failure")

    monkeypatch.setattr("src.pipeline.parse_frame", fail_parse)
    metrics = run_pipeline(
        str(input_path), str(output_path), 12.0, 2026, "qpsk", "awgn"
    )

    assert metrics["predecode_ber"] == 0.0
    assert metrics["payload_ber"] == 0.0
    assert metrics["frame_error_indicator"] == 0
    assert metrics["frame_parse_strategy"] == "length_crc_candidate"


def _set_cli_argv(monkeypatch, input_path: Path, output_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", [
        "main.py",
        "--input", str(input_path),
        "--output", str(output_path),
        "--snr", "12",
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])


def test_cli_returns_nonzero_when_plot_function_raises(monkeypatch, tmp_path):
    input_path = _write_input(tmp_path, "plot failure")
    output_path = tmp_path / "received.txt"
    _set_cli_argv(monkeypatch, input_path, output_path)

    def raise_plot(*_args, **_kwargs):
        raise RuntimeError("plot boom")

    monkeypatch.setattr(cli_main, "generate_all_plots", raise_plot)
    assert cli_main.main() == 1


def test_cli_rejects_empty_png_as_invalid(monkeypatch, tmp_path):
    input_path = _write_input(tmp_path, "empty png")
    output_path = tmp_path / "received.txt"
    _set_cli_argv(monkeypatch, input_path, output_path)

    def write_empty_plot(*_args, **kwargs):
        directory = Path(kwargs["output_dir"])
        (directory / "constellation.png").write_bytes(b"")
        (directory / "ber_curve.png").write_bytes(b"valid")

    monkeypatch.setattr(cli_main, "generate_all_plots", write_empty_plot)
    assert cli_main.main() == 1


def test_cli_accepts_all_expected_awgn_plots(monkeypatch, tmp_path):
    input_path = _write_input(tmp_path, "three plots")
    output_path = tmp_path / "received.txt"
    _set_cli_argv(monkeypatch, input_path, output_path)

    def write_three_plots(*_args, **kwargs):
        directory = Path(kwargs["output_dir"])
        (directory / "constellation.png").write_bytes(b"valid")
        (directory / "ber_curve.png").write_bytes(b"valid")
        (directory / "sync_peak.png").write_bytes(b"valid")

    monkeypatch.setattr(cli_main, "generate_all_plots", write_three_plots)
    assert cli_main.main() == 0
    assert (tmp_path / "run_manifest.json").exists()
