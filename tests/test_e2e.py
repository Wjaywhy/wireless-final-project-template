"""End-to-end / CLI boundary tests for the wireless final project."""

import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import run_pipeline
from src.metrics import save_metrics, calculate_ber
from src.plotting import generate_all_plots


# =====================  End-to-end recovery  =================================

def test_e2e_12db_full_recovery():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    text = (
        "无线通信技术课程要求学生理解调制、编码、信道和接收机处理。"
        "本测试文本用于验证源编码、帧结构、QPSK调制、AWGN信道、同步和端到端恢复。"
    )
    Path(fin).write_text(text, encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == text
    assert m["text_match_rate"] == 1.0
    assert m["checksum_pass"] is True
    assert m["fer"] == 0.0
    assert m["ber"] == 0.0
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_empty_text():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("", encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == ""
    assert m["payload_bits"] == 0
    assert m["text_match_rate"] == 1.0
    assert m["fer"] == 0.0
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_single_chinese_char():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("中", encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == "中"
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_mixed_emoji():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    text = "QPSK调制 \U0001f600 AWGN信道 \U0001f393 12dB"
    Path(fin).write_text(text, encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == text
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_long_text():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    text = "无线通信期末项目测试文本" * 40
    Path(fin).write_text(text, encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == text
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_seed_zero():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("seed=0测试", encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 0, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == "seed=0测试"
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_large_seed():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("大seed 99999999", encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 99999999, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == "大seed 99999999"
    import shutil; shutil.rmtree(d, ignore_errors=True)


# =====================  SNR boundaries  ======================================

def test_e2e_snr_neg5_no_crash():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("SNR=-5 不得崩溃", encoding="utf-8")
    m = run_pipeline(fin, fout, -5.0, 2026, "qpsk", "awgn")
    assert m["ber"] >= 0.0
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_snr_30_full_recovery():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("30dB高信噪比", encoding="utf-8")
    m = run_pipeline(fin, fout, 30.0, 2026, "qpsk", "awgn")
    assert Path(fout).read_text(encoding="utf-8") == "30dB高信噪比"
    assert m["ber"] == 0.0
    assert m["fer"] == 0.0
    import shutil; shutil.rmtree(d, ignore_errors=True)


# =====================  Output directory auto-creation  ======================

def test_e2e_nested_output_dir():
    d = tempfile.mkdtemp()
    deep = os.path.join(d, "a", "b", "c")
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(deep, "out.txt")
    Path(fin).write_text("多级目录", encoding="utf-8")
    assert not os.path.exists(deep)
    run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    assert os.path.exists(fout)
    import shutil; shutil.rmtree(d, ignore_errors=True)


# =====================  Metrics JSON and plots  ==============================

def test_e2e_metrics_json_fields():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("指标字段完整性", encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    save_metrics(m, d)
    data = json.loads(Path(os.path.join(d, "metrics.json")).read_text(encoding="utf-8"))
    for field in ["snr_db", "seed", "modulation", "channel", "payload_bits",
                  "ber", "fer", "text_match_rate", "checksum_pass", "sync_start_index"]:
        assert field in data
    assert data["modulation"] == "qpsk"
    assert data["channel"] == "awgn"
    assert isinstance(data["checksum_pass"], bool)
    import shutil; shutil.rmtree(d, ignore_errors=True)


def test_e2e_plots_generated():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("图表生成", encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    generate_all_plots(m, d, fin, 2026, "qpsk", "awgn")
    for name in ["constellation.png", "ber_curve.png", "sync_peak.png"]:
        p = os.path.join(d, name)
        assert os.path.exists(p)
        assert os.path.getsize(p) > 0
    import shutil; shutil.rmtree(d, ignore_errors=True)


# =====================  CRC / FER at low SNR  ================================

def test_e2e_fer_is_1_when_crc_fails():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("验证FER在低SNR时为1——CRC必须基于接收端数据", encoding="utf-8")
    m = run_pipeline(fin, fout, 0.0, 2026, "qpsk", "awgn")
    if m["ber"] > 0:
        assert m["checksum_pass"] is False
        assert m["fer"] == 1.0
    import shutil; shutil.rmtree(d, ignore_errors=True)


# =====================  BER length-diff regression  ==========================

def test_ber_length_diff_all_errors():
    assert calculate_ber([0, 0], []) == 1.0
    assert calculate_ber([], [0, 0]) == 1.0
    assert abs(calculate_ber([1], [1, 0, 1]) - 2.0 / 3.0) < 1e-9
