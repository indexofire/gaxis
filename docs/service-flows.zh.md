# 两条服务流程（产品核心）

本项目只在做一件事：**把论文里的高质量插图，变成"经过验证、可检索、可适配"的代码资产，再用它帮用户画出自己的论文插图。**

这件事表现为两条服务流程。它们是产品的主干；定期抓取论文、解析图与代码、沙箱复现，都是为了给这两条流程储备弹药。

```
┌──────────────────────── 背景：定期抓取（模块 A/B/C/D/H，M1–M2）────────────────────────┐
│ 论文源 → 质量筛选 → 图/caption/引用段/代码 → 沙箱复现 → L1/L2/L3 → 入库 paper-kb        │
└────────────────────────────────────────────────────────────────────────────────────────┘
                                    │ 知识库储备（gbrain paper-kb, federated=false）
                                    ▼
   服务 1：自然语言要图                              服务 2：给我一篇论文，画个类似的
   brief → 案例 → 对话收敛 → 方案/数据/代码          paper → 识别 → 建议 → 适配到我的数据
```

---

## 服务 1：自然语言 → 案例 → 对话收敛 → 方案/数据/代码

### 1.1 流程

| 步 | 谁 | 调用 | 产出 |
|---|---|---|---|
| 1 | 宿主 LLM | `plan_chart_from_brief(brief)` | **ChartPlan**：图表类型、期刊预设、风格要点、需要的列角色、待确认问题、候选案例 |
| 2 | 宿主 LLM | （对话）把 `open_questions` 逐条问清，按用户回答修订 brief / spec | 收敛后的 ChartSpec 草案 |
| 3 | 宿主 LLM | `search_chart_assets(query, filters)` | **可用（M3）**：知识库里的案例（asset_id、复现等级、缩略图路径、DOI） |
| 4 | 用户 | 提供数据（CSV/TSV） | — |
| 5 | 宿主 LLM | `describe_data_schema(data_path)` | 列画像、建议 spec、单位线索 |
| 6 | 宿主 LLM | `adapt_chart_code(data_path, asset_id/query)` 或 `render_chart_from_data(...)` | 图 + 独立脚本 + manifest + lint |
| 7 | 用户 | 看 contact sheet / 脚本，提修改意见 | 回到 2 或 6 |

关键点：**第 1 步不需要数据**。用户往往先讨论"要什么图"，数据后到。这就是契约里 `plan_chart_from_brief` 存在的唯一原因。

### 1.2 现在能做什么（已实现）

```bash
$ pixi run gaxis plan "grouped bar chart with error bars, Nature Microbiology, ggplot2, colour-blind palette"
chart:    bar   preset: nature_microbiology   backend: r   confidence: 0.85
style:
  - error bars: mean ± SD across replicates by default; pass a `yerr` column to supply SEM or 95% CI instead
columns:
  - x     categorical 2-12 groups
  - y     numeric     measurement per observation (omit to count rows)
  - hue   categorical grouping factor, 2-8 levels (colour/fill)
ask the user:
  ? Error bars: SD, SEM, or 95% CI? (and how many replicates per group)
  ? Attach the table (CSV/TSV, one observation per row) or describe its columns
note: knowledge base disabled ([knowledge] enabled = false) …
```

- 中英双语 brief（"画分组柱状图，带误差棒，色盲友好，投 mBio" 同样识别）；
- 图型 / 期刊预设 / 配色 / 后端 / 误差棒 / 多面板 / 对数轴 / 图例位置都能识别，**识别不到的进 `open_questions`，不会静默猜**；
- `confidence` 与 `degraded` 明示"这是启发式草案，不是检索结果"；
- 数据到位后，`render_chart_from_data` / `adapt_chart_code` 已经是可用的真实通路（6 图型 × 2 后端 × 7 期刊预设，36/36 lint clean）。

**M3 已完成**：`plan_chart_from_brief` 会在知识库可用时把检索到的案例放进 `matches`，并把它们的 asset_id 写进 `plan.candidate_asset_ids`、按命中数量抬高 `confidence`（每次 +0.05，上限 0.9）。若库里没有匹配，`message` 明说"no knowledge-base case matched"，而不是假装检索过。

### 1.3 对话收敛的约定（给宿主 LLM）

- 渲染之前必须让用户确认三件事：**图型**、**统计口径**（误差棒是 SD/SEM/CI，几重复）、**目标期刊/栏宽**。
- `confidence < 0.6` 或 `degraded` 时，不要直接渲染，先走 `open_questions`。
- 用户只给了截图或描述、没有数据时：只能给 `plan` + 案例，禁止伪造数据渲染（可选：明确标注的合成数据，M2 之后）。
- 渲染结果里的 `lint.issues` 必须原样呈现给用户，不能只报"成功"。

---

## 服务 2：用户给一篇论文，画文中类似的插图

### 2.1 流程（知识库优先）

明确原则：**先看库里有没有能满足的，再决定是否花时间解析论文、复现代码。**

| 步 | 谁 | 调用 | 产出 |
|---|---|---|---|
| 1 | 宿主 LLM | `ingest_paper(source, mode="kb_first")` | 来源识别（PDF / DOI / arXiv / PubMed·PMC / URL）+ 论文插图清单（`figure_briefs`）+ 库内匹配（M3 起可从已入库资产中给出）+ 是否值得深度解析 |
| 2 | 宿主 LLM | 把匹配项展示给用户（缩略图 + 复现等级 + 风格说明） | 用户判断：够用 / 不够用 |
| 3a | 够用 → | `adapt_chart_code(data_path, asset_id, preset)` | 图 + 代码 + manifest（服务 2 完成） |
| 3b | 不够用 → | `ingest_paper(source, mode="full")` | 深度解析：`get_chart_manifest` → `reproduce_chart_code` → L1/L2/L3 新资产入库 |
| 4 | 宿主 LLM | `search_chart_assets(query=该图语义, filters)` | 同类案例（含比原文更好的实现） |
| 5 | 宿主 LLM | `adapt_chart_code(...)` | 适配用户数据 → 图 + 代码 + manifest |
| 6 | 用户 | 校对/修改 | 回到 5 |

`mode="kb_first"` 是**默认值**（配置文件 `[ingest] default_mode`），因为它便宜：不下载仓库、不建环境、不跑沙箱，几秒内回答"库里有没有"。只有用户对库里的不满意，才付 `mode="full"` 的代价（分钟级、要联网、要跑代码）。

来源类型（`source_kind`，离线判定，`src/gaxis/acquire/identifiers.py`）：

| 类型 | 例子 | 需要联网 |
|---|---|---|
| `pdf` | `/path/paper.pdf` | 否 |
| `doi` | `10.1099/mgen.0.000001`、`https://doi.org/…` | 是 |
| `arxiv` | `arXiv:2103.00020`、`2103.00020v2` | 是 |
| `pmid` / `pmcid` | `PMID:12345678`、`PMC7654321` | 是 |
| `url` | 出版商页面、预印本页面 | 是 |

`normalised_id` 用于去重：`https://doi.org/…` 与裸 DOI 落成同一条，`PMID:` 前缀被剥离。网络开关 `[ingest] allow_network = false` 时，联网类型直接报 `network_disabled`（用本地 PDF 不受影响）。

### 2.2 现在能做什么

| 能力 | 状态 |
|---|---|
| `ingest_paper` | **可用**：来源识别、去重 id、网络策略、`kb_first/full` 路由、PDF 解析、代码仓库克隆与脚本挑选 |
| `get_chart_manifest` | **可用**：完整 manifest（代码候选、复现等级、评分） |
| `reproduce_chart_code` | **可用**：podman/本地沙箱、相似度分解、L1/L2/L3、代码资产化、KB 自动刷新 |
| `search_chart_assets` | **可用**：文本 / 表结构 / 图像 dHash 检索，设计分档与代码过滤，contact sheet |
| `adapt_chart_code` | **可用**：检索已验证模板 → 重绑数据路径/列/分隔符 → 试跑；缺失时降级并回报 `fallback_reason` |
| 选择候选图 | **可用**：`schema_path`（只给数据）、`design_tier`/`has_code` 过滤、去重、`render_sheet` |
| 批量复现 | **可用**：`reproduce-paper` / `ops enqueue --kind reproduce`，按配对置信度挑选，显式返回 `needs_data`/`needs_env` |
| 用户数据适配 + lint + manifest | **可用** |

尚未接线的部分：论文仓库依赖的自动安装已有逐篇镜像（`requirements.txt`/`DESCRIPTION`），但仓库内数据发现、
表格/SI 解析、扫描版 PDF OCR 仍待实现；对应限制写在功能说明里，不隐藏。

### 2.3 判断逻辑放在哪

"这篇论文里的图我能不能画、建议怎么画"这个判断，**不写死在 gaxis 里**：

- gaxis 提供事实：图的质量分、复现等级、依赖、输入 schema、许可证、沙箱运行结果、lint。
- 宿主 LLM 提供判断：值不值得复现、要不要换一种更清晰的表达、用户数据是否够。
- 这是 ADR-01/05 的直接结果：内核不做"论文理解"的自由发挥，只给可审计的事实与可运行的产物。

---

## 渲染前的确认：阈值写在配置里

`ChartPlan` 自带 `requires_confirmation / confirmation_threshold / confirmation_mode`，由 `gaxis.toml` 决定，宿主 LLM 不需要自己发明规则：

```toml
[confirmation]
mode = "auto"          # auto | always | never
min_confidence = 0.6   # auto 模式下，低于此值必须先与用户确认
```

- `auto`（默认）：置信度 ≥ 阈值可直接出图，低于阈值必须走 `open_questions` 确认；
- `always`：一律确认（投稿场景更稳）；
- `never`：不问（批量出图/脚本化，需自负风险）。

环境变量可临时覆盖：`GAXIS_CONFIRM_MODE`、`GAXIS_CONFIRM_MIN_CONFIDENCE`。配置优先级：`--config` > `$GAXIS_CONFIG` > `./gaxis.toml` > `~/.config/gaxis/config.toml` > 默认值；`pixi run gaxis config` 可查看生效值。模板见 `gaxis.example.toml`。

## 多面板：先单面板，再后期组合（已定）

用户先逐个完成单面板图（每张都是独立 figure：自己的 `figure.py`/`figure.R`、manifest、lint），后期再做拼版。为此现在就把两个前提做进去了：

1. **面板脚本可被"源引入"而不落盘**：设置 `GAXIS_PANEL_SOURCE=1` 运行 `figure.R` / `figure.py`，脚本只构建图对象不写文件 —— patchwork/cowplot（R）或 subfigure（matplotlib）可以直接拿它排版，矢量输出不被栅格化。
2. **证据链可组合**：每张面板都有 `figure_id` + manifest（`code_sha256`、`data.sha256`），将来的 `compose_panels` 只需引用子 manifest，不用重新渲染。

`compose_panels`（契约 v2.1）已经可用：把已渲染面板的 **PDF** 直接摆到一页（矢量保留、不重绘），
按 `ROWSxCOLS` 或自动网格排列，可加 A/B/C 标注，输出 `CompositionManifest`：

```
CompositionManifest {
  composition_id, panels: [{manifest_id, label: "A"|"B"|…, code_sha256}],
  layout: (rows, cols), preset, width_mm/height_mm, output_pdf/output_png, lint
}
```

R 路线（首选，用户指定）：`patchwork`/`cowplot` 源引入面板脚本 → `wrap_plots`/`plot_grid` → 统一 `ggsave` 出 PDF/SVG；兜底路线：矢量合并（`pdfjam`/`qpdf`）或 `magick`（会栅格化，不用于投稿）。多面板的期刊尺寸/字号规则需要单独一套预设（例如 183 mm 双栏、面板标签 8 pt 粗体），到 M4 再与 `[presets]` 一起补。

## 背景流程：定期抓取与复现（模块 H）

不是 MCP 工具，是常驻之外的定时任务：

1. 按质量分排序抓取论文（A）；
2. 解析图、caption、引用段、仓库代码（B）；
3. 建环境、造输入 schema、沙箱运行、渲染比对、标 L1/L2/L3（C/D）；
4. 写入 `paper-kb`（非联邦 source，见 `docs/gbrain-integration.md`）；
5. 检查点落库，中断可续；低等级资产入库但检索降权并标注原因（ADR-10）。

它的产物就是服务 1/2 的"弹药"。验收指标见 `dev/plan.md` §8.2/8.3（L1+L2 运行成功 ≥70%，L1 视觉通过 ≥60%，Top-5 命中 ≥70%）。

---

## 两条流程对知识库的要求（已按此设计）

每个资产页（gbrain `type: analysis`）至少要能回答：

| 字段 | 服务的用处 |
|---|---|
| `chart_type` + `visual_grammar`（文本） | 服务 1 的"文字描述找图"；服务 2 的"同类图" |
| `reproduction_level` / `sandbox_run_status` | 检索降权、可信度、服务 2 的"能不能直接抄" |
| `dependency_hints` / `input_schema_hints` | 服务 2 的适配可行性判断 |
| `code_path` + `code_sha256` | 交付物与可审计性 |
| `image_path`（相对路径，由 asset_id 解析） | 多模态宿主直接看图，不经 gbrain |
| `license` | 传染性许可证只重写逻辑，不直接复用 |
| `paper_id` / `doi` / `caption` / `citing_paragraph` | 引用与溯源 |

页面格式参考 `examples/paper-kb-page.example.md`；检索已验证支持 `--where chart_type=line --where reproduction_level=L1`。

---

## 已确认（2026-11-18）

1. 入口接受**文档（PDF）与 DOI / PubMed ID 等标识符** —— 已实现离线分类与去重，联网解析在 M1。
2. 服务 2 **知识库优先**：先解析论文里的插图需求，库里有符合的先给用户看；用户不满意才深度解析论文实现 —— `mode="kb_first"` 为默认，`full` 才付解析/复现代价。
3. **确认阈值写进配置文件**，`auto/always/never` + `min_confidence`，宿主不用自己判断 —— 已实现。
4. **多面板后期做**：先单面板，再用 R（patchwork/cowplot）组合 —— 已加"源引入不落盘"钩子，`compose_panels` 排入 M4。
