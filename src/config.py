"""项目级公共配置常量。"""

from __future__ import annotations

import math

MIN_SNR_DB = -100.0
MAX_SNR_DB = 100.0


def validate_snr_db(snr_db: float) -> float:
    """校验 SNR 是否为有限且处于项目允许范围内的 dB 值。

    Args:
        snr_db: 待校验的 SNR dB 值。

    Returns:
        通过校验后的 ``float`` 值。

    Raises:
        ValueError: 当 SNR 为 NaN、无穷大或超出允许范围时抛出。
    """
    value = float(snr_db)
    if not math.isfinite(value) or not (MIN_SNR_DB <= value <= MAX_SNR_DB):
        raise ValueError(
            f"SNR 必须是有限数，并位于 [{MIN_SNR_DB:g}, {MAX_SNR_DB:g}] dB 范围内。"
        )
    return value
