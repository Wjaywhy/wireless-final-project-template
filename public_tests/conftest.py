import importlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TEXT = (
    "无线通信技术课程要求学生理解调制、编码、信道和接收机处理。"
    "本测试文本用于验证源编码、帧结构、QPSK 调制、AWGN 信道、同步和端到端恢复。"
    "通信系统设计涉及多个关键模块：信源编码将文字转为比特流，信道编码增加冗余以对抗噪声，"
    "QPSK 调制将比特映射为复数符号，AWGN 信道叠加高斯白噪声，接收端通过同步定位帧起点、"
    "解调恢复比特、信道译码纠正错误，最终还原原始文本。系统需支持不同 SNR、不同 seed、"
    "不同文本长度以及随机同步偏移，并在低 SNR 下安全降级而非崩溃。Emoji 测试：🎓📡✨。"
)


def pytest_configure(config):
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def run_from_project_root(monkeypatch):
    monkeypatch.chdir(PROJECT_ROOT)


@pytest.fixture()
def sample_text():
    return SAMPLE_TEXT


@pytest.fixture()
def ensure_test_file(sample_text):
    path = PROJECT_ROOT / "Test.txt"
    path.write_text(sample_text, encoding="utf-8")
    return path


@pytest.fixture()
def clean_results():
    results = PROJECT_ROOT / "results"
    if results.exists():
        shutil.rmtree(results)
    results.mkdir(parents=True, exist_ok=True)
    return results


def read_text(path):
    return Path(path).read_text(encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def normalize_text(text):
    return re.sub(r"\s+", " ", text.lower())


def require_path(path):
    p = PROJECT_ROOT / path
    assert p.exists(), f"Required path does not exist: {path}"
    return p


def import_first_module(module_names):
    errors = []
    for name in module_names:
        try:
            return importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors.append(f"{name}: {exc}")
    raise AssertionError(
        "Cannot import any expected module. Tried:\n" + "\n".join(errors)
    )


def find_function(module_names, function_names):
    modules = []
    errors = []
    for module_name in module_names:
        try:
            modules.append(importlib.import_module(module_name))
        except Exception as exc:
            errors.append(f"{module_name}: {exc}")
    for module in modules:
        for function_name in function_names:
            func = getattr(module, function_name, None)
            if callable(func):
                return func
    raise AssertionError(
        "Cannot find required function.\n"
        f"Modules tried: {module_names}\n"
        f"Function names tried: {function_names}\n"
        "Import errors:\n" + "\n".join(errors)
    )


def call_with_fallback(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except TypeError:
        return func(*args)


def to_bit_list(value):
    if isinstance(value, str):
        assert set(value) <= {"0", "1"}, "Bit string must contain only 0 and 1"
        return [int(ch) for ch in value]
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [int(x) for x in list(value)]


def to_complex_list(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [complex(x) for x in list(value)]


def run_cli(snr=12, seed=2026, timeout=20):
    cmd = [
        sys.executable,
        "main.py",
        "--input",
        "Test.txt",
        "--output",
        "results/received.txt",
        "--snr",
        str(snr),
        "--seed",
        str(seed),
        "--mod",
        "qpsk",
        "--channel",
        "awgn",
    ]
    env = os.environ.copy()
    env.setdefault("MPLBACKEND", "Agg")
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def assert_cli_success(result):
    assert result.returncode == 0, (
        "CLI command failed.\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def text_file_mentions(path, keywords, min_count=None):
    text = normalize_text(read_text(PROJECT_ROOT / path))
    hits = [kw for kw in keywords if normalize_text(kw) in text]
    required = len(keywords) if min_count is None else min_count
    assert len(hits) >= required, (
        f"{path} should mention at least {required} of {keywords}, got {hits}"
    )
    return hits
