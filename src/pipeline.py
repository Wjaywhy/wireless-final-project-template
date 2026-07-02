"""Level 2 AWGN and optional Level 3 flat-Rayleigh pipelines.

Fixed pipeline chain (PRD §3)::

    Source Encode → Scramble → Channel Encode → Frame Build
    → QPSK Modulate → Prefix → Channel → Synchronisation
    → QPSK Demodulate → Frame Parse → Channel Decode
    → Descramble → Source Decode → Metrics / Plots
"""

# Standard library
import os

# Third-party
import numpy as np

# Local modules — ordered by pipeline stage
from src.source import source_encode, source_decode
from src.scramble import scramble, descramble
from src.channel_coding import channel_encode, channel_decode
from src.framing import build_frame, parse_frame, _PREAMBLE_BITS, _compute_crc32
from src.modulation import qpsk_modulate, qpsk_demodulate
from src.channel import awgn, rayleigh_flat_fading
from src.config import validate_snr_db
from src.synchronization import (
    synchronize_with_correlation,
    synchronize_branches,
)
from src.equalization import (
    estimate_flat_channel,
    zf_equalize,
    mmse_equalize,
)
from src.diversity import mrc_combine
from src.metrics import calculate_ber


#: Pre-computed preamble complex symbols (32 QPSK symbols from 64 preamble bits).
PREAMBLE_SYMBOLS = qpsk_modulate(list(_PREAMBLE_BITS))

MAX_PREAMBLE_BIT_ERRORS = 2
MAX_HEADER_FIELD_BIT_ERRORS = 4
MAX_CRC_FIELD_BIT_ERRORS = 1


def _bits_to_int_be(bits: list[int]) -> int:
    """Decode a big-endian bit list to an unsigned integer.

    Used to reconstruct the Original Length and Coded Length fields from
    their 32-bit frame representations.
    """
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def _int_to_bits_be(value: int, width: int) -> list[int]:
    """把非负整数编码成指定宽度的大端比特。"""
    return [(value >> bit) & 1 for bit in range(width - 1, -1, -1)]


def _hamming_distance(left: list[int], right: list[int]) -> int:
    """计算等长比特序列的汉明距离。"""
    return sum(int(a) != int(b) for a, b in zip(left, right))


def _candidate_original_lengths(bit_count: int) -> list[int]:
    """从接收帧总长度推断有限个合法原始长度候选。

    当前 CLI 输入来自 UTF-8 文本，因此原始 payload bit 数应为 8 的倍数；
    QPSK 调制最多只会在帧尾补 1 个 bit。该函数只使用接收端可见的
    解调比特长度和固定帧结构，不读取原始文本。
    """
    candidates = set()
    for qpsk_padding_bits in (0, 1):
        coded_length = bit_count - 64 - 32 - 32 - 32 - qpsk_padding_bits
        if coded_length < 0 or coded_length % 3 != 0:
            continue
        original_length = coded_length // 3
        if original_length >= 0 and original_length % 8 == 0:
            candidates.add(int(original_length))
    return sorted(candidates)


def _parsed_from_candidate(bits: list[int],
                           original_length: int,
                           strategy: str) -> dict | None:
    """按候选原始长度构造帧字段，并记录控制字段误差。"""
    coded_length = 3 * int(original_length)
    crc_start = 64 + 32 + 32 + coded_length
    crc_end = crc_start + 32
    padding_bits = len(bits) - crc_end
    if original_length < 0 or padding_bits not in (0, 1):
        return None
    if len(bits) < crc_end:
        return None

    preamble = [int(bit) for bit in bits[:64]]
    original_header = [int(bit) for bit in bits[64:96]]
    coded_header = [int(bit) for bit in bits[96:128]]
    coded_payload = [int(bit) for bit in bits[128:crc_start]]
    crc_received = [int(bit) for bit in bits[crc_start:crc_end]]
    expected_original = _int_to_bits_be(original_length, 32)
    expected_coded = _int_to_bits_be(coded_length, 32)

    return {
        "preamble": preamble,
        "original_length": int(original_length),
        "coded_length": int(coded_length),
        "payload": coded_payload,
        "coded_payload": coded_payload,
        "crc_received": crc_received,
        "length": int(original_length),
        "frame_parse_strategy": strategy,
        "preamble_bit_errors": _hamming_distance(
            preamble, list(_PREAMBLE_BITS)
        ),
        "header_bit_errors": _hamming_distance(
            original_header, expected_original
        ) + _hamming_distance(coded_header, expected_coded),
        "qpsk_padding_bits": int(padding_bits),
    }


def _evaluate_parsed_frame(parsed: dict, seed: int) -> dict:
    """对一个候选帧执行译码、解扰和 CRC 评估。"""
    original_length = int(parsed["original_length"])
    coded_length = int(parsed["coded_length"])
    coded_payload = [int(bit) for bit in parsed["coded_payload"]]
    encoded_length_ok = (
        coded_length == 3 * original_length
        and coded_length % 3 == 0
        and len(coded_payload) == coded_length
    )
    decoded = []
    descrambled = []
    decode_error = ""
    if encoded_length_ok and coded_length > 0:
        try:
            decoded = channel_decode(coded_payload)
            descrambled = descramble(decoded, seed)
        except ValueError as error:
            decode_error = str(error)
    elif encoded_length_ok and coded_length == 0:
        descrambled = []

    length_ok = encoded_length_ok and len(descrambled) == original_length
    crc_expected = _int_to_bits_be(_compute_crc32(descrambled), 32) \
        if length_ok else [0] * 32
    crc_bit_errors = _hamming_distance(
        [int(bit) for bit in parsed["crc_received"]], crc_expected
    )
    checksum_pass = (
        length_ok
        and parsed.get("preamble_bit_errors", 0) <= MAX_PREAMBLE_BIT_ERRORS
        and parsed.get("header_bit_errors", 0) <= MAX_HEADER_FIELD_BIT_ERRORS
        and crc_bit_errors <= MAX_CRC_FIELD_BIT_ERRORS
    )
    return {
        "parsed": parsed,
        "encoded_length_ok": bool(encoded_length_ok),
        "decoded": decoded,
        "descrambled": descrambled,
        "length_ok": bool(length_ok),
        "crc_bit_errors": int(crc_bit_errors),
        "checksum_pass": bool(checksum_pass),
        "decode_error": decode_error,
    }


def _recover_frame_fields(demod_bits: list[int], seed: int) -> dict:
    """用直接解析和有限候选搜索恢复帧字段。

    候选搜索只在直接解析失败或 CRC 不通过时作为兼容后备，不依赖发送端
    原始文本。排序优先级为 CRC、控制字段误差和是否直接解析。
    """
    bits = [int(bit) for bit in demod_bits]
    evaluated = []

    try:
        parsed = parse_frame(bits, preamble=list(_PREAMBLE_BITS))
        parsed["frame_parse_strategy"] = "direct"
        parsed["preamble_bit_errors"] = 0
        parsed["header_bit_errors"] = 0
        parsed["qpsk_padding_bits"] = max(
            0,
            len(bits) - (64 + 32 + 32 + int(parsed["coded_length"]) + 32),
        )
        evaluated.append(_evaluate_parsed_frame(parsed, seed))
    except (ValueError, IndexError):
        pass

    for original_length in _candidate_original_lengths(len(bits)):
        parsed = _parsed_from_candidate(bits, original_length, "length_crc_candidate")
        if parsed is not None:
            evaluated.append(_evaluate_parsed_frame(parsed, seed))

    if not evaluated:
        fallback = {
            "preamble": [],
            "original_length": 0,
            "coded_length": 0,
            "payload": [],
            "coded_payload": [],
            "crc_received": [0] * 32,
            "length": 0,
            "frame_parse_strategy": "failed",
            "preamble_bit_errors": None,
            "header_bit_errors": None,
            "qpsk_padding_bits": None,
        }
        return {
            "parsed": fallback,
            "encoded_length_ok": False,
            "decoded": [],
            "descrambled": [],
            "length_ok": False,
            "crc_bit_errors": None,
            "checksum_pass": False,
            "decode_error": "no valid frame candidate",
        }

    def sort_key(entry: dict) -> tuple:
        parsed = entry["parsed"]
        header_errors = parsed.get("header_bit_errors")
        preamble_errors = parsed.get("preamble_bit_errors")
        return (
            0 if entry["checksum_pass"] else 1,
            entry["crc_bit_errors"] if entry["crc_bit_errors"] is not None else 99,
            header_errors if header_errors is not None else 99,
            preamble_errors if preamble_errors is not None else 99,
            0 if parsed.get("frame_parse_strategy") == "direct" else 1,
        )

    return sorted(evaluated, key=sort_key)[0]


def _generate_prefix_symbols(n: int, seed: int) -> list[complex]:
    """Generate *n* random QPSK symbols for the transmit prefix.

    Uses a derived seed (``seed + 9999``) to keep the prefix random stream
    independent from scrambling and noise.  This is intentionally preserved
    from the Level 2 implementation for bit-exact AWGN regression.

    Design rationale: the AWGN path retains ``seed + 9999`` (rather than
    ``SeedSequence.spawn()``) to guarantee bit-exact backward compatibility
    with earlier Level 2 results.  The Rayleigh path uses ``SeedSequence``
    for strict sub-stream isolation because fading and noise streams must
    never couple when array lengths change across experiments.
    """
    rng = np.random.default_rng(seed + 9999)
    bits = [int(x) for x in rng.integers(0, 2, size=n * 2)]
    return qpsk_modulate(bits)


def _validate_modes(channel: str, equalizer: str, diversity_order: int) -> None:
    """Reject unsupported channel / equalizer / diversity combinations.

    Enforces DESIGN.md combinatorial constraints:
        * AWGN → equalizer='none', diversity_order=1
        * Rayleigh single-branch → equalizer='zf' or 'mmse'
        * Rayleigh dual-branch → equalizer='none' or 'mmse' (MRC used internally)

    Raises:
        ValueError: If the combination is invalid.
    """
    if diversity_order not in (1, 2):
        raise ValueError("diversity_order must be 1 or 2")
    if channel == "awgn" and (equalizer != "none" or diversity_order != 1):
        raise ValueError("AWGN requires equalizer='none' and diversity_order=1")
    if channel == "rayleigh" and diversity_order == 1 \
            and equalizer not in ("zf", "mmse"):
        raise ValueError(
            "single-branch Rayleigh requires equalizer='zf' or 'mmse'"
        )
    if channel == "rayleigh" and diversity_order == 2 \
            and equalizer not in ("none", "mmse"):
        raise ValueError(
            "two-branch Rayleigh uses MRC and accepts equalizer='none' "
            "or the CLI-compatible 'mmse' token"
        )


def run_pipeline(input_path: str, output_path: str,
                 snr_db: float, seed: int,
                 modulation: str = "qpsk", channel: str = "awgn",
                 equalizer: str = "none",
                 diversity_order: int = 1) -> dict:
    """Run the selected end-to-end baseband simulation.

    AWGN retains the original Level 2 path and random streams.  Rayleigh uses
    flat block fading, preamble-only LS estimates, scalar ZF/MMSE for one
    branch, or complex-symbol ordinary MRC for two branches.  True channel
    values remain simulation-only diagnostics.
    """
    snr_db = validate_snr_db(snr_db)
    if modulation != "qpsk":
        raise ValueError(
            f"Unsupported modulation: {modulation}. Only 'qpsk' is supported."
        )
    if channel not in ("awgn", "rayleigh"):
        raise ValueError(
            f"Unsupported channel: {channel}. Use 'awgn' or 'rayleigh'."
        )
    _validate_modes(channel, equalizer, diversity_order)
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with open(input_path, "r", encoding="utf-8", newline="") as file:
        original_text = file.read()

    original_bits = source_encode(original_text)
    scrambled = scramble(original_bits, seed)
    coded = channel_encode(scrambled)
    if len(coded) != 3 * len(original_bits):
        raise RuntimeError("channel coding length invariant failed")
    frame_bits = build_frame(original_bits, coded, seed=seed)
    frame_symbols = qpsk_modulate(frame_bits)

    receiver_failure_reason = ""
    noise_variance = 0.0
    channel_estimates = np.array([], dtype=np.complex128)
    true_channel = np.array([], dtype=np.complex128)
    branch_correlations = []
    raw_aligned_symbols = np.array([], dtype=np.complex128)

    if channel == "awgn":
        # ─── Level 2 AWGN path (preserved bit-exact) ───
        # Uses the original seed→rng→prefix→awgn chain.  Do not alter.
        rng = np.random.default_rng(seed)
        n_prefix = int(rng.integers(0, 129))
        prefix_symbols = _generate_prefix_symbols(n_prefix, seed)
        tx_symbols = prefix_symbols + frame_symbols
        rx_symbols = awgn(tx_symbols, snr_db=snr_db, seed=seed)
        sync_start, corr_values = synchronize_with_correlation(
            rx_symbols, PREAMBLE_SYMBOLS
        )
        receiver_symbols = np.asarray(rx_symbols[sync_start:])
        raw_aligned_symbols = receiver_symbols.copy()
    else:
        # ─── Level 3 Rayleigh fading path ───
        # Prefix, fading and noise use independent SeedSequence children
        # so that array-length changes cannot couple the random streams.
        prefix_stream, channel_stream = np.random.SeedSequence(seed).spawn(2)
        prefix_rng = np.random.default_rng(prefix_stream)
        n_prefix = int(prefix_rng.integers(0, 129))
        prefix_bits = prefix_rng.integers(0, 2, size=n_prefix * 2).tolist()
        tx_symbols = qpsk_modulate(prefix_bits) + frame_symbols

        # Apply flat block Rayleigh fading → received_branches shape (L, N)
        received_branches, true_channel, noise_variance = \
            rayleigh_flat_fading(
                tx_symbols, snr_db, channel_stream, diversity_order
            )
        rx_symbols = received_branches[0].tolist()

        # Synchronisation: single-branch correlation or dual-branch combining
        if diversity_order == 1:
            sync_start, corr_values = synchronize_with_correlation(
                received_branches[0], PREAMBLE_SYMBOLS
            )
            branch_correlations = [corr_values]
        else:
            sync_start, corr_values, branch_correlations = \
                synchronize_branches(received_branches, PREAMBLE_SYMBOLS)

        # Align all branches to the detected frame start
        aligned_branches = received_branches[:, sync_start:]
        if aligned_branches.shape[1] > 0:
            raw_aligned_symbols = aligned_branches[0].copy()
        try:
            preamble_length = len(PREAMBLE_SYMBOLS)
            if aligned_branches.shape[1] < preamble_length:
                raise ValueError("received frame is shorter than the preamble")

            # LS channel estimation per branch using the known preamble
            # ĥ_l = Σ y_{p,l}[k]·p*[k] / Σ |p[k]|²
            channel_estimates = np.asarray([
                estimate_flat_channel(
                    branch[:preamble_length], PREAMBLE_SYMBOLS
                )
                for branch in aligned_branches
            ])

            # Equalisation: ZF (single), MMSE (single), or MRC (dual-branch)
            if diversity_order == 1 and equalizer == "zf":
                # ẍ[k] = y[k] / ĥ
                receiver_symbols = zf_equalize(
                    aligned_branches[0], channel_estimates[0]
                )
            elif diversity_order == 1:
                # ẍ[k] = ĥ*·y[k] / (|ĥ|² + N₀/Eₛ)
                receiver_symbols = mmse_equalize(
                    aligned_branches[0], channel_estimates[0],
                    noise_variance, symbol_power=1.0,
                )
            else:
                # ẍ[k] = Σ ĥₗ*·yₗ[k] / Σ |ĥₗ|²
                receiver_symbols = mrc_combine(
                    aligned_branches, channel_estimates, noise_variance
                )
        except ValueError as error:
            receiver_failure_reason = str(error)
            receiver_symbols = np.array([], dtype=np.complex128)

    # ─── QPSK demodulation and frame parsing ───
    demod_bits = qpsk_demodulate(receiver_symbols)
    # Physical-layer hard-decision BER after synchronization and QPSK
    # demodulation. Extra demodulated bits after the transmitted frame are
    # ignored; missing frame bits are counted as errors by calculate_ber().
    predecode_ber = calculate_ber(frame_bits, demod_bits[:len(frame_bits)])
    payload_bits = len(original_bits)
    recovery = _recover_frame_fields(demod_bits, seed)
    parsed = recovery["parsed"]
    original_length = parsed["original_length"]
    coded_length = parsed["coded_length"]
    descrambled = recovery["descrambled"]
    length_ok = recovery["length_ok"]
    checksum_pass = bool(recovery["checksum_pass"])
    # Frame error: any failure in the chain → FER = 1.0
    fer = 0.0 if checksum_pass else 1.0

    recovered_text = ""
    if length_ok and descrambled and len(descrambled) % 8 == 0:
        try:
            recovered_text = source_decode(descrambled)
        except (ValueError, UnicodeDecodeError):
            recovered_text = ""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as file:
        file.write(recovered_text)

    payload_ber = calculate_ber(original_bits, descrambled)
    frame_error_indicator = 0 if checksum_pass else 1
    max_chars = max(len(original_text), len(recovered_text))
    if max_chars:
        matches = sum(
            (original_text[index] if index < len(original_text) else "")
            == (recovered_text[index] if index < len(recovered_text) else "")
            for index in range(max_chars)
        )
        text_match_rate = matches / max_chars
    else:
        text_match_rate = 1.0

    sync_error_symbols = int(sync_start) - int(n_prefix)
    sync_success = bool(abs(sync_error_symbols) <= 1)

    metrics = {
        "snr_db": float(snr_db),
        "seed": int(seed),
        "modulation": str(modulation),
        "channel": str(channel),
        "payload_bits": int(payload_bits),
        "ber": float(round(payload_ber, 10)),
        "payload_ber": float(round(payload_ber, 10)),
        "predecode_ber": float(round(predecode_ber, 10)),
        "fer": float(fer),
        "frame_error_indicator": int(frame_error_indicator),
        "text_match_rate": float(round(text_match_rate, 10)),
        "checksum_pass": bool(checksum_pass),
        "true_prefix_symbols": int(n_prefix),
        "sync_start_index": int(sync_start),
        "sync_error_symbols": int(sync_error_symbols),
        "sync_success": sync_success,
        "frame_parse_strategy": str(parsed.get("frame_parse_strategy", "unknown")),
        "preamble_bit_errors": parsed.get("preamble_bit_errors"),
        "header_bit_errors": parsed.get("header_bit_errors"),
        "crc_bit_errors": recovery.get("crc_bit_errors"),
        "qpsk_padding_bits": parsed.get("qpsk_padding_bits"),
        "_rx_symbols": rx_symbols,
        "_sync_start": sync_start,
        "_corr_values": corr_values,
        "_frame_symbols": frame_symbols,
        "_prefix_count": n_prefix,
        "_raw_aligned_symbols": raw_aligned_symbols,
        "_equalized_symbols": np.asarray(receiver_symbols),
    }

    if channel == "rayleigh":
        errors = np.abs(channel_estimates - true_channel) \
            if channel_estimates.size == true_channel.size else np.array([])
        metrics.update({
            "fading_model": "flat_block_rayleigh",
            "equalizer": equalizer if diversity_order == 1 else "mrc",
            "requested_equalizer": str(equalizer),
            "diversity_order": int(diversity_order),
            "channel_estimation_error": (
                float(np.mean(errors)) if errors.size else None
            ),
            "noise_variance": float(noise_variance),
            "failure_reason": receiver_failure_reason,
            "_channel_estimates": channel_estimates,
            "_true_channel": true_channel,
            "_branch_correlations": branch_correlations,
        })
        if diversity_order == 1:
            estimate = channel_estimates[0] if channel_estimates.size else 0j
            truth = true_channel[0] if true_channel.size else 0j
            metrics.update({
                "channel_estimate_real": float(np.real(estimate)),
                "channel_estimate_imag": float(np.imag(estimate)),
                "channel_estimate_magnitude": float(abs(estimate)),
                "channel_estimate_phase_rad": float(np.angle(estimate)),
                "simulation_only_true_channel_real": float(np.real(truth)),
                "simulation_only_true_channel_imag": float(np.imag(truth)),
            })
        else:
            metrics.update({
                "channel_estimates_real": np.real(channel_estimates).tolist(),
                "channel_estimates_imag": np.imag(channel_estimates).tolist(),
                "channel_estimates_magnitude": np.abs(channel_estimates).tolist(),
                "simulation_only_true_channels_real": np.real(true_channel).tolist(),
                "simulation_only_true_channels_imag": np.imag(true_channel).tolist(),
            })
    return metrics
