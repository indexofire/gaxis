# gbrain 集成(2026-11-18 已验证)

gbrain 已安装在本环境中，集成面已进行端到端演练。以下每一条都是实际执行过的命令及其观察到的行为——不是设计草图。版本：**0.60.740.0**(上游 `master`,`vendor/gbrain`)。

## 1. 安装(由 pixi 管理，不会写入 `~/.gbrain`)

```bash
pixi run gbrain-install     # vendor the repo, bun install, write the env shim
pixi run gbrain-init        # create the brain (PGLite, no embeddings)
pixi run gbrain --version   # gbrain 0.60.740.0
pixi run gbrain doctor      # 100/100 except sync_freshness (see §6)
```

各内容所在位置：

| 路径 | 内容 | 是否受版本控制 |
|---|---|---|
| `vendor/gbrain` | 上游检出(`git`、`bun install`) | gitignored |
| `vendor/bun` | 固定版本 bun **1.4.4**——gbrain 拒绝更旧版本；conda-forge 提供的是 1.4.2 | gitignored |
| `.pixi/envs/default/bin/gbrain` | 垫片(shim)→ `scripts/gbrain.sh` | env |
| `${XDG_DATA_HOME:-~/.local/share}/gaxis/gbrain` | brain 数据库(`GBRAIN_HOME`) | no |
| `~/.local/share/gaxis/paper-kb` | 源根目录：规范的页面文件 | no |

`scripts/gbrain.sh` 会导出 `GBRAIN_HOME`,因此 brain 属于每个用户且**位于任何 git 工作树之外**——gbrain 拒绝拥有仓库内部的内容目录(`local_conflict`),而与源代码相邻的 brain 距离被提交只差一次 `git add -f`(`home_dir_in_worktree`)。

## 2. 隔离:`federated=false` 确实存在且有效

```bash
pixi run gbrain sources add paper-kb \
  --path ~/.local/share/gaxis/paper-kb --no-federated --force --json
# {"id":"paper-kb", …, "federated":false}
# "federated: false — only searched when explicitly named via --source"
```

这是方案 ADR-04 的字面实现：没有指名它的搜索不会看到 `paper-kb`。两条用教训换来的硬性规则：

1. **源路径必须位于仓库工作树之外。**工作树内部的路径会被认作规范工作树，所有写入/同步都会被拒绝(`writer_coordinator_required`、`recovery_required`)。
2. **源的 id 不能重新指向新路径。**对已存在的 id 执行 `sources add` 会失败；必须先 `sources remove <id> --confirm-destructive`(会删除其页面)再重新添加。

## 3. 写入路径:`put` / `delete`,带修订保护

```bash
pixi run gbrain put paper-kb:smoke-0001 \
  --content-origin tool_output --reason "gaxis ingest" < examples/paper-kb-page.example.md
pixi run gbrain put paper-kb:smoke-0001 --expected-revision <rev> …   # correct update
pixi run gbrain put paper-kb:smoke-0001 --force …                      # deliberate re-ingest
pixi run gbrain delete paper-kb:smoke-0001 --expected-revision <rev>   # or --force
```

观察到的语义(均已验证)：

| 场景 | 结果 |
|---|---|
| 新页面 | 已创建;`put` 会把规范的 `.md` 文件同时写入源根目录**和**数据库 |
| 已存在页面，未提供修订版本 | `revision_required`——写入采用乐观并发控制，绝不盲目 upsert |
| `--force` | 无条件替换；gaxis 用它进行确定性的重新摄取 |
| `delete` | `soft_deleted`(可恢复)，页面从 `list`/`search` 中消失 |
| 论文衍生内容 | 必须传入 `--content-origin tool_output`——gbrain 随后将其视为不可信输入 |
| `--request-id` | **仅**用于重试完全相同的请求 |

`gbrain sync --source paper-kb` 对我们**不可**用：它需要激活 git/writer-coordinator(`writer_coordinator_required`),而且认领嵌套工作树会被拒绝。gaxis 显式写入页面，这也正是重新摄取具备幂等性的原因。

## 4. 读取路径：过滤，而不仅仅是文本

```bash
pixi run gbrain search "rarefaction curve" \
  --source-id paper-kb --types analysis --where chart_type=line --limit 5 --json
pixi run gbrain query "<question>" --expand        # hybrid + LLM expansion (costs tokens)
pixi run gbrain get paper-kb:smoke-0001 --json     # includes `revision`
pixi run gbrain call get_health '{}'               # engine health (wedged/declined/skipped)
```

- `--where key=value` 是 **frontmatter 相等匹配**：gaxis 正是借此对 `chart_type`、`reproduction_level`、`preset_hint` 进行过滤——也就是 ADR-10 所需要的过滤器。已验证可用。
- `--types` 按声明的页面类型过滤;`--source-id` 将范围限定到隔离的源。
- 在嵌入被禁用的情况下，结果会带有 `degraded: embed_unavailable`;关键词搜索仍会返回该页面。gaxis 必须呈现这个标志，而不是把寥寥无几的结果当作“未找到”。
- `get --json` 会返回 `revision`——如果你想用带修订保护的更新来替代 `--force`,请将其存储下来(SQLite)。

## 5. 页面类型必须先声明

使用 `type: chart-asset` 的 `put` 被拒绝：当前激活的 schema 包声明了 25 种类型(`analysis`、`code`、`concept`、`event` 等)。已验证可用：图形页面使用 **`type: analysis`**。M3 计划：图形用 `analysis`,提取的脚本用 `code`;自定义 `chart-asset` 类型需要随附一个 schema 包(`~/.gbrain/schema-packs/`)——在需要类型专属关系之前不值得这么做。

## 6. 健康检查：一个预期之内的 FAIL

`gbrain doctor` 对 `paper-kb` 报告 `sync_freshness` FAIL,因为该源采用直写(`put`)方式且从未执行过 `sync`。这是受支持写入路径带来的必然结果，而非安装损坏：其余项目评分均为 OK。`pixi run gbrain-doctor` 对该检查做了封装：它会打印完整报告，且仅在出现**预期之外**的 FAIL 时才失败，因此直写源的 `sync_freshness` 不会掩盖真正的问题。

## 7. 多模态：gbrain 需要做什么、不需要做什么

决策框架(用户提案)：**知识库(KB)只存储复现代码和元数据；图像以文件形式保存在某个目录里，由清单负责映射；多模态宿主想查看某张图形时直接打开对应路径——从不要求 gbrain 去“看”它。**

这是正确的默认选择，对以下查询已经足够：

| 查询 | 机制 |
|---|---|
| “查找稀释曲线的可复用代码” | 对题注 + 视觉语法 + 代码进行文本搜索 |
| “哪些故事含有带误差线的分组柱状图？” | `--where chart_type=bar` + 文本 |
| “展示原始图形” | 宿主打开清单/页面中的 `image_path` |
| “与本文图 3 相同的视觉风格” | 基于 `visual_grammar` + `preset_hint` 的文本搜索 |

但对于*以图检索*(“这是一张截图，帮我找出相似的图形”)它就**不**够了——这需要图像嵌入空间。存在两条升级路径，都以可插拔的方式隐藏在同一个 `VisualIndex` 端口之后：

1. **gbrain 原生多模态嵌入。**gbrain 0.60 在初始化时接受 `--embedding-model voyage:voyage-multimodal-3`(`embeddings enable` 可就地切换)。图像**和**文本共用一个向量空间；付费 API;需要重新嵌入所有内容，并把图形图像发送给第三方——对 bacmap 档案来说这是一个数据策略问题。
2. **本地 CLIP 索引。**约 1 GB 的模型跑在 CPU 上，免费且离线，以 numpy 矩阵形式存放在 SQLite 旁边；在 `kb/retrieve.py` 中与文本结果融合。不引入新服务，不发起外部调用。

建议：M3 阶段保持纯文本，并在摄取时把 `visual_grammar` 作为一等公民文本字段(图表类型、编码角色、配色、坐标轴/图例样式、面板布局、期刊预设、相似度得分)。只有当出现真实的“找出与这张图像相似的图形”用例时才引入路径 2。另寻其他 KB 产品**并无**必要：gbrain 已经覆盖了文本 + 代码 + 元数据过滤 + 源隔离；图像嵌入只是一个约 150 行的本地索引，不足以构成迁移的理由。

无论走哪条路都值得做的低成本改进：

- 摄取时计算感知哈希(pHash)→ 重复/近似重复的图形不会污染检索；
- 让 `image_path` 相对于资产根目录，并通过 `asset_id` 解析，这样移动数据目录不会破坏每一个页面；
- 清单才是权威数据；gbrain 页面只是一个**派生的、可重建的索引**(可以放心清空后重新摄取，这正是 `--force` 的用途)。

## 8. gaxis 已实现的内容(M3,已完成)

| 组件 | 方案 |
|---|---|
| `kb/gbrain.py` | 基于 CLI 的 `KnowledgeBase` 端口实现:`put_page`、`get_page`、`delete_page`、`search`、`status` |
| `kb/pages.py` | `ChartReproManifest` → markdown 页面(`type: analysis`,frontmatter = 可过滤事实，正文 = 题注 + 视觉语法 + 代码摘要 + 相对路径) |
| `kb/ingest.py` | 在 `data/kb/state.json` 中按资产记录内容哈希；未变更则跳过;`--force` 时重写；整篇论文摄取完成后自动摄取 |
| `kb/search.py` | 分块命中 → 每个页面对应一个资产；层级/预设过滤与排序；图表类型回退 |
| 配置 | `[knowledge] enabled, source, binary, gbrain_home, types, auto_ingest, timeout_s, retries`;环境变量 `GAXIS_KB_ENABLED`、`GAXIS_GBRAIN_BIN`、`GAXIS_GBRAIN_HOME` |
| 失败模式 | gbrain 缺失/忙碌 → `search_chart_assets` 返回 `degraded: true` 及原因 |

## 7b. 本地嵌入：在本机实测(2026-11-19)

以用户级方式安装(`~/ollama`、systemd 用户单元、`OLLAMA_KEEP_ALIVE=10m`),模型为 `bge-m3`(1.2 GB,1024 维)。切换 brain 使用的命令：

```bash
gbrain embeddings enable --embedding-model ollama:bge-m3   # keeps pages/facts, queues chunks
gbrain embed --stale                                      # 11 chunks across 10 pages
pixi run gaxis kb status                                  # missing_embeddings: 0
```

实测环境(Intel Core Ultra 7 255H,16 核，无 GPU,约 1000 字符的分块)：

| 指标 | bge-m3 | nomic-embed-text(对比) |
|---|---|---|
| 维度 | 1024 | 768 |
| 模型大小 | 1.2 GB | 274 MB |
| 冷启动(加载 + 嵌入) | ~3.5 s | ~1.0 s |
| 热态单块嵌入耗时 | **~1.43 s** | ~0.36 s |
| 内存(llama-server RSS) | **~1.4 GB** | 未测量 |
| 嵌入时的 CPU | ~170 %(llama-server),`OLLAMA_NUM_THREADS=8` 无差别 | — |
| 我们的规模 | 11 个分块共 **29 s**(含每次调用的开销) | — |

bge-m3 在这里比 nomic 慢约 4 倍，且受内存限制，但它支持多语言——这正是保留它的理由：没有关键词重叠的中文查询现在也能工作：

```
before (keyword only): gaxis kb search "稀释曲线"      → 0 hits
after  (bge-m3):       gaxis kb search "稀释曲线"      → 3 hits (rarefaction figures)
```

成本控制：单元文件中的 `OLLAMA_KEEP_ALIVE=10m`(设为 `0` 可立即卸载);`systemctl --user disable --now ollama` 会关闭语义搜索，gbrain 随之降级为 `embed_unavailable`(关键词搜索仍然可用，`degraded` 会由 gaxis 呈现)。

## 仍待解决的开放问题(均不阻塞 M3 脚手架搭建)：

1. 启用本地嵌入(`ollama:bge-m3`),还是在首次检索质量测量之前保持仅关键词模式？仅关键词会让“查找相似”能力偏弱；本地嵌入模型免费，但需要宿主机上装有 Ollama。
2. 如果/当需要图像检索时：选本地 CLIP(离线)还是 `voyage-multimodal-3`(付费，且图形图像会离开本机——与 bacmap 的云端档案上限相关)？
3. 我们到底需不需要 `gbrain think`(多跳综合)？它需要 LLM 密钥且产出的是散文式文本；gaxis 自身的适配路径并不需要它。

## 9. 快速参考

```bash
pixi run gaxis kb status
pixi run gaxis kb ingest --force
pixi run gaxis kb search "rarefaction curve" --min-level L2 --json
pixi run gbrain sources list --json
pixi run gbrain search "growth curve" --source-id paper-kb --where reproduction_level=L1 --json
pixi run gbrain get paper-kb:<asset_id> --json | jq .revision
pixi run gbrain put paper-kb:<asset_id> --force --content-origin tool_output --reason "re-ingest"
pixi run gbrain delete paper-kb:<asset_id> --force
pixi run gbrain doctor
```
