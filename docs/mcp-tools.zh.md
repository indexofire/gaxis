# MCP 工具参考 — 契约 v2.1

gaxis 内核与每个宿主之间的冻结表面。事实来源：
`src/gaxis/models/tools.py`；快照：`tests/contract_snapshot.json`；使用
`pixi run python scripts/freeze_contract.py` 刷新（仅在有意的版本号提升之后）。

## 0. 传输、认证与生命周期

| 条目 | 值 |
|---|---|
| 传输方式（生产） | Streamable HTTP，`http://127.0.0.1:8770/mcp` |
| 传输方式（仅调试） | stdio（`gaxis-mcp --transport stdio`） |
| 认证 | `Authorization: Bearer $GAXIS_MCP_TOKEN`；缺少该令牌时服务器拒绝以 HTTP 方式启动 |
| 绑定 | 默认绑定回环地址；对所配置的主机提供 DNS 重绑定防护 |
| 健康检查 | `health` 为只读；可安全用于定时器与受监督的重启 |
| 生命周期 | 服务器是独立进程；宿主可自由连接与断开（ADR-02） |

启动服务器：

```bash
export GAXIS_MCP_TOKEN="$(openssl rand -hex 24)"
gaxis-mcp --transport http --host 127.0.0.1 --port 8770     # endpoint: /mcp
```

客户端（宿主、notebook）应使用类型化客户端，而非原始 JSON-RPC：

```python
from gaxis.client import GaxisClient
from gaxis.models.tools import RenderRequest

async with GaxisClient("http://127.0.0.1:8770/mcp", token=token) as gaxis:
    schema = await gaxis.describe_data_schema("/abs/results.tsv")
    figure = await gaxis.render_chart_from_data(
        RenderRequest(data_path=schema.data_schema.path, preset="nature_microbiology")
    )
```

内核错误以 `{"status": "error", "code", "message", "hint"?}` 的形式返回；`GaxisClient` 会抛出
`GaxisError`，因此调用方按错误码分支处理，而不是解析文字描述。

工具命名：gaxis 暴露裸名称（`render_chart_from_data`）。为工具添加命名空间的宿主（bacmap）会在自己一侧重命名（`bacmap_chart_render`）—— 重命名是适配层的关注点，绝不是内核的。

## 1. 门控元数据（为什么每个工具都有一个）

每个工具在其机器可读的规格中声明：

| 字段 | 含义 |
|---|---|
| `data_class` | `D1` 公开 … `D4` 仅限本地。当调用会读取本地用户文件时使用 `D3` |
| `side_effects` | 人类可读的列表；为空表示该调用不会造成变更 |
| `needs_network` | 仅论文获取类工具为 true |
| `cost` | `ms`、`s`、`min`、`10min+` —— 供宿主侧调度与 UI 使用 |
| `implemented` + `milestone` | 让宿主隐藏桩实现，而不是暴露失败 |

实施数据策略的宿主（bacmap `cloud` 配置 = D1 上限）会在调用**之前**据此过滤。`pixi run gaxis tools` 会打印整个工具目录。

## 2. 工具

### 2.1 `health` — D1，无副作用

```json
// request
{}
// response
{
  "ok": true,
  "version": "0.1.0",
  "data_root": "/…/data",
  "python_backend": true,
  "r_backend": true,
  "presets": ["asm", "cell_host_microbe", "default", "isme", "microbial_genomics", "nature", "nature_microbiology"],
  "stages": {"render_chart_from_data": "ready", "search_chart_assets": "ready"},
  "message": "5 palettes, 7 journal presets"
}
```

绝不触发渲染、下载或写入。用于存活检测，以及在请求 ggplot2 图形之前验证 R 后端是否确实已安装。

### 2.2 `describe_data_schema` — D3（跟随输入文件），只读

```json
// request
{"data_path": "/abs/path/results.tsv"}
// response (abridged)
{
  "data_schema": {
    "path": "/abs/path/results.tsv",
    "format": "tsv",
    "delimiter": "\t",
    "n_rows": 48,
    "sha256": "…",
    "columns": [
      {"name": "genotype", "kind": "categorical", "n_unique": 4, "missing_ratio": 0.0,
       "sample_values": ["WT", "dpsA", "rpoS"], "unit_hint": null},
      {"name": "expr_fpkm", "kind": "numeric", "n_unique": 47, "missing_ratio": 0.0,
       "sample_values": ["114.93", "124.35", "110.87"], "unit_hint": "FPKM"}
    ]
  },
  "suggested_spec": {"chart_type": "bar", "x": "genotype", "y": "expr_fpkm", "hue": "condition", "preset": "default"},
  "summary": "48 rows x 6 columns (results.tsv)\n- `genotype`: categorical, 4 unique, 0% missing, …"
}
```

代理契约：先调用此工具，然后要么接受 `suggested_spec`，要么覆盖特定字段。
错误：`data_not_found`、`data_unreadable`。

### 2.3 `render_chart_from_data` — D3，执行沙箱化脚本

```json
// request
{
  "data_path": "/abs/path/results.tsv",
  "chart_type": "bar",
  "x": "genotype", "y": "expr_fpkm", "hue": "condition",
  "preset": "nature_microbiology",
  "backend": "r",
  "formats": ["pdf", "png"],
  "dpi": 600,
  "out_dir": "/abs/path/project/figures"
}
// response (abridged)
{
  "figure_id": "bar-f485e439e0",
  "manifest_path": "…/bar-f485e439e0/manifest.json",
  "code_path": "…/bar-f485e439e0/figure.R",
  "outputs": [{"format": "pdf", "width_mm": 89.0, "height_mm": 60.0, "bytes": 8421, "dpi": null}],
  "lint": {"issues": []},
  "duration_s": 1.9
}
```

保证：返回的脚本自包含（不导入 gaxis），manifest 携带 `data.sha256` + `code_sha256`，lint 错误会被报告而非隐藏。lint 结果不干净仍然算渲染成功 —— 策略由宿主决定。

错误：`unknown_column`、`not_numeric`、`missing_x`、`missing_y`、`render_failed`、`bad_parameter`。

### 2.3b `plan_chart_from_brief` — D1，已就绪（启发式）

服务流程 1 的入口：**无需数据**。将一句话转化为宿主 LLM 与用户共同收敛的计划。

```json
// request
{"brief": "grouped bar chart with error bars, Nature Microbiology, ggplot2, colour-blind palette"}
// response (abridged)
{
  "plan": {
    "brief": "…",
    "spec": {"chart_type": "bar", "preset": "nature_microbiology", "palette": "okabe_ito",
             "backend": "r", "x": null, "y": null, "hue": null},
    "required_columns": [
      {"role": "x", "kind": "categorical", "hint": "2-12 groups"},
      {"role": "y", "kind": "numeric", "hint": "measurement per observation (omit to count rows)"},
      {"role": "hue", "kind": "categorical", "hint": "grouping factor, 2-8 levels (colour/fill)"}
    ],
    "style_notes": ["error bars: mean ± SD across replicates by default; pass a `yerr` column …"],
    "open_questions": ["Error bars: SD, SEM, or 95% CI? (and how many replicates per group)",
                       "Attach the table (CSV/TSV, one observation per row) or describe its columns"],
    "confidence": 0.85
  },
  "matches": [], "degraded": true, "message": "knowledge base disabled ([knowledge] enabled = false) …",
  "requires_confirmation": false, "confirmation_threshold": 0.6, "confirmation_mode": "auto"
}
```

`requires_confirmation` 由 `gaxis.toml` 中的 `[confirmation]`（`mode` +
`min_confidence`）计算得出，因此宿主无需重新发明该策略。`mode="always"` 强制确认，
`"never"` 跳过确认，`"auto"` 将 `plan.confidence` 与阈值比较。

输出确定且双语（支持英文与中文简报）；未知方面会成为 `open_questions` 而不是默默猜测。列名有意保持为 `null` —— 因为表格尚不存在。
错误：`bad_parameter`（简报为空、preset 未知）。

### 2.3c `ingest_paper` — D1，`needs_network`，M1/M2

```json
// request
{"source": "10.1099/mgen.0.000001", "min_quality": 0.0, "reproduce": true, "timeout_s": 900}
// response today
{"paper_id": "", "manifest_ids": [], "charts_found": 0, "reproduced": {},
 "not_implemented": true, "message": "paper ingestion lands with M1 …"}
```

`source` 接受 DOI、arXiv id、URL 或绝对 PDF 路径。实现后将返回所创建的
`ChartReproManifest` id，宿主便可立即调用 `get_chart_manifest` /
`reproduce_chart_code` —— 服务流程 2。

### 2.4 `search_chart_assets` — D1，已就绪（M3）

```json
// request
{"query": "phylogenetic tree enterotoxin", "k": 3}
// response (real brain, 7 ingested manifests)
{"assets": [{"asset_id": "pdf-958cda27/fig-2",
             "paper_title": "A novel staphylococcal enterotoxin SE02 …",
             "doi": "10.1016/j.ijfoodmicro.…", "chart_type": null,
             "reproduction_level": null, "visual_similarity": null,
             "thumb_path": "/abs/data/assets/pdf-958cda27/figures/fig-2.jpeg",
             "design_score": 0.45, "design_tier": "dense", "usefulness_score": 0.57}],
 "total": 1, "degraded": false, "message": ""}
```

行为：

- 针对 **gbrain 源 `paper-kb`**（`federated=false`）运行，页面类型为 `analysis`；其文本由图注 + 引用段落 + 视觉语法 + 代码摘要组成，因此自然语言请求能够匹配。
- Frontmatter 过滤器被下推至 gbrain（`--where chart_type=…`）；层级排序与 preset 过滤器在检索之后应用，因为 gbrain 只支持等值比较。
- **严格的图表类型过滤绝不会隐藏文本匹配**：若其结果为空，则去掉该过滤重试查询，并在消息中提示 `no 'bar' asset matched; showing textual matches instead`。
- `schema_path`（可选）将表格转化为查询：对表格进行剖析，推断出图表类型与编码，由派生的文本/类型驱动检索，因此 `query` 可以为空。
  `design_tier`、`has_code` 与 `dedupe` 用于过滤结果集；`render_sheet: true` 会生成一张带编号的候选缩略图总览并返回 `sheet_path`。
- `query_image_path`（可选）切换到感知检索：查询图与候选缩略图以 dHash（64 位）计算指纹，按汉明相似度（`image_similarity`，0–1）排序，并以层级/设计/实用性作为平局决胜依据。这是一种*形状*信号，而非品味模型：它找出外观相似的图形，但不评判它们。无法读取的缩略图则不参与排序。
- 仅当 brain 被禁用或不可达时才会 `degraded: true` —— 绝不会因为其为空。
  `reproduction_level: null` 表示“尚未复现”，排序低于 L1/L2/L3。
- `design_score` / `design_tier` 来自设计评审器（`docs/design-quality.md`）；当美学尚未被评审时为 null。宿主可以按 `design_tier`（`gold`/`dense`）过滤。
- `usefulness_score` 回答“这是否属于值得复现的那类图形”（发表期刊、统计方法、子图丰富度、图注完整性、已验证代码）。检索先按
  `reproduction_level` 排序，再按 `0.7 × design_score + 0.3 × usefulness_score`（`[ranking]`），最后按文本得分。
- 资产由 `gaxis kb ingest`（幂等、基于哈希）执行插入或更新（upsert），或在 `ingest_paper(mode="full")` 之后且 `[knowledge] auto_ingest = true` 时自动完成。

### 2.5 `get_chart_manifest` — D1，已就绪（M1）

```json
{"manifest_id": "pdf-958cda27/fig-3"}
→ {"manifest_id": "pdf-958cda27/fig-3", "found": true,
   "manifest": {"figure_ref": "Fig. 3", "chart_file": "assets/pdf-958cda27/figures/fig-3.jpeg",
                "caption": "Fig. 3. Effects of heat …", "citing_paragraph": "…",
                "chart_quality_score": 0.85, "geometry": {"page": 38, "pixel_width": 1000, …},
                "visual_grammar": {"chart_type": null, "notes": ["caption found on page 30",
                                   "artwork paired across pages …"]},
                "code_candidates": [], "reproduction": {"level": "none",
                                   "sandbox_run_status": "skipped"}}}
```

路径相对于数据根目录。`found: false` 时会附带一条消息，指出下一步操作（`ingest_paper`）。

### 2.6 `reproduce_chart_code` — D1，已就绪（M2），`cost: min`

成功时运行结果会被**资产化**：脚本被复制到 `data/assets/code/<asset>/<sha8>/`，manifest 的最后一个 `code_candidate` 以 `code_sha256` 指向该副本，且 KB 页面立即刷新（`sandbox_report.kb_refresh` 显示 `refreshed`/`unchanged`/`failed: …`）。`reproduction.data_source` 记录 `user` / `repo` / `synthetic` / `none`。

```json
// request
{"manifest_id": "pdf-958cda27/fig-3", "code_path": "/abs/figure.py",
 "data_path": "/abs/data.csv", "engine": "podman", "allow_network": false, "timeout_s": 300}
// response (abridged)
{
  "manifest_id": "pdf-958cda27/fig-3",
  "level": "L1", "run_status": "success", "visual_similarity": 1.0,
  "engine": "podman", "code_sha256": "…",
  "outputs": [{"path": "…/reproduced.png", "format": "png", "bytes": 8421}],
  "sandbox_report": {"engine": "podman", "image": "gaxis-repro:py312", "image_id": "4f1e703b3a28…",
                     "network": false, "network_enforced": true, "read_only_root": true,
                     "scan": {"findings": [], "licences": [], "blocking": false},
                     "dependencies": ["matplotlib"]},
  "similarity_detail": {"score": 1.0, "correlation": 1.0, "edge_agreement": 1.0, …},
  "manifest_path": "…/manifests/pdf-958cda27__fig-3.json"
}
```

关键行为：

- 在 **rootless podman** 中运行：除非 `allow_network` *且* 配置允许，否则 `--network none`；只读根文件系统、tmpfs `/tmp`、`--cap-drop ALL`、`no-new-privileges`、内存/CPU/pids 上限。
- 先执行静态扫描：`os.system`/`subprocess`/`eval`/`exec`/`ctypes`/凭据路径会**阻断**运行（`level: "none"`、`run_status: "skipped"`，并记录原因）；网络使用仅为警告。
- 拒绝 copyleft 许可证（GPL/AGPL）—— 复用逻辑，而非代码。
- `local` 引擎仅供开发使用：它以当前解释器运行，报告会显示 `"network_enforced": false, "read_only_root": false, "warning": "no isolation"`。
- 评级：`similarity ≥ l1`（默认 0.85）→ L1；`≥ l2`（0.55）→ L2；成功运行但低于阈值 → L3；运行失败 → L3 并附带 stderr 末尾；被阻断 → `none`。每个层级都会在 manifest 中记录其原因。
- 更新后的 manifest 会被写回（`reproduction.*`、`code_candidates[]`），运行旁的 `reproduction.json` 记录扫描、沙箱报告与相似度分量。
- 目前仅支持 Python；`.R` 脚本会抛出 `unsupported_language`（R 镜像是一个独立任务）。

错误：`manifest_not_found`、`code_required`、`code_not_found`、`unsupported_language`、`data_not_found`。

### 2.7 `adapt_chart_code` — D3，已就绪（KB 模板）

```json
{"data_path": "/abs/path/results.tsv", "query": "bacterial growth curve with error bars",
 "asset_id": null, "preset": "asm", "backend": "python", "formats": ["pdf", "svg"], "dry_run": false}
→ {"figure_id": "line-…", "code_path": "…", "outputs": [...], "lint": {...},
   "source": "kb_asset", "asset_ids": ["a1b2…"], "fallback_reason": "", "not_implemented": false}
```

解析顺序：

1. `asset_id` —— 必须是**模板**页面（`type: template`）。论文图形资产会被明确拒绝（`fallback_reason` 会说明）；不会悄悄尝试对论文代码进行适配。
2. 否则使用与 `(preset, chart type, backend)` 精确匹配的模板，其中图表类型来自 `query`（`"grouped bar"`）或数据推断出的 spec。
3. 否则回退到内置模板，`fallback_reason` 会指出缺失的模板及修复方法（`gaxis kb seed`）。

经验证的模板是由 `gaxis kb seed` 生成的一次真实渲染：包含生成的脚本、lint 报告和 manifest。适配只重写人类会编辑的常量 —— 数据路径、输出目录、文件名主干、分隔符、编码意图 —— 绘图代码保持不动。每次重写都会被验证；模板结构出乎意料时抛出 `adaptation_failed`，而不是运行错误的代码。
`dry_run: true` 会生成脚本和 manifest 但不执行。

模板在本地播种（`gaxis kb seed`，7 种 preset × 6 种图表 × 2 种后端约需 2.5 分钟），并以 `type: template` 页面的形式存放在 `paper-kb` 源中，因此绝不会出现在
`search_chart_assets`（它查询 `type: analysis`）的结果里。

### 2.8 `compose_panels` — D3，已就绪

```json
{"panel_ids": ["bar-…", "line-…"], "preset": "nature_microbiology", "layout": "1x2",
 "width_mm": null, "height_mm": null, "labels": true, "out_dir": null}
→ {"composition_id": "composition-…", "panels": [{"manifest_id": "bar-…", "label": "A", "code_sha256": "…"}],
   "layout": [1, 2], "output_pdf": "…", "output_png": "…", "lint": {...}}
```

`uniform: true` 会在放置之前，按合成图的 preset 与单元格尺寸从各面板的 manifest 重新渲染每个面板，从而保证排版一致；默认行为则原样放置现有 PDF。

使用 PyMuPDF 将已完成的 **PDF** 面板排布在同一页上（保留矢量，不重新渲染），添加 A/B/C 字母标记，并在合成 manifest 中记录每个面板的 `code_sha256`。面板 id 是
`render_chart_from_data` 打印的 id，或指向某个面板 `manifest.json` 的路径；同样的操作也可通过 CLI 完成
（`gaxis compose --panels a,b`）。没有 PDF 输出的面板会被以 `panel_not_vector` 拒绝，而不是被悄悄栅格化；过小的布局会抛出 `bad_layout`。

## 3. 结果约定

- 结构化输出；需要 JSON 字符串的宿主在适配层边界进行字符串化。
- 每次失败都是 `{"code", "message", "hint?"}`，并带有稳定的错误码。
- 响应中的路径为绝对路径，且可被调用进程读取。
- `outputs[]` 的几何尺寸从产物中测量，而非从 preset 推断。
- `lint.issues[]` 使用 `docs/presets.md` 中记录的数字 `L0xx` 代码。

## 4. 版本演进

| 契约 | 日期 | 变更 |
|---|---|---|
| v1.0 | 计划 v2.0 | `search_chart_assets`、`get_chart_manifest`、`reproduce_chart_code`、`adapt_chart_code`、`health` |
| v1.1 | M0 脚手架 | + `describe_data_schema`、`render_chart_from_data`（ADR-14）；所有工具附带门控元数据；`adapt_chart_code` 随附内置模板回退 |
| v1.2 | 服务流程 | + `plan_chart_from_brief`（无数据规划）与 `ingest_paper`（按需论文摄取）；见 `docs/service-flows.md`（ADR-17） |
| v1.3 | 流程 2 精化 | `ingest_paper` 新增 `mode`（kb_first/full）、来源分类与去重 id；`plan_chart_from_brief` 新增所配置的确认策略（ADR-19/20） |
| v1.4 | M2 复现 | `reproduce_chart_code` 成为真实实现：`data_path`、`engine`、`code_sha256`、`sandbox_report`、`similarity_detail`、`manifest_path` |
| v1.5 | M1 完成 | 标识符解析（Crossref/arXiv/PubMed/PMC/Unpaywall）、PDF 下载、仓库链接 + 绘图脚本发现；摄取结果新增 `pdf_url`、`repository_urls`、`code_candidate_count`，请求新增 `with_code` |
| v1.7 | 设计分级 | `ChartAssetSummary` 新增 `design_score` 与 `design_tier`（gold/dense/reject） |
| v1.8 | 实用性 | `ChartAssetSummary` 新增 `usefulness_score`；检索按设计 × 实用性排序 |
| v2.1 | schema 检索 + 批量 | `search_chart_assets` 接受 `schema_path`、`design_tier`、`has_code`、`dedupe`、`render_sheet`（返回 `sheet_path`）；`ChartAssetSummary.has_code`；`ReproduceChartCodeResult` 在 `sandbox_report.kb_refresh` 中报告 KB 刷新；`RenderRequest.source_asset` 记录选择反馈 |
| v2.0 | 感知检索 + uniform | `search_chart_assets` 新增可选的 `query_image_path` 与 `image_similarity`（dHash 排序）；`compose_panels` 新增 `uniform`（按合成图的 preset 重渲染各面板） |
| v1.9 | 组合 + 适配 | 新增 `compose_panels` 工具；`adapt_chart_code` 现改为检索经验证的 KB 模板并报告 `fallback_reason`，而不是默默降级 |

破坏性变更需要：版本号提升、刷新快照、更新 `docs/mcp-tools.md`，并在
`CHANGELOG.md` 中添加说明。
