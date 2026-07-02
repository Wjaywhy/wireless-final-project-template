# 无线通信技术期末项目

本仓库是无线通信技术课程期末项目的教师模板仓库。学生需要 Fork 本仓库到自己的 GitHub 账号，完成项目后向本仓库创建 Pull Request。教师将通过 Pull Request 中的 GitHub Actions 公开测试结果、隐藏验证集和文档检查完成验收。

项目目标：根据 `PRD.docx` 的要求，使用 AI 辅助编程实现一个无线通信基带仿真系统，将 `Test.txt` 的 UTF-8 文本内容通过发送端、无线信道和接收端处理后恢复为 `results/received.txt`。

## 提交流程

1. 点击本仓库右上角 `Fork`，将仓库复制到自己的 GitHub 账号下。
2. Clone 自己 Fork 后的仓库到本地。

```bash
git clone https://github.com/<your-username>/wireless-final-project-template.git
cd wireless-final-project-template
```

3. 按 `PRD.docx` 完成设计、mock 测试和代码实现。
4. 本地运行公开测试。

```bash
pip install -r requirements.txt
pytest public_tests -q
```

5. 提交并推送到自己的 Fork。

```bash
git add .
git commit -m "Complete wireless final project"
git push origin main
```

6. 回到 GitHub 网页，从自己的 Fork 向教师原仓库创建 Pull Request。
7. Pull Request 创建后，GitHub Actions 会自动运行公开测试，并在 PR 页面显示结果。

请不要直接向教师仓库 main 分支提交代码。最终提交以 Pull Request 为准。

## 必须提交的文件

学生最终项目至少应包含：

```text
DESIGN.md
TEST_PLAN.md
MOCK_TEST_REPORT.md
AI_LOG.md
main.py
src/
tests/
results/
```

## 统一运行命令

项目必须支持以下命令：

```bash
python main.py --input Test.txt --output results/received.txt --snr 12 --seed 2026 --mod qpsk --channel awgn
```

运行后应生成：

```text
results/received.txt
results/metrics.json
```

AWGN 默认模式应生成以下三张图表：

```text
results/constellation.png
results/ber_curve.png
results/sync_peak.png
```

## 公开测试

本仓库包含 `public_tests/`，用于公开验收和学生调试。这些测试只覆盖部分基础要求，不代表最终全部评分。

运行方式：

```bash
pytest public_tests -q
```

公开测试主要检查：

- 项目结构和文档是否完整
- 统一命令行入口是否可运行
- 源编码、帧结构、扰码或加密、信道编码、QPSK、AWGN、同步等模块是否满足基本要求
- `results/received.txt` 和 `results/metrics.json` 是否生成
- `metrics.json` 字段是否完整
- 是否生成结果图
- 是否存在明显绕过无线链路的直接复制行为

## 隐藏验证

教师最终评分还会使用隐藏验证集。隐藏验证集不会公开，可能覆盖：

- 不同中文文本
- 不同文本长度
- 不同 SNR
- 不同随机 seed
- 随机同步偏移
- 异常参数
- 反硬编码检查
- 设计文档与代码一致性检查

## AI 使用要求

允许并鼓励使用 AI 辅助编程。建议使用 Claude Code 或 Codex，并加装或启用 Superpowers skills。

必须保留 `AI_LOG.md`，记录关键 prompt、AI 生成内容、人工修改内容、测试失败修复过程和最终采纳理由。

即使程序运行成功，学生仍需能够解释每个模块的通信原理、关键参数、代码逻辑和实验结果。

## Pull Request 要求

创建 Pull Request 时，请填写 PR 模板中的学生信息和检查清单。PR 标题建议使用：

```text
学号-姓名-无线通信期末项目
```

例如：

```text
2023123456-张三-无线通信期末项目
```
## 2026-07 可复现性与审计输出

统一 CLI 保持向后兼容：

```bash
python main.py --input Test.txt --output results/received.txt --snr 12 --seed 2026 --mod qpsk --channel awgn
```

成功运行后，AWGN 默认模式的输出目录应包含 `received.txt`、`metrics.json`、
三张有效 PNG 图表（`constellation.png`、`ber_curve.png`、`sync_peak.png`），
以及 `run_manifest.json`。`run_manifest.json` 记录本次命令行、UTC
时间、可用时的 Git commit 和工作区 dirty 状态、Python/平台信息、依赖版本、输入
和输出 SHA-256、运行时间、seed、SNR、调制方式、信道类型和生成文件清单。
如果 Git 不可用，或当前目录不是 Git 仓库，程序不会崩溃；Git 相关字段写为
`null`。

`metrics.json` 保留旧字段 `ber`。为兼容旧测试，`ber` 等于 `payload_ber`，
即经过帧解析、信道译码、解扰、CRC 检查和源解码后的端到端 payload BER。
新增的 `predecode_ber` 在更早阶段计算：同步和 QPSK 硬判决解调后，用接收端
原始 frame bits 与发送端 frame bits 在发送帧长度内比较。因此，后续帧解析失败
或 UTF-8 解码失败不会把 `predecode_ber` 直接改写为 1.0。

同步真值字段仅用于后验审计：

- `true_prefix_symbols`：仿真中实际加入的随机前缀符号数。
- `sync_start_index`：接收端同步算法检测到的帧起点。
- `sync_error_symbols = sync_start_index - true_prefix_symbols`。
- `sync_success = abs(sync_error_symbols) <= 1`。

接收端同步算法不读取 `true_prefix_symbols`；该字段只在接收处理结束后写入，
用于追溯同步误差。

`frame_error_indicator` 是单次运行的帧错误指示：`0` 表示该帧完整恢复，
`1` 表示该帧恢复失败。单次运行不能把它解释为稳定 FER；在 Level 3 多 seed
实验中，该指示量的均值才是有限样本 FER。

CLI 对 `--snr` 采用集中校验：合法值必须是有限数，并位于 `[-100, 100]` dB
范围内。`nan`、`inf`、`-inf`、`-9999` 和 `9999` 会在主流程开始前以非零
退出码拒绝；正常负 SNR（例如 `-10` dB）仍允许运行。输入路径不存在、输入路径
是目录、输出父路径不是目录或输出目录不可写时，CLI 会向 `stderr` 输出中文错误
并返回非零退出码，不写出误导性的半成品。

接收端帧解析保持旧帧格式兼容。发送端仍使用
`Preamble | Original Length | Coded Length | Coded Payload | CRC-32`，
未新增 OFDM、16-QAM 或多径功能。若直接解析因少量帧头硬判决错误失败，接收端会
在严格边界内根据接收 frame bit 总长度、`coded_length == 3 * original_length`
和 CRC 选择有限候选，并在 `metrics.json` 记录 `frame_parse_strategy`、
`preamble_bit_errors`、`header_bit_errors`、`crc_bit_errors` 和
`qpsk_padding_bits`。该过程不读取原始输入文本，不复制答案，也不把同步真值传给
接收端。
当 payload 恢复后重新计算的 CRC 与接收 CRC 字段仅差 1 bit 时，系统将其作为 CRC
字段自身的单 bit 硬判决错误处理；`crc_bit_errors` 会记录该事实。超过 1 bit 或
payload 本身错误仍会导致帧失败。

`ber_curve.png` 现在使用每个 SNR 至少 20 个 seed 的 `predecode_ber` 均值绘制
物理层 BER，并把 `predecode_ber` 的均值、标准差、最小值、最大值、端到端 FER、
CRC 通过率和完整恢复率保存到 `ber_curve_data.json`。理论 Gray QPSK 曲线只作为
同口径物理层硬判决 BER 参考；端到端失败率单独以 FER 展示，不再与 `payload_ber`
混用。

一键验收命令：

```bash
python scripts/verify_submission.py
```

该脚本会运行公开测试、内部测试、统一 CLI、文本 SHA-256 检查、metrics schema
检查、manifest schema 检查、图表有效性检查和相同 seed 的可复现性检查。
机器可读报告写入 `verification_report.json`。

依赖文件的用途区分如下：

- `requirements.txt`：兼容安装范围。
- `requirements-lock.txt`：本次审计环境的精确版本。

Level 3 实验支持可配置的有限 seed 数：

```bash
python -m src.level3 --input Test.txt --output-dir results/level3 --seed 2026 --seed-count 20
```

默认仍为 5 个 seed。结果是有限样本观测，不是理论曲线。报告中应使用
“本次有限传输中未观察到误码”或“BER 低于当前实验的检测分辨率”等表述；
不得据此声称真实 BER 为 0，也不得把当前样本下的 MRC 表现写成固定理论 dB
增益。
