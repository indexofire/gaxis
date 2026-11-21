# 配置参考

配置是一个 TOML 文件，加上少量环境变量覆盖。**坏配置会抛 `config_invalid`，绝不静默回退。**

## 查找顺序（先命中者生效）

1. `--config PATH`
2. `$GAXIS_CONFIG`
3. `./gaxis.toml`（项目）
4. `${XDG_CONFIG_HOME:-~/.config}/gaxis/config.toml`（用户）
5. 内置默认值

```bash
cp gaxis.example.toml gaxis.toml
pixi run gaxis config          # 查看生效值（含覆盖）
```

`data_root` 默认 `./data`，可用 `GAXIS_DATA_DIR` 覆盖。

## `[confirmation]` — 何时必须与用户确认

| 键 | 默认 | 说明 |
|---|---|---|
| `mode` | `auto` | `auto` 按置信度决定；`always` 一律确认；`never` 不问 |
| `min_confidence` | `0.6` | `auto` 模式下低于该值必须先确认 |

## `[render]`

| 键 | 默认 | 说明 |
|---|---|---|
| `timeout_s` | `180` | 单次渲染/脚本执行上限 |
| `default_preset` | `default` | CLI 未指定时的预设 |
| `default_backend` | `python` | `python` 或 `r` |

## `[ingest]` — 论文获取

| 键 | 默认 | 说明 |
|---|---|---|
| `default_mode` | `kb_first` | `kb_first` 或 `full` |
| `allow_network` | `true` | 关闭后只处理本地文件 |
| `timeout_s` | `900` | 单篇论文解析上限 |
| `min_quality` | `0.0` | 低于该提取质量不建 manifest |
| `contact_email` | `""` | Unpaywall/NCBI 的礼貌地址（建议填） |
| `max_download_mb` | `40` | PDF 大小上限 |
| `with_code` | `true` | 是否尝试定位代码仓库 |
| `repo_timeout_s` | `120` | 单仓库克隆上限 |
| `max_repos` | `2` | 每篇论文最多克隆的仓库数 |

## `[quality]` — 提取质量权重

| 键 | 默认 |
|---|---|
| `caption` | 0.28 |
| `artwork` | 0.18 |
| `resolution` | 0.14 |
| `area` | 0.09 |
| `vector` | 0.13 |
| `cited` | 0.08 |
| `crop_clean` | 0.10 |

改权重会改变已有分数：重新跑 `quality backfill` 并 `kb ingest`。

## `[usefulness]` — 有用性权重

| 键 | 默认 |
|---|---|
| `journal` | 0.35 |
| `statistics` | 0.20 |
| `verification` | 0.20 |
| `panels` | 0.15 |
| `caption` | 0.10 |

## `[ranking]` — 检索融合

| 键 | 默认 | 说明 |
|---|---|---|
| `design_weight` | 0.70 | 设计分权重 |
| `usefulness_weight` | 0.30 | 有用性权重 |

设计领先是有意的：强期刊不能把弱图推上来。

## `[design]` — 设计评审

| 键 | 默认 | 说明 |
|---|---|---|
| `judge` | `heuristic` | `heuristic`（离线客观特征）或 `vision` |
| `base_url` | `https://api.openai.com/v1` | OpenAI 兼容端点 |
| `model` | `gpt-4o-mini` | 视觉模型名 |
| `api_key_env` | `OPENAI_API_KEY` | 从哪个环境变量读 key |
| `timeout_s` | `300` | 单图上限 |
| `max_side` | `768` | 送模型的图片长边（延迟旋钮） |
| `gold_score` | `0.60` | 可入选金标准/优先检索 |
| `dense_score` | `0.45` | 低于此判为 `reject` |
| `retries` | `2` | 失败重试 |
| `skip_plates` | `false` | 外部拼版图不当单图评分 |
| `allow_nonchart` | `false` | 是否把示意图/显微图当案例入库 |

示例（本机使用的 GLM 视觉模型）：

```toml
[design]
judge = "vision"
base_url = "https://open.bigmodel.cn/api/coding/paas/v4"
model = "glm-4.5v"
api_key_env = "GLM_API_KEY"
max_side = 768
```

## `[reconstruct]` — LLM 辅助重建

作者代码缺失或无法运行时使用：模型写脚本，沙箱运行并与论文图比对。结果记录为
`reproduction.method = llm_reconstruction`（或 `llm_repair`），绝不冒充作者代码复现。

| 键 | 默认 | 含义 |
|---|---|---|
| `enabled` | `false` | 是否允许批量回退（`reproduce-paper --reconstruct-missing`） |
| `base_url` | `""` | OpenAI 兼容端点；空则继承 `[design]` |
| `model` | `glm-5.3-flash` | 视觉/代码模型 |
| `api_key_env` | `""` | key 环境变量；空则继承 `[design]` |
| `max_rounds` | `3` | 生成 → 渲染 → 比对 → 修正的轮数 |
| `max_side` | `1024` | 送给模型的图片长边 |
| `target_similarity` | `0.85` | 达到该相似度提前停止 |
| `timeout_s` | `300` | 单次模型请求上限 |
| `temperature` | `0.0` | 确定性生成 |
| `disable_thinking` | `true` | 否则 GLM-5 会把 token 预算花在隐藏推理上 |
| `max_tokens` | `8000` | 单次生成长度上限 |
| `fallback_model` | `glm-4.5v` | 仅当主模型低于 L2 时重试，保留更好的渲染 |

## `[sandbox]` — 复现隔离

| 键 | 默认 | 说明 |
|---|---|---|
| `backend` | `podman` | `podman` 或 `local`（仅开发） |
| `image` | `gaxis-repro:py312` | 基础 Python 镜像 |
| `autobuild` | `true` | 镜像缺失时自动构建/拉取 |
| `autobuild_packages` | `matplotlib==3.11.2`, `numpy==2.5.5` | 基础图栈 |
| `per_paper_env` | `true` | 按论文仓库依赖构建派生镜像 |
| `r_image` | `gaxis-repro-r:4.5` | R 镜像 |
| `r_base_image` | `docker.io/rocker/tidyverse:4.5` | R 基础镜像 |
| `r_packages` | `svglite`, `patchwork`, `cowplot` | R 附加包 |
| `network` | `false` | 容器默认无网络 |
| `memory` | `4g` | 内存上限 |
| `cpus` | `2.0` | CPU 上限 |
| `pids_limit` | `256` | 进程数上限 |
| `timeout_s` | `300` | 单次运行上限 |
| `allow_network` | `false` | 是否允许显式放开网络 |

**不要削弱隔离**：网络、只读根、cap-drop、资源上限与 `no-new-privileges` 都是默认值，
修改需要显式配置键和测试。

## `[reproduction]` — 分级阈值

| 键 | 默认 | 说明 |
|---|---|---|
| `l1_similarity` | 0.85 | L1 的相似度阈值 |
| `l2_similarity` | 0.55 | L2 的相似度阈值 |
| `compare_size` | 256 | 比对前缩放到的最长边 |

阈值只在这里定义，runner 和测试都不得硬编码。

## `[knowledge]` — gbrain

| 键 | 默认 | 说明 |
|---|---|---|
| `enabled` | `true` | 关闭后检索返回 `degraded` |
| `source` | `paper-kb` | gbrain source |
| `binary` | `null` | gbrain CLI 路径（默认 PATH → `scripts/gbrain.sh`） |
| `gbrain_home` | `null` | 数据目录（默认 `${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain`） |
| `types` | `["analysis"]` | 检索的页面类型 |
| `timeout_s` | `120` | 单次调用上限 |
| `retries` | `3` | 失败重试 |
| `auto_ingest` | `true` | 解析后自动入库 |
| `include_rejected_design` | `false` | 是否索引设计判为 reject 的页面 |

## 环境变量覆盖

| 变量 | 覆盖 |
|---|---|
| `GAXIS_DATA_DIR` | `data_root` |
| `GAXIS_CONFIG` | 配置文件路径 |
| `GAXIS_CONFIRM_MODE` | `[confirmation] mode` |
| `GAXIS_CONFIRM_MIN_CONFIDENCE` | `[confirmation] min_confidence` |
| `GAXIS_INGEST_MODE` | `[ingest] default_mode` |
| `GAXIS_RENDER_TIMEOUT` | `[render] timeout_s` |
| `GAXIS_CONTACT_EMAIL` | `[ingest] contact_email` |
| `GAXIS_SANDBOX_BACKEND` | `[sandbox] backend` |
| `GAXIS_SANDBOX_IMAGE` | `[sandbox] image` |
| `GAXIS_SANDBOX_TIMEOUT` | `[sandbox] timeout_s` |
| `GAXIS_KB_ENABLED` | `[knowledge] enabled` |
| `GAXIS_GBRAIN_BIN` | `[knowledge] binary` |
| `GAXIS_GBRAIN_HOME` | `[knowledge] gbrain_home` |
| `GAXIS_MCP_TOKEN` | MCP server 的 Bearer token（必需） |

## 数据目录布局

```
data/
  renders/<figure_id>/        渲染产物 + figure.py/.R + manifest.json + render.log
  manifests/                  ChartReproManifest（论文图，权威）
  assets/                     论文图、代码资产、模板代码
  repro/<asset>/<sha8>/       复现工作目录 + reproduction.json
  synthetic/                  合成输入表
  kb/state.json               页面内容 hash（幂等入库）
  kb/sheets/                  contact sheet
  kb/selections.jsonl         选择反馈
  ops/queue.db                队列
  ops/heartbeat.json          最近一次运行
```

`data/` 不入 git；知识库页面可由 manifest 重建。
