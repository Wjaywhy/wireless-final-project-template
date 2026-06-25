# DESIGN.md — 无线通信基带仿真系统设计文档

## 设计范围

本文档描述端到端无线通信基带仿真系统的设计方案，覆盖从 `Test.txt` 到 `results/received.txt` 的完整链路。文档说明系统架构、模块接口、算法选择、数据约定、关键参数、命令行接口、性能指标、图表输出、异常处理策略和已知风险。本文档包含系统设计方案及基于最终实现获得的实测结果，所有性能数据均来自实际运行，不包含虚构结果。

## 系统架构

### 固定链路

```
Test.txt
  → Source Encode        # UTF-8 文本 → bitstream
  → Scramble             # PN 序列 XOR 扰码
  → Channel Encode       # 三重复码编码
  → Frame Build          # 组装前导 + 长度 + 载荷 + CRC-32
  → QPSK Modulate        # Gray 映射 QPSK
  → Random Symbol Offset # 0～128 个随机 QPSK 符号前置
  → AWGN                 # 复高斯加性白噪声，可配置符号 SNR
  → Synchronization      # 归一化滑动互相关帧检测
  → QPSK Demodulate      # 硬判决解调
  → Frame Parse          # 解析帧结构，提取载荷
  → Channel Decode       # 三重复码多数表决译码
  → Descramble           # PN 序列 XOR 解扰
  → Source Decode        # bitstream → UTF-8 文本
  → received.txt         # 恢复文本
  → Metrics / Plots      # 指标 JSON + 可视化图表
```

### 推荐目录结构

```text
wireless-final-project/
  main.py                # CLI 入口与主流程
  src/
    source.py            # UTF-8 ↔ bitstream
    scramble.py          # PN 扰码与解扰
    channel_coding.py    # 三重复码编码与多数表决译码
    framing.py           # 帧封装与解析
    modulation.py        # QPSK Gray 映射调制与硬判决解调
    channel.py           # AWGN 信道
    synchronization.py   # 前导归一化滑动互相关同步
    metrics.py           # 指标计算与 JSON 输出
    plotting.py          # 图表生成
    pipeline.py          # 端到端管线编排
  tests/
  public_tests/          # 教师提供的公开测试
  results/               # 运行时自动创建
```

## 数据约定

### 通用约定

- 所有 bit 使用 Python `list[int]` 表示，元素为 0 或 1。
- 复数符号使用 Python `list[complex]` 或 NumPy `ndarray[complex128]` 表示。
- 随机种子通过 `seed` 参数在模块间传递，确保全程可复现。
- UTF-8 文本的编码与解码使用 Python 标准库 `str.encode('utf-8')` 和 `bytes.decode('utf-8')`。
- SNR 使用符号 SNR（$E_s/N_0$），单位为 dB。

### 发送端模块

#### 源编码 (`src/source.py`)

**功能：** 将 UTF-8 文本转换为 bitstream，并能从 bitstream 精确恢复原始文本。

**算法：**
1. `source_encode(text: str) -> list[int]`：使用 `text.encode('utf-8')` 获得 `bytes`，逐字节展开为 8-bit 序列（MSB 优先），拼接为 `list[int]`。
2. `source_decode(bits: list[int]) -> str`：将 bitstream 每 8 bit 分组（MSB 优先）还原为字节，组合为 `bytes`，调用 `.decode('utf-8')` 恢复文本。

**输入约束：**
- 输入必须为有效 UTF-8 字符串。
- bitstream 长度必须是 8 的整数倍。若传入长度非 8 的倍数，`source_decode` 应抛出异常。

**设计理由：** UTF-8 是 PRD 指定的文本编码，每字符 1～4 字节。MSB 优先便于与字节级操作对齐。

#### 扰码 (`src/scramble.py`)

**功能：** 使用固定种子的 PN 序列对 bitstream 逐位 XOR，实现可逆扰码。扰码不作为安全加密，仅用于避免载荷中长连 0/1 导致的同步退化。

**算法：**
1. `scramble(bits: list[int], seed: int = 2026) -> list[int]`：
   - 使用 `numpy.random.default_rng(seed)` 生成长度等于 `len(bits)` 的随机 bit 序列。
   - 逐位 XOR，返回扰码后的 `list[int]`。
2. `descramble(bits: list[int], seed: int = 2026) -> list[int]`：与 `scramble` 完全相同的操作（XOR 两次恢复原值）。

**关键参数：**
- `seed`：随机种子，默认 2026，从 CLI 传入以保证可复现性。

**设计理由：** XOR 可逆，PN 序列简单高效。固定种子确保同一输入在相同 SNR 下产生相同输出，满足教师可复现性要求。

#### 信道编码 (`src/channel_coding.py`)

**功能：** 三重复码——每 bit 重复 3 次，接收端采用硬判决多数表决译码。

**算法：**
1. `channel_encode(bits: list[int]) -> list[int]`：将输入 bitstream 中每位 b 展开为 `[b, b, b]`。
2. `channel_decode()` 要求输入长度为 3 的整数倍。若输入长度不满足要求，则抛出 `ValueError`，避免对不完整码组进行静默译码。完整管线在调用译码前通过 Coded Length 和 `coded_length == 3 × original_length` 检查保证码组完整。

**关键参数：**
- 编码率 $R = 1/3$。
- 每 bit 可纠正至多 1 位错误。

**设计理由：** 三重复码实现简单、无噪声下完美恢复、抗噪声能力明确。契合课程教学内容，可验证信道编码的基本功能。编码率 1/3 在 12 dB AWGN 下足以保障可靠传输。

### 帧结构 (`src/framing.py`)

帧结构设计如下（所有字段均为 bit 序列）：

| 字段 | 长度 (bit) | 内容 |
|---|---|---|
| Preamble | 64 | 固定前导序列，用于同步 |
| Original Length | 32 | 源编码后、扰码前的原始 bit 数（大端无符号整数） |
| Coded Length | 32 | 信道编码后的 payload bit 数（大端无符号整数） |
| Coded Payload | 可变（Coded Length 指定） | 经 Scramble → Channel Encode 后的载荷 bit |
| CRC-32 | 32 | 对 **原始源 payload**（扰码前、编码前）计算的 CRC-32 |

**前导序列（已确定）：** 使用 7 阶最大长度 LFSR 生成（本原多项式 $x^7 + x^6 + 1$，周期 127），初始状态 `0b1010111`，取前 64 bit 输出。

生成的 64-bit 前导序列：
```
1 1 1 0 1 0 1 0
0 1 1 0 0 1 0 0
0 0 1 1 1 1 0 0
1 0 1 1 0 1 1 0
1 0 0 1 0 0 0 1
0 1 0 1 1 1 1 0
1 1 0 0 1 1 0 0
0 1 1 1 0 1 1 1
```

该序列已硬编码于 `src/framing.py` 的 `_PREAMBLE_BITS`。Mock 测试验证：32 符号滑动窗口互相关在 12 dB AWGN 下主峰 > 0.95，旁瓣均 < 65% 主峰值。

**Original Length：** 32-bit 大端无符号整数，记录 `source_encode` 输出的原始 bit 数（即 UTF-8 文本编码后、扰码前的 bitstream 长度）。此字段用于接收端在 `source_decode` 前精确截断 bitstream。

**Coded Length：** 32-bit 大端无符号整数，记录信道编码后的 payload bit 数。此字段用于接收端帧解析器正确切分 Coded Payload 字段，明确区分有效数据与 QPSK 调制时因奇数 bit 产生的补零。

**CRC-32：** 使用 `zlib.crc32`（IEEE 802.3 多项式 `0x04C11DB7`），对原始源 payload bitstream（`source_encode` 输出，即扰码前的 bitstream）进行计算。具体约定：

- Bit → Bytes：MSB 优先，每 8 bit 组成 1 字节
- 零长度 payload：`zlib.crc32(b"") & 0xFFFFFFFF`
- 非 8 倍数 bitstream：先补零至字节边界再计算（防御性设计；UTF-8 编码输出始终为 8 的倍数）
- 返回值取低 32 bit（`& 0xFFFFFFFF`）
- CRC 在帧中存储为 32 bit 大端序列

CRC-32 校验通过则 `checksum_pass = true`。

**QPSK 奇数长度补零处理：** 帧序列化后的总 bit 数可能为奇数，QPSK 调制以 2 bit 为单位。补零 bit 不计入任何帧字段，接收端通过 `Coded Length` 精确恢复帧边界后丢弃末尾补零。

#### 函数接口

```python
def build_frame(original_payload_bits: list[int],
                coded_payload_bits: list[int] | None = None,
                seed: int = 2026) -> list[int]:
    """
    组装完整帧 bitstream。
    单参数模式：build_frame(payload) — 不进行编码，payload 即 coded payload。
    双参数模式：build_frame(original, coded) — CRC 基于 original，存储 coded。
    """

def parse_frame(frame_bits: list[int], preamble: list[int] | None = None) -> dict:
    """
    解析帧，返回 dict:
    {
        "preamble": list[int],         # 检测到的前导 (64 bit)
        "original_length": int,        # Original Length 字段值
        "coded_length": int,           # Coded Length 字段值
        "payload": list[int],          # coded_payload 别名（兼容公开测试）
        "coded_payload": list[int],    # Coded Length 指定位数的编码载荷
        "crc_received": list[int],     # 接收到的 32-bit CRC
        "length": int,                 # original_length 别名（兼容公开测试）
    }
    """
```

**设计理由：** 双长度字段（Original + Coded）将原始 bit 数和编码后 bit 数解耦，接收端可利用 `Coded Length` 精确截断编码载荷后再做译码，同时用 `Original Length` 在源解码前恢复精确的原始 bitstream 长度。64-bit 前导在 0～128 符号偏移下提供足够的相关增益。

### 调制与信道

#### QPSK 调制 (`src/modulation.py`)

**星座映射（Gray QPSK）：**

| bit 对 (b0, b1) | 符号值 | 归一化符号 | I (real) | Q (imag) |
|---|---|---|---|---|
| 00 | $1 + j$ | $(1 + j) / \sqrt{2}$ | + | + |
| 01 | $-1 + j$ | $(-1 + j) / \sqrt{2}$ | − | + |
| 11 | $-1 - j$ | $(-1 - j) / \sqrt{2}$ | − | − |
| 10 | $1 - j$ | $(1 - j) / \sqrt{2}$ | + | − |

**Bit 到 I/Q 规则：** b1 控制 I 路（实部），b0 控制 Q 路（虚部）。b1=0 → I=+1, b1=1 → I=−1；b0=0 → Q=+1, b0=1 → Q=−1。

**归一化：** 除以 $\sqrt{2}$，使得星座点平均功率 $E_s = 1$。

**函数接口：**
```python
def qpsk_modulate(bits: list[int]) -> list[complex]:
    """将 bitstream 映射为 QPSK 符号序列。若 bit 数为奇数，末尾补 1 个 0。"""

def qpsk_demodulate(symbols: list[complex]) -> list[int]:
    """硬判决解调：I≥0→b1=0, Q≥0→b0=0。"""
```

**设计理由：** Gray 映射使得相邻星座点的 bit 对仅差 1 bit，在高 SNR 下将符号错误转化为单 bit 错误，降低 BER。Mock 测试阶段发现并修正了 b0/b1 与 I/Q 的对应关系（b1→I, b0→Q）。QPSK 是 PRD 指定的必修调制方式，平衡了频谱效率和抗噪声能力。

#### AWGN 信道 (`src/channel.py`)

**功能：** 对复基带符号添加复高斯白噪声。

**算法：**
```python
def awgn(symbols: list[complex], snr_db: float, seed: int = 2026) -> list[complex]:
    """
    符号 SNR AWGN 信道。
    - 计算符号能量 E_s = mean(|symbols|^2)。
    - 由 SNR_dB 和 E_s 计算噪声功率 N0 = E_s / 10^(SNR_dB/10)。
    - 噪声每维方差 = N0/2（实部和虚部各半）。
    - 使用 seed 初始化 rng 生成复高斯噪声并叠加。
    """
```

**关键参数：**
- `snr_db`：符号 SNR（$E_s/N_0$），单位 dB。
- `seed`：随机种子，确保噪声可复现。

**设计理由：** AWGN 是无线通信的基础信道模型，PRD 必修要求。使用符号 SNR（而非 bit SNR）直接对应调制符号能量，便于与星座图归一化配合。

#### 随机符号偏移

在 AWGN 之前，发送符号序列前插入 0～128 个随机 QPSK 符号。随机种子派生自全局 seed（`seed + 9999`），保证可复现且独立于其他随机子流。发送端实际插入的前置符号数量由随机偏移生成模块确定；`sync_start_index` 表示接收端同步算法估计出的帧起始符号索引。两者在同步正确时应一致，但概念上不能混同。

#### 帧完整性校验

`parse_frame()` 在解析前至少检查：
- 帧长度 ≥ 160 bit（前导 64 + 原始长度 32 + 编码长度 32 + CRC 32，零载荷下限）
- coded_length 和 CRC 不能超过剩余帧长度
- 若提供 preamble 引用值，验证接收前导是否匹配

校验失败抛出 `ValueError`，由 pipeline 捕获，设置 `frame_ok = False` 和 `fer = 1.0`。

### 同步 (`src/synchronization.py`)

**功能：** 检测帧起点偏移，输出帧起始索引。

**算法：** 归一化滑动互相关。
1. 已知前导序列的 QPSK 符号（由前导 bit 序列经 QPSK 调制得到）。
2. 对接收符号序列进行滑动窗口归一化互相关：
   $$C[k] = \frac{|\sum_{m=0}^{L-1} r[k+m] \cdot p^*[m]|}{\sqrt{\sum |r[k+m]|^2 \cdot \sum |p[m]|^2}}$$
   其中 $r$ 为接收序列，$p$ 为前导模板符号，$L$ 为前导符号数（32 个 QPSK 符号对应 64 bit），$*$ 表示复共轭。
3. 相关峰值位置即为帧起点估计 `sync_start_index`。

**函数接口：**
```python
def synchronize(received_symbols: list[complex], preamble: list[complex]) -> int:
    """
    返回帧起点索引（整数）。
    preamble 为前导 bit 序列经 QPSK 调制后的复符号模板。
    """
```

**设计理由：** 归一化互相关能够降低接收幅度变化对检测统计量的影响。在已知前导和 AWGN 条件下，该方法与匹配相关检测具有一致的基本思想，适合本项目的帧起点估计。系统使用 QPSK 调制后的前导复符号进行相关，使同步处理与接收端符号级数据表示保持一致。

### 接收端流程

接收端严格按发送端的逆序处理：

1. **同步：** 使用归一化滑动互相关定位帧起点，并从检测位置截取帧符号。

2. **QPSK 解调：** 对接收符号进行硬判决，恢复帧 bitstream。

3. **帧解析：** 读取并验证 Preamble、Original Length、Coded Length、Coded Payload 和 CRC。

4. **编码长度预检查：** 在调用译码器前验证 `coded_length == 3 × original_length`、`coded_length` 是 3 的整数倍，且实际 Coded Payload 长度等于 `coded_length`；任一条件失败时跳过译码并进入安全失败路径。

5. **信道译码：** 仅对通过长度预检查的 Coded Payload 执行三重复码多数表决译码，恢复扰码后的 bitstream。

6. **解扰与恢复长度检查：** 使用与发送端相同的 seed 对译码结果执行 XOR 解扰，并检查解扰后 bit 数是否等于 `original_length`。

7. **CRC 校验：** 对接收端实际恢复的解扰 bitstream 重新计算 CRC-32，并与帧内 CRC 比较。不得使用发送端保存的原始 bitstream 参与接收端 CRC 判定。

8. **帧错误判定：** 仅当帧解析、编码长度关系、恢复长度和 CRC 全部通过时，设置 `checksum_pass = true`、`fer = 0.0`；任一失败时设置 `checksum_pass = false`、`fer = 1.0`。

9. **源解码：** 对通过长度处理后的恢复 bitstream 执行 UTF-8 解码。若发生长度异常或 UTF-8 解码错误，端到端管线采用安全失败策略，将恢复文本置为空字符串并继续输出诊断指标。

10. **输出：** 写出 `received.txt`、`metrics.json` 及三张结果图。

## 模块接口一览

### 必须暴露的函数

| 模块文件 | 函数 | 签名 |
|---|---|---|
| `src/source.py` | `source_encode` | `(text: str) -> list[int]` |
| | `source_decode` | `(bits: list[int]) -> str` |
| `src/scramble.py` | `scramble` | `(bits: list[int], seed: int) -> list[int]` |
| | `descramble` | `(bits: list[int], seed: int) -> list[int]` |
| `src/channel_coding.py` | `channel_encode` | `(bits: list[int]) -> list[int]` |
| | `channel_decode` | `(bits: list[int]) -> list[int]` |
| `src/framing.py` | `build_frame` | `(original_payload_bits: list[int], coded_payload_bits: list[int]) -> list[int]` |
| | `parse_frame` | `(frame_bits: list[int], preamble: list[int]) -> dict` |
| `src/modulation.py` | `qpsk_modulate` | `(bits: list[int]) -> list[complex]` |
| | `qpsk_demodulate` | `(symbols: list[complex]) -> list[int]` |
| `src/channel.py` | `awgn` | `(symbols: list[complex], snr_db: float, seed: int) -> list[complex]` |
| `src/synchronization.py` | `synchronize` | `(received_symbols: list[complex], preamble: list[complex]) -> int` |

### 编排模块 (`src/pipeline.py`)

负责按链路顺序串联所有模块。建议暴露：

```python
def run_pipeline(input_path: str, output_path: str, snr_db: float, seed: int,
                 modulation: str, channel: str) -> dict:
    """执行完整端到端流程，返回 metrics dict。"""
```

## CLI 与输出

### 命令行接口 (`main.py`)

```
python main.py --input Test.txt --output results/received.txt --snr 12 --seed 2026 --mod qpsk --channel awgn
```

使用 `argparse` 实现：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `--input` | str | 必填 | 输入 UTF-8 文本文件路径 |
| `--output` | str | 必填 | 输出恢复文本文件路径 |
| `--snr` | float | 必填 | 符号 SNR，单位 dB |
| `--seed` | int | 必填 | 全局随机种子 |
| `--mod` | str | 必填 | 调制方式，基础必须支持 `qpsk` |
| `--channel` | str | 必填 | 信道类型，基础必须支持 `awgn` |

**约束：**
- 不允许交互式输入（如 `input()`）。
- 不允许直接复制输入文件到输出。
- 自动创建 `results/` 目录（若不存在）。
- 低 SNR 下不得崩溃，应正常输出结果（即使 BER 较高）。
- 单次运行应在 20 秒内完成。

### 输出文件

| 文件 | 说明 |
|---|---|
| `results/received.txt` | 接收端恢复的 UTF-8 文本 |
| `results/metrics.json` | 性能指标 JSON |
| `results/constellation.png` | 接收端 QPSK 星座图 |
| `results/ber_curve.png` | BER-SNR 曲线 |
| `results/sync_peak.png` | 同步相关峰值图 |

## 指标 (`results/metrics.json`)

### 必需字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `snr_db` | float | 使用的符号 SNR（dB） |
| `seed` | int | 随机种子 |
| `modulation` | str | 调制方式（`"qpsk"`） |
| `channel` | str | 信道类型（`"awgn"`） |
| `payload_bits` | int | 原始源 payload bit 数（Original Length） |
| `ber` | float | Bit Error Rate |
| `fer` | float | Frame Error Rate（0.0 或 1.0） |
| `text_match_rate` | float | 文本字符级一致率 |
| `checksum_pass` | bool | CRC-32 校验是否通过 |
| `sync_start_index` | int | 同步检测到的帧起点索引 |

### 计算方法

- **BER：** 调用 `calculate_ber(original_bits, descrambled)`——共同长度范围逐 bit 比较，长度差每一 bit 均计为错误，分母为 $\max(L_{sent}, L_{received})$。两端均为空时 BER=0。
- **FER：** 帧解析成功 **且** `coded_length == 3 × original_length` **且** `len(descrambled) == original_length` **且** 对接收端恢复 bitstream 重算 CRC 与帧内 CRC 一致 → `0.0`；任一失败 → `1.0`。
- **text_match_rate：** 逐字符比较 `Test.txt` 与 `received.txt`。完全一致时为 `1.0`。
- **checksum_pass：** 接收端满足三重复码长度关系、恢复长度一致且 CRC 通过时为 `true`。**不使用发送端原始数据。**
- **sync_start_index：** 同步模块输出的帧起始符号索引。

### JSON 序列化注意事项

NumPy 整数和浮点数类型不能直接 JSON 序列化。输出前需将 `np.integer` 转换为 `int`，`np.floating` 转换为 `float`，`np.bool_` 转换为 `bool`。可自定义 JSON encoder 或在写入前逐字段转换。

## 图表

### `constellation.png` — 接收端 QPSK 星座图

- X 轴：同相分量（I），Y 轴：正交分量（Q）。
- 以散点图绘制解调前（AWGN 后）的所有 QPSK 符号。
- 宜使用半透明点或 2D 直方图以避免过密重叠。
- 叠加参考星座点（理想位置）作为标记。

### `ber_curve.png` — BER-SNR 曲线

- X 轴：SNR $E_s/N_0$（dB），范围 `[0, 2, 4, 6, 8, 10, 12]` dB。
- Y 轴：BER（对数坐标）。
- 两条曲线：
  1. **Simulated** — 实测端到端 BER（含同步、帧头、三重复码、CRC 和安全失败机制）
  2. **Ideal uncoded QPSK reference** — $P_b = 0.5 \cdot \mathrm{erfc}(\sqrt{E_s/N_0 / 2})$
- 实测曲线包含 preamble 校验、帧完整性检查和 CRC，不能与理想未编码 QPSK 曲线直接等价比较。
- BER=0 的点使用检测下限 `0.5 / payload_bits` 绘图并标注 "0 errors observed"。
- 能量换算关系（$R=1/3$）：$E_b/N_{0(dB)} = E_s/N_{0(dB)} + 10\log_{10}(3/2) \approx E_s/N_{0(dB)} + 1.76\text{ dB}$。这只是能量换算，不等于完整端到端 BER 理论公式。

### `sync_peak.png` — 同步相关峰值图

- X 轴：符号偏移索引。
- Y 轴：归一化互相关值（0～1）。
- 在真实帧起点处应出现明显峰值。

## 异常处理

### 可恢复场景

| 场景 | 处理策略 |
|---|---|
| 低 SNR 导致 BER 上升 | 正常输出，BER 和 FER 反映实际性能 |
| 同步偏移检测偏差 （±1 符号） | 容差为 ±1 符号（与公开测试一致） |
| QPSK 奇数输入补零 | 调制时自动补零，接收端依 Coded Length 丢弃 |
| 帧 CRC 校验失败 | `checksum_pass = false`，`fer = 1.0`，仍输出恢复文本供分析 |
| 帧解析失败（无法定位前导） | `fer = 1.0`，`checksum_pass = false`，尝试 best-effort 恢复 |
| `results/` 目录不存在 | CLI 启动时自动创建 |

### 不可恢复场景

| 场景 | 处理策略 |
|---|---|
| `Test.txt` 不存在 | 打印错误信息并 `sys.exit(1)` |
| 接收 bitstream 长度非法或 UTF-8 严格解码失败 | `source_decode()` 直接调用时分别抛出 `ValueError` 或 `UnicodeDecodeError`；端到端管线先检查 bit 长度，长度非法时跳过解码，长度合法但 UTF-8 解码异常时捕获异常。两条路径都将恢复文本安全置空、写出 `received.txt`，并继续输出失败指标，不因低 SNR 数据损坏而退出 |
| SNR 参数为非数值 | argparse 自动校验 |
| `--mod` 参数值不支持 | 打印支持列表并 `sys.exit(1)` |

## 测试追踪矩阵

以下矩阵将设计需求与公开测试用例（`public_tests/`）对应。

| 需求 | 相关模块 | 测试用例 |
|---|---|---|
| UTF-8 编解码可逆 | `src/source.py` | `test_tc_t_004` |
| 帧封装包含必需字段 | `src/framing.py` | `test_tc_t_005` |
| 帧封装与解析可逆 | `src/framing.py` | `test_tc_t_006` |
| 扰码可逆（seed 固定） | `src/scramble.py` | `test_tc_t_007` |
| 信道编码无噪声可逆 | `src/channel_coding.py` | `test_tc_t_008` |
| QPSK 星座象限正确、单位功率 | `src/modulation.py` | `test_tc_t_009` |
| QPSK 无噪声解调无误码 | `src/modulation.py` | `test_tc_t_010` |
| 奇数 bit 载荷经 QPSK 补零后正确恢复 | `src/framing.py` + `src/modulation.py` | `test_tc_t_011` |
| AWGN 固定 seed 可复现 | `src/channel.py` | `test_tc_t_012` |
| 同步检测 25 符号偏移 | `src/synchronization.py` | `test_tc_t_013` |
| metrics.json 包含全部必需字段 | `src/metrics.py` | `test_tc_t_014` |
| 12 dB 端到端文本完全一致 | `src/pipeline.py` + 全部 | `test_tc_t_015` |
| 生成至少两张图 | `src/plotting.py` | `test_tc_t_016` |
| CLI 非交互运行 | `main.py` | `test_tc_t_017` |
| 项目结构和文档完整 | 全部 | `test_tc_t_001` |
| DESIGN.md 覆盖系统链路关键词 | 本文档 | `test_tc_t_002` |
| 无直接文件复制行为 | `main.py` + `src/` | `test_tc_t_020` |

## 风险

### R1：UTF-8 多字节字符错误扩散
UTF-8 多字节字符（如中文字符占 3 字节）中单个 bit 错误可能使恢复字节序列不再是合法 UTF-8，或在字节序列仍合法时解码为错误字符。`source_decode()` 使用严格 UTF-8 解码，不会生成替换字符 U+FFFD；若抛出 `ValueError` 或 `UnicodeDecodeError`，端到端管线会捕获异常，将 `recovered_text` 置为空字符串并写入 `received.txt`，随后继续输出 BER、FER、`text_match_rate` 和 `checksum_pass`，避免低 SNR 场景崩溃。缓解：三重复码提供基础纠错能力，CRC 和上述指标用于显式标记恢复失败。

### R2：长度字段被噪声破坏
Original/Coded Length 字段（各 32 bit）若出现 bit 错误，会导致帧解析错误，进而使整个帧无效。当前设计中长度字段无单独保护。缓解：12 dB SNR 下 32 bit 全部正确的概率较高；若需增强，可在后续设计中加入长度字段的 Hamming 保护。

### R3：奇数 bit 补零与 Coded Length 不一致
QPSK 调制补零后，接收端若未正确使用 Coded Length 截断，会将补零 bit 视为数据，导致信道译码输出多出额外 bit。缓解：`parse_frame` 严格按 Coded Length 提取编码载荷后再传递给 `channel_decode`。

### R4：低 SNR 下同步失败
SNR 低于阈值时，归一化互相关峰值可能被噪声淹没，导致 `sync_start_index` 偏差。若偏差超过前导长度，帧解析完全失败。缓解：同步模块返回峰值索引；管线中检测异常偏移并记录 FER=1.0。

### R5：CRC 校验失败
CRC 失败说明帧载荷中存在不可纠正的 bit 错误。当前设计对 CRC 失败采取记录而非重传策略（仿真系统无重传机制）。缓解：记录 `checksum_pass = false` 和 `fer = 1.0`。

### R6：随机种子可复现性
若某模块遗漏 seed 传递或使用了非确定性操作（如 Python set 迭代顺序），会导致同 seed 下输出不一致。缓解：所有涉及随机性的模块（扰码、AWGN、偏移生成）统一接受 seed 参数并使用 `np.random.default_rng(seed)`。

### R7：NumPy 类型 JSON 序列化
`numpy.integer`、`numpy.floating`、`numpy.bool_` 类型无法被 `json.dump` 序列化，直接使用会抛出 `TypeError`。缓解：指标输出前显式转换为 Python 原生类型。

### R8：输出目录被删除或不可写
若 `results/` 目录在运行时被外部删除或权限不足，文件写入失败。缓解：`main.py` 开始时检查并创建 `results/`；若创建失败，打印错误并退出。

### R9：隐藏测试更换文本、SNR、seed 和偏移
教师隐藏验证集会使用不同的输入文本（不同长度、不同内容）、不同的 SNR、不同的 seed 和不同的同步偏移。缓解：系统不应对任何特定输入做硬编码优化；所有参数应通过 CLI 和 Frame 字段传递；帧结构中的长度字段使系统自动适应不同文本长度。

### R10：BER 曲线生成超时
若 BER 曲线遍历过多 SNR 点（如 20 个点），单次 CLI 运行可能超过 20 秒限制。缓解：
- 统一 CLI 每次运行都会先计算当前 `--snr` 的指标，再调用 `generate_all_plots()` 生成三张图；其中 BER 曲线固定额外运行 `[0, 2, 4, 6, 8, 10, 12]` dB 共 7 个 SNR 点。
- 不在默认流程中扩展 SNR 点数或增加 Monte Carlo 重复次数；如需提高统计精度，应先单独评估运行时间并调整 CLI 超时预算。
- 优化调制/解调循环，避免逐符号 Python 循环。
- 测试 `test_tc_t_017` 允许 20s timeout。

## 实测结果

以下为 `seed=2026, mod=qpsk, channel=awgn` 下的实测结果（教师原始 Test.txt, 262 字符, 6128 bit payload）。

帧完整性校验（preamble 验证 + 最小长度 + coded_length 边界 + CRC 检查）使系统在 preamble 比特错误时直接判定帧解析失败，形成"悬崖效应"：8 dB 以上完全恢复，6 dB 以下整帧失败。

| SNR (dB) | BER | FER | text_match_rate | checksum_pass | sync_start_index |
|---|---|---|---|---|---|
| 12 | 0.0 | 0.0 | 1.0 | true | 109 |
| 10 | 0.0 | 0.0 | 1.0 | true | 109 |
| 8 | 0.0 | 0.0 | 1.0 | true | 109 |
| 6 | 1.0 | 1.0 | 0.0 | false | 109 |
| 4 | 1.0 | 1.0 | 0.0 | false | 109 |
| 2 | 1.0 | 1.0 | 0.0 | false | 109 |
| 0 | 1.0 | 1.0 | 0.0 | false | 109 |

关键观察：
- **8 dB 及以上：** preamble 64 bit 在 AWGN 下全部正确，帧解析成功，text 完全恢复。
- **6 dB 及以下：** preamble 比特错误导致帧解析失败，恢复 bitstream 为空，BER=1.0 且 FER=1.0（符合"长度差计错"定义）。
- **同步：** 归一化互相关在所有 SNR 下均正确检测偏移 109，验证了前导检测的鲁棒性远高于 preamble 比特匹配。偏移值恒为 109 是因为固定 seed=2026 下 AWGN 路径使用确定性子流（`seed+9999` 派生前缀长度），前缀符号数完全确定；不同 seed 会产生不同的偏移值。

### Level 3 多 seed 实测结果

以下为 `seed=2026` 派生的 5 个独立实验 seed、教师原始 Test.txt（262 字符 / 6128 bit payload）下的平均 FER。每 SNR 点 5 次独立衰落实现取均值。

| SNR (dB) | AWGN 基线 | Rayleigh+ZF | Rayleigh+MMSE | Rayleigh+MRC (2-branch) |
|---|---|---|---|---|
| 0 | 1.0 | 1.0 | 1.0 | 1.0 |
| 4 | 1.0 | 1.0 | 1.0 | 0.8 |
| 8 | 0.0 | 0.8 | 0.8 | 0.4 |
| 12 | 0.0 | 0.2 | 0.2 | 0.0 |
| 16 | 0.0 | 0.0 | 0.0 | 0.0 |
| 20 | 0.0 | 0.0 | 0.0 | 0.0 |

关键观察：
- **AWGN 基线：** 与 Level 2 单 seed 结论一致，8 dB 以上完全恢复。
- **Rayleigh 单分支（ZF/MMSE）：** 因深衰落可能，8 dB 仍有 80% 帧失败；需 16 dB 以上才能稳定恢复。标量平坦信道硬判决下 ZF 与 MMSE 的 FER 相同（符合阶段 D 设计预期）。
- **双分支 MRC：** 在 12 dB 即实现完全恢复，相比单分支有约 4 dB 的有效分集增益。两个独立分支同时深衰落的概率显著低于单分支。
- **同步：** 所有方案和 SNR 下同步成功率均为 100%——前导互相关对平坦衰落具有鲁棒性，远高于 preamble 比特级正确接收的要求。
- **有限样本提示：** 以上为 5 个固定 seed 的平均值，不构成严格理论性能曲线。

## Level 3 高级模块设计

Level 3 以可选参数扩展现有单载波 QPSK 链路，不改变默认 AWGN 路径。实现范围限定为平坦块 Rayleigh 衰落、前导辅助信道估计、ZF/MMSE 均衡和二分支 MRC 接收分集；不包含 OFDM、卷积码 Viterbi、自适应调制或 GUI。

### Level 3 架构与模块接口

单分支接收链路计划为：

```text
QPSK frame + random prefix
→ flat block Rayleigh channel
→ normalized-correlation synchronization
→ preamble LS channel estimation
→ ZF or MMSE equalization of the complete aligned frame
→ existing QPSK demodulation, frame parsing, decoding, CRC and source recovery
```

双分支接收链路计划为：

```text
two independent Rayleigh receive branches
→ per-branch normalized correlation and combined peak selection
→ per-branch preamble LS estimates
→ complex-symbol MRC
→ existing QPSK demodulation and receive chain
```

计划新增接口如下，生产实现只能在阶段 E 写入：

```python
# src/channel.py
def rayleigh_flat_fading(symbols, snr_db, seed=2026, diversity_order=1):
    """Return received_branches, simulation_only_true_channel, noise_variance."""

# src/equalization.py
def estimate_flat_channel(received_preamble, known_preamble,
                          epsilon=1e-12) -> complex: ...
def zf_equalize(received, h_est, epsilon=1e-12): ...
def mmse_equalize(received, h_est, noise_variance,
                  symbol_power=1.0, epsilon=1e-12): ...

# src/diversity.py
def mrc_combine(received_branches, channel_estimates,
                noise_variance=None, epsilon=1e-12): ...

# src/synchronization.py
def synchronize_branches(received_branches, preamble):
    """Return start index, combined correlation and branch correlations."""

# src/pipeline.py
def run_pipeline(input_path, output_path, snr_db, seed,
                 modulation="qpsk", channel="awgn",
                 equalizer="none", diversity_order=1): ...
```

模块边界要求：`main.py` 只负责参数解析和产物调度；信道、估计、均衡、分集和实验扫描不得堆入 CLI 文件。`synchronize()`、`awgn()` 及旧 `run_pipeline()` 调用方式必须保持兼容。

### Rayleigh 平坦块衰落模型

第 $l$ 个接收分支采用：

$$y_l[k] = h_l x[k] + n_l[k], \qquad h_l \sim \mathcal{CN}(0,1), \quad n_l[k] \sim \mathcal{CN}(0,N_0).$$

每个分支的 $h_l$ 在随机前置符号、前导和完整帧载荷期间保持不变，不同分支和不同 seed 相互独立。$N_0$ 仍由发送符号平均功率与符号 SNR $E_s/N_0$ 计算。该模型适合验证单帧窄带链路中的深衰落、相位旋转、均衡和接收分集，但不是频率选择性多径模型。

随机子流采用确定性分离：

| 用途 | 派生方式 |
|---|---|
| Scrambling | 保留 Level 2 的 `default_rng(seed)`，维持基线兼容性 |
| Prefix generation | `SeedSequence(seed).spawn(2)` 的 prefix 子流 |
| Fading coefficients | channel 子流继续 spawn 的 fading 子流 |
| Branch-1 noise | channel 子流继续 spawn 的第 1 噪声子流 |
| Branch-2 noise | channel 子流继续 spawn 的第 2 噪声子流 |
| Experiment seed sweep | `SeedSequence(root_seed).spawn(5)` 的独立实验 seed |

上述设计不使用 Python `hash()`，同一输入、seed 和参数可完全复现。空输入返回 shape 正确的空接收数组、有限信道系数和零噪声方差。

### 前导辅助信道估计

同步后，第 $l$ 个分支从检测起点提取 32 个接收前导复符号 $y_{p,l}$，并使用已知发送前导 $p$ 做最小二乘估计：

$$\hat h_l = \frac{\sum_k y_{p,l}[k]p^*[k]}{\sum_k |p[k]|^2}.$$

接收恢复路径只允许使用 $\hat h_l$。仿真生成的真实 $h_l$ 仅允许通过 `simulation_only_true_channel*` 字段保存，用于计算 $|\hat h_l-h_l|$，不得参与同步、均衡、MRC 或判决。后续测试必须通过依赖注入验证这一隔离约束。

### ZF 均衡

单分支 ZF 使用：

$$\hat x[k] = \frac{y[k]}{\hat h}.$$

ZF 可直接抵消平坦复增益，但当 $|\hat h|$ 很小时会显著增强噪声。设计要求对近零或非有限信道估计显式抛出异常，端到端管线转入安全失败路径，不允许产生未捕获的 `inf` 或 `NaN`。

### MMSE 均衡

标量 MMSE 使用线性域噪声方差：

$$\hat x[k] = \frac{\hat h^*}{|\hat h|^2 + N_0/E_s}y[k].$$

$N_0$ 和 $E_s$ 均为线性量，dB 值不会直接进入公式。正则项在深衰落时限制 ZF 的无界增益。阶段 C Mock 证明：当 $N_0=0$ 时 MMSE 严格退化为 ZF；只有使用 $N_0>0$ 的公式测试才能区分两种实现。对于本项目的标量平坦信道和零阈值 QPSK 硬判决，ZF 与 MMSE 输出之间可能只差正实数尺度，因此有限样本 BER/FER 可以相同；不能据此声称实现错误，也不能声称 MMSE 必然优于 ZF。

### 二分支 MRC 分集

双分支先分别相关并相加统计量：

$$C_{\mathrm{total}}[k] = \sum_l C_l[k],$$

再从统一起点估计各分支 $\hat h_l$，最后在复符号域执行普通等噪声 MRC：

$$\hat x[k] = \frac{\sum_l \hat h_l^* y_l[k]}{\sum_l |\hat h_l|^2}.$$

MRC 在 QPSK 解调前完成，不是分支硬判决投票。两个独立分支同时深衰落的概率低于单分支，因此产生分集增益。阶段 C Mock 确认等噪声分支的公共噪声方差在归一化权重中相消，因此普通 MRC 分母只包含 $\sum_l|\hat h_l|^2$；若未来加入正则项，必须使用独立名称，不能混称普通 MRC。分母过小时显式安全失败。CLI 为兼容给定调用示例，在双分支模式接受 `--equalizer none` 或 `--equalizer mmse`，但实际算法和 metrics 均明确标记为普通 `mrc`。

### 阶段 C Mock 后的设计修订

| Mock 发现 | 设计修订 |
|---|---|
| MMSE 在 $N_0=0$ 时与 ZF 相同 | MMSE 公式测试固定使用正的线性 $N_0$；端到端 BER 允许重合 |
| 普通等噪声 MRC 不需要额外正则项 | `mrc_combine()` 仅使用标准 MRC 分母；`noise_variance` 只作接口一致性校验/诊断 |
| LS 零能量、ZF/MRC 零分母必须拒绝 | LS、ZF、MMSE、MRC 接口统一引入默认 `epsilon=1e-12` 边界 |
| 公式测试不能证明完整接收机 | 阶段 E 前仍需保留 Rayleigh、联合同步、真值隔离和 Level 2 回归测试门槛 |

### Level 3 CLI 与参数

旧 AWGN 命令保持不变。新增参数：

```text
--channel awgn|rayleigh
--equalizer none|zf|mmse
--diversity-order 1|2
```

约束如下：

- AWGN：`equalizer=none` 且 `diversity_order=1`。
- Rayleigh 单分支：`equalizer=zf` 或 `equalizer=mmse`。
- Rayleigh 双分支：执行普通 MRC，接受 `equalizer=none` 或兼容 token `equalizer=mmse`，metrics 中记录 `equalizer=mrc`。
- 非法组合在进入 pipeline 前返回非零退出码和明确错误。

单次 Rayleigh CLI 只生成当前运行的指标、星座图和同步图；多 SNR、多 seed 扫描仅由独立的 `src/level3.py`（通过 `python -m src.level3`）执行，不影响 Level 2 的 20 秒约束。

### Level 3 指标

Rayleigh 模式保留原十个 Level 2 字段，并增加：

- `fading_model = flat_block_rayleigh`
- `equalizer`、`requested_equalizer`、`diversity_order`
- 单分支的信道估计实部、虚部、幅度和相位，或双分支对应列表
- `channel_estimation_error`、`noise_variance`、`sync_success`
- `failure_reason`
- 以 `simulation_only_true_channel*` 命名的真实系数诊断字段

所有持久化字段均转换为 Python 原生类型；内部接收符号、相关曲线和信道数组使用 `_` 前缀，不写入 JSON。

### Level 3 预期实验与判定边界

后续独立实验计划比较 AWGN、Rayleigh+ZF、Rayleigh+MMSE 和双分支 MRC，在 `[0, 4, 8, 12, 16, 20]` dB 上使用多个由 `SeedSequence` 派生的固定 seed。每点应报告平均 BER、FER、完整恢复率、同步成功率和平均信道估计误差。

阶段 A 不填写任何 Level 3 性能数值。预期双分支 MRC 能降低两个分支同时深衰落的风险，MMSE 在深衰落时应比无界 ZF 更稳定；这些仅是待检验假设，不是既定结果。不得用单个 seed 证明算法优劣，也不得把有限样本曲线称为理论曲线。

### Level 3 预期风险

| 风险 | 可能后果 | 设计缓解与后续验证 |
|---|---|---|
| 深衰落导致 $|\hat h|\approx0$ | ZF 噪声增强、inf/NaN 或整帧失败 | ZF/MRC 设置显式分母阈值；MMSE 使用线性正则项；Mock 验证安全失败 |
| 前导估计偏差 | 全帧相位/幅度补偿错误 | 无噪声 LS Mock、估计误差指标和多 seed 扫描 |
| 双分支起点不一致 | MRC 合并错位 | 每分支单独相关，合并相关统计量后使用统一起点 |
| 接收端误用真实 $h$ | 产生不可部署的乐观结果 | 真值仅诊断；依赖注入测试返回错误真值验证隔离 |
| 随机子流复用 | 改变数组长度会耦合衰落与噪声 | 使用 `SeedSequence.spawn()` 分离 prefix、fading 和各分支噪声 |
| Level 3 参数侵入 AWGN 默认路径 | 破坏公开测试和 20 秒限制 | AWGN 保留原分支和原 RNG；Level 3 仅由可选参数进入 |
| 单 seed 性能偶然性 | 对 ZF/MMSE/MRC 作不可靠结论 | 固定多 seed 平均；不对单次衰落断言优劣 |
| 实验扫描进入默认 CLI | 基础命令超时 | 独立 `src/level3.py`，默认 CLI 不运行 Level 3 扫描 |

### 适用边界与限制

- 当前信道在完整帧内恒定，不描述帧内时变衰落。
- 当前模型为窄带平坦衰落，不包含频率选择性多径、ISI 或均衡器抽头。
- 未建模载波频偏、采样频偏、相位噪声、信道估计反馈或重传。
- 只有一个帧样本和 5 个固定 seed/点，性能曲线具有有限样本不确定性，不能外推为严格理论性能。
- 三重复码和未保护帧头造成明显悬崖效应；Level 3 扩展不等同于工程无线标准实现。

## 修订记录

| 版本 | 日期 | 修订内容 | 触发来源 |
|---|---|---|---|
| v1.0 | 2026-06-24 | 初始设计文档，覆盖全部必需章节 | PRD + 公开测试分析 |
| v1.1 | 2026-06-24 | 确定前导序列（7 阶 LFSR m 序列）；补充 CRC-32 约定（zlib.crc32、bit→bytes MSB 优先、零长度处理）；修正 QPSK bit 到 I/Q 映射规则（b1→I, b0→Q）；更新 build_frame/parse_frame 签名；补充空输入行为 | Mock 测试 MT-001~011 结果 |
| v1.2 | 2026-06-24 | 补充实测结果表（0~12 dB）；更新预期结果为实测数据；确认同步在所有 SNR 下稳定 | 端到端测试 + CLI 实际运行 |
| v1.3 | 2026-06-24 | CRC 修复、FER 修正、前置符号 QPSK、帧校验、CLI nan/inf、BER 图零误码标注 | 最终审计修复 |
| v1.4 | 2026-06-24 | 理论曲线修正（仅保留 uncoded QPSK 参考，删除非精确重复码理论）；使用教师原始 Test.txt 重测 | 曲线修正 |
| v2.0 | 2026-06-24 | **BER：** 实现 `calculate_ber()`，共同长度逐 bit 比较 + 长度差计错；**CRC/FER：** 增加 `coded_length==3×original_length` 和 `len(descrambled)==original_length` 条件；CRC 仅对接收端 `descrambled` 计算；**帧解析：** 强化 preamble 校验、coded_length/crc 边界、padding 处理；**图表：** 删除非精确理论曲线，仅保留理想 uncoded QPSK 参考并明确标注；**种子：** 子流使用确定派生 seed；**文档：** 全部更新为 v2.0 | 最终修复 |
| v2.1 | 2026-06-24 | 修正 BER 图默认生成流程的过时描述；明确 UTF-8 严格解码异常在模块层抛出、在端到端管线层安全置空并继续输出失败指标 | 文档—实现一致性审计 |
| v2.2 | 2026-06-24 | 修正设计范围与实测结果表述；完善接收端长度、CRC 和 FER 判定流程；区分真实同步偏移与估计起点；收敛归一化互相关的性能表述；核对信道译码异常行为 | 最终文档一致性审计 |
| v3.0 | 2026-06-24 | 定义平坦块 Rayleigh、前导 LS 信道估计、ZF/MMSE、双分支联合同步、普通 MRC、CLI、指标、随机子流和预期风险；不含 Level 3 实验结果 | 阶段 A：Level 3 设计 |
| v3.1 | 2026-06-24 | 根据 4 项真实公式 Mock，明确 MMSE 的 $N_0>0$ 区分测试、普通 MRC 无正则项、统一 epsilon 失败边界及尚未验证的系统级风险 | 阶段 D：Mock 后设计修订 |
| v3.2 | 2026-06-24 | 实现全部 Level 3 生产代码：`rayleigh_flat_fading()`（平坦块 Rayleigh，SeedSequence 子流分离）、`estimate_flat_channel()`（前导 LS）、`zf_equalize()`/`mmse_equalize()`（标量均衡）、`mrc_combine()`（普通等噪声 MRC）、`synchronize_branches()`（多分支联合同步）；扩展 `run_pipeline()` 和 `main.py` CLI（`--channel`/`--equalizer`/`--diversity-order`）；创建 `src/level3.py` 独立实验脚本。AWGN 默认路径保留原随机流不变。修复 3 项实现问题：AWGN 前缀兼容性、MRC equalizer 字段记录、noise_variance 类型持久化 | 阶段 E：Level 3 完整实现 |
| v3.3 | 2026-06-24 | 完成 26 条 Level 3 专项测试（全部通过）；Level 2 回归 53+22=75 条全部通过。多 seed 实验（4 方案 × 6 SNR × 5 seed）确认：AWGN 8 dB 以上完全恢复；Rayleigh 单分支需 16 dB；双分支 MRC 在 12 dB 完全恢复（分集增益验证）；ZF 与 MMSE 标量硬判决 FER 相同（符合预期）；同步成功率全部 100%；MRC 平均 FER ≤ 单分支 ZF。更新实测结果与修订记录 | 阶段 F：测试与实验 |
