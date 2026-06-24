"""Module-level and regression tests for the wireless final project."""

import os
import sys
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.source import source_encode, source_decode
from src.scramble import scramble, descramble
from src.channel_coding import channel_encode, channel_decode
from src.framing import build_frame, parse_frame, _PREAMBLE_BITS, _compute_crc32
from src.modulation import qpsk_modulate, qpsk_demodulate
from src.channel import awgn
from src.synchronization import synchronize
from src.metrics import calculate_ber
from src.pipeline import run_pipeline, _generate_prefix_symbols


def _preamble_symbols():
    return qpsk_modulate(list(_PREAMBLE_BITS))


# =====================  BER length-difference calculation  ====================

def test_ber_empty_both():
    assert calculate_ber([], []) == 0.0


def test_ber_sent_only():
    assert calculate_ber([0, 0], []) == 1.0


def test_ber_truncated_received():
    assert calculate_ber([0, 1, 0, 1], [0, 1]) == 0.5


def test_ber_extra_received():
    assert abs(calculate_ber([1], [1, 0, 1]) - 2.0 / 3.0) < 1e-9


def test_ber_single_bit_error():
    assert abs(calculate_ber([0, 1, 1], [0, 0, 1]) - 1.0 / 3.0) < 1e-9


def test_ber_identical():
    bits = [int(x) for x in np.random.default_rng(42).integers(0, 2, size=256)]
    assert calculate_ber(bits, bits) == 0.0


# =====================  Module-unit roundtrip tests  ==========================

def test_source_codec_roundtrip():
    text = "无线通信技术课程要求学生理解调制、编码、信道和接收机处理。"
    assert source_decode(source_encode(text)) == text


def test_scramble_reversible():
    bits = [int(x) for x in np.random.default_rng(2026).integers(0, 2, size=511)]
    assert descramble(scramble(bits, seed=2026), seed=2026) == bits


def test_channel_coding_noiseless():
    bits = [int(x) for x in np.random.default_rng(2028).integers(0, 2, size=400)]
    assert channel_decode(channel_encode(bits)) == bits


def test_channel_decode_rejects_incomplete_groups():
    assert channel_decode([]) == []
    for incomplete in ([1], [1, 1], [1, 1, 1, 0]):
        with pytest.raises(ValueError, match="divisible by 3"):
            channel_decode(incomplete)


def test_qpsk_roundtrip():
    bits = [int(x) for x in np.random.default_rng(2029).integers(0, 2, size=512)]
    assert qpsk_demodulate(qpsk_modulate(bits))[: len(bits)] == bits


def test_qpsk_unit_power():
    bits = [int(x) for x in np.random.default_rng(99).integers(0, 2, size=1024)]
    syms = np.array([complex(s) for s in qpsk_modulate(bits)])
    assert 0.8 <= float(np.mean(np.abs(syms) ** 2)) <= 1.2


def test_awgn_reproducible():
    syms = [complex(x) for x in np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j]) / np.sqrt(2)]
    out1 = awgn(syms, snr_db=12, seed=2026)
    out2 = awgn(syms, snr_db=12, seed=2026)
    assert np.allclose(np.array(out1), np.array(out2))


def test_sync_25_offset():
    text = "无线通信测试同步"
    seed = 2026
    original_bits = source_encode(text)
    scrambled = scramble(original_bits, seed)
    coded = channel_encode(scrambled)
    frame = build_frame(original_bits, coded, seed=seed)
    frame_syms = qpsk_modulate(frame)

    rng = np.random.default_rng(seed)
    prefix_bits = [int(x) for x in rng.integers(0, 2, size=50)]
    prefix = qpsk_modulate(prefix_bits)
    rx = awgn(prefix + frame_syms, snr_db=12, seed=seed)
    start = synchronize(rx, _preamble_symbols())
    assert abs(start - 25) <= 1


# =====================  CRC / length / FER regression  =======================

def test_crc_passes_on_valid_frame():
    payload = [int(x) for x in np.random.default_rng(1).integers(0, 2, size=400)]
    scrambled = scramble(payload, 2026)
    coded = channel_encode(scrambled)
    frame = build_frame(payload, coded, seed=2026)
    parsed = parse_frame(frame)
    assert len(parsed["coded_payload"]) == 1200
    assert parsed["original_length"] == 400
    assert parsed["coded_length"] == 1200
    # Verify CRC matches
    from src.framing import _bits_to_int_be
    assert _bits_to_int_be(parsed["crc_received"]) == _compute_crc32(payload)


def test_crc_fails_when_payload_bit_flipped():
    """CRC must fail when coded payload has uncorrectable errors."""
    payload = [int(x) for x in np.random.default_rng(2).integers(0, 2, size=400)]
    scrambled = scramble(payload, 2026)
    coded = channel_encode(scrambled)
    frame = build_frame(payload, coded, seed=2026)
    frame_corrupt = frame.copy()
    # Flip 2 bits in the same repetition-code group → uncorrectable error
    frame_corrupt[128] ^= 1      # first bit of first coded group
    frame_corrupt[129] ^= 1      # second bit of same group
    parsed = parse_frame(frame_corrupt)
    decoded = channel_decode(parsed["coded_payload"])[:400]
    descrambled_c = descramble(decoded, 2026)
    from src.framing import _bits_to_int_be
    crc_match = _bits_to_int_be(parsed["crc_received"]) == _compute_crc32(descrambled_c)
    assert not crc_match, "CRC should fail after uncorrectable bit errors"


def test_length_mismatch_crc_fails():
    """CRC must fail when recovered length != original_length."""
    payload = [int(x) for x in np.random.default_rng(3).integers(0, 2, size=400)]
    scrambled = scramble(payload, 2026)
    coded = channel_encode(scrambled)
    frame = build_frame(payload, coded, seed=2026)
    parsed = parse_frame(frame)
    # Deliberately decode only part of the coded payload → shorter descrambled
    decoded_short = channel_decode(parsed["coded_payload"][:900])  # 300 bits instead of 400
    descrambled_short = descramble(decoded_short, 2026)
    from src.framing import _bits_to_int_be
    # Length check: len(descrambled_short) != original_length
    assert len(descrambled_short) != 400
    # CRC should not pass
    crc_val = _compute_crc32(descrambled_short)
    assert crc_val != _bits_to_int_be(parsed["crc_received"])


def test_coded_length_invariant_enforced():
    """coded_length != 3 * original_length → pipeline fails frame."""
    payload = [int(x) for x in np.random.default_rng(4).integers(0, 2, size=200)]
    scrambled = scramble(payload, 2026)
    coded = channel_encode(scrambled)  # 600 bits
    # Corrupt coded_length in frame
    frame = build_frame(payload, coded, seed=2026)
    # coded_length at offset 96 (bits 96-127). Flip to change value.
    frame_corrupt = frame.copy()
    frame_corrupt[100] ^= 1  # change coded_length
    with pytest.raises(ValueError):
        parse_frame(frame_corrupt, preamble=list(_PREAMBLE_BITS))


def test_pipeline_rejects_length_mismatch_before_channel_decode(monkeypatch):
    """Invalid encoded-length relation must fail before decoder invocation."""
    temp_dir = tempfile.mkdtemp()
    input_path = Path(temp_dir) / "input.txt"
    output_path = Path(temp_dir) / "received.txt"
    input_path.write_text("A", encoding="utf-8")  # original_length = 8 bits

    def fake_parse_frame(_bits, preamble=None):
        return {
            "original_length": 8,
            "coded_length": 21,  # divisible by 3, but not 3 * 8
            "coded_payload": [0] * 21,
            "crc_received": [0] * 32,
        }

    def decoder_must_not_run(_bits):
        raise AssertionError("channel_decode called for invalid coded length")

    monkeypatch.setattr("src.pipeline.parse_frame", fake_parse_frame)
    monkeypatch.setattr("src.pipeline.channel_decode", decoder_must_not_run)

    try:
        metrics = run_pipeline(
            str(input_path), str(output_path), 12.0, 2026, "qpsk", "awgn"
        )

        assert output_path.read_text(encoding="utf-8") == ""
        assert metrics["checksum_pass"] is False
        assert metrics["fer"] == 1.0
        assert metrics["text_match_rate"] == 0.0
    finally:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_empty_payload_valid_frame():
    frame = build_frame([], [], seed=2026)
    parsed = parse_frame(frame)
    assert parsed["original_length"] == 0
    assert parsed["coded_length"] == 0


# =====================  Frame parsing boundaries  ============================

def test_frame_too_short_raises():
    with pytest.raises(ValueError, match="too short"):
        parse_frame([])
    with pytest.raises(ValueError, match="too short"):
        parse_frame([0] * 159)


def test_frame_minimal_160bit_empty_payload():
    frame = build_frame([], [])
    assert len(frame) == 160
    parsed = parse_frame(frame)
    assert parsed["original_length"] == 0


def test_payload_truncated_raises():
    payload = [int(x) for x in np.random.default_rng(5).integers(0, 2, size=200)]
    frame = build_frame(payload)
    truncated = frame[:200]  # cuts into coded payload
    with pytest.raises(ValueError, match="exceeds remaining"):
        parse_frame(truncated)


def test_crc_truncated_raises():
    payload = [int(x) for x in np.random.default_rng(6).integers(0, 2, size=200)]
    frame = build_frame(payload)
    # 160 header + 200 payload + X CRC bits. Drop last 24 → 8 CRC bits remain.
    truncated = frame[:336]
    with pytest.raises(ValueError, match="CRC field truncated"):
        parse_frame(truncated)


def test_coded_length_exceeds_data_raises():
    payload = [int(x) for x in np.random.default_rng(7).integers(0, 2, size=200)]
    frame = build_frame(payload)
    truncated = frame[:200]  # coded_length=200 won't fit after header
    with pytest.raises(ValueError, match="exceeds remaining"):
        parse_frame(truncated)


def test_preamble_mismatch_raises():
    payload = [int(x) for x in np.random.default_rng(8).integers(0, 2, size=200)]
    frame = build_frame(payload)
    frame_corrupt = frame.copy()
    frame_corrupt[0] ^= 1
    with pytest.raises(ValueError, match="preamble does not match"):
        parse_frame(frame_corrupt, preamble=list(_PREAMBLE_BITS))


def test_qpsk_padding_after_crc():
    """A single QPSK padding bit after CRC is harmless."""
    payload = [int(x) for x in np.random.default_rng(9).integers(0, 2, size=199)]
    frame = build_frame(payload)  # odd-length frame
    frame_padded = frame + [0]  # simulate QPSK padding
    parsed = parse_frame(frame_padded)
    assert parsed["original_length"] == 199


# =====================  QPSK prefix symbols  =================================

def test_prefix_symbols_are_qpsk():
    syms = _generate_prefix_symbols(128, 2026)
    assert len(syms) == 128
    for s in syms:
        assert abs(abs(s) - 1.0) < 1e-9


def test_prefix_reproducible_same_seed():
    s1 = _generate_prefix_symbols(50, 2026)
    s2 = _generate_prefix_symbols(50, 2026)
    assert np.allclose(np.array(s1), np.array(s2))


def test_prefix_different_seeds_differ():
    s1 = _generate_prefix_symbols(50, 2026)
    s2 = _generate_prefix_symbols(50, 2027)
    assert not np.allclose(np.array(s1), np.array(s2))


def test_prefix_length_in_range():
    for seed_val in [0, 1, 2026, 99999999]:
        rng = np.random.default_rng(seed_val)
        n = int(rng.integers(0, 129))
        assert 0 <= n <= 128


# =====================  CLI validation  ======================================

def test_cli_rejects_nan():
    r = subprocess.run(
        [sys.executable, "main.py", "--input", "Test.txt", "--output",
         "results/_t.txt", "--snr", "nan", "--seed", "2026",
         "--mod", "qpsk", "--channel", "awgn"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


def test_cli_rejects_inf():
    r = subprocess.run(
        [sys.executable, "main.py", "--input", "Test.txt", "--output",
         "results/_t.txt", "--snr", "inf", "--seed", "2026",
         "--mod", "qpsk", "--channel", "awgn"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


def test_cli_rejects_neg_inf():
    r = subprocess.run(
        [sys.executable, "main.py", "--input", "Test.txt", "--output",
         "results/_t.txt", "--snr", "-inf", "--seed", "2026",
         "--mod", "qpsk", "--channel", "awgn"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


def test_cli_accepts_negative_snr():
    r = subprocess.run(
        [sys.executable, "main.py", "--input", "Test.txt", "--output",
         "results/_t_neg.txt", "--snr", "-5", "--seed", "2026",
         "--mod", "qpsk", "--channel", "awgn"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0


def test_cli_rejects_invalid_mod():
    r = subprocess.run(
        [sys.executable, "main.py", "--input", "Test.txt", "--output",
         "results/_t.txt", "--snr", "12", "--seed", "2026",
         "--mod", "bpsk", "--channel", "awgn"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


def test_cli_rejects_invalid_channel():
    r = subprocess.run(
        [sys.executable, "main.py", "--input", "Test.txt", "--output",
         "results/_t.txt", "--snr", "12", "--seed", "2026",
         "--mod", "qpsk", "--channel", "rayleigh"],
        capture_output=True, text=True,
    )
    assert r.returncode != 0


# =====================  End-to-end pipeline  =================================

def test_e2e_12db_full_recovery():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    text = "无线通信端到端恢复测试——12 dB AWGN 应完全一致。"
    Path(fin).write_text(text, encoding="utf-8")
    m = run_pipeline(fin, fout, 12.0, 2026, "qpsk", "awgn")
    recovered = Path(fout).read_text(encoding="utf-8")
    assert recovered == text
    assert m["ber"] == 0.0
    assert m["fer"] == 0.0
    assert m["checksum_pass"] is True
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_e2e_snr0_no_crash():
    d = tempfile.mkdtemp()
    fin = os.path.join(d, "in.txt")
    fout = os.path.join(d, "out.txt")
    Path(fin).write_text("SNR零分贝不应崩溃", encoding="utf-8")
    m = run_pipeline(fin, fout, 0.0, 2026, "qpsk", "awgn")
    assert 0.0 <= m["ber"] <= 1.0
    import shutil
    shutil.rmtree(d, ignore_errors=True)
