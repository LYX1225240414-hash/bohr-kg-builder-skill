---
name: kg-builder
description: "从科研文献抽取带证据的实体关系知识图谱：识别研究者/材料/方法/任务/指标/数据集/条件/结论八类实体，只建立有原文证据支持的关系并标注方向、条件与证据强度，处理别名与同名冲突，输出可校验、可查询、每个节点每条边都能回到论文位置的图谱；内置可离线运行的 kg_lint.py（结构校验 + 子图查询），机械检出悬空边、无证据边、重复实体、方向冲突与孤立节点；当用户要求从论文构建知识图谱、抽取实体关系、做别名归一或按图查询时使用。"
---

# 文献知识图谱构建：抽得准、连得对、对得齐、查得到回得去

把一批论文转成**带证据、可查询、可校验**的节点与边，而不是一堆看起来像三元组的字符串。本 Skill 自带执行内核 `resources/scripts/kg_lint.py`：结构校验、别名归并建议、子图查询都由确定性算法完成。你的工作是判断"什么算实体""关系是否真有原文支持"，把脚本发现的问题改对。

## 四条判据（对应题面四个问题）

| 判据 | 含义 | 反例 |
|---|---|---|
| **抽得准** | 实体是论文里真实出现的科研对象，保留原文表述 | 模型凭常识补出的"常见做法"概念 |
| **连得对** | 关系类型、方向、适用条件与原文一致，只建直接证据支持的关系 | 把同段共现、综述转述、推测当成关系依据 |
| **对得齐** | 别名、缩写、大小写、同名冲突处理正确，不重复节点也不错误合并 | LiFePO4 与 LFP 建成两个节点；两个不同"Chen et al."被合并 |
| **查得到回得去** | 至少 3 个真实查询能答出，且每个节点每条边能回到论文位置与原文片段 | 查询只能返回空，或边没有 anchor |

## 运行环境与输出路径（重要）

- 平台把本 Skill 安装到 `/skills/weekly-skill`，用固定的 3 个案例运行。先读真实输入 `/input/case.json` 与 `/input/task.md`；`case.json` 可能含 `case_id`、`output_contract`、论文路径、目标实体类型与查询问题。**以实际字段为准，不从题目标签或文件名推断材料内容**。
- 中间文件写 `/app/work`（`graph.json` 工作图、`kg_report.json` 校验报告）；资源从 `/skills/weekly-skill/resources/` 读。
- 最终结果写 `/app/output/result.json`（UTF-8 合法 JSON），**原样回填 `case_id` 与 `output_contract` 全部字段**，再补扩展字段；同名以合同为准。
- 同时产出 `/app/output/graph.json`（最终图谱，entities + relations）、`/app/output/kg_queries.md`（查询与结果子图，含证据）、`/app/output/evidence_index.md`（节点/边 → 论文位置 → 原文片段）、`/app/output/kg_log.txt`（处理过程、校验与修正记录）。
- 预算：64 次模型请求、900 秒、单次 16384 tokens。**尽早把骨架落盘**，再增量补边。
- 禁止提交预制答案或正式案例答案；包内不含任何 `result.json`。
- 资源限制：最多 50 个 UTF-8 文本文件、单文件 ≤500KB、总 ≤2MB、无符号链接。

## 输入输出

输入：论文材料（PDF / 文本 / 抽取后的文本）与任务说明；可选约束：关注主题、必须覆盖的实体类型、需要回答的查询。

`result.json` 字段（`output_contract` 优先）：

| 字段 | 要求 |
|---|---|
| case_id | 原样回填，缺失填 `N/A` |
| status | `success` / `partial` / `unable` / `refused`；部分完成写明未覆盖的论文/章节 |
| entities | 数组，每项 `id` / `name`（原文表述）/ `type`（八类之一）/ `aliases` / `paper` / `anchor` / `evidence`（原文片段）/ `confidence` |
| relations | 数组，每项 `id` / `subject` / `predicate`（schema 内类型）/ `object` / `anchor` / `evidence` / `strength`（direct/indirect/cooccurrence/inferred）/ `condition`（适用条件）/ `paper` |
| alias_decisions | 数组，每项 `canonical` / `variants` / `decision`（merge/keep_separate）/ `reason` / `anchor`；合并与不合并都要有依据 |
| queries | 数组，**至少 3 条**，每项 `question` / `answer` / `subgraph`（实体与边 id）/ `evidence`（anchor + 片段）/ `undetermined`（答不出的部分及原因） |
| evidence_map | 数组，每项 `claim` / `evidence` / `anchor` / `paper` / `source_type`（text/table/figure_caption） |
| verification | 对象，八项带计数，口径见 `resources/checklist.md` |
| uncertainties | 数组，每项 `item` / `reason` / `anchor` / `question_for_author`；同名实体、冲突关系、无法判断的方向都在此说明 |
| sources | 处理的论文列表、页码范围、抽取方式与工具版本 |
| change_log | 校验发现的问题、修正动作、修正位置 |

**锚点格式**：`p<页>:<段>` / `<章节>:<段>` / `tab<号>` / `fig<号>`；多论文时用 `<paper_id>@p<页>:<段>`。必须指向真实位置。

## 工作流

### 第 0 步：落盘骨架
读 `/input/case.json` 与 `/input/task.md`，记下 `case_id`、`output_contract`、论文清单、必须回答的查询。立即写 `/app/output/result.json` 骨架（`status: partial`，`entities`/`relations`/`queries` 空数组）。

### 第 1 步：导出 schema，明确本次范围
```bash
K=/skills/weekly-skill/resources/scripts/kg_lint.py
python3 "$K" schema --out /app/work/schema.json
```
确认本次允许的八类实体（researcher / material / method / task / metric / dataset / condition / conclusion）与十类关系（uses / applied_to / compares_with / outperforms / supports / contradicts / part_of / measured_by / derived_from / authored_by）。若案例要求自定义类型，在 `change_log` 写明新增类型与理由，并保持全篇一致。

### 第 2 步：抽取实体（抽得准）
逐篇逐段扫描，只登记论文里**真实出现的科研对象**，`name` 用原文表述（首次出现处），并记 `anchor` 与 `evidence`（≤120 字原文片段）。判定准则：
- 材料/方法/指标等专有对象 → 实体；"近年来受到广泛关注"这类泛化描述 → 不是实体。
- 区分**作者自述**与**他人转述**：转述内容若作为实体结论，`confidence` 降为 `medium` 并在 evidence 注明转述来源。
- 同一对象的不同写法**先不合并**，全部记为候选（别名候选），留到第 4 步统一决策，避免中途误合并。

### 第 3 步：抽取关系（连得对）
只建立**有原文直接支持**的关系。每条边必须同时具备：`predicate`（schema 内）、方向正确、`anchor`、`evidence` 原文片段、`strength`、`condition`（若原文限定条件）。
- 强度判定：原文直陈 → `direct`；需一步推理 → `indirect`（在 evidence 写明推理依据）；仅同段共现 → `cooccurrence`（**不得作为结论使用**）；模型推测 → `inferred`（**必须写入 uncertainties**）。
- 方向判定：`A outperforms B` 不能写成 `B outperforms A`；`compares_with` 是对称比较，不表示优劣。
- 数值比较必须带条件：写清指标名、取值、测试条件，否则改写为 `compares_with` 而不写 `outperforms`。

### 第 4 步：别名与同名冲突（对得齐）
对第 2 步的候选逐个决策，写入 `alias_decisions`：
- **合并**：全称/缩写、大小写、连字符差异、同一对象的中英文写法 → `decision: merge`，保留 `canonical` 与全部 `variants`，写合并依据（如"原文 p2 明确 LFP 即 LiFePO4"）。
- **不合并**：不同材料/不同人同名 → `decision: keep_separate`，在 `name` 中加可区分标识（如 `Chen et al. (2019, Nature)`），并写入 `uncertainties`。
- 无法判断是否同一对象 → 保留两个节点 + `uncertainties` 记录，**不擅自合并**。

### 第 5 步：结构校验（脚本，必跑）
把工作图写到 `/app/work/graph.json`（entities + relations，字段同 `result.json`），然后：
```bash
python3 "$K" check --graph /app/work/graph.json --out /app/work
cat /app/work/kg_report.md
```
按报告逐项修：

| 报告项 | 含义 | 动作 |
|---|---|---|
| `dangling` | 关系端点不在实体表 | 补登记实体或修正拼写；歧义名称改用 id 引用 |
| `unsupported` | 边缺 anchor 或 evidence | 补证据；补不出**删除该边**（这是最常被扣分的地方） |
| `duplicates` | 归一后同名实体 | 按第 4 步决策合并或加区分 |
| `unknown_predicate` | 关系类型不在 schema | 改用 schema 类型，或说明新增理由 |
| `direction_conflict` | 反对称关系出现双向 | 核对原文，删掉错向的那条 |
| `isolated` | 孤立节点 | 无任何关系的实体要么补边，要么说明它是独立登记的结论/指标 |

修完重跑 `check`，直到 `dangling` / `unsupported` / `direction_conflict` 为 0。每轮修正记 `change_log`。

### 第 6 步：查询验证（查得到回得去）
写**至少 3 条真实查询**（不要自问自答的送分题），逐条用脚本取子图：
```bash
python3 "$K" query --graph /app/work/graph.json --entity "LiFePO4" --hops 1
python3 "$K" query --graph /app/work/graph.json --predicate outperforms
```
每条查询在 `queries[]` 里给出：`question`（真实问题）、`answer`（基于子图的结论）、`subgraph`（实体/边 id）、`evidence`（每条边的 anchor + 原文片段）、`undetermined`（图上答不出的部分及原因，如"该论文未报告温度条件"）。查询答不出时必须如实写"图谱中无相关信息"，不得编造。

### 第 7 步：自检与交付
逐项核对 `resources/checklist.md`，`verification` 八项**优先采用 `kg_report.json` 的计数**：
- `entity_grounding`：实体数、缺 name/type 数
- `relation_integrity`：关系数、悬空数、证据缺失数（后两者必须为 0）
- `alias_alignment`：疑似重复组数、孤立实体数
- `evidence_coverage`：证据齐备关系数 / 关系总数
- `query_answerability`：可答查询数 / 查询总数
- `direction_accuracy`：抽查方向正确数 / 抽查数
- `no_new_facts`：材料外新增实体或关系数（必须为 0）
- `uncertainty_disclosure`：已披露项 / 发现项

输出 `result.json` 与四个产物；确认 `case_id` 已回填、`output_contract` 齐全、每条边有 anchor、查询至少 3 条、`uncertainties` 如实。

## 异常处理

| 情况 | 处理 |
|---|---|
| PDF 无法解析 / 无文字层 | 尝试 OCR；失败则 `status: unable` 或 partial，写明无法处理的论文与页 |
| 实体同名但实为不同对象 | `keep_separate` + 区分标识 + 写入 uncertainties，不合并 |
| 关系证据冲突（两篇结论相反） | 两条边都保留，用 `contradicts` 连接，写入 uncertainties |
| 只有共现、无直接表述 | `strength: cooccurrence`，不得用于结论；必要时列入 uncertainties |
| 查询无结果 | 如实返回空并说明图谱覆盖范围，不编造答案 |
| 论文数量超出预算 | 按重要性排序处理，`status: partial` 写明已处理/未处理清单 |
| 增量更新（新论文加入） | 保留既有实体 id 与编号，新增节点追加编号，合并与冲突记 `change_log` |

## 资源

- `resources/scripts/kg_lint.py`：**执行内核**。`schema` 导出实体/关系类型与规则；`check` 输出八类结构问题与计数；`query` 按实体/关系类型做邻域子图检索（返回每条边的 anchor 与 evidence）。纯标准库，无第三方依赖。
- `environment/resources.yaml`：资源清单、schema 位置、运行时说明。
- `resources/checklist.md`：带计数的自检清单（对应 verification 八项）。
- `resources/field_dict.md`：实体/关系字段字典、锚点格式、强度与方向判定口径。
- `resources/output_example.json`：输出结构示意（占位，非任何真实案例图谱）。
- `examples/README.md`：最小调用示例与完整步骤。

## 最小示例（示意，非真实案例结果）

```bash
K=/skills/weekly-skill/resources/scripts/kg_lint.py
python3 "$K" schema --out /app/work/schema.json
python3 "$K" check  --graph /app/work/graph.json --out /app/work
python3 "$K" query  --graph /app/work/graph.json --entity "LiFePO4" --hops 1
```

示意输出（仅结构，数值为占位）：

```json
{"entity_count": 24, "relation_count": 31, "dangling_count": 0, "unsupported_count": 0,
 "duplicate_group_count": 1, "direction_conflict_count": 0, "evidence_coverage": 1.0}
```

真正的图谱必须来自本次实际运行，示意输出不得冒充正式案例答案。
