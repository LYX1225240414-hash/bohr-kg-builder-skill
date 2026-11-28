# 最小调用示例（示意，非正式案例）

仅演示接口、流程与字段，不代表任何真实论文的图谱或答案。

## 输入
```json
{
  "case_id": "示意-case-001",
  "task": "从给定论文抽取实体与关系，构建带证据的图谱，并回答指定查询",
  "papers": ["paper1.pdf", "paper2.pdf"],
  "output_contract": {"case_id": "string", "status": "string", "entities": "array", "relations": "array"}
}
```
实际评测时输入为 `/input/case.json` 与 `/input/task.md`，论文路径以其中字段为准。

## 调用步骤
1. 加载本目录为 Skill（安装位置 `/skills/weekly-skill`）。
2. 读 `/input/case.json`、`/input/task.md`，写 `status: partial` 骨架到 `/app/output/result.json`。
3. 导出 schema，按 SKILL.md 第 2–4 步抽实体、抽关系、定别名，工作图写 `/app/work/graph.json`。
4. 跑结构校验，把问题改到 0。
5. 至少 3 条真实查询，逐条取子图并写证据。
6. 输出 `result.json` + `graph.json` + `kg_queries.md` + `evidence_index.md` + `kg_log.txt`。

## 脚本命令
```bash
K=/skills/weekly-skill/resources/scripts/kg_lint.py

# 1) 导出 schema（实体/关系类型与规则）
python3 "$K" schema --out /app/work/schema.json

# 2) 结构校验（必跑；dangling/unsupported/direction_conflict 要改到 0）
python3 "$K" check --graph /app/work/graph.json --out /app/work
cat /app/work/kg_report.md

# 3) 子图查询
python3 "$K" query --graph /app/work/graph.json --entity "<实体名>" --hops 1
python3 "$K" query --graph /app/work/graph.json --predicate outperforms
```

## 示意输出
字段结构见 `../resources/output_example.json`；其中所有值均为占位示例，`status` 为 `partial`，不得当作正式案例答案或评测结果。
