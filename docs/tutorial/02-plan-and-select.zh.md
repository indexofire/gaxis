# 02 需求或数据 → 选图

## 目标

在动手画之前，先从知识库里拿到**可看的候选图**，人工选一张，再决定是"照它的结构渲染"还是"适配它的代码"。
这一节完全离线（KB 已 seed 的情况下）。

## 方式 A：给一句话需求

```bash
pixi run gaxis plan "grouped bar with error bars, Nature Microbiology"
```

输出一份数据无关的计划：图型、需要的列角色、风格提示、待确认问题、以及知识库里的匹配案例
（`matches[]`，含缩略图路径与分数）。

## 方式 B：只给数据

不用编 query。gaxis 会先给表做画像，推断图型和编码，再用它检索：

```bash
pixi run gaxis kb search --schema examples/demo/expr.tsv --k 8 --sheet
```

```
8 hit(s)  degraded=False
sheet: /…/data/kb/sheets/search-3b5827d227/contact-sheet.png
  pdf-0883b2ad/fig-1   bar    L2   sim=- img=-
  ...
```

!!! tip "候选集要能看"
    `--sheet` 会生成编号 contact sheet（`#1 … #N`），这是给**人**选图用的；纯 JSON 返回适合宿主渲染。

![候选图 contact sheet](/gaxis/assets/example-candidates.png)

## 过滤：只留下值得选的

```bash
# 只要设计评为 gold 的
pixi run gaxis kb search "bar chart" --tier gold

# 只要有代码记录的（后续可复现）
pixi run gaxis kb search "bar chart" --has-code

# 相似图去重（默认开；--no-dedupe 关闭，用于排查）
pixi run gaxis kb search "bar chart" --k 20
```

可组合：`--tier gold --has-code --chart bar`。

## 用图片找图

```bash
pixi run gaxis kb search "bar chart" \
  --image data/corpus/single-figures/review/cand-03.png --k 5
```

感知哈希（dHash）按形状排序，输出 `img=0.66` 这样的相似度。它是**形状信号**，不是语义模型：
能找到"长得像"的图，找不到"意思像但结构不同"的图。

## 选一张，再渲染

假设你选中 `pdf-0883b2ad/fig-1`（或某个模板），渲染时把它记下来：

```bash
pixi run gaxis render --data examples/demo/expr.tsv --preset asm \
  --source-asset template:asm-bar-python --out data/demo
```

两个效果：

1. `manifest.asset_ids` 记录来源资产——图不再是无出处的；
2. 追加一条选择记录到 `data/kb/selections.jsonl`：

```json
{"recorded_at": "...", "asset_id": "template:asm-bar-python", "action": "render",
 "figure_id": "bar-43e3d19d74", "preset": "asm", "chart_type": "bar"}
```

选择反馈是**追加只写**的本地日志，用来校准排序；写入失败会记 warning，不会阻断渲染。

## 选"渲染"还是"适配"？

| 你的情况 | 选择 |
|---|---|
| KB 里是论文图，但你没有它的数据/代码 | 用它的**结构**作为参考，`render` 自己的数据（`--source-asset` 记来源） |
| KB 里有**验证过的模板**，且列名不同 | `adapt`（下一节），复用模板代码，只改绑定 |
| 你有一篇论文的代码且已经复现 | `kb adopt` → `adapt`（第 04 节） |

## 检查点

- [ ] `contact-sheet.png` 存在且编号与终端顺序一致；
- [ ] 选中的资产 id 出现在 `manifest.asset_ids`；
- [ ] `data/kb/selections.jsonl` 有对应记录；
- [ ] `--tier gold` 真的只返回 gold（否则说明页面 frontmatter 没有 `design_tier`，先跑 `quality backfill`）。

## 常见问题

**`bad_parameter: give a query, a schema_path, or both`**：两者都为空。至少给一个。

**候选为空但 KB 有页面**：先看 `gaxis kb status` 是否 `available=False`；再看查询是否过于具体。
严格过滤（如 `--chart heatmap`）无结果时，gaxis 会自动回退到纯文本匹配并在 message 里说明。

**缩略图缺失**：页面的 `image_path` 指向的文件不存在（数据目录被清过）。重跑 `gaxis kb ingest`，
它会按 manifest 重建页面与路径。
