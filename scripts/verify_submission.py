"""无线通信期末项目一键验收脚本。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = PROJECT_ROOT / "results" / "verification"
REPORT_PATH = PROJECT_ROOT / "verification_report.json"


def sha256_file(path: Path) -> str | None:
    """返回文件 SHA-256；文件缺失时返回 ``None``。"""
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(args: list[str], timeout: int) -> dict[str, Any]:
    """在项目根目录运行子进程并保留诊断输出。"""
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    try:
        completed = subprocess.run(
            args,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "args": args,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "returncode": None,
            "stdout": (exc.stdout or "")[-8000:],
            "stderr": (exc.stderr or "")[-8000:],
            "timed_out": True,
        }


def load_json(path: Path) -> dict[str, Any]:
    """读取 JSON 对象；失败时返回空字典。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def check_required_files() -> bool:
    """检查源码、文档、测试和追溯矩阵是否存在。"""
    required = [
        "PRD.md",
        "README.md",
        "DESIGN.md",
        "TEST_PLAN.md",
        "MOCK_TEST_REPORT.md",
        "AI_LOG.md",
        "TRACEABILITY.md",
        "main.py",
        "requirements.txt",
        "requirements-lock.txt",
        "src",
        "tests",
        "public_tests",
    ]
    return all((PROJECT_ROOT / item).exists() for item in required)


def run_cli(output_dir: Path) -> dict[str, Any]:
    """执行统一 AWGN CLI，并把结果写入指定目录。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    return run_command(
        [
            sys.executable,
            "main.py",
            "--input", "Test.txt",
            "--output", str(output_dir / "received.txt"),
            "--snr", "12",
            "--seed", "2026",
            "--mod", "qpsk",
            "--channel", "awgn",
        ],
        timeout=120,
    )


def metrics_schema_ok(metrics: dict[str, Any]) -> bool:
    """校验当前 metrics.json 必需字段。"""
    required = {
        "snr_db", "seed", "modulation", "channel", "payload_bits",
        "ber", "payload_ber", "predecode_ber", "fer",
        "frame_error_indicator", "text_match_rate", "checksum_pass",
        "true_prefix_symbols", "sync_start_index", "sync_error_symbols",
        "sync_success", "frame_parse_strategy", "preamble_bit_errors",
        "header_bit_errors", "crc_bit_errors", "qpsk_padding_bits",
    }
    return required.issubset(metrics)


def manifest_schema_ok(manifest: dict[str, Any]) -> bool:
    """校验 run_manifest.json 必需字段。"""
    required = {
        "schema_version", "timestamp_utc", "git_commit", "git_dirty",
        "command", "python_version", "platform", "package_versions",
        "input_path", "input_sha256", "output_path", "output_sha256",
        "runtime_seconds", "seed", "snr_db", "modulation", "channel",
        "generated_files",
    }
    return required.issubset(manifest)


def valid_plot_count(output_dir: Path) -> int:
    """统计 AWGN CLI 承诺的非空 PNG 图像数量。"""
    names = ["constellation.png", "ber_curve.png", "sync_peak.png"]
    return sum(
        1 for name in names
        if (output_dir / name).exists() and (output_dir / name).stat().st_size > 0
    )


def reproducible(first_dir: Path, second_dir: Path) -> bool:
    """检查相同 seed 下文本和关键指标是否可复现。"""
    first_text = sha256_file(first_dir / "received.txt")
    second_text = sha256_file(second_dir / "received.txt")
    if first_text is None or first_text != second_text:
        return False

    first = load_json(first_dir / "metrics.json")
    second = load_json(second_dir / "metrics.json")
    keys = [
        "snr_db", "seed", "modulation", "channel", "payload_bits",
        "ber", "payload_ber", "predecode_ber", "fer",
        "frame_error_indicator", "text_match_rate", "checksum_pass",
        "true_prefix_symbols", "sync_start_index", "sync_error_symbols",
        "sync_success", "frame_parse_strategy", "preamble_bit_errors",
        "header_bit_errors", "crc_bit_errors", "qpsk_padding_bits",
    ]
    return {key: first.get(key) for key in keys} == {
        key: second.get(key) for key in keys
    }


def main() -> int:
    """运行验收检查并写出 ``verification_report.json``。"""
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    first_dir = RESULT_DIR / "run1"
    second_dir = RESULT_DIR / "run2"

    commands: dict[str, Any] = {}
    checks: dict[str, bool] = {}

    checks["required_files"] = check_required_files()

    commands["public_tests"] = run_command(
        [sys.executable, "-m", "pytest", "public_tests", "-q"],
        timeout=120,
    )
    checks["public_tests"] = commands["public_tests"]["returncode"] == 0

    commands["internal_tests"] = run_command(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        timeout=300,
    )
    checks["internal_tests"] = commands["internal_tests"]["returncode"] == 0

    commands["cli"] = run_cli(first_dir)
    checks["cli"] = commands["cli"]["returncode"] == 0

    input_hash = sha256_file(PROJECT_ROOT / "Test.txt")
    output_hash = sha256_file(first_dir / "received.txt")
    checks["text_hash_match"] = (
        input_hash is not None and input_hash == output_hash
    )

    metrics = load_json(first_dir / "metrics.json")
    checks["metrics_schema"] = metrics_schema_ok(metrics)

    manifest = load_json(first_dir / "run_manifest.json")
    checks["manifest_schema"] = manifest_schema_ok(manifest)

    checks["plots"] = valid_plot_count(first_dir) >= 3

    commands["cli_reproducibility"] = run_cli(second_dir)
    checks["reproducibility"] = (
        commands["cli_reproducibility"]["returncode"] == 0
        and reproducible(first_dir, second_dir)
    )

    overall_pass = all(checks.values())
    report = {
        "overall_pass": overall_pass,
        "summary_zh": "通过" if overall_pass else "失败",
        "checks": checks,
        "input_sha256": input_hash,
        "output_sha256": output_hash,
        "commands": commands,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print("提交验收:", "通过" if overall_pass else "失败")
    for name, passed in checks.items():
        print(f"  {name}: {'通过' if passed else '失败'}")
    print(f"报告路径: {REPORT_PATH}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
