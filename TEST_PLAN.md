# TEST_PLAN.md — 无线通信基带仿真系统测试计划

## 测试目标与范围

本文档定义端到端无线通信基带仿真系统的测试策略，覆盖所有模块的单元测试、边界测试、异常测试、mock 集成测试和端到端验证。测试范围对齐 PRD 的功能需求、DESIGN.md 的模块接口设计、以及教师公开测试集 `public_tests/` 的覆盖范围。

**测试层级：**

1. **单元测试（UT）：** 逐模块验证核心函数在正常、边界和异常输入下的行为。
2. **Mock 测试（MT）：** 在无完整链路时，用可控假数据串联多个模块验证接口一致性与流程正确性。
3. **集成/端到端测试（IT）：** 完整 CLI 下的端到端验证，覆盖公开测试 TC-T-013 至 TC-T-020 的相关要求。

## 测试环境

- Python 3.11
- 依赖：`numpy`, `scipy`, `matplotlib`, `pytest`
- 运行命令：`pytest tests/ -q`（学生自测）、`pytest public_tests -q`（公开验收）
- 固定 seed 测试默认使用 `seed = 2026`
- 默认 SNR 12 dB，调制 qpsk，信道 awgn

---

## A. 单元测试

### A.1 源编码 (`src/source.py`)

| 编号 | 目标 | 输入 | 步骤 | 预期结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-SRC-001 | UTF-8 英文正常往返 | `"Hello World"` | `encode → decode` | 文本完全一致 | `decoded == input` | 低 |
| UT-SRC-002 | UTF-8 中文正常往返 | `"无线通信技术"` | `encode → decode` | 中文文本完全一致 | `decoded == input` | 低 |
| UT-SRC-003 | 中英文混合往返 | `"QPSK调制与AWGN信道"` | `encode → decode` | 混合文本完全一致 | `decoded == input` | 低 |
| UT-SRC-004 | 空文本 | `""` | `encode → decode` | 空字符串，bitstream 为空列表 | `decoded == ""` 且 `bits == []` | 低 |
| UT-SRC-005 | 单字符（ASCII） | `"A"` | `encode → decode` | 单字符恢复 | `decoded == "A"`，bitstream 长度 8 | 低 |
| UT-SRC-006 | 单字符（中文） | `"中"` | `encode → decode` | 单中文恢复（3 字节） | `decoded == "中"`，bitstream 长度 24 | 低 |
| UT-SRC-007 | 长文本（>1000 字符） | 中文长文本 2000 字符 | `encode → decode` | 长文本完全一致 | `decoded == input` | 低 |
| UT-SRC-008 | 非 8 倍数 bitstream 解码 | `[1,0,1,0,1]`（5 bit） | `source_decode` | 抛出异常（`ValueError`） | 函数抛出异常 | 低 |
| UT-SRC-009 | 编码输出长度是 8 的倍数 | `"test"` | `source_encode` | 返回 list 长度为 32 | `len(bits) % 8 == 0` | 低 |

### A.2 扰码 (`src/scramble.py`)

| 编号 | 目标 | 输入 | 步骤 | 预期结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-SCR-001 | 扰码+解扰正常往返 | 512 bit 随机序列, seed=2026 | `scramble → descramble` | 完全恢复原始 bit | `descrambled == input` | 低 |
| UT-SCR-002 | 同 seed 两次扰码输出一致 | 256 bit 随机序列, seed=2026 | `scramble` 两次（分别新建 rng） | 两次输出逐位相等 | `out1 == out2` | 低 |
| UT-SCR-003 | 不同 seed 输出不同 | 256 bit 随机序列, seed=2026 vs 2027 | 分别扰码 | 两输出不完全相同（高概率） | `out1 != out2`（至少 1 位不同） | 低 |
| UT-SCR-004 | 空 bitstream | `[]`, seed=2026 | `scramble → descramble` | 返回空列表 | `result == []` | 低 |
| UT-SCR-005 | 单 bit 扰码 | `[0]` 或 `[1]`, seed=2026 | `scramble → descramble` | 单 bit 可逆 | `descrambled == input` | 低 |
| UT-SCR-006 | 扰码改变原始数据 | 全 0 序列（128 bit）, seed=2026 | `scramble` | 输出不全为 0（高概率） | `sum(output) > 0` | 低 |

### A.3 信道编码 (`src/channel_coding.py`)

| 编号 | 目标 | 输入 | 步骤 | 期望结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-CC-001 | 编码长度三倍 | 400 bit | `channel_encode` | 输出长度 = 1200 | `len(output) == 3 * len(input)` | 低 |
| UT-CC-002 | 无噪声编解码往返 | 400 bit 随机序列 | `encode → decode` | 完全恢复 | `decoded == input` | 低 |
| UT-CC-003 | 单 bit 翻转可纠正（多数表决） | `[0,0,0, 1,1,1, 0,0,0]` 9 bit | 将每组第一个 bit 翻转后 `decode` | `[0,1,0]` | `decoded == expected` | 低 |
| UT-CC-004 | 两组中每组 2 位翻转仍可纠正 | `[0,0,0, 1,1,1]` 6 bit | 每组翻转 2 个 bit 后 `decode` | `[0,1]` | `decoded == expected` | 低 |
| UT-CC-005 | 空 bitstream | `[]` | `encode → decode` | 返回空列表 | `result == []` | 低 |
| UT-CC-006 | 长度非 3 倍数译码 | 7 bit `[1,1,1, 0,0,0, 1]` | `channel_decode` | 前 2 组正确，末 1 bit 按多数表决 | 前 2 组 `[1,0]`，剩余按实现约定处理 | 中 |

### A.4 帧结构 (`src/framing.py`)

| 编号 | 目标 | 输入 | 步骤 | 期望结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-FRM-001 | 正常帧封装与解析可逆 | 2400 bit 原始 payload（8 的倍数） | `build_frame → parse_frame` | 各字段一致，CRC 匹配 | `parsed.original_length == len(payload)`，CRC 验证通过 | 中 |
| UT-FRM-002 | 帧包含 Preamble 字段 | 800 bit payload | `build_frame` | 返回 dict/bitlist 含 preamble | preamble 存在于帧首 64 bit | 低 |
| UT-FRM-003 | 帧包含 Original Length 字段 | 800 bit payload | `build_frame → parse_frame` | parsed 中 `original_length == 800` | 长度数值正确 | 中 |
| UT-FRM-004 | 帧包含 Coded Length 字段 | 800 bit payload → 2400 coded | `build_frame → parse_frame` | parsed 中 `coded_length == 2400` | 编码长度正确 | 中 |
| UT-FRM-005 | 帧包含 CRC-32 字段 | 800 bit payload | `build_frame` | 帧结构含 32 bit CRC | CRC 字段存在（32 bit） | 低 |
| UT-FRM-006 | 奇数 bit 原始 payload | 255 bit payload | `build_frame → QPSK → parse_frame` (无噪声) | 通过 Coded Length 精确切分，恢复原始 255 bit | `len(recovered_payload) == 255` | 高 |
| UT-FRM-007 | 零长度 payload | 0 bit payload | `build_frame → parse_frame` | 帧仅含 header（无载荷），`original_length == 0` | `original_length == 0`, `coded_length == 0` | 低 |
| UT-FRM-008 | 帧总长度验证 | 已知 payload | `build_frame` | 帧总 bit = 64+32+32+CodedLen+32 | 帧长度公式成立 | 低 |

### A.5 QPSK 调制 (`src/modulation.py`)

| 编号 | 目标 | 输入 | 步骤 | 期望结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-MOD-001 | 星座象限映射正确 | `[0,0, 0,1, 1,1, 1,0]` | `qpsk_modulate` | 对应 I/Q 象限: (+,+), (-,+), (-,-), (+,-) | 各符号实部/虚部符号正确 | 低 |
| UT-MOD-002 | 单位平均功率 | 随机 512 bit | `qpsk_modulate` | 符号平均功率 ≈ 1.0 | `0.8 <= mean(abs(s)^2) <= 1.2` | 低 |
| UT-MOD-003 | 无噪声调制-解调往返 | 随机 512 bit（偶数） | `modulate → demodulate` | 完全恢复 | `decoded == input` | 低 |
| UT-MOD-004 | 奇数 bit 调制 | 255 bit 随机 | `qpsk_modulate` | 输出 128 符号（补 1 个 0） | `len(symbols) == 128` | 中 |
| UT-MOD-005 | 空 bitstream 调制 | `[]` | `qpsk_modulate` | 返回空符号列表 | `len(symbols) == 0` | 低 |
| UT-MOD-006 | 解调奇数符号 | 3 个符号 | `qpsk_demodulate` | 输出 6 bit | `len(bits) == 6` | 低 |
| UT-MOD-007 | 噪声下符号错误可检测 | 已知 bit + low SNR 符号 | `demodulate` 后与原始对比 | BER > 0 | BER 非零但合理 | 低 |
| UT-MOD-008 | 16-QAM/BPSK 参数校验（扩展） | `--mod 16qam` | 若支持→正确映射；若不支持→报错 | 明确行为（报错或正确映射） | 低 |

### A.6 AWGN 信道 (`src/channel.py`)

| 编号 | 目标 | 输入 | 步骤 | 期望结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-CH-001 | 同 seed 输出可复现 | 4 符号, SNR=12, seed=2026 | 两次 `awgn` | 两次输出完全一致 | `allclose(out1, out2)` | 低 |
| UT-CH-002 | 不同 seed 噪声不同 | 4 符号, SNR=12, seed=2026 vs 2027 | 对比两次输出 | 输出不完全相同 | `not allclose` | 低 |
| UT-CH-003 | 高 SNR 噪声功率小 | 4 符号, SNR=40 dB | `awgn` | 输出接近输入 | `allclose(out, in, atol=0.05)` | 低 |
| UT-CH-004 | SNR=0 dB 噪声功率与信号相当 | 4 符号, SNR=0 dB | `awgn` | 输出与输入差异明显 | `not allclose(out, in, rtol=0.2)` | 低 |
| UT-CH-005 | 空符号序列 | `[]`, SNR=12 | `awgn` | 返回空列表 | `result == []` | 低 |
| UT-CH-006 | 负 SNR 不崩溃 | 4 符号, SNR=-5 dB | `awgn` | 正常返回（噪声功率大于信号） | 程序不崩溃，返回 4 符号 | 低 |

### A.7 同步 (`src/synchronization.py`)

| 编号 | 目标 | 输入 | 步骤 | 期望结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| UT-SYNC-001 | 零偏移同步 | 帧符号序列（偏移 0） | `synchronize` | 返回 `0` | `start == 0` | 中 |
| UT-SYNC-002 | 25 符号偏移同步 | 25 前缀符号 + 帧符号 | `synchronize` | 返回 `25` | `abs(start - 25) <= 1` | 高 |
| UT-SYNC-003 | 128 符号偏移同步（边界） | 128 前缀 + 帧符号, SNR=12 dB | `synchronize` | 返回约 `128` | `abs(start - 128) <= 1` | 高 |
| UT-SYNC-004 | 无前导序列 | 纯随机符号 | `synchronize` | 相关峰明显低于有前导情况 | 相关峰值 < 0.5 | 中 |
| UT-SYNC-005 | 12 dB AWGN 下 25 偏移 | 同 UT-SYNC-002 + AWGN 12 dB | `synchronize` | 仍能准确检测 | `abs(start - 25) <= 1` | 高 |
| UT-SYNC-006 | 0 dB AWGN 下偏移检测 | 25 前缀 + 帧, SNR=0 dB | `synchronize` | 可能出现偏差（记录行为） | 函数不崩溃，返回有效索引 | 高 |

---

## B. Mock 测试

Mock 测试在缺少完整链路实现时，使用可控假数据和跨模块调用验证接口一致性和数据流正确性。

### MT-001：UTF-8 完整往返（源编码 → 扰码 → 解扰 → 源解码）

| 属性 | 内容 |
|---|---|
| **编号** | MT-001 |
| **对应公开测试** | TC-T-004, TC-T-007 |
| **覆盖模块** | `src/source.py`, `src/scramble.py` |
| **风险等级** | 中 |
| **目标** | 验证 UTF-8 文本经源编码和扰码/解扰后完整恢复 |
| **输入** | `"无线通信技术课程要求学生理解调制、编码、信道和接收机处理。"` |
| **步骤** | 1. `source_encode(text)` → 原始 bitstream；2. `scramble(原始 bits, seed=2026)` → 扰码 bits；3. `descramble(扰码 bits, seed=2026)` → 解扰 bits；4. `source_decode(解扰 bits)` → 恢复文本 |
| **预期结果** | 恢复文本与原始文本完全一致；原始 bitstream 长度 = 解扰后 bitstream 长度 |
| **通过标准** | `recovered_text == input_text` 且 `len(original_bits) == len(descrambled_bits)` |

### MT-002：奇数 bit 帧与 QPSK padding

| 属性 | 内容 |
|---|---|
| **编号** | MT-002 |
| **对应公开测试** | TC-T-005, TC-T-006, TC-T-011 |
| **覆盖模块** | `src/framing.py`, `src/modulation.py`, `src/channel_coding.py`, `src/scramble.py` |
| **风险等级** | 高 |
| **目标** | 验证奇数长度原始 payload 经编码、组帧、QPSK 调制和解调后，通过 Coded Length 字段精确恢复 |
| **输入** | 255 bit 随机原始 payload（奇数长度） |
| **步骤** | 1. `scramble(原始payload, seed=2026)` → 扰码 bits；2. `channel_encode(扰码bits)` → 编码 bits（765 bit）；3. `build_frame(原始payload, 编码bits)` → 帧 bits（64+32+32+765+32=925 bit）；4. `qpsk_modulate(帧bits)` → 463 符号（自动补 1 个 0）；5. 无噪声 `qpsk_demodulate(symbols)` → 926 bit（含补零）；6. `parse_frame(demod_bits, preamble)` → 帧 dict；7. 提取 `coded_payload`（765 bit）；8. `channel_decode(coded_payload)` → 恢复扰码 bits（255 bit）；9. `descramble(恢复扰码bits, seed=2026)` → 原始 bits |
| **预期结果** | parse_frame 中 `original_length == 255`, `coded_length == 765`；最终恢复原始 255 bit |
| **通过标准** | `recovered_bits[:255] == original_payload[:255]` 且 `len(recovered_bits) == 255` |

### MT-003：25 符号偏移同步

| 属性 | 内容 |
|---|---|
| **编号** | MT-003 |
| **对应公开测试** | TC-T-013 |
| **覆盖模块** | `src/synchronization.py`, `src/modulation.py`, `src/framing.py`, `src/channel.py` |
| **风险等级** | 高 |
| **目标** | 验证同步模块在 AWGN 信道下检测 25 符号偏移 |
| **输入** | 已知帧 bitstream，seed=2026，SNR=12 dB |
| **步骤** | 1. `build_frame(payload, coded_payload)` → 帧 bits；2. `qpsk_modulate(帧bits)` → 帧符号；3. 生成 25 个随机 QPSK 前缀符号（固定 seed）；4. 拼接前缀 + 帧符号 → 发送符号；5. `awgn(发送符号, SNR=12, seed=2026)` → 接收符号；6. `synchronize(接收符号, 前导模板)` → start_index |
| **预期结果** | 同步峰值位于索引 25 附近（±1 符号） |
| **通过标准** | `abs(start_index - 25) <= 1` |

### MT-004：CRC 与长度字段验证

| 属性 | 内容 |
|---|---|
| **编号** | MT-004 |
| **对应公开测试** | TC-T-005, TC-T-006, TC-T-014（checksum_pass 字段） |
| **覆盖模块** | `src/framing.py` |
| **风险等级** | 高 |
| **目标** | 验证 CRC 计算与校验、长度字段在无噪声下的正确性 |
| **输入** | 800 bit 原始 payload, seed=2026 |
| **步骤** | 1. 计算原始 payload 的 CRC-32（发送端）；2. `build_frame(原始payload, coded_payload)` → 帧；3. `parse_frame(帧bits, preamble)` → 解析帧；4. 提取 CRC_received，对解析出的原始 payload 重新计算 CRC；5. 验证 `original_length` 和 `coded_length` 值 |
| **预期结果** | CRC 匹配；`original_length == 800`；`coded_length == 2400` |
| **通过标准** | `crc_computed == crc_received` 且两个长度字段数值正确 |

### MT-005：12 dB 中文文本端到端恢复

| 属性 | 内容 |
|---|---|
| **编号** | MT-005 |
| **对应公开测试** | TC-T-015 |
| **覆盖模块** | 全部 |
| **风险等级** | 高 |
| **目标** | 端到端验证：中文文本经完整链路后在 12 dB AWGN 下完全恢复 |
| **输入** | `Test.txt` 内容（公开测试 conftest.py 中的 `SAMPLE_TEXT`）；SNR=12 dB, seed=2026, mod=qpsk, channel=awgn |
| **步骤** | 1. 读取 `Test.txt`；2. Source Encode → Scramble → Channel Encode → Frame Build → QPSK Modulate → Add Offset(0~128) → AWGN → Synchronization → QPSK Demodulate → Frame Parse → Channel Decode → Descramble → Source Decode；3. 写入 `received.txt`；4. 计算指标 → 写入 `metrics.json` |
| **预期结果** | `received.txt` 与 `Test.txt` 字符级完全一致；`metrics.json` 中 `text_match_rate == 1.0`, `checksum_pass == true`, `fer == 0.0`, `ber == 0.0` |
| **通过标准** | `read_text("results/received.txt") == read_text("Test.txt")` |

### MT-006：CRC 故意损坏检测

| 属性 | 内容 |
|---|---|
| **编号** | MT-006 |
| **风险等级** | 中 |
| **目标** | 验证接收端能检测 CRC 失败（帧载荷 bit 被翻转后 CRC 不匹配） |
| **步骤** | 1. 正常组帧；2. 手动翻转帧中 Coded Payload 的 1 个 bit；3. 解析帧并重算 CRC |
| **预期结果** | `checksum_pass == false`, `fer == 1.0` |
| **通过标准** | 重算的 CRC 与帧中 CRC 不一致 |

### MT-007：长度字段噪声破坏检测

| 属性 | 内容 |
|---|---|
| **编号** | MT-007 |
| **风险等级** | 中 |
| **目标** | 验证当长度字段受噪声破坏时帧解析的失效模式 |
| **步骤** | 1. 正常组帧（payload = 800 bit）；2. 手动翻转 Original Length 字段 1 bit → 例如 800 变为 288；3. 解析帧 |
| **预期结果** | 帧解析可完成，但 `original_length` 值异常，导致后续源解码可能产生长度不符的 bitstream |
| **通过标准** | `parse_frame` 不崩溃；CRC 大概率失败（长度错误导致提取的载荷与预期不同） |

---

## C. 集成 / 端到端测试

| 编号 | 目标 | 对应公开测试 | 步骤 | 预期结果 | 通过标准 | 风险 |
|---|---|---|---|---|---|---|
| IT-001 | 12 dB 端到端文本完全一致 | TC-T-015 | CLI `--snr 12 --seed 2026` | `received.txt` 与 `Test.txt` 完全一致 | 文本逐字符匹配 | 高 |
| IT-002 | CLI 参数校验（非法值） | TC-T-017 | `--mod bpsk`（若仅支持 qpsk）, `--channel rayleigh`（若仅支持 awgn） | 报错退出，非崩溃 | returncode ≠ 0，stderr 含提示信息 | 低 |
| IT-003 | metrics.json 字段完整 | TC-T-014 | CLI 正常运行 | 10 个必需字段全部存在 | 无 missing fields | 中 |
| IT-004 | 图表文件生成 | TC-T-016 | CLI 正常运行 | 至少 2 个非空 PNG 文件 | `constellation.png`, `ber_curve.png`, `sync_peak.png` 中 ≥2 个存在且 >0 byte | 中 |
| IT-005 | 非交互运行 | TC-T-017 | CLI 全默认参数 | 程序无 `input()` 调用，20s 内完成 | returncode == 0，stdout 无交互提示 | 低 |
| IT-006 | 低 SNR 不崩溃 | TC-T-017 | `--snr -5` | 正常退出，输出指标（BER 可能高） | returncode == 0，`metrics.json` 存在 | 中 |
| IT-007 | 不同 seed 输出可复现 | TC-T-012 | `--seed 2026` 运行两次 | `received.txt` 和 `metrics.json` 内容完全一致 | 文件摘要/文本一致 | 中 |
| IT-008 | 无直接文件复制 | TC-T-020 | 代码审计 | `shutil.copy`、`copyfile` 等不存在于 `src/` 和 `main.py` | 搜索结果为 0 | 低 |

---

## D. 边界覆盖清单

### D.1 文本边界

| 边界 | 对应单元测试 | 风险 |
|---|---|---|
| 空文本（0 字符） | UT-SRC-004 | 低 |
| 单字符 ASCII | UT-SRC-005 | 低 |
| 单字符中文（3 字节） | UT-SRC-006 | 低 |
| 纯英文 | UT-SRC-001 | 低 |
| 纯中文 | UT-SRC-002 | 低 |
| 中英文混合 | UT-SRC-003 | 低 |
| 长文本（>2000 字符） | UT-SRC-007 | 低 |
| 含换行符文本 | UT-SRC-001（变体） | 低 |

### D.2 Bitstream 边界

| 边界 | 对应测试 | 风险 |
|---|---|---|
| 0 bit | UT-SRC-004, UT-SCR-004, UT-CC-005, UT-FRM-007 | 低 |
| 1 bit | UT-SCR-005, UT-CC-006 | 中 |
| 奇数 bit（非 2 的倍数） | UT-MOD-004, UT-FRM-006, MT-002 | 高 |
| 非 8 倍数 bitstream 解码 | UT-SRC-008 | 低 |
| 非 3 倍数 bitstream 信道译码 | UT-CC-006 | 中 |

### D.3 扰码参数边界

| 边界 | 对应测试 | 风险 |
|---|---|---|
| seed=2026（默认） | UT-SCR-001, UT-SCR-002 | 低 |
| seed=0 | UT-SCR-003（变体） | 低 |
| seed=-1（非法值） | 实现时考虑 | 低 |
| 同 seed 两次调用 | UT-SCR-002 | 低 |
| 不同 seed 不同输出 | UT-SCR-003 | 低 |

### D.4 SNR 边界

| 边界 | 对应测试 | 风险 |
|---|---|---|
| SNR = 12 dB（基准） | MT-005, IT-001 | 中 |
| SNR = 0 dB | UT-CH-004, UT-SYNC-006 | 高 |
| SNR = 4 dB | IT-006（变体） | 高 |
| SNR = 8 dB | IT-006（变体） | 中 |
| SNR = 40 dB（近无噪声） | UT-CH-003 | 低 |
| SNR = -5 dB（负值） | UT-CH-006 | 中 |

### D.5 同步偏移边界

| 边界 | 对应测试 | 风险 |
|---|---|---|
| offset = 0 | UT-SYNC-001 | 中 |
| offset = 25 | UT-SYNC-002, MT-003 | 高 |
| offset = 128（最大） | UT-SYNC-003 | 高 |
| 无前导（纯噪声前缀） | UT-SYNC-004 | 中 |

### D.6 CLI 异常边界

| 边界 | 对应测试 | 风险 |
|---|---|---|
| `--input` 文件不存在 | 设计文档异常处理 | 低 |
| `--output` 目录不存在 | IT-005（自动创建） | 低 |
| `--mod` 非法值 | IT-002 | 低 |
| `--channel` 非法值 | IT-002 | 低 |
| `--snr` 非数值 | argparse 自动 | 低 |
| `--seed` 非整数 | argparse 自动 | 低 |
| `results/` 目录已存在 | 正常运行（不冲突） | 低 |

---

## E. 性能要求

| 指标 | 约束 | 验证方式 |
|---|---|---|
| 单次 CLI 运行时间 | < 20 秒 | `time python main.py ...` |
| BER 曲线扫描点 | 7 点：`[0, 2, 4, 6, 8, 10, 12]` dB | 代码审计 |
| 无蒙特卡洛迭代 | 每个 SNR 点单次运行 | 代码审计 |
| Matplotlib 后端 | `Agg`（无 GUI），避免弹出窗口和交互 | CI 中由 `test_tc_t_017` 验证 |

---

## F. Mock 测试执行策略

Mock 测试在代码实现前执行，使用最小化的函数 stub 和可控假数据验证接口设计。

1. **阶段 1（源编码 + 扰码）：** 实现 `source_encode/decode` 和 `scramble/descramble` stub，执行 MT-001。
2. **阶段 2（帧结构 + 信道编码 + QPSK）：** 实现 `build_frame/parse_frame`、`channel_encode/decode`、`qpsk_modulate/demodulate` stub，执行 MT-002 和 MT-004。
3. **阶段 3（同步 + AWGN）：** 实现 `awgn` 和 `synchronize` stub，执行 MT-003。
4. **阶段 4（全链路）：** 实现 `pipeline.py` 和 `main.py`，执行 MT-005 和 MT-006。
5. **阶段 5（验证）：** 运行 `pytest public_tests -q`，检查 TC-T-001 至 TC-T-020。

---

## G. 可追踪性矩阵

### PRD 需求 → DESIGN 章节 → 测试编号

| PRD 需求 | DESIGN 章节 | UT | MT | IT | 公开测试 |
|---|---|---|---|---|---|
| 源编码 UTF-8 ↔ bitstream | 源编码 | UT-SRC-001~009 | MT-001, MT-005 | IT-001 | TC-T-004 |
| 扰码/解扰可逆 | 扰码 | UT-SCR-001~006 | MT-001, MT-005 | IT-001 | TC-T-007 |
| 信道编码（抗噪） | 信道编码 | UT-CC-001~006 | MT-002, MT-005 | IT-001 | TC-T-008 |
| 帧结构（前导+长度+载荷+校验） | 帧结构 | UT-FRM-001~008 | MT-002, MT-004 | IT-001 | TC-T-005, TC-T-006 |
| QPSK 调制/解调 | QPSK 调制 | UT-MOD-001~008 | MT-002, MT-005 | IT-001 | TC-T-009, TC-T-010 |
| 奇数 bit padding | QPSK 调制, 帧结构 | UT-MOD-004, UT-FRM-006 | MT-002 | — | TC-T-011 |
| AWGN 可配置 SNR | AWGN 信道 | UT-CH-001~006 | MT-003, MT-005 | IT-001, IT-006 | TC-T-012 |
| 同步检测帧起点 | 同步 | UT-SYNC-001~006 | MT-003 | IT-001 | TC-T-013 |
| metrics.json 生成 | 指标 | — | MT-005 | IT-003 | TC-T-014 |
| 端到端文本恢复 | 接收端流程 | — | MT-005 | IT-001 | TC-T-015 |
| 图表生成 | 图表 | — | — | IT-004 | TC-T-016 |
| CLI 非交互 | CLI 与输出 | — | — | IT-002, IT-005 | TC-T-017 |
| 无直接复制 | — | — | — | IT-008 | TC-T-020 |
| CRC 校验 | 帧结构, 指标 | — | MT-004, MT-006 | IT-003 | TC-T-014 |
| 24 dB→12 dB 可复现 | AWGN 信道 | UT-CH-001 | — | IT-007 | TC-T-012 |
| 单次 < 20s | 性能要求 | — | — | IT-005 | TC-T-017 |
| 低 SNR 不崩溃 | 异常处理 | UT-CH-006 | — | IT-006 | TC-T-017 |

### 公开测试覆盖确认

| 公开测试 ID | 测试内容 | 本文档覆盖的测试编号 |
|---|---|---|
| TC-T-001 | 项目结构和文档完整 | 由工程流程保证（TEST_PLAN.md 自身即为必需文档之一） |
| TC-T-002 | DESIGN.md 覆盖系统链路关键词 | 由 DESIGN.md 保证 |
| TC-T-003 | MOCK_TEST_REPORT 含修订记录 | 由后续 MOCK_TEST_REPORT.md 保证 |
| TC-T-004 | UTF-8 编解码可逆 | UT-SRC-001~009, MT-001 |
| TC-T-005 | 帧封装含必需字段 | UT-FRM-001~005, MT-002 |
| TC-T-006 | 帧封装与解析可逆 | UT-FRM-001, UT-FRM-006, MT-002 |
| TC-T-007 | 扰码可逆 | UT-SCR-001~006, MT-001 |
| TC-T-008 | 信道编码无噪声可逆 | UT-CC-001~006 |
| TC-T-009 | QPSK 星座象限 + 单位功率 | UT-MOD-001, UT-MOD-002 |
| TC-T-010 | QPSK 无噪声解调 | UT-MOD-003 |
| TC-T-011 | 奇数 bit 补零与恢复 | UT-FRM-006, UT-MOD-004, MT-002 |
| TC-T-012 | AWGN 固定 seed 可复现 | UT-CH-001, UT-CH-002 |
| TC-T-013 | 同步检测 25 符号偏移 | UT-SYNC-002, UT-SYNC-005, MT-003 |
| TC-T-014 | metrics.json 必需字段 | MT-005, IT-003 |
| TC-T-015 | 12 dB 端到端文本一致 | MT-005, IT-001 |
| TC-T-016 | 生成至少两张图 | IT-004 |
| TC-T-017 | CLI 非交互 20s 内完成 | IT-002, IT-005, IT-006 |
| TC-T-018 | AI_LOG 记录 AI 辅助 | 由后续 AI_LOG.md 保证 |
| TC-T-019 | 报告/设计解释结果 | 由 DESIGN.md 和 MOCK_TEST_REPORT.md 保证 |
| TC-T-020 | 无直接文件复制 | IT-008 |

---

## H. Level 3 高级模块测试计划

本阶段只定义测试，不创建 Level 3 生产模块或完整专项测试文件。计划测试统一使用固定 seed，不修改 `public_tests/`，并将 AWGN 默认链路作为不可回归基线。

### H.1 单元测试

| 编号 | 输入 | 步骤 | 预期结果 | 通过标准 |
|---|---|---|---|---|
| L3-UT-001 | 相同 QPSK symbols、SNR、seed、双分支 | 两次调用 Rayleigh 信道 | 接收数组、$h_l$、$N_0$ 完全复现 | `np.array_equal` 且方差相等 |
| L3-UT-002 | 相同 symbols、不同 seed | 分别生成 Rayleigh 信道 | 信道系数不同 | 两次 `true_channel` 不相等 |
| L3-UT-003 | 空 symbols、双分支 | 调用 Rayleigh 信道 | 无除零或 NaN | shape=`(2,0)`，$h_l$ 有限，$N_0=0$ |
| L3-UT-004 | 1000 个独立 seed | 收集 $h$ 并计算 $|h|^2$ 均值 | $E[|h|^2]\approx1$ | 绝对误差 ≤0.10 |
| L3-UT-005 | 无噪声 $y=hx$，$h=0.35-0.8j$ | 执行 ZF | 恢复原复符号 | `np.allclose(output,x)` |
| L3-UT-006 | 固定 $y,h,N_0,E_s$ | 执行 MMSE 并手算公式 | 两者一致且一般不等于 ZF 数值 | `np.allclose` |
| L3-UT-007 | 无噪声 $y_p=hp$ | 执行 LS 估计 | $\hat h=h$ | 误差 ≤$10^{-12}$ |
| L3-UT-008 | 前导长度不等、空前导、零能量 | 调用 LS 估计 | 明确拒绝 | 分别抛出 `ValueError` |
| L3-UT-009 | 固定双分支 $y_l,h_l$ | 执行 MRC 并手算公式 | 两者一致 | `np.allclose` |
| L3-UT-010 | 无噪声双分支 $y_l=h_lx$ | MRC 合并 | 恢复原复符号 | `np.allclose(output,x)` |
| L3-UT-011 | $\hat h=0$、MRC 分母为 0 | 调用 ZF/MMSE/MRC | 无未捕获 NaN/inf | ZF/MRC 明确抛错；MMSE 输出有限或明确抛错 |
| L3-UT-012 | 两分支含相同起点前导 | 分支相关后求和取峰值 | 得到统一真实起点 | 检测索引等于前缀长度 |

### H.2 最小 Mock 测试

Mock 只允许在测试文件中定义局部数学原型，不创建完整 Rayleigh pipeline。

| 编号 | 输入 | 步骤 | 预期结果 | 通过标准 |
|---|---|---|---|---|
| L3-MT-001 | QPSK symbols、已知非零 $h$ | 构造无噪声 $y=hx$；用最小 ZF/MMSE 原型恢复 | ZF 恢复 $x$；MMSE 与手算式一致 | 复符号数值误差 ≤$10^{-12}$ |
| L3-MT-002 | 已知前导 $p$、固定 $h$ | 构造 $y_p=hp$；最小 LS 原型估计 | $\hat h=h$ | 估计误差 ≤$10^{-12}$ |
| L3-MT-003 | 两个独立 $h_l$、共同 $x$ | 构造 $y_l=h_lx$；最小 MRC 原型合并 | 恢复 $x$ | 数值误差 ≤$10^{-12}$ |
| L3-MT-004 | $h=0$ 或全部 $h_l=0$ | 调用原型边界检查 | 安全拒绝 | 明确异常，不产生 NaN/inf |

### H.3 Level 2 回归测试

| 编号 | 输入 | 步骤 | 预期结果 | 通过标准 |
|---|---|---|---|---|
| L3-REG-001 | 现有 `tests/` | `pytest tests -q` | 原测试不退化 | 回退基线 53 条和后续新增测试全部通过 |
| L3-REG-002 | 教师 `public_tests/` | `pytest public_tests -q` | 公开验收不退化 | 22/22 通过；不修改公开测试 |
| L3-REG-003 | 原始 `Test.txt`、12 dB、seed=2026 | 运行统一 AWGN CLI | 行为与 Level 2 相同 | BER=0、FER=0、match=1、CRC=true、耗时<20s |
| L3-REG-004 | 旧 `run_pipeline` 调用与显式默认参数 | 分别运行并比较 | 输出与关键 metrics 一致 | 输出字节和字段值相等 |

### H.4 Level 3 端到端与接口测试

| 编号 | 输入 | 步骤 | 预期结果 | 通过标准 |
|---|---|---|---|---|
| L3-IT-001 | Rayleigh、40 dB、ZF、短中文 | 完整单分支 pipeline | 文本恢复 | CRC=true、FER=0、文本一致 |
| L3-IT-002 | Rayleigh、40 dB、MMSE、短中文 | 完整单分支 pipeline | 文本恢复 | CRC=true、FER=0、文本一致 |
| L3-IT-003 | Rayleigh、40 dB、双分支 MRC | 联合同步、估计、合并、接收 | 文本恢复 | `equalizer=mrc`、CRC=true |
| L3-IT-004 | 中英文和 emoji 混合 | 分别运行 Rayleigh 模式 | UTF-8 正常运行 | 恢复文本一致 |
| L3-IT-005 | Rayleigh、0 dB | 运行完整 pipeline | 不崩溃并记录失败 | BER/FER/CRC 为合法诊断值 |
| L3-IT-006 | 单分支/双分支 Rayleigh | 保存 metrics JSON | 新字段完整且原字段保留 | JSON 可解析、无 NumPy 标量 |
| L3-IT-007 | 相同输入、参数和 seed | 两次端到端运行 | 可复现 | 全部持久化字段相等 |
| L3-IT-008 | 物理信道与故意错误的诊断 true h | 依赖注入运行接收端 | 仍依靠前导估计恢复 | CRC=true 且估计误差显著非零 |
| L3-IT-009 | AWGN+ZF、Rayleigh 单分支+none、双分支+ZF | 运行 CLI | 非法组合被拒绝 | 非零退出码和明确错误文本 |

### H.5 多 seed 性能实验

计划比较 AWGN、Rayleigh+ZF、Rayleigh+MMSE 和双分支 MRC。SNR 使用 `[0,4,8,12,16,20]` dB，每点至少 5 个由 `SeedSequence` 派生的固定 seed，统计平均 BER、FER、完整恢复率、同步成功率和平均信道估计误差。

性能验收不允许使用单次随机试验。预期 MRC 平均 FER/BER 不高于单分支方案；若不满足，应检查模型、估计、SNR 和合并公式，不得事后调整 seed 或阈值。ZF 与 MMSE 在标量平坦信道硬判决下允许出现相同 BER，但公式级单元测试必须证明实现不同。

---

## 测试状态

| 状态 | 含义 |
|---|---|
| ⬜ 待实现 | 测试用例已设计，代码实现后可运行 |
| 🔄 进行中 | 正在调试 |
| ✅ 通过 | 全部断言通过 |
| ❌ 失败 | 部分断言失败 |
| ⚠️ 阻塞 | 依赖未完成的模块 |

当前 Level 2 基线已复核为 53 条自有自动化测试和 22 条公开测试。Level 3 测试已全部实现并通过。

- **自有 Level 2 测试 53 条：** ✅ 全部通过（`tests/test_mock.py` + `tests/test_e2e.py`）
- **自有 Level 3 测试 26 条：** ✅ 全部通过（`tests/test_level3.py`）
- **公开测试 22 条：** ✅ 全部通过（`public_tests/`）
- **合计 101 条：** ✅ 全部通过

---

## 修订记录

| 版本 | 日期 | 修订内容 | 触发来源 |
|---|---|---|---|
| v1.0 | 2026-06-24 | 初始测试计划，覆盖单元测试 49 条、mock 测试 7 条、集成测试 8 条 | PRD + DESIGN.md + public_tests 分析 |
| v1.1 | 2026-06-24 | 更新测试状态为全部通过；补充最终审计结果 | 最终提交前审计 |
| v2.0 | 2026-06-24 | 增加 Level 3 单元、最小 Mock、Level 2 回归、端到端、接口和多 seed 性能测试计划 | Level 3 测试计划 |
