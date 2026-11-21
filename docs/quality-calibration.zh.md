# 抽取质量校准（是门槛，不是评判）

> **范围：**本文档讨论的是*抽取门槛*——即该文件能否被使用。它并非衡量图表是否优秀的标准；美观性与信息设计在 `docs/design-quality.md` 中单独评判。早先将该分数校准为“质量”的尝试是无效的，并已在该文档中作为警告记录。

抽取分数决定某个资产是否可以被复现或被索引。它必须可解释，因此它是由 `[quality]` 中带权重的组件构成，而不是隐藏在代码里的公式。

| 组件 | 得分为 1.0 的条件 | 为什么重要 |
|---|---|---|
| `caption` | 说明文字超过 20 个字符 | 没有说明文字，资产只是一张图片，而非知识 |
| `artwork` | 存在图表图像 | 仅含说明文字的资产仍会被索引，但无法被复现 |
| `resolution` | 最长边 ≥ 900 px | 在印刷尺寸下清晰可读 |
| `area` | 裁剪覆盖页面的 5–95 % | 排除整页扫描件和杂散的标志 |
| `vector` | 源图像是矢量格式 | 矢量图在任何尺寸下都能清晰渲染 |
| `cited` | 正文引用了该图表 | 可以作为示例被检索到，并有语义锚定 |
| `crop_clean` | 像素检查判定裁剪内容是图表 | 能捕获正文的裁剪、空白区域、带底色的扫描件，以及在边框处被裁断的图表 |

`crop_clean` 信号（全部基于 600-px 缩减图，见 `src/gaxis/quality_image.py`）：

- 空白裁剪（几乎没有墨迹）→ 0；
- 正文文本：≥6 条高度近似相等（CV < 0.2）、由空白行分隔的水平墨迹带，且以短水平笔画为主 → 0.35；
- 外框墨迹密集（图表被裁断）→ −0.25；
- 大面积浅色但饱和度高的背景（带底色的扫描件）→ −0.2。

细线条图表（系统发生树、折线图、散点图）仅凭行程长度会看起来像文本，这正是需要墨迹带测试的原因——它是在一棵树被误判为文本之后加入的。

实现：`src/gaxis/quality.py` + `quality_image.py`；默认值位于 `[quality]`；每个清单（manifest）都会把该分数存储在 `geometry.crop_clean` 中。在该组件出现之前抽取的清单可以通过 `pixi run gaxis quality backfill` 更新（重新计算并重新摄取）。

## 操作流程（20–30 个图表就足够了）

```bash
pixi run gaxis quality sheet                # sheet.md + contact-sheet.png + rankings.template.csv
# rank 1..N in sheet.md by "how usable is this extraction", then:
cat > rankings.csv <<'CSV'
manifest_id,human_rank
pdf-958cda27/fig-1,1
pdf-958cda27/fig-3,2
CSV
pixi run gaxis quality calibrate rankings.csv        # or pass sheet.md directly
pixi run gaxis quality calibrate data/calibration/sheet.md --json
```

重新生成已包含排名的工作表（sheet）会被拒绝（`sheet_has_ranks`）；只有在你打算丢弃排名时才使用 `gaxis quality sheet --force`。

需要评判的内容（评分标准见工作表头部）：

1. 说明文字是否完整且自解释？
2. 图像在印刷尺寸下是否清晰——裁剪的是图表本身而非正文？
3. 图表是否完整呈现（而非片段或单个分图）？
4. 正文是否引用了它？

**不要**按论文有多有趣来排名；这个分数关注的是抽取的忠实度。

## 校准报告的内容

- `baseline` — 当前分数与你的排名之间的 Spearman ρ。
- `best` — 对六个权重进行坐标下降后的 ρ（乘性与加性移动，因此被置零的组件可以复活）。
- `component_spearman` — 哪些组件确实与你的判断相关；负值是对抽取器的缺陷报告，而不仅仅是权重问题。
- 一个可直接粘贴的 `[quality]` 配置块。

计划中的验收标准：分数排序与人工排序之间的 **ρ ≥ 0.7**（Spearman）。低于此值，说明权重或抽取器有误；应首先报告哪个组件不一致。

## 状态

`gaxis quality sheet` 已基于当前语料库（10 个图表，SE02 + PLOS + 演示）生成到 `data/calibration/`，并带有 `crop` 列。校准**尚待人工排名**——填写 `rankings.template.csv`（或工作表的最后一列）并运行 `gaxis quality calibrate`。

状态说明：当前语料库过于同质（每个图表的得分都在 0.73–0.87 之间，因为它们都有说明文字、图像、分辨率和引用）。有意义的校准还需要覆盖各种失败模式：来自预印校样（pre-proofs）的仅含说明文字的资产、正文的裁剪、低分辨率扫描件、被裁断的图表。这些都可以被表示（`crop_clean` = 0.35、`artwork` = 0、`resolution` = 0），因此下一步校准工作是再摄取 10–20 篇更多样化的论文，而不是修改公式。
