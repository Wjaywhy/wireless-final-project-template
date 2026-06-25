无线通信技术期末项目 PRD
基于 AI 辅助编程的无线通信文件传输基带仿真系统
适用课程：无线通信技术 / 无线通信基础    考核性质：替代闭卷期末考试
1. 项目背景
本课程期末考核采用项目形式替代传统闭卷考试。学生需要在教师提供的 PRD 和部分公开测试案例基础上，使用 AI 辅助编程完成一个可运行的无线通信基带仿真系统。系统需要将教师给定的 Test.txt 文档作为业务载荷，经过发送端、无线信道和接收端处理后，在接收端恢复为 received.txt。
本项目重点考查学生对无线通信系统链路的整体理解、模块化设计能力、测试驱动开发意识、AI 辅助编程能力，以及对通信原理、关键参数、代码逻辑和实验结果的解释能力。
2. 项目目标
实现一个端到端无线通信基带仿真系统，完成 Test.txt 到 received.txt 的可靠传输。
理解并实现源编码、扰码或加密、信道编码、QPSK 调制、无线信道、同步、解调、译码和文件恢复流程。
基于公开测试案例生成和修订设计文档，完成 mock 测试并据此调整方案。
生成性能指标和可视化结果，包括误比特率、帧错误率、文本恢复率、星座图和同步相关峰值图等。
规范记录 AI 辅助编程过程，并能解释每个模块的通信原理、关键参数、代码逻辑和实验结果。
3. 统一系统流程
所有学生必须实现同一条固定系统链路，模块顺序如下：
Test.txt -> Source Encode -> Encrypt/Scramble -> Channel Encode -> Frame Build -> QPSK Modulate -> Channel -> Synchronization -> QPSK Demodulate -> Channel Decode -> Decrypt/Descramble -> Source Decode -> received.txt -> Metrics/Plots
其中 QPSK 为基础必做调制方式。BPSK 和 16-QAM 可作为对比实验或扩展模块，不替代 QPSK 基础要求。
4. 输入与输出要求
项目
要求
输入文件
教师提供 Test.txt，内容为约 300 字的课程描述，编码格式为 UTF-8。
输出文件
系统必须生成 results/received.txt。
一致性检查
系统必须比较 Test.txt 与 received.txt，并输出比特错误率、字符恢复率或文本一致性结果。
复现实验
系统必须支持固定随机种子，以便教师公开测试和隐藏测试复现。
命令行运行
必须支持：python main.py --input Test.txt --output results/received.txt--snr 12 --seed 2026 --mod qpsk --channel awgn

5. 功能需求
源编码模块必须将 UTF-8 文本转换为比特流，并能从比特流恢复文本。
扰码或加密模块必须对发送比特进行可逆处理，可采用 XOR、PN 序列扰码或简单流密码。
信道编码模块必须提供基本抗噪能力，可选择重复码、汉明码、卷积码等课程相关方案。
帧结构模块必须至少包含前导序列、长度字段、载荷字段和校验字段。
调制模块基础必做 QPSK，必须说明星座映射、归一化方式和比特到符号的关系。
信道模块基础必做 AWGN 信道，必须支持可配置 SNR；Rayleigh/Rician 衰落可作为扩展。
同步模块必须利用前导序列等方法检测帧起点，不能假设接收端天然知道起点。
接收端必须完成同步、解调、信道译码、解扰或解密、源解码和文件恢复。
系统必须输出 metrics.json 或等价文本结果，记录 SNR、BER、FER、文本一致率、随机种子和关键参数。
系统必须至少生成两类可视化图表：QPSK 星座图、BER-SNR 曲线、同步相关峰值图三者中至少两项。
6. 模块边界与可选设计空间
模块
固定要求
允许选择或扩展
源编码
UTF-8 文本与比特流互转
可自行设计补零、长度记录、异常字符处理策略
扰码/加密
必须可逆
XOR、PN 序列扰码、简单流密码
信道编码
必须实现一种编码
重复码、汉明码、卷积码、简化 LDPC
帧结构
必须含前导、长度、载荷、校验
字段长度、CRC/checksum 方案可自选
调制
基础必做 QPSK
BPSK、16-QAM 作为对比或提高项
信道
AWGN 必做
Rayleigh、Rician、多径信道作为提高项
同步
必须检测帧起点
前导相关、匹配滤波、能量检测辅助
均衡
基础系统可不做
ZF、MMSE 作为提高项
OFDM/分集/多址
基础系统可不做
作为挑战模块或加分模块

6.1 基础系统统一验收口径
为保证教师能够统一运行测试集和验证集，基础系统必须采用以下统一口径：
项目
统一要求
QPSK 映射
基础系统必须采用 Gray 编码 QPSK：00 -> (1+j)/sqrt(2)01 -> (-1+j)/sqrt(2)11 -> (-1-j)/sqrt(2)10 -> (1-j)/sqrt(2)
SNR 定义
基础系统中 SNR 定义为接收端调制符号平均功率与复高斯噪声平均功率之比，单位 dB；若使用 Eb/N0，必须在 DESIGN.md 和 metrics.json 中说明换算关系。
length 字段
length 字段必须表示源编码后、扰码前的原始 payload bit 数，接收端应使用该长度去除 padding 并恢复 UTF-8 文本。
QPSK padding
若进入 QPSK 调制的 bit 数不是 2 的整数倍，系统必须在帧尾补 0，并在接收端根据 length 字段去除 padding。
校验字段
校验字段至少覆盖原始 payload bytes 或原始 payload bitstream。接收端必须在 metrics.json 中记录 checksum_pass 或 crc_pass。
同步偏移
基础系统应能处理 0 到 128 个 QPSK 符号的随机前置偏移。在 SNR >= 12 dB 的 AWGN 信道下，帧起点检测误差应不超过 1 个符号。
公开基础通过条件
SNR >= 12 dB、AWGN、固定 seed 条件下，received.txt 必须与 Test.txt 完全一致。
低 SNR 行为
较低 SNR 条件下不强制完全一致，但系统不得崩溃，必须输出 BER、FER、text_match_rate 和失败原因或校验失败标记。

6.2 metrics.json 最低字段
系统必须生成 results/metrics.json，且至少包含以下字段：
{  "snr_db": 12,  "seed": 2026,  "modulation": "qpsk",  "channel": "awgn",  "payload_bits": 2400,  "ber": 0.0,  "fer": 0.0,  "text_match_rate": 1.0,  "checksum_pass": true,  "sync_start_index": 25}
7. 分级要求
等级
得分上限
要求
Level 1 基础必做
70
跑通端到端系统；实现 QPSK、AWGN、帧同步、信道编码、文件恢复；输出基本性能指标。
Level 2 完整系统
85
在 Level 1 基础上增加扰码或加密、BER-SNR 曲线、星座图、同步峰值图、mock 测试报告和设计修订记录。
Level 3 提高模块
100
任选 Rayleigh 信道、均衡、OFDM、分集、卷积码 Viterbi、自适应调制、图形化界面等高级模块。

8. 工程流程要求
学生不得直接跳到最终代码生成，必须按以下工程流程完成项目：
阅读教师 PRD，生成 DESIGN.md，说明系统架构、模块接口、算法选择、关键参数和预期风险。
阅读教师公开的 20% 测试案例，生成 TEST_PLAN.md。
进行 mock 测试，验证设计文档中的接口、帧结构、同步流程和端到端流程是否可行。
根据 mock 测试结果修订 DESIGN.md，并在 MOCK_TEST_REPORT.md 中说明发现的问题和调整内容。
在设计文档稳定后，使用 AI 辅助生成和完善系统代码。
运行公开测试、自测和端到端实验，输出 received.txt、metrics.json 和图表。
提交 AI_LOG.md，记录关键 prompt、AI 生成内容、人工修改内容和调试过程。
9. 教师公开测试案例边界
教师将提供测试集作为公开测试案例，用于帮助学生理解需求、验证设计和调整实现。测试集建议覆盖基础正确性，不覆盖全部鲁棒性：
Test.txt 能正确读入并转换为 bitstream。
bitstream 能恢复为原 UTF-8 文本。
帧结构能正确封装和解析。
QPSK 在无噪声或低噪声 AWGN 条件下能恢复文本。
AWGN 信道在固定随机种子下输出可复现。
同步模块能检测简单前导偏移。
端到端运行能生成 received.txt、metrics.json 和至少两张图表。
公开测试不覆盖全部隐藏场景。学生不得针对公开测试硬编码输入、输出或中间结果。
10. 验证集与最终验收要求
教师保留验证集作为隐藏测试案例，用于最终验收。验证集可包括：
不同内容的中文 UTF-8 文本。
不同长度的输入文本。
不同 SNR 和固定随机种子。
随机帧起点偏移。
较高噪声下的恢复率门限。
不同调制对比或扩展模块检查。
异常输入、缺失文件、参数错误等鲁棒性检查。
检测是否存在硬编码公开测试样例的行为。
建议测试集约占总案例的 20%，用于学生调试和设计修订；验证集约占总案例的 80%，用于教师最终评分。
10.1 统一自动验收入口
基础系统必须支持以下统一命令行入口：
python main.py --input Test.txt --output results/received.txt --snr 12 --seed 2026 --mod qpsk --channel awgn
测试集基础用例通过条件：
程序正常退出。
生成 results/received.txt。
生成 results/metrics.json。
在 SNR >= 12 dB、AWGN、seed 固定条件下，received.txt 与 Test.txt 完全一致。
metrics.json 至少包含 snr_db、seed、modulation、channel、payload_bits、ber、fer、text_match_rate、checksum_pass、sync_start_index。
至少生成 constellation.png、ber_curve.png、sync_peak.png 中两项。
11. 学生提交物
学生最终提交的项目目录建议如下：
wireless-final-project/  PRD.md  DESIGN.md  TEST_PLAN.md  MOCK_TEST_REPORT.md  AI_LOG.md  Test.txt  main.py  src/  tests/  results/    received.txt    metrics.json    constellation.png    ber_curve.png    sync_peak.png
12. GitHub 提交与公开验收流程
本项目不使用 GitHub Classroom。学生需要采用与课程实验相同的 GitHub Fork + Pull Request 工作流提交项目。
项目
要求
教师仓库
https://github.com/jwentong/wireless-final-project-template
提交方式
学生 Fork 教师仓库到个人 GitHub 账号，在个人 Fork 中完成项目，然后向教师原仓库创建 Pull Request。
PR 标题格式
学号-姓名-无线通信期末项目，例如：2023123456-张三-无线通信期末项目。
身份信息
创建 Pull Request 时必须填写学号、姓名、GitHub 用户名。
仓库信息
创建 Pull Request 时必须填写学生 Fork 仓库地址和提交分支。PR 编号由 GitHub 自动生成，学生可创建后补填。
提交清单
PR 模板中必须勾选 DESIGN.md、TEST_PLAN.md、MOCK_TEST_REPORT.md、AI_LOG.md、main.py、src/、tests/、results/ 等完成情况。
自动公开验收
Pull Request 创建或更新后，教师仓库的 GitHub Actions 会自动运行 public_tests，并在 Actions Summary 或 PR 评论中显示公开测试结果。
自动记录
教师可通过 GitHub Pull Request 元数据自动导出 students.csv，记录学号、姓名、GitHub 用户名、学生 Fork 仓库地址、提交分支和 PR 编号。
最终验收
公开测试只作为基础检查。教师还将使用隐藏验证集、文档检查和必要的人工复核进行最终评分。

学生提交步骤如下：
访问教师仓库 https://github.com/jwentong/wireless-final-project-template。
点击 Fork，将仓库复制到自己的 GitHub 账号。
Clone 自己 Fork 后的仓库到本地。
按照 PRD 完成设计文档、mock 测试报告、AI_LOG 和系统代码。
在本地运行 pytest public_tests -q，尽量通过公开测试。
将代码 push 到自己的 Fork 仓库。
从自己的 Fork 向教师原仓库 main 分支创建 Pull Request。
在 PR 模板中填写学号、姓名、GitHub 用户名、Fork 仓库地址、提交分支和提交清单。
查看 GitHub Actions 结果，根据公开测试失败信息继续修改并 push。
12.1 Pull Request 信息填写要求
学生创建 Pull Request 时，必须按照仓库中的 PR 模板填写个人身份和提交信息。这些信息将用于教师后续自动整理学生名单、定位学生仓库并运行隐藏验证集。
字段
填写要求
Student ID
填写本人学号，必须与课程名单一致。
Name
填写本人中文姓名，必须与课程名单一致。
GitHub username
填写本人 GitHub 用户名。
Fork repository URL
填写自己 Fork 后的仓库地址，例如 https://github.com/<username>/wireless-final-project-template.git。
Branch
填写提交分支，默认通常为 main。
PR number
GitHub 创建 Pull Request 后自动生成；学生可先留空，创建后补填。
Checklist
逐项勾选是否已完成 DESIGN.md、TEST_PLAN.md、MOCK_TEST_REPORT.md、AI_LOG.md、main.py、src/、tests/、results/ 等提交物。

12.2 教师自动记录与隐藏验收
教师端将使用私有评分仓库 wireless-final-project-grader 进行隐藏验收。截止后，教师可从 GitHub Pull Request 自动导出 students.csv。该文件记录每位学生的学号、姓名、GitHub 用户名、Fork 仓库地址、提交分支和 PR 编号。
自动导出优先使用学生在 PR 模板中填写的信息；若学生漏填部分字段，教师脚本会尝试从 GitHub PR 元数据补全：
GitHub 用户名：来自 PR author。
Fork 仓库地址：来自 PR head repository clone URL。
提交分支：来自 PR head branch。
PR 编号：来自 GitHub PR number。
教师隐藏验收流程如下：
截止后，教师在私有评分仓库 wireless-final-project-grader 中手动触发 hidden-validation workflow，或本地运行评分脚本。
评分脚本从教师模板仓库的 Pull Request 列表自动导出 students.csv。
评分脚本根据 students.csv 批量 clone 学生 Fork 仓库。
评分脚本复制隐藏测试集和隐藏 Test.txt 到学生项目运行环境。
评分脚本运行隐藏 pytest 验证集，检查不同文本、不同 SNR、不同 seed、同步偏移、异常参数、反硬编码和文档一致性。
评分脚本生成 results/grade_report.csv，作为隐藏验证集评分依据。
公开测试用于帮助学生理解需求和调试基础功能；隐藏验证集不向学生公开，主要用于最终评分和防止针对公开样例硬编码。
13. AI 使用要求
允许并鼓励使用 AI 辅助编程、生成设计草稿、生成测试代码、调试错误和解释结果。
建议使用 Claude Code 或 Codex 作为主要 AI 编程环境，并加装或启用 Superpowers skills，用于需求澄清、设计文档、测试驱动开发、系统调试和完成前验证。
学生应优先让 AI 按 PRD -> DESIGN.md -> TEST_PLAN.md -> MOCK_TEST_REPORT.md -> 代码实现 -> 测试验证 的工程流程工作，而不是直接生成最终代码。
学生必须保留 AI_LOG.md，记录关键 prompt、AI 生成内容、人工修改内容、测试失败修复过程和最终采纳理由。
学生必须能够解释每个模块的通信原理、关键参数、代码逻辑和实验结果。
不能解释者，即使程序运行成功，也不得获得对应模块满分。
禁止提交本人无法解释的代码，禁止抄袭他人项目，禁止硬编码教师公开测试输入输出。
14. 评分标准
评分项
分值
评价重点
需求理解与设计文档
20
设计完整性、通信原理正确性、接口清晰度、参数合理性
mock 测试与设计修正
15
是否先验证设计、是否发现问题、是否根据测试反馈修订
系统代码实现
25
端到端链路、模块化结构、QPSK/AWGN/同步/编码译码实现质量
公开与隐藏测试通过情况
20
received.txt 恢复、BER/FER、鲁棒性、无硬编码行为
实验分析报告
10
星座图、BER 曲线、同步图、结果解释和失败分析
AI 使用记录与答辩
10
AI_LOG 完整性、代码理解、现场解释能力、学术诚信

15. 答辩与解释要求
教师可通过现场演示或口头答辩确认学生是否真正理解系统。建议问题包括：
为什么基础系统选择 QPSK？QPSK 的星座映射和归一化方式是什么？
你的帧结构如何支持同步、长度识别和错误检测？
信道编码解决了什么问题？编码率和纠错能力如何影响传输效率？
SNR 降低时，系统中哪个模块最先出现问题？如何定位？
如果 received.txt 出现乱码，你的排查顺序是什么？
mock 测试发现了哪些设计缺陷？你如何修改设计？
AI 生成的代码中你保留、修改或拒绝了哪些内容？为什么？
16. 学术诚信与限制
项目原则上个人完成；如课程另行允许小组完成，必须提交明确分工和个人答辩记录。
禁止复制他人完整项目或共享最终代码。
禁止绕过通信链路直接复制 Test.txt 到 received.txt。
禁止针对公开测试案例硬编码输出。
教师可通过隐藏测试、代码检查、运行日志和答辩综合判断项目真实性。

本 PRD 为期末项目最低需求边界，教师可根据教学进度补充公开测试案例和隐藏验收标准。
