# 字段与判定口径

## 实体类型（entity.type，八类）
| 类型 | 含义 | 判定要点 |
|---|---|---|
| researcher | 研究者/团队/机构 | 原文署名或明确归属，不是泛指"研究者" |
| material | 材料、化合物、样品 | 有化学式/名称/牌号 |
| method | 方法、模型、算法、流程 | 有名称或明确指代（如"our two-stage framework"） |
| task | 任务、问题设定、应用场景 | 可独立描述的科研问题 |
| metric | 指标、评价标准、测量量 | 有名称与量纲/单位 |
| dataset | 数据集、语料、样本集合 | 有名称、版本或规模 |
| condition | 实验条件、参数、环境 | 温度、倍率、pH、硬件等 |
| conclusion | 结论、发现、主张 | 可被支持或反驳的陈述 |

## 关系类型（relation.predicate，十类）
| 类型 | 方向 | 语义 | 是否反对称 |
|---|---|---|---|
| uses | A→B | A 使用 B | 是 |
| applied_to | A→B | A 应用于 B | 是 |
| compares_with | A↔B | 被比较（不代表优劣） | 否 |
| outperforms | A→B | A 优于 B（须带指标与条件） | 是 |
| supports | A→B | A 支撑 B | 是 |
| contradicts | A↔B | 结论矛盾 | 否 |
| part_of | A→B | A 是 B 的组成部分 | 是 |
| measured_by | A→B | A 由 B 度量 | 是 |
| derived_from | A→B | A 来自 B | 是 |
| authored_by | A→B | A 由 B 完成 | 是 |

## 证据强度（relation.strength）
| 值 | 含义 | 能否作结论依据 |
|---|---|---|
| direct | 原文直接陈述 | 能 |
| indirect | 需一步推理 | 能，但 evidence 须写推理依据 |
| cooccurrence | 仅同段共现 | **不能** |
| inferred | 模型推断 | **不能**，必须进 uncertainties |

## 必填字段
**entity**：`id` / `name` / `type` / `anchor` / `evidence`；建议 `aliases` / `paper` / `confidence`
**relation**：`id` / `subject` / `predicate` / `object` / `anchor` / `evidence` / `strength`；建议 `condition` / `paper`
**alias_decisions**：`canonical` / `variants` / `decision`（merge|keep_separate）/ `reason` / `anchor`
**queries**：`question` / `answer` / `subgraph` / `evidence` / `undetermined`

## 锚点格式
`p<页>:<段>` / `<章节>:<段>` / `tab<号>` / `fig<号>`
多论文时：`<paper_id>@p<页>:<段>`，`paper_id` 与 `sources` 中的论文标识一致。

## 常见误判
| 误判 | 正确做法 |
|---|---|
| 把"A 与 B 在同段出现"当成 uses | 找明确表述；找不到则 strength=cooccurrence 或删边 |
| "A 表现更好"直接建 outperforms | 必须有指标名 + 取值 + 条件，否则用 compares_with |
| LiFePO4 与 LFP 建两个节点 | 合并，`variants` 记全部写法，`reason` 引原文依据 |
| 两个不同 Chen 2019 合并 | keep_separate，加期刊/机构区分，写入 uncertainties |
| 综述里"已有研究表明 X"当成作者结论 | 降 confidence，evidence 注明是转述 |
