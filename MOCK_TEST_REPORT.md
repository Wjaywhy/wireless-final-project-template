# MOCK_TEST_REPORT.md — Mock 测试报告

## 概述

本文档记录 Mock 验证阶段的测试执行结果、发现的问题、修复内容以及对 DESIGN.md 的修订。

测试日期：2026-06-24
测试范围：核心模块单元与组合测试（不含 CLI、绘图、BER 扫描）

## 测试环境

- Python 3.13.5
- numpy, scipy, pytest
- Windows 11
- 测试命令：`pytest tests/test_mock.py -v`

## 测试结果汇总

| 编号 | 测试名称 | 结果 | 备注 |
|---|---|---|---|
| MT-001 | UTF-8 中文文本无噪声往返 | ✅ 通过 | |
| MT-002 | 255 bit 奇数载荷经编码、帧封装、QPSK 后完整恢复 | ✅ 通过 | 修正后通过 |
| MT-003 | 25 符号偏移、12 dB AWGN 下同步误差 ≤1 | ✅ 通过 | |
| MT-004 | CRC、Original Length、Coded Length 正确解析 | ✅ 通过 | |
| MT-005 | 中文文本在 12 dB 下完整链路恢复 | ✅ 通过 | 修正后通过 |
| MT-006 | 前导序列自相关验证 | ✅ 通过 | 测试方法修正后通过 |
| MT-007 | 扰码 seed 可复现 | ✅ 通过 | |
| MT-008 | AWGN seed 可复现 | ✅ 通过 | |
| MT-009 | 空输入处理 | ✅ 通过 | 修正后通过 |
| MT-010 | 三重复码单 bit 纠错 | ✅ 通过 | |
| MT-011 | QPSK 单位平均功率 | ✅ 通过 | |

**总计：11 通过 / 0 失败**

---

## 各测试详情

### MT-001：UTF-8 中文文本无噪声往返

- **输入：** `"无线通信技术课程要求学生理解调制、编码、信道和接收机处理。"`
- **预期：** source_encode → scramble → descramble → source_decode 后文本完全一致
- **实际：** 文本完全一致，bitstream 长度 552 bit（69 字节 × 8）
- **通过：** ✅

### MT-002：255 bit 奇数载荷经编码、帧封装、QPSK 后完整恢复

- **输入：** 255 bit 随机载荷（seed=2030）
- **步骤：** scramble(255) → channel_encode(765) → build_frame(925 bit 奇数) → qpsk_modulate(463 符号) → qpsk_demodulate(926 bit) → parse_frame → channel_decode(255) → descramble(255)
- **预期：** 恢复 255 bit 与原始完全一致，Coded Length=765 正确截断补零
- **实际：** 完全一致，`original_length=255`, `coded_length=765`
- **通过：** ✅

### MT-003：25 符号偏移、12 dB AWGN 下同步误差 ≤1

- **输入：** 中文文本 `"无线通信测试同步"`，25 个随机前缀符号，SNR=12 dB
- **步骤：** 构建完整帧 → QPSK → 添加 25 符号前缀 → AWGN(12dB) → synchronize
- **预期：** 同步偏移检测在 25±1 符号内
- **实际：** `start=25`，精确命中
- **通过：** ✅

### MT-004：CRC、Original Length、Coded Length 正确解析

- **输入：** 800 bit 随机载荷
- **步骤：** build_frame(original=800, coded=2400) → parse_frame → 验证字段 + CRC 校验 + CRC 损坏检测
- **预期：** 长度字段正确，CRC 校验通过，CRC bit 翻转后检测到不匹配
- **实际：** 所有断言通过
  - `original_length=800`, `coded_length=2400`
  - CRC 匹配（原始 payload 计算值与帧中 CRC 一致）
  - CRC bit 翻转后不匹配被正确检测
  - 仅翻转 coded payload bit 时 CRC 不变（因 CRC 作用于 original payload）
- **通过：** ✅

### MT-005：中文文本在 12 dB 下完整链路恢复

- **输入：** 包含通信术语的中文文本（82 字符，246 字节）
- **步骤：** source_encode → scramble → channel_encode → build_frame → QPSK → 25 符号偏移 → AWGN(12dB) → synchronize → QPSK demod → parse_frame → channel_decode → descramble → source_decode
- **预期：** 恢复文本与原始完全一致，CRC 通过
- **实际：** 文本完全一致，CRC 校验通过
- **通过：** ✅

### MT-006：前导序列自相关验证

- **输入：** 64 bit LFSR 前导（7 阶 m 序列，本原多项式 x⁷+x⁶+1，初态 0b1010111）
- **方法：** 将前导嵌入随机符号序列中，滑动窗口互相关检测峰值
- **预期：** 峰值位于正确偏移位置，旁瓣显著低于主峰
- **实际：** 峰值在嵌入位置（index=50），峰值 > 0.95；所有旁瓣 < 峰值的 65%
- **通过：** ✅

### MT-007：扰码 seed 可复现

- **输入：** 256 bit 随机序列，seed=2026
- **预期：** 两次 scramble 输出逐位相同
- **实际：** 完全一致
- **通过：** ✅

### MT-008：AWGN seed 可复现

- **输入：** 4 个 QPSK 符号，SNR=12 dB，seed=2026
- **预期：** 两次 awgn 输出数值完全相同
- **实际：** `np.allclose` 通过
- **通过：** ✅

### MT-009：空输入处理

- **输入：** 空文本、空 bitstream、空符号序列
- **预期：** 所有函数不崩溃
- **实际：** 所有函数正常返回空列表/空字符串
- **通过：** ✅

### MT-010：三重复码单 bit 纠错

- **输入：** `[1,0,1,1,0,0]` → 编码 → 每组翻转 1 bit → 译码
- **预期：** 多数表决纠正所有单 bit 错误
- **实际：** 完全恢复
- **通过：** ✅

### MT-011：QPSK 单位平均功率

- **输入：** 1024 随机 bit → QPSK 调制
- **预期：** 平均功率 ∈ [0.8, 1.2]
- **实际：** 平均功率 ≈ 1.0
- **通过：** ✅

---

## 发现的问题与修复

### 问题 1：QPSK 星座映射 b0/b1 错位

**严重程度：** 高

**现象：** 公开测试 TC-T-009（星座象限验证）失败。测试预期 `[00, 01, 11, 10]` 的星座象限为 `[(+,+), (-,+), (-,-), (+,-)]`，但实际输出为 `[(+,+), (+,-), (-,-), (-,+)]`。

**根因：** `qpsk_modulate` 中 `b0` 被映射到 I 路（实部）、`b1` 映射到 Q 路（虚部），但 Gray QPSK 规范要求 `b1` 控制 I 路（实部）、`b0` 控制 Q 路（虚部）。

原始代码：
```python
real = 1.0 if b0 == 0 else -1.0   # 错误：b0→I
imag = 1.0 if b1 == 0 else -1.0   # 错误：b1→Q
```

修正后：
```python
real = 1.0 if b1 == 0 else -1.0   # 正确：b1→I
imag = 1.0 if b0 == 0 else -1.0   # 正确：b0→Q
```

对应解调也一并修正：
```python
# 修正前：
b1 = 0 if s.imag >= 0 else 1   # 错误
b0 = 0 if s.real >= 0 else 1   # 错误
# 修正后：
b1 = 0 if s.real >= 0 else 1   # 正确：I(real)→b1
b0 = 0 if s.imag >= 0 else 1   # 正确：Q(imag)→b0
```

**为何之前 MT-002/MT-005 也通过：** 调制和解调使用了相同（对称）的错误映射，往返可逆但星座位置与规范不一致。公开测试 TC-T-009 显式检查象限位置才暴露此问题。

### 问题 2：前导自相关测试方法不当

**严重程度：** 低（仅测试代码问题）

**现象：** `test_mt_006` 使用零填充非周期互相关（aperiodic correlation with zero-padding）计算 preamble 的自相关，在非零滞后获得异常高的旁瓣值（1.0）。

**根因：** 零填充非周期互相关在部分重叠区域（特别是 lag=±1 等小偏移）的归一化分母包含零功率符号，导致相关值畸高。这不反映同步模块实际使用的滑动窗口互相关性能。

**修正：** 将测试改为嵌入法——把 preamble 符号插入随机符号序列中央，用同步模块使用的滑动窗口法计算相关值。这直接验证 preamble 在实际工作条件下的检测能力。峰值在正确位置 >0.95，所有旁瓣 <65% 峰值。

### 问题 3：空 bitstream 的 source_decode 行为

**严重程度：** 低（仅测试代码问题）

**现象：** 测试预期 `source_decode([])` 抛出 `ValueError`（非 8 倍数长度），但实际返回 `""`。

**根因：** 0 % 8 = 0，空 bitstream 被视为合法的 0 字节 UTF-8 编码，解码为空字符串。这是合理行为。

**修正：** 更新测试断言为 `assert source_decode([]) == ""`。

---

## 前导序列验证

### 序列定义

使用 7 阶最大长度 LFSR（本原多项式 x⁷ + x⁶ + 1，周期 127）生成 64 bit 前导。

初始状态：`0b1010111`（十进制 87）

生成的前导 bit 序列（64 bit）：

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

### 验证结果

- **滑动窗口主峰：** > 0.95（32 符号窗口在正确偏移处）
- **最大旁瓣：** < 65% 主峰值（与随机背景符号序列比较）
- **同步测试（MT-003）：** 25 符号偏移 + 12 dB AWGN 下精确检测（误差 0）
- **结论：** 前导序列满足同步检测需求

---

## CRC-32 实现约定

### 已确认规则

1. 使用 `zlib.crc32` 计算 CRC-32（IEEE 802.3 多项式 `0x04C11DB7`）
2. CRC 计算对象：原始源 payload bitstream（source_encode 输出，即 UTF-8 编码后、扰码前的 bitstream）
3. Bit → Bytes 转换：MSB 优先，每 8 bit 组成 1 字节
4. 零长度 payload：CRC = `zlib.crc32(b"") & 0xFFFFFFFF`
5. 非 8 倍数 bitstream：先补零到字节边界再计算 CRC（实际场景中 UTF-8 编码的 bitstream 始终是 8 的倍数，此规则仅为防御性设计）
6. 帧中 CRC 存储为 32 bit 大端序列

### 验证结果

- **MT-004：** CRC 正确计算、编码、传输和校验
- **MT-004（损坏检测）：** CRC bit 翻转被正确检测
- **MT-005：** 端到端 CRC 校验通过

---

## 对 DESIGN.md 的修订建议

### 修订 1：前导序列明确化

DESIGN.md 原为"建议采用巴克尔码扩展或 64-bit PN 序列"，现确定为：

- 7 阶 m 序列 LFSR（x⁷+x⁶+1），初态 0b1010111
- 取前 64 bit 输出
- 已在 `src/framing.py` 中硬编码为 `_PREAMBLE_BITS`

### 修订 2：QPSK 星座映射补充说明

DESIGN.md 已正确描述星座映射（b1→I, b0→Q），但实现时曾出现 b0/b1 错位。在 DESIGN.md 中补充明确的 bit 到 I/Q 的对应规则。

### 修订 3：CRC 规则补充

补充以下细节：
- 零长度 payload 的 CRC 值为 `zlib.crc32(b"") & 0xFFFFFFFF`
- bit → bytes 使用 MSB 优先
- 非 8 倍数 bitstream 的 padding 策略

### 修订 4：空输入行为

补充各模块对空输入的处理约定。

---

## 最终审计发现与修复（2026-06-24 v1.3）

### 问题 4：CRC 错误使用发送端原始数据进行校验

- **严重程度：** 高
- **现象：** `pipeline.py` 中 CRC 校验使用了 `_compute_crc32(original_bits)`（发送端原始数据），导致即使接收端 bitstream 出现误码，CRC 也永远通过。
- **根因：** 设计文档要求 CRC 校验数据完整性，但代码错误地使用了发送端而非接收端 bitstream。
- **修复：** 改为 `_compute_crc32(descrambled[:original_length])`，使用接收端恢复的数据重算 CRC。增加回归测试 MT-012：在 SNR 0 dB 下验证 BER>0 时 CRC 必须失败、FER 必须为 1。
- **修改文件：** `src/pipeline.py`、`tests/test_mock.py`

### 问题 5：FER 可能在数据错误时错误为 0

- **严重程度：** 高
- **现象：** 因 CRC 校验使用了发送端数据，FER 在 CRC 通过时错误返回 0.0 而非 1.0。
- **修复：** 与问题 4 同步修复。FER 仅当帧解析成功且接收端 CRC 通过时才为 0.0。

### 问题 6：截断帧没有被拒绝

- **严重程度：** 中
- **现象：** `parse_frame()` 缺少帧完整性校验，过短帧、coded_length 越界、CRC 截断等情况未报错。
- **修复：** 增加最小帧长度检查（160 bit）、coded_length 边界验证、CRC 存在性检查。新增 5 条帧结构边界测试（MT-013~MT-018）。
- **修改文件：** `src/framing.py`、`tests/test_mock.py`

### 问题 7：前置符号实现与文档不一致

- **严重程度：** 中
- **现象：** DESIGN.md 描述前置符号为"随机 QPSK 符号"，但 `_generate_prefix_symbols()` 使用复高斯随机样本（非 QPSK 星座点），功率不恒定。
- **修复：** 改为从随机 bit 经 `qpsk_modulate()` 生成标准单位功率 QPSK 符号。新增 MT-022 验证。
- **修改文件：** `src/pipeline.py`、`tests/test_mock.py`

### 问题 8：非有限 SNR 未校验

- **严重程度：** 中
- **现象：** `main.py` 未拒绝 `nan`、`inf`、`-inf` 等非有限 SNR 值，可能导致 AWGN 计算异常。
- **修复：** 增加 `math.isfinite()` 检查，非有限 SNR 返回退出码 1。新增 MT-019~MT-021 和 E2E-015~E2E-016 测试。
- **修改文件：** `main.py`、`tests/test_mock.py`、`tests/test_e2e.py`

### 问题 9：BER 零误码点对数坐标处理

- **严重程度：** 低
- **现象：** BER=0 在对数坐标中不可见，可能被误解为"无数据点"。
- **修复：** 零误码点使用 `0.5 / payload_bits` 检测下限绘图，并标注 "0 errors observed"。理论曲线明确标注为"uncoded QPSK reference"。
- **修改文件：** `src/plotting.py`

### 问题 10：Eb/N0 公式标注

- **严重程度：** 低
- **现象：** DESIGN.md 和 plotting.py 中 Eb/N0 换算公式有符号错误，已修正为 $E_b/N_0\text{(dB)} = E_s/N_0\text{(dB)} + 10\log_{10}(3/2) \approx E_s/N_0\text{(dB)} + 1.76\text{ dB}$。
- **修改文件：** `DESIGN.md`、`src/plotting.py`

---

## Level 3 阶段 C 最小 Mock 验证

本阶段仅在 `tests/test_level3_mock_prototype.py` 中定义局部数学原型，没有创建 Rayleigh 信道、均衡、分集或 Level 3 pipeline 生产模块。

执行命令：

```bash
pytest tests/test_level3_mock_prototype.py -q
```

真实结果：`4 passed in 0.21s`。

### L3-MT-001：已知信道的 ZF/MMSE

- **输入：** 单位功率 QPSK symbols，$h=0.35-0.8j$，无噪声 $y=hx$；MMSE 另设线性噪声方差 $N_0=0.2$。
- **步骤：** 用局部 ZF/MMSE 原型计算，并与手工公式比较。
- **结果：** ZF 在 $10^{-12}$ 容差内恢复 $x$；MMSE 与 $h^*/(|h|^2+N_0/E_s)y$ 一致，且在 $N_0>0$ 时数值上不同于 ZF。
- **判定：** ✅ 通过。

### L3-MT-002：前导 LS 信道估计

- **输入：** 当前 32-symbol QPSK 前导，$h=-0.25+0.9j$，$y_p=hp$。
- **步骤：** 计算 $\hat h=\sum y_pp^*/\sum|p|^2$。
- **结果：** $|\hat h-h|<10^{-12}$。
- **判定：** ✅ 通过。

### L3-MT-003：双分支普通 MRC

- **输入：** 两个非零复信道 $[0.1+0.2j,-0.7+0.4j]$ 和共同 QPSK symbols。
- **步骤：** 构造 $y_l=h_lx$，按 $\sum h_l^*y_l/\sum|h_l|^2$ 合并。
- **结果：** 在 $10^{-12}$ 容差内恢复 $x$。
- **判定：** ✅ 通过；确认 MRC 必须在复符号域执行。

### L3-MT-004：深衰落安全边界

- **输入：** ZF/MMSE 的 $\hat h=0$，MRC 的全部分支估计为 0。
- **步骤：** 调用局部原型。
- **结果：** 三种原型均抛出含 `too small` 的 `ValueError`，未产生 NaN/inf。
- **判定：** ✅ 通过。

### Mock 发现及阶段 D 修订输入

1. MMSE 在 $N_0=0$ 时退化为 ZF；后续测试必须使用 $N_0>0$ 才能证明两套公式实现不同。
2. 普通等噪声 MRC 的公共噪声方差在归一化权重中相消，不应未经命名就在分母中增加 MMSE 正则项。
3. LS、ZF 和 MRC 都需要显式非空/能量/分母阈值；不能依赖 NumPy 的除零警告作为失败处理。
4. 公式 Mock 已通过，可以进入设计修订；尚未证明 Rayleigh 随机模型、同步、pipeline 或 CLI 正确。

---

## 测试结论（最终）

Level 2 Mock 11/11 通过；Level 3 最小公式 Mock 4/4 通过；Level 3 完整生产测试 26/26 通过；Level 2 回归 53/53 通过；公开测试 22/22 通过。**合计 101/101 全部通过。**

### Level 3 最终验证（2026-06-24）

| 验证项 | 结果 |
|---|---|
| Rayleigh 可复现性、不同 seed、空输入、统计功率 | ✅ |
| ZF 无噪声恢复 + MMSE 手算公式 ≠ ZF（$N_0>0$） | ✅ |
| LS 估计精确性 + 非法输入拒绝 | ✅ |
| MRC 手算公式 + 无噪声恢复 | ✅ |
| 深衰落安全失败（不产生 NaN/inf） | ✅ |
| 多分支联合同步 | ✅ |
| AWGN 旧调用与显式默认参数输出一致 | ✅ |
| 单分支 ZF/MMSE + 双分支 MRC 高 SNR 中文恢复 | ✅ |
| Emoji 混合文本 | ✅ |
| 低 SNR Rayleigh 不崩溃 | ✅ |
| Metrics JSON 新字段完整可序列化 | ✅ |
| 端到端可复现性 | ✅ |
| 接收端使用前导估计非真实信道（依赖注入验证） | ✅ |
| CLI 非法组合全部拒绝 | ✅ |
| 固定多 seed MRC FER ≤ 单分支 ZF | ✅ |
| 多 seed 实验 4 方案 × 6 SNR × 5 seed 完整运行 | ✅ |

核心模块接口稳定，CRC/FER 逻辑正确，帧校验完整，CLI 参数验证完备。Level 3 Rayleigh+ZF/MMSE/MRC 链路全部通过专项和端到端测试。项目可以提交。
