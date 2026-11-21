# 运维：摄取队列与组合

## 1. 带检查点的论文摄取（`gaxis ops`）

```bash
pixi run gaxis ops enqueue 10.1099/mgen.0.000001 10.1371/journal.pone.0000217 paper.pdf
pixi run gaxis ops run --limit 5 --retries 2 --stall-minutes 30
pixi run gaxis ops status            # counts, last errors, last run
pixi run gaxis ops verify            # requeue done jobs whose manifests vanished
pixi run gaxis ops status --reset all   # requeue failed jobs
```

- 队列存储在 `data/ops/queue.db`（SQLite）中：包含 `source`、`mode`、`status`
  （`pending|running|done|failed`）、`attempts`、`last_error`、`manifest_ids`。
- 每个来源都有自己的检查点。崩溃或网络故障会从队列恢复；`done` 状态的来源绝不会被重新摄取
  （按来源字符串去重——请使用规范的 DOI/ID）。
- 重试次数有上限，且仅针对瞬态故障（`resolution_failed`、`download_failed`、
  `pdf_unreadable`）；永久性故障（`unrecognised_source` 等）会进入 `failed` 并一直保持，
  直到执行 `--reset`。
- 成功的运行会返回 `manifest_ids`，它们同时也会记录在对应的队列行中，因此即使知识库被重建，
  后续步骤仍能核验当时生成了哪些内容。
- **停滞恢复**：因进程被杀而滞留在 `running` 状态的任务，一旦超过 `--stall-minutes`
  （默认 30），就会在下次运行时被重置为 `pending`。正是这一机制让定时器在无守护进程的情况下
  也能安全使用。

### 通过定时器运行

该队列可安全地由 systemd 定时器运行（无守护进程状态，每次运行一个进程）：

```ini
# ~/.config/systemd/user/gaxis-crawl.service
[Unit]
Description=gaxis paper ingestion queue

[Service]
Type=oneshot
WorkingDirectory=%h/repos/github/gaxis
ExecStart=%h/.pixi/bin/pixi run gaxis ops run --limit 10 --retries 2
```

```ini
# ~/.config/systemd/user/gaxis-crawl.timer
[Unit]
Description=Run gaxis ingestion every 6 hours

[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now gaxis-crawl.timer
systemctl --user list-timers gaxis-crawl.timer
```

目前已具备的自愈能力：

- **停滞检测**：超过 `--stall-minutes` 时限的 `running` 任务会被重置为 `pending`；
- **心跳**：每次运行都会写入 `data/ops/heartbeat.json`（finished_at、duration、processed、
  failed、reclaimed、队列计数）；`gaxis ops status` 可查看最近一次运行；
- **深度检查**：`gaxis ops verify` 会复查每个 `done` 任务的 manifest，并把证据已丢失
  （`data/` 被清理、恢复失败）的来源重新入队。没有 manifest 的 `done` 任务是在撒谎，
  因此会被纠正，而不是被掩盖。

### 复现论文图表

```bash
pixi run gaxis reproduce-paper pdf-<sha8>                 # suitable figures, best code first
pixi run gaxis reproduce-paper pdf-<sha8> --data table.csv
pixi run gaxis reproduce-paper pdf-<sha8> --synthetic     # labelled synthetic input
pixi run gaxis ops enqueue --kind reproduce pdf-<sha8> && pixi run gaxis ops run
```

- 适配性：图表需要有一个置信度达到或高于 `--min-confidence`（默认 0.5）的代码候选；
  已评为 L1/L2 的图表会被跳过，除非使用 `--force`。
- 结果是明确的：`reproduced`、`needs_data`（脚本请求了表格数据）、`needs_env`
  （沙箱镜像不可用）、`skipped`（无代码 / 低置信度）、`failed`。
- 合成输入根据脚本索引的列生成，并记录为 `data_source: synthetic`；以这种方式构建的图表
  证明的是代码能运行，而非论文中的数值。
- 每个复现的脚本都会被复制到 `data/assets/code/…` 中，其 manifest 页面也会在知识库中刷新，
  因此检索能立即看到新的复现级别。

## 2. 预置已验证模板（`gaxis kb seed`）

`adapt_chart_code` 会复用已验证模板的*绘图代码*，因此知识库中每个 `(preset, chart type, backend)`
组合至少需要一份通过 lint 检查的资源：

```bash
pixi run gaxis kb seed                                  # all presets, python + R (~2.5 min)
pixi run gaxis kb seed --preset asm --backend python    # narrower
pixi run gaxis kb seed --force                          # rewrite pages even if unchanged
```

- 每个模板都是一次真实的渲染：包含生成的脚本、PDF、lint 报告和 manifest，由与用户相同的
  流水线产出。lint 不通过的模板会被报告为失败，绝不建立索引。
- 脚本会被复制到 `data/assets/templates/<preset>/<chart>-<backend>/figure.<py|R>`，
  页面则存储 `code_path`、`code_sha256`、`reproduction_level: L1` 和 `type: template`。
- 页面的类型为 `type: template`，因此 `search_chart_assets`（查询的是 `type: analysis`）
  永远不会返回它们；适配时通过精确的 slug 来解析它们。
- 重复运行是幂等的：代码哈希未变化的会被跳过，发生变化的模板会被重写。
- 预置生成的图表不是论文证据：其复现级别为 L1 是因为流水线能逐字节复现它们，
  而不是因为某篇论文曾在沙箱中运行过。

## 3. 采用论文脚本（`gaxis kb adopt`）

`adapt_chart_code` 可以复用已复现的论文脚本，但前提是遵循一个明确、可检查的接口：
脚本必须通过 `DATA_PATH`（Python 赋值 / R 的 `<-`）读取输入。

```bash
pixi run gaxis kb adopt pdf-<sha8>/fig-1 --code path/to/script.py --preset asm
pixi run gaxis adapt --data my.tsv --asset template:paper-pdf-<sha8>-fig-1 --preset asm
```

- 采用过程从不运行代码；它只是把代码复制到 `data/assets/templates/paper/<id>/`，
  并记录 `origin: paper`、`interface: path`、`source_asset`、许可证和复现级别。
- 适配只重写 `DATA_PATH`（以及脚本声明的 `OUT_DIR`），然后在隔离的输出目录中运行脚本，
  并收集其写入的所有图表文件。
- 没有 `DATA_PATH` 绑定的脚本会被拒绝（`adoption_refused`）——gaxis 不会去猜测研究代码库的
  I/O。列名保持论文中的原样；请先映射你的表格。
- 列/编码不匹配的问题由运行本身报告（`render_failed` 附带 traceback），绝不会粉饰掩盖。

## 4. 多面板组合（`gaxis compose`）

面板先逐个渲染，每个面板都带有自己的脚本和 manifest。组合过程只对已完成的 **PDF** 进行排版
（不重新渲染），因此矢量内容得以保留，每个面板也保留其证据
（`code_sha256` 记录在 `CompositionManifest` 中）。

```bash
pixi run gaxis compose --panels bar-<id>,line-<id> --layout 1x2 \
  --preset nature_microbiology --out data/demo/composition
```

- 面板可以是图表 ID（由 `render` 打印输出）或指向面板 `manifest.json` 的路径——ID 会在
  `data/renders` 下以及数据根目录的任意位置解析，因此自定义的 `--out` 目录也能正常工作。
- 布局：`ROWSxCOLS` 或自动（≤3 个时 1×n，四个时 2×2，其余为网格）。
- 页面尺寸默认为预设的双栏宽度；可用 `--width/--height` 覆盖（mm）。
- 指定 `--labels` 时会添加面板字母 A/B/C（默认开启）。
- 输出：`composition-<id>.pdf`（外加 `.png` 预览）和 `composition-<id>.json`
  （`CompositionManifest`，包含面板 ID、标签、代码哈希、几何信息和 lint 结果）。
- `--uniform` 会按组合预设和单元格尺寸从每个面板的 manifest 重新渲染各面板，
  使各面板之间的字号和线条粗细保持一致。不加该选项时，面板按其原始渲染结果放置。
- lint 会对组合输出运行，因此几何/字体问题也会在此暴露。
- 限制：混用后端没有问题（两者都输出 PDF），但面板必须是**矢量**格式；
  仅含 PNG 的面板会被拒绝并报错 `panel_not_vector`。
