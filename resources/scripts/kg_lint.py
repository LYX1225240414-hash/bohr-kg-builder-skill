#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kg_lint.py — 文献知识图谱结构校验与查询（kg-builder Skill 的执行内核）

解决的问题：知识图谱最容易出错的地方不是"抽不出来"，而是抽出来之后结构坏了——
关系指向不存在的实体、边没有证据、同一对象被建成两个节点、关系方向互斥、
查询答不出来。这些都能机械校验。

子命令：
  schema  导出内置 schema（实体类型 / 关系类型 / 约束说明）→ schema.json
  check   校验 graph.json，输出八类问题与计数 → kg_report.json + kg_report.md
  query   在图上做子图检索（按实体名 / 关系类型 / 邻域跳数）→ 结果子图 JSON

graph.json 约定：
{
  "entities": [{"id": "e1", "name": "LiFePO4", "type": "material",
                "aliases": ["LFP"], "anchor": "p3:L2", "evidence": "原文片段",
                "confidence": "high"}],
  "relations": [{"id": "r1", "subject": "e1", "predicate": "uses", "object": "e2",
                 "anchor": "p3:L4", "evidence": "原文片段", "strength": "direct",
                 "condition": "在 0.1C 倍率下"}]
}
subject/object 可写实体 id，也可写实体 name（自动解析，重复名会报歧义）。

校验输出：
  dangling_relations   关系端点在实体表中不存在
  unsupported_relations 关系缺 anchor 或 evidence
  duplicate_entities   归一后同名的实体（疑似重复节点）
  unknown_predicate    predicate 不在 schema 内
  direction_conflict   同一对实体间同类型关系方向互斥
  isolated_entities    度数为 0 的孤立实体
  weak_evidence        证据强度标为 inferred/cooccurrence 却被当直接结论使用
  missing_fields       实体缺 name/type，或关系缺 subject/object/predicate

用法：
  python3 kg_lint.py schema --out /app/work/schema.json
  python3 kg_lint.py check  --graph /app/work/graph.json --out /app/work
  python3 kg_lint.py query  --graph /app/work/graph.json --entity "LiFePO4" --hops 1
"""

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = {
    "entity_types": {
        "researcher": "研究者/团队/机构",
        "material": "材料、化合物、样品",
        "method": "方法、模型、算法、流程",
        "task": "任务、问题设定、应用场景",
        "metric": "指标、评价标准、测量量",
        "dataset": "数据集、语料、样本集合",
        "condition": "实验条件、参数、环境",
        "conclusion": "结论、发现、主张",
    },
    "relation_types": {
        "uses": "A 使用 B（方法用材料/数据/工具）",
        "applied_to": "A 应用于 B（任务/场景）",
        "compares_with": "A 与 B 被比较（同级对照，非优劣）",
        "outperforms": "A 优于 B（须给出指标与条件）",
        "supports": "A 支撑 B（证据支持某结论）",
        "contradicts": "A 与 B 矛盾（结论冲突）",
        "part_of": "A 是 B 的组成部分",
        "measured_by": "A 由 B 度量",
        "derived_from": "A 来自 B（数据/结论来源）",
        "authored_by": "A 由 B 完成（研究者归属）",
    },
    "symmetric_relations": [],
    "antisymmetric_relations": ["uses", "applied_to", "part_of", "measured_by",
                                "derived_from", "authored_by", "outperforms", "supports"],
    "evidence_strength": {
        "direct": "原文直接陈述，可作直接证据",
        "indirect": "需一步推理，应注明推理链",
        "cooccurrence": "仅同段共现，不得当作关系证据",
        "inferred": "模型推断，必须写入 uncertainties",
    },
    "rules": [
        "关系端点必须存在于 entities 表",
        "每条关系必须有 anchor 与 evidence 原文片段",
        "同一对象的不同写法应合并为一个实体并记 aliases",
        "antisymmetric 关系不得同时出现 A→B 与 B→A（除原文明确对比）",
        "cooccurrence / inferred 强度不得作为结论依据",
        "每个查询结果必须能回到具体论文位置",
    ],
}

WS = re.compile(r"[\s\-_·・]+")


def norm_name(s):
    s = str(s or "").strip().lower()
    s = WS.sub("", s)
    s = re.sub(r"[（）()【】\[\]“”\"'.,;:：，；]", "", s)
    # 常见缩写后缀：-based / -type / 研究方法
    s = re.sub(r"(based|type|method|model|approach)$", "", s)
    return s


def load_graph(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def cmd_schema(args):
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(SCHEMA, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "out": args.out,
                      "entity_types": len(SCHEMA["entity_types"]),
                      "relation_types": len(SCHEMA["relation_types"])}, ensure_ascii=False))
    return 0


def resolve(ents, ref):
    """把 id 或 name 解析为实体 id；返回 (id, 是否歧义)"""
    if ref is None:
        return None, False
    ref = str(ref)
    if ref in ents:
        return ref, False
    byname = [e for e in ents.values() if e.get("name") == ref]
    if len(byname) == 1:
        return byname[0]["id"], False
    if len(byname) > 1:
        return byname[0]["id"], True
    byalias = [e for e in ents.values() if ref in (e.get("aliases") or [])]
    if len(byalias) == 1:
        return byalias[0]["id"], False
    return None, False


def cmd_check(args):
    g = load_graph(args.graph)
    if "_error" in g:
        print(json.dumps({"ok": False, "error": g["_error"]}, ensure_ascii=False))
        return 1
    raw_ents = g.get("entities") or []
    raw_rels = g.get("relations") or g.get("edges") or []
    ents, missing_fields = {}, []
    for i, e in enumerate(raw_ents):
        eid = str(e.get("id") or e.get("name") or f"e{i+1}")
        rec = {"id": eid, "name": str(e.get("name") or "").strip(),
               "type": str(e.get("type") or "").strip(),
               "aliases": [str(a).strip() for a in (e.get("aliases") or []) if str(a).strip()],
               "anchor": e.get("anchor") or e.get("evidence_anchor"),
               "evidence": e.get("evidence") or e.get("quote"),
               "confidence": e.get("confidence")}
        ents[eid] = rec
        if not rec["name"] or not rec["type"]:
            missing_fields.append({"kind": "entity", "id": eid,
                                   "missing": [k for k in ("name", "type") if not rec[k]]})

    dangling, unsupported, unknown_pred, missing_rel = [], [], [], []
    direction_pairs = {}
    weak, degrees = [], {k: 0 for k in ents}
    valid_preds = set(SCHEMA["relation_types"].keys())
    anti = set(SCHEMA["antisymmetric_relations"])

    for i, r in enumerate(raw_rels):
        rid = str(r.get("id") or f"r{i+1}")
        s_ref, o_ref = r.get("subject") or r.get("from"), r.get("object") or r.get("to")
        pred = str(r.get("predicate") or r.get("type") or "").strip()
        s_id, s_amb = resolve(ents, s_ref)
        o_id, o_amb = resolve(ents, o_ref)
        if not s_id or not o_id:
            dangling.append({"id": rid, "subject": s_ref, "object": o_ref, "predicate": pred,
                             "anchor": r.get("anchor"),
                             "missing": [x for x, v in (("subject", s_id), ("object", o_id)) if not v],
                             "action": "端点必须先作为实体登记，或修正拼写"})
            continue
        if s_amb or o_amb:
            dangling.append({"id": rid, "subject": s_ref, "object": o_ref, "predicate": pred,
                             "reason": "端点名称对应多个实体，存在歧义",
                             "action": "改用实体 id 引用"})
        anchor = r.get("anchor") or r.get("evidence_anchor")
        evidence = r.get("evidence") or r.get("quote")
        if not anchor or not evidence:
            unsupported.append({"id": rid, "subject": s_id, "object": o_id, "predicate": pred,
                                "missing": [x for x, v in (("anchor", anchor), ("evidence", evidence)) if not v],
                                "action": "补论文位置与原文片段；补不出则删除该关系"})
        if pred and pred not in valid_preds:
            unknown_pred.append({"id": rid, "predicate": pred,
                                 "action": f"改用 schema 内关系类型（{', '.join(sorted(valid_preds))}）或说明新增理由"})
        strength = str(r.get("strength") or "").strip()
        if strength in ("cooccurrence", "inferred") and str(r.get("used_as_conclusion") or "").lower() in ("1", "true", "yes"):
            weak.append({"id": rid, "strength": strength,
                         "action": "共现/推断强度不得作为结论依据，改写为 uncertain 或补直接证据"})
        if pred in anti:
            direction_pairs.setdefault((frozenset((s_id, o_id)), pred), []).append(rid)
        degrees[s_id] = degrees.get(s_id, 0) + 1
        degrees[o_id] = degrees.get(o_id, 0) + 1

    # 别名归一后的重复实体
    buckets = {}
    for e in ents.values():
        for nm in [e["name"]] + e["aliases"]:
            if nm:
                buckets.setdefault(norm_name(nm), set()).add(e["id"])
    duplicates = []
    seen_groups = set()
    for k, ids in buckets.items():
        if len(ids) > 1:
            sig = frozenset(ids)
            if sig in seen_groups:
                continue
            seen_groups.add(sig)
            names = [ents[i]["name"] or i for i in ids]
            duplicates.append({"normalized": k, "entity_ids": sorted(ids), "names": names,
                               "action": "确认是否同一对象：是则合并并保留 aliases，否则在各自名称中加区分说明"})

    # 方向冲突：A-B 同时存在双向
    conflicts = []
    seen_pairs = {}
    for i, r in enumerate(raw_rels):
        s_id, _ = resolve(ents, r.get("subject") or r.get("from"))
        o_id, _ = resolve(ents, r.get("object") or r.get("to"))
        pred = str(r.get("predicate") or r.get("type") or "").strip()
        if not s_id or not o_id or pred not in anti:
            continue
        seen_pairs.setdefault((s_id, pred), set()).add(o_id)
    reported = set()
    for (s_id, pred), objs in seen_pairs.items():
        for o_id in objs:
            if s_id in seen_pairs.get((o_id, pred), set()):
                sig = (frozenset((s_id, o_id)), pred)
                if sig in reported:
                    continue
                reported.add(sig)
                conflicts.append({"a": s_id, "b": o_id, "predicate": pred,
                                  "action": "antisymmetric 关系出现双向，确认原文是否真的互为关系，否则删一条"})

    isolated = [{"id": k, "name": ents[k]["name"]} for k, d in degrees.items() if d == 0]
    covered = len(raw_rels) - len(unsupported) - len(dangling)
    report = {
        "ok": True, "graph": str(args.graph),
        "entity_count": len(ents), "relation_count": len(raw_rels),
        "dangling_count": len(dangling), "unsupported_count": len(unsupported),
        "unknown_predicate_count": len(unknown_pred),
        "duplicate_group_count": len(duplicates),
        "direction_conflict_count": len(conflicts),
        "isolated_count": len(isolated), "weak_evidence_count": len(weak),
        "missing_field_count": len(missing_fields),
        "evidence_coverage": round(covered / len(raw_rels), 4) if raw_rels else 0.0,
        "avg_degree": round(sum(degrees.values()) / max(1, len(ents)), 3),
        "dangling": dangling[:40], "unsupported": unsupported[:40],
        "duplicates": duplicates[:30], "unknown_predicates": unknown_pred[:30],
        "direction_conflicts": conflicts[:20], "isolated": isolated[:30],
        "weak_evidence": weak[:20], "missing_fields": missing_fields[:30],
        "verification_hint": {
            "entity_grounding": f"实体 {len(ents)} 个；缺 name/type {len(missing_fields)} 个",
            "relation_integrity": f"关系 {len(raw_rels)} 条；悬空 {len(dangling)}；证据缺失 {len(unsupported)}",
            "alias_alignment": f"疑似重复实体组 {len(duplicates)}；孤立实体 {len(isolated)}",
            "evidence_coverage": f"证据齐备关系 {covered} / {len(raw_rels)}（{round(covered/max(1,len(raw_rels))*100,1)}%）",
        },
    }
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "kg_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# 知识图谱结构校验报告", "",
          f"- 实体 {len(ents)} 个｜关系 {len(raw_rels)} 条｜平均度 {report['avg_degree']}",
          f"- 悬空边 {len(dangling)}｜证据缺失 {len(unsupported)}｜未知关系类型 {len(unknown_pred)}",
          f"- 疑似重复实体组 {len(duplicates)}｜方向冲突 {len(conflicts)}｜孤立实体 {len(isolated)}", ""]
    for title, items, fmt in [
        ("悬空边（端点不存在）", dangling, lambda x: f"- `{x['id']}` {x['subject']} -{x['predicate']}-> {x['object']} 缺 {x['missing']}"),
        ("关系缺证据（必须补或删）", unsupported, lambda x: f"- `{x['id']}` {x['subject']} -{x['predicate']}-> {x['object']} 缺 {x['missing']}"),
        ("疑似重复实体（确认合并）", duplicates, lambda x: f"- {x['names']}（归一后 `{x['normalized']}`）"),
        ("未知关系类型", unknown_pred, lambda x: f"- `{x['id']}` predicate=`{x['predicate']}`"),
        ("方向冲突", conflicts, lambda x: f"- {x['a']} <-> {x['b']} 同为 `{x['predicate']}`"),
        ("孤立实体（无任何关系）", isolated, lambda x: f"- `{x['id']}` {x['name']}"),
    ]:
        if items:
            md += [f"## {title}", ""] + [fmt(x) for x in items[:25]] + [""]
    md += ["## 自检口径建议", ""] + [f"- `{k}`：{v}" for k, v in report["verification_hint"].items()]
    (outdir / "kg_report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ["entity_count", "relation_count", "dangling_count",
                                            "unsupported_count", "duplicate_group_count",
                                            "direction_conflict_count", "isolated_count",
                                            "evidence_coverage", "avg_degree"]}, ensure_ascii=False))
    return 0


def cmd_query(args):
    g = load_graph(args.graph)
    if "_error" in g:
        print(json.dumps({"ok": False, "error": g["_error"]}, ensure_ascii=False))
        return 1
    ents = {}
    for i, e in enumerate(g.get("entities") or []):
        eid = str(e.get("id") or e.get("name") or f"e{i+1}")
        ents[eid] = e
    rels = g.get("relations") or g.get("edges") or []

    seeds = set()
    if args.entity:
        target = norm_name(args.entity)
        for eid, e in ents.items():
            names = [e.get("name")] + list(e.get("aliases") or [])
            if any(norm_name(n) == target for n in names if n):
                seeds.add(eid)
    if args.predicate:
        for r in rels:
            if str(r.get("predicate") or "") == args.predicate:
                for k in ("subject", "object"):
                    v = r.get(k)
                    if v in ents:
                        seeds.add(v)
    if not seeds and not (args.entity or args.predicate):
        seeds = set(ents.keys())

    frontier, visited = set(seeds), set(seeds)
    for _ in range(max(0, args.hops)):
        nxt = set()
        for r in rels:
            s, o = r.get("subject"), r.get("object")
            if s in frontier and o in ents and o not in visited:
                nxt.add(o)
            if o in frontier and s in ents and s not in visited:
                nxt.add(s)
        visited |= nxt
        frontier = nxt

    sub_rels = [r for r in rels
                if (r.get("subject") in visited or r.get("object") in visited)
                and (not args.predicate or str(r.get("predicate")) == args.predicate)]
    sub_ents = [ents[k] for k in visited if k in ents]
    out = {
        "ok": True, "query": {"entity": args.entity, "predicate": args.predicate, "hops": args.hops},
        "seed_ids": sorted(seeds),
        "entity_count": len(sub_ents), "relation_count": len(sub_rels),
        "entities": sub_ents, "relations": sub_rels,
        "unresolved": [] if seeds else [f"未找到实体: {args.entity}"],
        "note": "每条边返回其 anchor 与 evidence，可直接回查原文；无结果时如实返回空并说明。",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="文献知识图谱结构校验与查询")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("schema"); s1.add_argument("--out", required=True)
    s2 = sub.add_parser("check"); s2.add_argument("--graph", required=True); s2.add_argument("--out", required=True)
    s3 = sub.add_parser("query"); s3.add_argument("--graph", required=True)
    s3.add_argument("--entity"); s3.add_argument("--predicate"); s3.add_argument("--hops", type=int, default=1)
    a = ap.parse_args()
    return {"schema": cmd_schema, "check": cmd_check, "query": cmd_query}[a.cmd](a) or 0


if __name__ == "__main__":
    sys.exit(main())
