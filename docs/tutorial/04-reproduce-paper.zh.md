# 04 论文复现 → 代码入库

## 目标

把一篇论文变成可检索、可复现、可复用的资产：解析图与 caption → 找到代码 → 沙箱运行 → 视觉比对分级 →
**脚本自动资产化** → KB 页面刷新 → （可选）注册成模板。

这一节需要网络与 podman。

## 1. 入库一篇论文

```bash
# 本地 PDF
pixi run gaxis ingest examples/demo/paper.pdf --mode full

# DOI / arXiv / PubMed / PMC
pixi run gaxis ingest 10.1099/mgen.0.000001 --mode full
```

`--mode kb_first` 只解析图与 caption；`--mode full` 还会下载开放版 PDF、找代码仓库、克隆并挑选绘图脚本。

输出是 manifest 列表：

```
paper: pdf-0883b2ad
manifests: pdf-0883b2ad/fig-1, …
kb: 12 upserted, 0 failed
```

## 2. 看一篇论文有哪些图、哪些有代码

```bash
pixi run gaxis manifest pdf-0883b2ad/fig-1 --json
```

重点字段：

```json
{"code_candidates": [{"code_path": "…", "pairing_confidence": 0.82, "license": "MIT",
                      "packages": ["matplotlib==3.8", "seaborn"]}],
 "reproduction": {"level": "none", "sandbox_run_status": "skipped"},
 "usefulness": {"score": 0.71}}
```

`packages` 来自仓库的 `requirements.txt` / `environment.yml` / `DESCRIPTION`，用于构建逐篇镜像。

## 3. 复现一张图（单图）

```bash
# 用解析时发现的代码；没有数据时会明确告诉你
pixi run gaxis reproduce pdf-0883b2ad/fig-1 --code figure.py --engine podman

# 指定输入数据
pixi run gaxis reproduce pdf-0883b2ad/fig-1 --code figure.py --data my_table.csv
```

```
manifest: pdf-0883b2ad/fig-1
engine:   podman   run: success   level: L1
similarity: 0.93
```

`local` 引擎可用于开发，但报告会写明 `network_enforced: false, read_only_root: false`；
**不要把它当作安全执行的证据**。

## 4. 批量复现一篇论文

```bash
pixi run gaxis reproduce-paper pdf-0883b2ad
pixi run gaxis reproduce-paper pdf-0883b2ad --data table.csv
pixi run gaxis reproduce-paper pdf-0883b2ad --synthetic --min-confidence 0.6
```

它按代码配对置信度挑图，并给出明确状态：

| 状态 | 含义 | 你的动作 |
|---|---|---|
| `reproduced` | 跑成功，level 见括号 | 看相似度，决定是否 adopt |
| `needs_data` | 脚本要输入表，但没给 | `--data` 或 `--synthetic` |
| `needs_env` | 沙箱镜像不可用 | 检查 podman / 依赖，或改用 `--engine local` 仅做结构验证 |
| `skipped` | 没有代码或置信度低于阈值 | 换图，或降低 `--min-confidence` |
| `failed` | 代码跑了但失败（异常/超时/被拦截） | 看 `failure_reason` |

## 5. 复现成功后自动发生了什么

一次成功的复现会做四件事：

1. **脚本资产化**：复制到 `data/assets/code/<asset>/<sha8>/figure.py`，manifest 的候选指向这份副本，
   并带 `code_sha256`；
2. **manifest 更新**：`reproduction.level / visual_similarity / failure_reason / data_source / environment_lock`；
3. **KB 页面刷新**：同一调用内重投影页面，`sandbox_report.kb_refresh = "refreshed"`；
4. **检索可见**：立刻能在 `kb search` 里看到新等级和相似度。

验证：

```bash
pixi run gaxis kb search "bar chart expression" --k 3
# pdf-0883b2ad/fig-1   bar   L2   sim=0.775
```

## 6. 把复现过的脚本变成模板

```bash
pixi run gaxis kb adopt pdf-0883b2ad/fig-1 --code data/assets/code/pdf-0883b2ad__fig-1/<sha8>/figure.py
```

采纳有明确的接口契约：脚本必须通过 `DATA_PATH` 绑定输入（Python 赋值 / R `<-`）。
不满足就拒绝：

```
{"code": "adoption_refused", "message": "the script does not bind its input through DATA_PATH",
 "hint": "expose the input file as DATA_PATH (and optionally OUT_DIR) and adopt again"}
```

采纳后：

```bash
pixi run gaxis adapt --data my.csv --asset template:paper-pdf-0883b2ad-fig-1 --preset asm
```

适配只改 `DATA_PATH`（和脚本声明了的 `OUT_DIR`），然后运行、收集它写出的图。列名仍是论文的，
需要先映射你的表——这是刻意的：gaxis 不猜研究语义。

## 7. 没有数据：合成输入

```bash
pixi run gaxis reproduce-paper pdf-0883b2ad --synthetic
```

gaxis 从脚本实际索引的列名生成一张确定性表，并记录 `data_source: synthetic`。

!!! warning "合成数据能证明什么"
    它证明**代码能跑、结构能对上**；它**不能**支持"数据级复现"的结论。不要用合成数据的结果
    去声称 L1 的数值复现。

## 8. 队列化

```bash
pixi run gaxis ops enqueue --kind reproduce pdf-0883b2ad
pixi run gaxis ops run --limit 5
pixi run gaxis ops verify
```

队列会检查点、重试、回收停滞作业（见第 06 节）。

## 检查点

- [ ] `manifest.reproduction.level` 与你看到的一致；
- [ ] `data/assets/code/...` 里有脚本，且 `code_sha256` 与 manifest 一致；
- [ ] `kb_refresh` 是 `refreshed` 或 `unchanged`（不是 `failed`）；
- [ ] `kb search` 能按新的 level 排序到它；
- [ ] adopt 后的模板页有 `origin: paper`、`interface: path`。

## 常见问题

**`needs_data` 但论文仓库里明明有数据**：目前只支持你显式给 `--data`；仓库内数据发现尚未接线。
用 `--synthetic` 先验证代码，或手动指向仓库里的文件。

**`needs_env`**：逐篇镜像构建失败或 podman 不可用。看 `sandbox_report.notes`，它会说明是构建失败、
拉取失败还是镜像缺失。

**`reproduce` 被拦截（`level: none`）**：静态扫描发现危险调用，或许可证是 GPL/AGPL。这是结果，不是错误：
manifest 会记录原因。

**复现后 KB 还是旧等级**：只有通过 `reproduce_chart_code` 的路径才会自动刷新；如果你手工改了 manifest，
重新跑 `pixi run gaxis kb ingest`。
