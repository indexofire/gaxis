# 05 多面板拼版

## 目标

把已经渲染好的若干面板拼成一页投稿图：矢量保留、编号 A/B/C、页面尺寸可控、合成过程有 manifest。
可选 `--uniform` 让所有面板按同一预设与同一单元格尺寸**重渲染**，字号和线宽一致。

## 前提

每个面板必须已经渲染过（有自己的 `figure.py` 和 manifest）。拼版**不重绘**，只摆放 PDF 页面。

```bash
pixi run gaxis render --data examples/demo/expr.tsv --chart bar --preset nature_microbiology --out data/demo
pixi run gaxis render --data examples/demo/expr.tsv --chart line --x time_h --y od600 --out data/demo
```

得到两个 figure id，例如 `bar-b7d31efe17`、`line-3b81d186c6`。

## 基本拼版

```bash
pixi run gaxis compose \
  --panels bar-b7d31efe17,line-3b81d186c6 \
  --layout 1x2 --preset nature_microbiology \
  --out data/demo/composition
```

```
composition: composition-8cbe3c3a38
layout:      1x2  183.0x71.4 mm
pdf:         …/composition-8cbe3c3a38.pdf
png:         …/composition-8cbe3c3a38.png
  A  bar-b7d31efe17
  B  line-3b81d186c6
lint: clean
```

![拼版示例](/gaxis/assets/example-composition.png)

## 布局与标注

- `--layout ROWSxCOLS`；不传时自动：≤3 个面板用 1×n，4 个用 2×2，更多用接近正方形网格。
- `--no-labels` 去掉 A/B/C；默认加。
- `--width/--height`（mm）覆盖默认页面尺寸；默认用预设的双栏宽度。
- 面板可以用 figure id，也可以直接给 `manifest.json` 路径（自定义 `--out` 时方便）。

## 统一排版：`--uniform`

默认是"原样摆放"：每个面板保留自己渲染时的字号和几何。想统一：

```bash
pixi run gaxis compose \
  --panels bar-b7d31efe17,line-3b81d186c6 \
  --layout 1x2 --preset asm --uniform \
  --out data/demo/composition
```

`--uniform` 会用合成预设和单元格尺寸**重新渲染每个面板**（用各自 manifest 里的 spec 和数据），
然后摆放。因此：

- 字号、线宽、字体一致；
- 每个面板的数据文件必须仍可读，否则会明确报 `data_not_found`；
- 合成 manifest 的 `panels[].manifest_id` 指向**重渲染后的**面板，`code_sha256` 也是新的。

![统一排版示例](/gaxis/assets/example-composition.png)

## 合成 manifest

```bash
pixi run gaxis manifest data/demo/composition/composition-8cbe3c3a38.json --json
```

```json
{"composition_id": "composition-8cbe3c3a38",
 "panels": [{"manifest_id": "bar-b7d31efe17", "label": "A", "code_sha256": "…"}],
 "layout": [1, 2], "width_mm": 183.0, "height_mm": 71.4,
 "uniform": false, "lint": {"ok": true}}
```

它是拼版的证据：每个面板的代码 hash 都在里面，任何面板被替换都能追到。

## 限制（明确的设计边界）

- 只接受矢量面板：PNG-only 面板会报 `panel_not_vector`，不会静默栅格化。
- 布局只支持矩形网格：没有嵌套（1×3+2）、没有跨面板共享轴、没有图例合并。
- `--uniform` 是"重渲染后再摆"，不是"在拼版阶段改各面板内部布局"。

## 检查点

- [ ] 输出 PDF 打开后每个面板仍是矢量（可选中文字/放大不糊）；
- [ ] 编号与 `panels[].label` 一致；
- [ ] 页面尺寸与 `width_mm/height_mm` 一致（±2%）；
- [ ] 合成 lint 为 clean。

## 常见问题

**`figure_not_found`**：id 不在 `data/renders` 也不在数据目录里。用 `manifest.json` 路径更稳。

**`bad_layout`**：网格放不下这么多面板。增大网格（如 `2x2`）或减少面板。

**`panel_not_vector`**：某个面板只渲染了 PNG。重新 `render --formats pdf`。
