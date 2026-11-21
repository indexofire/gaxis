# 视觉评审：候选模型、成本与校准方法

美学无法用公式从像素中度量（见 `docs/design-quality.md`）。唯一可扩展的评审手段是由视觉语言模型按评分标准打分，并以你的排序进行校准。本文档列出各候选模型、它们的接入方式，以及实测的本地基线。

## 1. 接入方式（除 Claude 外的所有候选）

评审器使用**OpenAI 兼容的 chat completions** 接口并携带图像 data URL，因此一套实现几乎能覆盖所有情况：

```toml
[design]
judge = "vision"
base_url = "…"          # provider endpoint, /v1 style
model = "…"
api_key_env = "…"       # env var holding the key
max_side = 768          # vision input long side (smaller = faster on CPU)
timeout_s = 300
```

`gaxis design judge <image> --caption "…"` 对单个文件评分；ingest/backfill 会将其应用到各图上。`aesthetic`、`visualization` 以及模型的评分理由会存入 manifest（`design.method = "vision:<model>"`）；一旦失败，会回退到客观评审器并明确标注。

## 2. 候选模型

| 候选模型 | 接入方式 | 优势 | 每图大致成本 | 备注 |
|---|---|---|---|---|
| **Qwen-VL-Max**（DashScope） | `https://dashscope.aliyuncs.com/compatible-mode/v1`，`DASHSCOPE_API_KEY` | 一流的图表/OCR 识读，中文能力强 | ~$0.002–0.01 | 图表密集评审的良好默认选择 |
| **GLM-4.5V / 4.6V**（智谱） | `https://open.bigmodel.cn/api/paas/v4`，`ZHIPUAI_API_KEY` | 中文能力强、便宜、本技术栈已有 GLM 套餐 | ~$0.001–0.005 | 中文提示词/评分标准效果很好 |
| **GPT-4o-mini / GPT-4.1-mini**（OpenAI） | `https://api.openai.com/v1`，`OPENAI_API_KEY` | JSON 可靠，严格遵循评分标准 | ~$0.001–0.003 | 结构化输出最安全 |
| **Gemini 2.5 Flash**（Google，OpenAI 兼容） | `https://generativelanguage.googleapis.com/v1beta/openai`，`GEMINI_API_KEY` | 便宜，视觉推理良好 | ~$0.0005–0.002 | 批量使用时性价比高 |
| **Claude Sonnet**（Anthropic） | Anthropic Messages API | 实践中“设计眼光”最佳 | ~$0.01–0.02 | 需要一个小适配器（不兼容 OpenAI） |
| **qwen2.5vl:7b**（本地，Ollama） | `http://127.0.0.1:11434/v1`，无需密钥 | 免费、私密、可离线 | 0 | **在本机 CPU 上 768 px 时实测 145–150 s/图**；分数区分度较弱 |

上述成本是针对一张 1024 px 级图像和简短 JSON 回答的单图估算；在批量执行前请核对各服务商的当前定价。

## 2b. 在本技术栈上已验证：通过 GLM coding plan 使用 GLM-4.5V

现有的 GLM coding 密钥在**两个**端点上均可用于视觉任务（coding plan 端点提供 `glm-4.5v`）：

```toml
[design]
judge = "vision"
base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
model = "glm-4.5v"
api_key_env = "GLM_API_KEY"
max_side = 1024
timeout_s = 120
```

实测：每张图约 1.8 s（coding 端点）、3.0 s（标准端点），JSON 回答可靠。

校准（最终版，`data/corpus/golden/`）：来自微信“高分文章配色指南”系列的 22 张精选期刊图 + 8 张生成的反例。

| 指标 | 数值 |
|---|---|
| good 均值 / 范围 | **0.623** / 0.45–0.90 |
| bad 均值 / 范围 | **0.256** / 0.15–0.45 |
| AUC | **0.991** |

所有者认为这 22 张精选图“质量都很高，难以排序”，因此校准采用**二元**判断（金标准 vs 反例）而非全序——无法可靠产生的排序还不如没有排序。评审器给出的理由具体且可操作（“基因名称在 89 mm 下无法辨认”、“panel B 中超过 20 种颜色”、“一致的色盲友好配色”）。离线回归测试 `tests/test_golden_design.py` 会重放缓存的评审结果，若区分度下降则报错。

该样本所用的策略：≥0.55 入选；0.45–0.55 归为 dense 但有效；<0.45 拒绝（bad 组最高分 = 0.45）。随版本发布的默认值是更严格的 **0.60 / 0.45**（见 §5）。

使用 rubric v3.1（先分类别）进行的单图校准：在 24 张由所有者标注的图上 **AUC 0.937**；0.60 → 精确率/召回率 0.80/0.89，0.70 → 1.00/0.78。详见 `data/corpus/single-figures/review/report.md`。

## 3. 实测本地基线（本机）

Ollama `qwen2.5vl:7b`（6 GB），Intel Core Ultra 7 255H，无 GPU：

| 输入尺寸 | 延迟 | CNS 多面板图结果 | 凝胶组合图结果 |
|---|---|---|---|
| 1024 px | 367 s | aes 0.60 / vis 0.70 | — |
| 768 px | ~145 s | aes 0.60 / vis 0.70 | aes 0.50 / vis 0.30 |
| 448 px | ~148 s | — | aes 0.50 / vis 0.30 |

观察：延迟主要被图像 token 的 prefill 占据（768 ≈ 448，因为模型会按自身分辨率重新切分）；7B 的评分理由看似合理（“配色不符合色盲安全”、“面板组织可以更清晰”），但其绝对分数区间被压缩，在校准阶段不能替代前沿模型。

## 4. 校准流程

1. 精选 20–30 张你认为优秀的图，再加 5–10 张差的图（微信配色系列是很好的素材来源：`gaxis design candidates <dir>`）。
2. 由你自己把它们按 1..N 排序（只针对设计，不针对提取）。
3. 对同一组图运行评审器，并对照你的排序计算 Spearman 相关系数（`gaxis quality calibrate`，在评审完成后即使用设计分数）。
4. 目标为 ρ ≥ 0.7。若未达标，检查分歧最大处的评审理由：通常评分标准只需补充一条具体规则（例如“跨面板共享图例是好的”、“渐变背景属于装饰”）。
5. 只有在此之后才将 `design.score` 用于筛选阈值；在 manifest 中记录模型 + 提示词版本，以便旧的评审结果可比较。

## 4b. 接入点

评审在 `ingest_paper`/`quality backfill` 时运行。得到的分数按 `[design] gold_score`（0.60）和 `dense_score`（0.45）分桶；`reject` 图不会进入知识库，除非设置 `[knowledge] include_rejected_design = true`。见 `docs/design-quality.md` §4c。

## 5. 当前状态

- **GLM-4.5V 已接入并投入使用**，运行于所有者的 coding plan 端点（`base_url = https://open.bigmodel.cn/api/coding/paas/v4`，`model = glm-4.5v`，`api_key_env = GLM_API_KEY`）：768 px 下每张图约 1.8 s。这就是支撑当前校准结果的评审器。
- 校准：二元金标准集（22 张精选 vs 8 张反例）AUC **0.991**；单图集（24 个所有者标注：keep/borderline/drop）在 rubric v3.1 下 AUC **0.937**。两者均作为离线回归测试重放（`tests/data/*_judgements.json`）。
- 本地 `qwen2.5vl:7b`（Ollama）仍保留作为离线批处理的回退方案（768 px 下约 145 s/图；1024 px 约 6 min）。它不用于持续评审。
- 策略阈值：`gold_score = 0.60`，`dense_score = 0.45`；`0.70` 相当于严格模式（在标注集上精确率 1.00 / 召回率 0.78）。这些阈值属于配置项，绝不作为代码中的常量。
