"""CLI 参数和路径错误处理回归测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import main as cli_main


def _write_input(tmp_path: Path, text: str = "cli validation") -> Path:
    path = tmp_path / "input.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _patch_valid_plots(monkeypatch: pytest.MonkeyPatch) -> None:
    def write_plots(*_args, **kwargs):
        directory = Path(kwargs["output_dir"])
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "constellation.png").write_bytes(b"plot")
        (directory / "ber_curve.png").write_bytes(b"plot")
        (directory / "sync_peak.png").write_bytes(b"plot")

    monkeypatch.setattr(cli_main, "generate_all_plots", write_plots)


def _run_cli(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    monkeypatch.setattr(sys, "argv", ["main.py", *args])
    return cli_main.main()


@pytest.mark.parametrize("snr", ["nan", "inf", "-inf", "-9999", "9999"])
def test_cli_rejects_invalid_snr_without_traceback(
        monkeypatch, capsys, tmp_path, snr):
    input_path = _write_input(tmp_path)
    output_path = tmp_path / "out" / "received.txt"

    code = _run_cli(monkeypatch, [
        "--input", str(input_path),
        "--output", str(output_path),
        "--snr", snr,
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])

    captured = capsys.readouterr()
    assert code != 0
    assert "--snr" in captured.err
    assert "Traceback" not in captured.err
    assert not output_path.exists()
    assert not (output_path.parent / "metrics.json").exists()


@pytest.mark.parametrize("snr", ["-10", "12"])
def test_cli_accepts_normal_snr_values(monkeypatch, tmp_path, snr):
    _patch_valid_plots(monkeypatch)
    input_path = _write_input(tmp_path, f"valid snr {snr}")
    output_path = tmp_path / "valid" / "received.txt"

    code = _run_cli(monkeypatch, [
        "--input", str(input_path),
        "--output", str(output_path),
        "--snr", snr,
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])

    assert code == 0
    assert output_path.exists()
    assert (output_path.parent / "metrics.json").exists()


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--mod", "bpsk"),
        ("--channel", "rician"),
        ("--equalizer", "ml"),
    ],
)
def test_cli_rejects_invalid_mode_arguments(
        monkeypatch, capsys, tmp_path, option, value):
    input_path = _write_input(tmp_path)
    output_path = tmp_path / "out" / "received.txt"
    args = [
        "--input", str(input_path),
        "--output", str(output_path),
        "--snr", "12",
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ]
    index = args.index(option) if option in args else len(args)
    if option in args:
        args[index + 1] = value
    else:
        args.extend([option, value])

    code = _run_cli(monkeypatch, args)

    captured = capsys.readouterr()
    assert code != 0
    assert option in captured.err
    assert "Traceback" not in captured.err


def test_cli_rejects_missing_input_path_without_traceback(
        monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "out" / "received.txt"

    code = _run_cli(monkeypatch, [
        "--input", str(tmp_path / "missing.txt"),
        "--output", str(output_path),
        "--snr", "12",
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])

    captured = capsys.readouterr()
    assert code != 0
    assert "输入文件不存在" in captured.err
    assert "Traceback" not in captured.err
    assert not output_path.exists()


def test_cli_rejects_input_directory_without_traceback(
        monkeypatch, capsys, tmp_path):
    output_path = tmp_path / "out" / "received.txt"

    code = _run_cli(monkeypatch, [
        "--input", str(tmp_path),
        "--output", str(output_path),
        "--snr", "12",
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])

    captured = capsys.readouterr()
    assert code != 0
    assert "不是普通文件" in captured.err
    assert "Traceback" not in captured.err
    assert not output_path.exists()


def test_cli_rejects_output_parent_that_is_file(
        monkeypatch, capsys, tmp_path):
    input_path = _write_input(tmp_path)
    parent_file = tmp_path / "notdir"
    parent_file.write_text("I am a file", encoding="utf-8")
    output_path = parent_file / "received.txt"

    code = _run_cli(monkeypatch, [
        "--input", str(input_path),
        "--output", str(output_path),
        "--snr", "12",
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])

    captured = capsys.readouterr()
    assert code != 0
    assert "无法创建输出目录" in captured.err
    assert "Traceback" not in captured.err
    assert parent_file.is_file()
    assert not (tmp_path / "metrics.json").exists()
    assert not (tmp_path / "run_manifest.json").exists()


def test_cli_rejects_output_path_that_is_directory(
        monkeypatch, capsys, tmp_path):
    input_path = _write_input(tmp_path)
    output_dir = tmp_path / "received.txt"
    output_dir.mkdir()

    code = _run_cli(monkeypatch, [
        "--input", str(input_path),
        "--output", str(output_dir),
        "--snr", "12",
        "--seed", "2026",
        "--mod", "qpsk",
        "--channel", "awgn",
    ])

    captured = capsys.readouterr()
    assert code != 0
    assert "输出路径不能是目录" in captured.err
    assert "Traceback" not in captured.err
