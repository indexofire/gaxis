# 常见问题

## 安装与环境

### 一定要用 pixi 吗？

推荐。gaxis 同时需要 Python 3.12、matplotlib、R + ggplot2，pixi 一次装好并且锁定版本。
用其他环境时，至少要保证这些依赖和 Python 3.12。

### 没有 podman 能测试吗？

能。出图、选图、适配、拼版、KB 检索都不需要 podman。复现时可以用 `--engine local`，
但报告会写明没有隔离，**不要把本地运行当作安全执行的证据**。生产复现请装 rootless podman。

### 没有 gbrain / ollama 能测试吗？

能。`[knowledge] enabled = false` 或 `GAXIS_KB_ENABLED=false` 时，检索返回 `degraded: true`，
其余功能照常。嵌入模型（bge-m3）只影响语义检索；关键词检索在 ollama 不可用时仍然工作。

### 知识库要提交到 git 吗？

不要。KB 页面由 manifest 重建，`data/` 已在 `.gitignore`。新机器上：

```bash
pixi run gbrain-init
pixi run gaxis kb seed
pixi run gaxis kb ingest
```

## 数据

### 支持哪些数据格式？

当前是分隔文本：CSV 与 TSV（自动识别分隔符，UTF-8、可带 BOM）。
Excel / Parquet / JSON 尚未支持，请先导出为 CSV。

### 我的列名不是英文怎么办？

可以。列名只作为标识符使用，图上的标签可以先由列名生成，再在 `figure.py` 里改成中文/单位。
注释和 `SPEC` 里的列名必须与表头一致。

### 数据里有缺失值怎么办？

渲染时按 `""`、`NA`、`n/a`、`nan`、`None` 识别为缺失；需要更复杂的缺失策略时，先清洗再交给 gaxis，
或在生成的脚本里改。

## 出图

### 为什么 lint 报 L005（字体回退）？

预设要求 Arial/Helvetica 系列，系统没有时回退到 Liberation Sans 等。回退会写进 lint，
不会静默替换。安装字体或调整预设的 `font_family` 后重跑。

### 生成的脚本可以改吗？

可以，而且应该改——它是交付物。注意：改完后它就不再与 manifest 的 `code_sha256` 对应；
如果要保留证据链，把改动同步进模板或重新渲染。

### 为什么同一份数据两次渲染的 `figure_id` 一样？

`figure_id` 由 `PIPELINE_VERSION + 数据 hash + spec` 决定，确定性是有意的。换预设、换列、换数据都会变。

## 选图与知识库

### `kb seed` 要多久？

7 预设 × 6 图型 × 2 后端 = 84 个模板，本机约 2.5 分钟，可离线，幂等。

### 为什么检索不到模板？

`search_chart_assets` 默认只查 `type: analysis`（论文图）。模板用 `kb search` 的普通查询也不会返回，
这是设计：模板通过 `adapt` 的精确 slug 解析，不混进论文候选。

### contact sheet 里的图和终端顺序对不上？

sheet 按返回顺序编号（`#1…`），终端也是同一顺序。若顺序不同，检查是否用了 `--tier`/`--has-code`
之类的过滤（过滤发生在服务端，两边应一致）。

## 复现

### `needs_data` 是什么意思？

脚本要读一张表，但你没给 `--data`，也没开 `--synthetic`。这不是失败，是明确的输入缺口。

### `needs_env` 是什么意思？

沙箱镜像不可用（podman 缺失、构建失败、拉取失败）。看 `sandbox_report.notes`。

### 为什么大多数真实论文跑不出 L1？

两个常见原因：论文仓库可能不带原始数据；依赖没有锁定导致构建失败。gaxis 会明确分级与说明，
不会把"跑起来了"冒充成"复现了"。

### 复现后 KB 里的等级没变？

只有走 `reproduce_chart_code` 的路径会自动刷新。手工改 manifest 后要 `pixi run gaxis kb ingest`。

### GPL 代码为什么不能进模板？

许可证是门控：copyleft 代码可以被记录（用于理解逻辑），但不会被复制进模板或在沙箱里执行。
这是产品规则，不是 bug。

## MCP / 宿主

### 为什么没有 token 启动不了 server？

生产传输必须带 Bearer token（ADR-02）。`stdio` 只用于本地调试。

### 宿主看不到 D3 工具？

宿主按 profile 过滤 `data_class`。cloud profile 只放行 D1；`render`/`adapt`/`compose` 是 D3。

### 工具契约变了怎么升级？

契约版本在 `scripts/freeze_contract.py`，快照在 `tests/contract_snapshot.json`。
改契约必须：升版本、刷新快照、更新 `docs/mcp-tools.md`、写 changelog。

## 开发

### 怎么跑全部检查？

```bash
pixi run check        # ruff + format check + mypy + pytest
pixi run test         # 只跑测试
pixi run docs-build   # 构建本站（strict）
```

### 测试会碰真实知识库吗？

不会。autouse fixture 设置 `GAXIS_KB_ENABLED=false`；需要 KB 的测试用 `tests/fake_gbrain.py`。
写测试时不要 shell 调用真实 `gbrain`。
