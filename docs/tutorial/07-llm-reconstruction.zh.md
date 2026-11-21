# 07 LLM 重建（作者代码不可用时）

## 目标

当论文**没有公开代码**，或代码已经跑不起来（依赖漂移、数据缺失）时，仍然得到一张接近原图的图，
并且**明确记录**这是模型写的，不是作者代码。

!!! warning "这不是作者代码复现"
    `reproduce` 运行作者脚本；`reconstruct` 让视觉模型写一个新脚本，再用**同一套沙箱与比对器**评判。
    manifest 记录 `reproduction.method = llm_reconstruction`（或 `llm_repair`）、模型名和每轮相似度；
    同一等级下，检索会优先作者代码复现。

## 什么时候用

| 情况 | 命令 |
|---|---|
| 没有代码候选，或 `pairing_confidence` 太低 | `reconstruct` |
| 代码能跑但视觉相似度低（L3） | `reconstruct --repair`（从作者脚本出发修） |
| 代码直接失败（依赖、版本、缺数据） | `reconstruct --repair` |
| 整篇论文批量补齐 | `reproduce-paper --reconstruct-missing` |

## 配置模型

空字段继承 `[design]`，一个视觉端点同时配置两处：

```toml
[reconstruct]
enabled = true
max_rounds = 3
target_similarity = 0.85
# base_url/model/api_key_env 为空时继承 [design]
```

```bash
export GLM_API_KEY="…"        # 或你的 api_key_env 指定的名字
```

### 模型选择

重建需要模型**既能看图、又能写对代码**，这种组合比纯视觉评审稀缺。循环能靠确定性修复
（补 `import matplotlib`、把 `plt.use` 改成 `matplotlib.use`）和最多 `max_rounds` 轮修正容忍弱代码，
但无法凭空补出模型没理解的几何。

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --model glm-5.3-flash --timeout 900 --max-side 768
```

实测（2026 年 *npj Science of Food* 复合图，裁成单面板，GLM-4.5V，2 轮）：Sankey 面板 0.43、
网络图面板 0.37（均为 L3，结构接近但像素不接近）；简单柱状图用 `glm-5.3-flash` 约 0.72（L2）。
最新视觉模型生成长代码时可能超过请求超时；可提高 `--timeout`、降低 `--max-side`，或改用更小的面板。

建议：优先作者代码（`reproduce`）；只对单面板图表用重建，尽量给 `--data`；把 L3 重建当作风格参考，
而不是复现证据。

## 单图

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --engine podman
```

```
manifest: pdf-<sha8>/fig-1
method:   llm_reconstruction   model: glm-4.5v   rounds: 2
engine:   podman   level: L2
similarity: 0.781   history: [0.642, 0.781]
code:     data/assets/code/pdf-.../recon-<sha8>/figure.py
kb:       refreshed
```

修复已有作者脚本（如果模型没有改动脚本，结果仍记为 `method = author_code`）：

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --repair --rounds 3
```

有数据时（模型会被要求读 `GAXIS_DATA`，而不是自行编数值）：

```bash
pixi run gaxis reconstruct pdf-<sha8>/fig-1 --data my_table.csv
```

## 一轮里发生什么

1. 模型收到参考图、caption、图型与视觉语法提示，必须返回一个独立的 matplotlib 脚本
   （仅标准库 + matplotlib + numpy）；
2. 脚本先静态扫描，再在**离线沙箱**中运行（无网络、只读根、资源限制）；
3. 渲染出的位图与论文图用与 `reproduce` 相同的可解释指标比对（相关度、MAD、边缘、墨量、长宽比）；
4. 低于 `target_similarity` 时，把渲染图、相似度分解和 traceback 再交给模型，返回修正后的脚本；
5. 保留最好的一轮：脚本复制到 `data/assets/code/…`，更新 manifest，刷新 KB 页面。每次运行都有独立的
   `data/recon/<paper>__<fig>/<时间戳>-<模型>/` 目录，后一次运行不会覆盖前一次的图或代码；每轮写
   `attempt.json`，整次运行写 `reconstruction.json`。

`level` 仍由 `[reproduction]` 阈值决定，描述**视觉接近程度**；`method` 描述**来源**。两者都入库，
检索先按等级、再按 `author_code` 优先于 `llm_*` 排序。

## 批量回退

```bash
pixi run gaxis reproduce-paper pdf-<sha8> --reconstruct-missing
```

先前 `skipped`（无代码）、`needs_data`、`needs_env`、`failed` 的图会被重建；成功的显示为
`reconstructed` 并带等级。作者代码复现永远不会被替换。

## 限制

- **不适合示意图、拼版、显微图**：生成的图表无法诚实复现示意图或照片面板，gaxis 仍会拒绝把它们
  当数据图；
- **近似数据**：没有 `--data` 时模型从图上读数，数值是近似的；manifest 记录 `data_source: none`，
  不要把它当作数据级复现；
- **模型质量决定上限**：多轮能改善，但弱模型会平台化；`similarity_history` 告诉你加轮是否值得；
- **成本与延迟**：每轮一次模型调用 + 一次沙箱运行，默认 3 轮、0.85 提前停止；
- **用户数据不出本机**：模型只看到公开的论文图与 caption；输入表挂载进沙箱，不发送到端点。

## 检查点

- [ ] `manifest.reproduction.method` 是 `llm_reconstruction` / `llm_repair`（不是 `author_code`）；
- [ ] `similarity_history` 每轮一项，与 attempts 一致；
- [ ] 生成的候选带 `generated: true` 与 `code_sha256`；
- [ ] `kb_refresh` 不是 `failed`，检索结果能看到 method。
