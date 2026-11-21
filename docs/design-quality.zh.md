# 设计质量：gaxis 实际上为何而选

> 本文档取代早先的“质量校准”方法。那次尝试对*技术*参数（分辨率、裁剪整洁度、图注是否存在）进行打分，并依据一组低质量图形的排序来校准分数。该分数衡量的是“我们能否使用这个文件”，而不是“这是不是一张好图”，而且语料库使任何排序都变得随意。这两个错误都在本文中得到了修正。

## 1. 两个独立的问题

| 问题 | 判定者 | 存储为 | 用途 |
|---|---|---|---|
| **这个资产到底能不能用？** | 确定性检查（图注、图形、分辨率、面积、矢量、裁剪整洁度） | `chart_quality_score` (extraction) | 一道**门槛**：不要复现或索引不可用的裁剪图 |
| **这是不是一张好图？** | 由视觉模型或人类依据评分细则判定 | `design.method`, `design.aesthetic`, `design.visualization`, `design.score` | 对要复现的内容进行**选择与排序** |

两者从不混用。一张丑陋图表在技术上完美的裁剪图仍然是糟糕的示例；一张被切成两半的漂亮图形仍然不可用。

## 2. “好”意味着什么（评分细则）

两个维度，每个均为 0–1：

**Aesthetic（美学）** — 配色纪律（3–8 种经过考量的颜色，色盲友好）、留白与边距、对齐与排版一致性、无图表垃圾（过重的网格线、3-D、阴影、装饰）。

**Visualization（可视化）** — 为数据选择正确的图表类型、坐标轴标注单位、展示不确定性（误差棒 / CI / 箱线图）、在 89 mm 印刷宽度下清晰可读（≥ 6 pt）、合理的子图组织。

## 3. 由谁判定

`[design] judge = "vision" | "heuristic"` (`src/gaxis/design_judge.py`)：

- **vision** — 一个兼容 OpenAI 的视觉模型按评分细则打分并返回 JSON 及简短理由；以 `method: vision:<model>` 存储，附带模型的理由。这是评判美学的唯一自动化方式，且在其数值被用于任何重要决策之前，必须先针对人工排序进行校准。
- **heuristic**（默认，离线）— 仅限客观的那一半：基于 PDF 字号的可读性、图注声明的单位 / 不确定性 / 子图、色盲安全性、图表与照片区分、留白。它会把 `aesthetic: null` 和 `score: null` 写入结果。它是一个*初筛*，绝不是品味判断。

```toml
[design]
judge = "vision"
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
api_key_env = "OPENAI_API_KEY"
```

没有密钥时，ingest 会回退到客观判定器，并在 manifest 备注中记录 `vision judge unavailable: …`。绝不静默地假装成功。

## 4. 校准（真正意义上的校准）

1. 构建**黄金集（golden set）**：20–30 张你认为优秀的图形，来自你的目标期刊（Nature Microbiology, Cell Host & Microbe, ISME J, mBio, …），再加上 5–10 张刻意糟糕的图形（默认 matplotlib 风格、彩虹配色、3-D 饼图、无标注坐标轴、网格过重）。
2. `gaxis quality sheet --min-design 0.5` → `sheet.md` + 缩略图总览表。
3. 按“我会把它放进我的论文吗？”来排序 1..N（美学 + 可视化，*不是*提取质量）。
4. `gaxis quality calibrate <sheet.md>` → 与当前判定器做 Spearman 相关。对视觉判定器，将其分数与你的排序比较；若 ρ < 0.7 则调整 prompt/评分细则。
5. 此后才可将 `design.score` 用于排序阈值。

## 4b. 校准结果（二元黄金集）

把 22 张优秀图形两两排序被证明不合理（它们都很好），因此黄金集采用二元标签：22 张精选期刊图形 = 正例，8 张生成的反例 = 负例。GLM-4.5V 对它们的打分达到 **AUC 0.991**（好图均值 0.62，坏图均值 0.26）。缓存的判定结果是一个回归测试；策略阈值：≥0.60 选用 (0.70 = strict)，0.45–0.60 为密集但有效，<0.45 拒绝。详见 `data/corpus/golden/report.md`、`docs/vision-judge.md`。

## 4c. 分数如何被使用（已接入流水线）

- 在 ingest 时，每张图形都会被判定（配置了 vision 就用 vision，否则回退 objective），并依据 `[design] gold_score` / `dense_score`（默认 0.60 / 0.45）被赋予一个 `design.tier`：`gold` ≥ 0.60，`dense` 0.45–0.60，`reject` < 0.45；`null` 表示美学未被判过。
- `reject` 资产仍会作为提取资产写出（manifest + 图像），但**不会**被索引进知识库（`[knowledge] include_rejected_design = false`）。仅调试时才翻转该开关。
- KB 页面携带 `design_tier`、`design_score`、`design_model`，检索按（复现级别、设计分数、文本分数）排序。
- 黄金集（22 好 + 8 坏）是回归基线：`tests/test_golden_design.py` 离线重放缓存的判定结果，若区分度崩塌则测试失败。
- 一个更大的**分层库（tiered library）**由判定过的序列构建（137 张感知上不重复的图形）：`data/corpus/library/{gold,dense,reject}/`，每层带一份 `index.csv` 和缩略图总览表（`scripts/curate_corpus.py library`）。当前划分：**gold 85、dense 36、reject 16**。这是候选池，不是黄金集：只有经过人工审核后，才能把某张图形提升进黄金集（22 张精选图形全都经过了这个步骤）。

## 4d. 图版不是单张图形（所有者发现，2026-11-20）

精选语料的图像是每篇文章里**若干完整图形拼成的蒙太奇**。把一张蒙太奇当作单张图形来评判毫无意义：密度/可读性方面的意见针对的是整个图版，而所有者的 keep/drop 标注也证实分数无法把它们区分开（keep 的分数横跨 0.35–0.80，唯一一张 drop 得分 0.50）。

已实现：

- `design.plate_like` 检测由沟槽分隔的 ≥2 个竖长内容块（或 2×2 网格）；24 张边界图像中有 20 张、原“黄金好图”集 22 张中有 15 张是图版。
- `apply_plate_policy`（配置 `[design] skip_plates = true`）将图版标记为 `archetype: "plate"`，清空 `score`/`tier`，并记录 “style reference only”。图版仍可用作配色和布局参考，但绝不能替代单图评分。
- 黄金集被拆分：`data/corpus/golden/plates/`（15 张，风格参考）和 `data/corpus/golden/single/`（7 张）。单图校准现在有自己独立的数据集：`data/corpus/single-boundary/`（17 张带 GLM 分数的论文图形）和 `data/corpus/single-figures/review/`（24 张由所有者标注的裁剪图：keep / borderline / drop）。

## 4e. 在当前论文语料上的负面结果（2026-11-20）

所有者对当前流水线产出的 17 张单图裁剪（SE02 pre-proof、PLOS ONE、一个 demo）进行了标注：**keep 0、borderline 3、drop 14**。判定器曾把其中六张放入 `gold`（≥0.55）——该层的精确率为 0。结论：这些图形在技术上可提取，但不值得进论文；该语料无法校准单图设计。

对产品的后果：设计判定器只是一个**优先级辅助工具，而非真值来源**，直到它在高质量论文的单图上完成校准。`plates` 保持为风格参考（`skip_plates`），当前 KB 也不宣称具备设计质量判断力。

为了构建合适的语料，图版现在会被拆分成单图候选：

```bash
pixi run python scripts/split_plates.py --plates data/corpus/boundary data/corpus/golden/plates     --out data/corpus/single-figures --limit 60
```

共产出 65 个候选；判定器为其打分，`data/corpus/single-figures/review/` 保存了得分最高的 12 张和最低的 12 张，供所有者标注（keep/drop）。那里的标注将成为真正的单图校准集。

## 4f. 评分细则 v3.1 — 类别优先（2026-11-20）

第一轮单图标注暴露出一个系统性偏差：判定器偏爱显微照片和插图，惩罚了密集但有效的图形（AUC 0.516）。评分细则现在**先分类再打分**：

- `chart` / `mixed` — 按配色纪律、标签+单位、不确定性、可读性、子图组织打分；只要标签仍可读，密度不受惩罚。
- `schematic` / `micrograph` — 上限 3/10：是参考资料，不是可复用的数据图。
- `plate` — 作为蒙太奇打分（完整性、配色一致性、布局），而不是作为单个子图打分。

在 24 个由所有者标注的案例上：使用 rubric v3.1 的 **AUC 0.937**（v3：0.929；之前：0.516），在 0.55 处 precision/recall 为 0.89/0.89，在 0.60 处为 1.00/0.78。剩余的分歧是两张图形（一张被保留的类示意图复合图得 0.30，一张被丢弃的图表得 0.55）——记录于 `data/corpus/single-figures/review/report.md`，并固定在 `tests/test_single_figure_judge.py` 中。

`skip_plates` 现在默认为 **false**：图版检测是一项策展诊断（用于决定是否拆分外部蒙太奇），而不是针对从 PDF 提取的图形的评分规则。

## 4g. 两个分数，有意为之：设计 vs 有用性

`design.score` 回答“它做得好不好”。`usefulness_score` 回答“它是不是微生物学家会复用的那类图形”。二者分开，是因为一张干净但平庸的 PLOS 图可以做得很好（design 0.85）却仍不值得复现（usefulness 0.34），而一张来自强期刊的密集图形可能不够精致但价值大得多。

Usefulness 的组成部分（`src/gaxis/usefulness.py`，权重在 `[usefulness]`：journal 0.20、statistics 0.25、verification 0.25、panels 0.20、caption 0.10）：

| 组件 | 信号 |
|---|---|
| `journal` | 由 DOI 前缀得出的期刊层级 — **刻意压缩**（Nature 1.00, ASM 0.92, Microbiology Society 0.88, PLOS 0.82, bioRxiv 0.72, unknown 0.85），使期刊只是平局打破者，而非主导因素 |
| `statistics` | 图注声明了不确定性、样本量、单位 |
| `verification` | 复现级别 L1 1.0 / L2 0.7 / L3 0.3 / none 0.2 |
| `panels` | 由图注得出的子图数量（a–d → 4） |
| `caption` | 图注完整性 |

检索先按 `reproduction_level` 排序，再按**加权**分数 `0.7 × design_score + 0.3 × usefulness_score`（权重在 `[ranking]` 中，已归一化），最后按文本分数。设计分数有意优先：这个产品旨在复现设计良好的图形，期刊或子图数量绝不能排在一张明显更好的图形之上。
两个分数都存储在 manifest 和 KB 页面 frontmatter 中。Usefulness 是确定性的（不调用模型）且可解释的；一旦有更多标注数据，就可以重新校准。

## 5. 当前状态（坦白说）

- 客观的那一半已实现并测试（可读性、单位、不确定性、子图、色盲、图表与照片、留白）。它**不**声称评判美学；在被判定之前 `score` 保持为 `null`。
- 视觉判定器已实现（兼容 OpenAI 的 chat completions、宽容的 JSON 解析、存储理由）。**已在所有者的 GLM-4.5V 端点上启用**（`docs/vision-judge.md` 中的 `[design]` 配方）：约 1.8 s/figure，在 24 张所有者标注的单图上 AUC 0.937。本地的 `qwen2.5vl:7b` 回退约为 145 s/figure，仅用于离线批处理。
- 语料：早先的低质量样本（pre-proof 凝胶图、极小的 PLOS 子图）仍在 KB 中，绝不能用于设计校准。已添加一篇 Nature Communications 论文（7 张图形）且解析正确，但产品需要上面那个由*你*亲自挑选的黄金集。
- 检索按（复现级别、设计分数、文本分数）排序；当 `design.score` 为 null 时，它会回退到客观的 visualization 值，再回退到文本——绝不编造美学分数。

## 6. 之前的错误（保留作为警示）

- 该分数由六个技术成分组成，其权重是在 10 张本来就彼此相似的图形上“校准”出来的，因此拟合度不可能超过 ρ = 0.62，权重也动不了。
- `crop_clean` 惩罚了一张色调偏色的凝胶照片，而它其实是一张好图（人工排名第 3/10）——这个启发式错误之所以被发现，仅仅因为有人亲眼看了。
- 那个分数中没有任何内容编码了配色质量、图表类型的恰当性或排版工艺。
