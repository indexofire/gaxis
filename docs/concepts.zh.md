# 核心概念

理解下面六个概念，就能理解 gaxis 的所有行为。

## 1. 图 = 脚本 + 产物 + manifest

一次渲染产出三样东西，它们必须一起存在：

```
data/renders/bar-65ca394dac/
  figure.py                    # 可交付脚本，不 import gaxis
  bar-65ca394dac.pdf / .png    # 产物（按请求的 formats）
  manifest.json                # 证据：data.sha256, code_sha256, 几何, lint
```

- **`figure.py` 是交付物，不是构建中间物。** 它在一个干净的 Python 环境里就能跑。
- **`manifest.json` 是证据。** 数据或代码任何一个变了，hash 就变；`figure_id` 也变。
- **没有 manifest 的图不算产物。** 规则上，任何渲染路径都必须写 manifest。

`figure_id` 由 `PIPELINE_VERSION + 数据 hash + spec` 决定。模板或 emission 一变，版本号必须变，
所以旧代码永远不会被误认为当前输出。

## 2. 三个分数，绝不合并

| 分数 | 回答的问题 | 位置 |
|---|---|---|
| `chart_quality_score` | 这张**提取出来的图**可不可用？（caption、清晰度、裁切） | manifest / KB |
| `design.score` | 这张图**设计得好不好**？（美学 + 信息设计） | manifest / KB |
| `usefulness_score` | 这张图**值不值得复现**？（期刊、统计、验证、面板、caption） | manifest / KB |

提取质量是**门控**，不是审美判断；设计分是评审结论，未评审就保持 `null`；有用性负责排序。
检索默认按 `0.7 × design + 0.3 × usefulness` 排序（`[ranking]` 可改）。

## 3. 复现等级 L1 / L2 / L3

| 等级 | 含义 | 证据 |
|---|---|---|
| **L1** | 代码能跑，渲染结果与论文图高度相似（≥ `[reproduction] l1_similarity`） | 沙箱报告 + 相似度分解 |
| **L2** | 能跑且结构相似，但数值/样式有差异 | 相似度分解 + 失败原因 |
| **L3** | 代码能跑，但视觉差异大；作为**风格/逻辑参考** | 运行日志 + 失败原因 |
| **none** | 没跑、被拦截（许可证/静态扫描）、或跑失败 | 明确原因，不隐藏 |

等级是排序的主键：同等相关性下，L1 > L2 > L3 > none。`level=none` 的资产默认排在最后，
这是设计，不是 bug。

## 4. 沙箱与证据

论文代码默认在 **rootless podman** 里跑：

```
--network none  --read-only  --cap-drop ALL  --pids-limit  --memory  --cpus  no-new-privileges
```

- 每次运行记录解析出的 **image id**；换镜像会让旧评级失效，gaxis 明确记录而不是静默比较。
- 许可证是门控：GPL/AGPL 可以被记录（用于复用逻辑），但**不会**被复制进模板、也不会在沙箱里跑。
- 静态扫描拦截 `os.system`、`eval`、`exec` 等危险模式。
- `local` 引擎只用于开发与测试，报告永远写明 `network_enforced: false, read_only_root: false`。

!!! warning "local 不是安全执行"
    本地引擎的运行结果不能当作"安全执行"的证据，也不应出现在对外结论里。

## 5. 知识库：manifest 是权威，页面是索引

```
data/manifests/*.json        ← 权威：论文图的事实
        │  kb ingest（幂等，按内容 hash）
        ▼
gbrain source `paper-kb`      ← 派生：可重建的页面（正文 + 可过滤 frontmatter）
        │  search（文本 / 表格结构 / 图像 dHash）
        ▼
候选图 → contact sheet → 你选一张 → 渲染 / 适配
```

- 页面可以随时删掉重建，manifest 不能。
- 模板（`type: template`）是另一类页面：它们由 `gaxis kb seed`/`kb adopt` 生成，记录代码 hash 和接口。
- `search_chart_assets` 默认只查 `type: analysis`（论文图），模板不会混进论文候选。

## 6. 两种数据分级

每个 MCP 工具声明 `data_class`：

| 等级 | 含义 | 例子 |
|---|---|---|
| `D1` | 公开数据 | 检索、manifest、论文入库 |
| `D3` | 会读本地用户文件 | `render_chart_from_data`、`adapt_chart_code`、`compose_panels` |

宿主（如 bacmap）在调用前按 profile 过滤：cloud profile 只看到 D1 工具，本地可信 profile 才看到全部 10 个。
这是**边界**层面的保证，不是靠工具自觉。

## 概念之间的关系

```text
DataSchema ──► ChartSpec ──► emit(script) ──► run ──► outputs + lint
                   ▲                                  │
                   │                                  ▼
        KB template ─┘                              manifest
                   ▲                                  │
       paper code ─┘（复现 / adopt）                  ▼
                                                KB page ──► search
```

三个生产者（内置模板、KB 模板、论文复现）共用一个渲染路径，所以"生成图"和"复现图"不可能漂移。
