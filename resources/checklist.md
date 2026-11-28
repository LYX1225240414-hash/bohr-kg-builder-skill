# 知识图谱自检清单（必须带计数写入 verification）

## 第 0–1 步：输入与 schema
- [ ] 已读 `/input/case.json` 与 `/input/task.md`，`case_id`、`output_contract`、论文清单、必须回答的查询已记录
- [ ] 骨架 `result.json` 已早期落盘（`status: partial`）
- [ ] 已跑 `kg_lint.py schema` 导出 schema，本次允许的实体/关系类型已确认
- [ ] 自定义类型（若有）已在 `change_log` 说明理由并全篇一致
- [ ] 未用题目标签或文件名推断材料内容

## 第 2 步：实体（entity_grounding）
- [ ] 每个实体都在论文原文真实出现，`name` 用原文表述
- [ ] 每个实体有 `type`（八类之一）、`anchor`、`evidence` 原文片段
- [ ] 未把泛化描述（"受到广泛关注"）登记为实体
- [ ] 他人转述内容已降 `confidence` 并注明转述来源
- [ ] 计数：实体数；缺 name/type 数（必须为 0）

## 第 3 步：关系（relation_integrity）
- [ ] 每条边有 schema 内 `predicate`、正确方向、`anchor`、`evidence`
- [ ] `strength` 判定正确；cooccurrence/inferred 未用于结论
- [ ] 数值比较带指标名、取值与测试条件；条件不全的已改为 `compares_with`
- [ ] 计数：关系数；悬空 0；证据缺失 0（跑 `kg_lint.py check` 确认）

## 第 4 步：别名（alias_alignment）
- [ ] 每个别名决策都写入 `alias_decisions`，有 `decision` 与 `reason`
- [ ] 合并的保留全部 `variants`；不合并的加了可区分标识
- [ ] 无法判断的保留双节点并写入 `uncertainties`，未擅自合并
- [ ] 计数：疑似重复实体组数（跑 `check` 的 `duplicate_group_count`）；孤立实体数

## 第 5–6 步：校验与查询（query_answerability）
- [ ] `kg_lint.py check` 已跑到 dangling/unsupported/direction_conflict 全为 0
- [ ] 至少 3 条真实查询，每条给 `question` / `answer` / `subgraph` / `evidence` / `undetermined`
- [ ] 查询答不出时如实写"图谱中无相关信息"，未编造
- [ ] 计数：可答查询数 / 查询总数；证据齐备关系数 / 关系总数

## 交付前
- [ ] `direction_accuracy`：抽查 5 条边的方向，记录正确数 / 5
- [ ] `no_new_facts`：材料外新增实体或关系数 = 0
- [ ] `uncertainty_disclosure`：已披露项 / 发现项
- [ ] `result.json` 原样回填 `case_id` 与全部 `output_contract` 字段
- [ ] `graph.json` / `kg_queries.md` / `evidence_index.md` / `kg_log.txt` 已写盘
- [ ] 包内不含 `result.json`、正式案例答案或预制输出
- [ ] 资源为 UTF-8 文本、相对路径、无符号链接，单文件 ≤500KB、总量 ≤2MB
