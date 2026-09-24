"""合规差距分析：企业事实 (fact) + 政策控制措施 (YAML) -> 差距报告"""
import json
from pathlib import Path

import yaml

from app import config
from app.services.llm import chat_json

# ---------------------------------------------------------------------------
# 政策加载
# ---------------------------------------------------------------------------


def load_policies() -> list[dict]:
    policies = []
    if not config.POLICIES_DIR.exists():
        return policies
    for path in sorted(config.POLICIES_DIR.glob("*.y*ml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "controls" in data:
                policies.append(data)
        except yaml.YAMLError:
            continue
    return policies


def get_policy_names() -> list[str]:
    return [p.get("id", "") for p in load_policies() if p.get("id")]


# ---------------------------------------------------------------------------
# 差距分析
# ---------------------------------------------------------------------------

GAP_SYSTEM = (
    "你是一名隐私与数据保护合规分析师。根据企业提供的事实信息，"
    "逐条评估每个控制措施的满足状态。"
    '状态只能取以下值之一："conformant"（已满足）、"partial"（部分满足）、'
    '"gap"（未满足/缺失）、"unknown"（信息不足无法判断）。'
    "严格以 JSON 数组输出，不要输出其他内容。每个元素包含字段："
    'control_id（对应输入的控制措施 id）、status、risk（low/medium/high）、'
    "explanation（一句话中文说明）、recommendation（具体整改建议，中文）、"
    "evidence_needed（建议补充的证据列表）。"
)


def analyze_gap(fact: dict, policy_ids: list[str] | None = None) -> dict:
    policies = load_policies()
    if policy_ids:
        policies = [p for p in policies if p.get("id") in policy_ids]
    if not policies:
        return {
            "fact": fact,
            "policies": [],
            "gaps": [],
            "summary": {"total": 0, "gaps": 0, "partial": 0, "conformant": 0, "unknown": 0},
            "disclaimer": config.DISCLAIMER,
        }

    controls = []
    for p in policies:
        for c in p.get("controls", []):
            controls.append(
                {
                    "control_id": c.get("id"),
                    "requirement": c.get("requirement"),
                    "policy": p.get("title"),
                    "jurisdiction": p.get("jurisdiction"),
                }
            )

    user_payload = {
        "企业事实": fact,
        "控制措施": controls,
    }
    result = chat_json(GAP_SYSTEM, json.dumps(user_payload, ensure_ascii=False))

    # 标准化输出并补充控制措施元数据
    meta = {c["control_id"]: c for c in controls}
    gaps = []
    for item in result if isinstance(result, list) else []:
        cid = str(item.get("control_id", ""))
        base = meta.get(cid, {})
        status = item.get("status", "unknown")
        if status not in {"conformant", "partial", "gap", "unknown"}:
            status = "unknown"
        gaps.append(
            {
                "control_id": cid,
                "requirement": base.get("requirement", item.get("requirement", "")),
                "policy": base.get("policy", ""),
                "jurisdiction": base.get("jurisdiction", ""),
                "status": status,
                "risk": item.get("risk", "medium"),
                "explanation": item.get("explanation", ""),
                "recommendation": item.get("recommendation", ""),
                "evidence_needed": item.get("evidence_needed", []),
            }
        )

    # 未返回的控制措施标记为 unknown
    returned = {g["control_id"] for g in gaps}
    for cid, base in meta.items():
        if cid not in returned:
            gaps.append(
                {
                    "control_id": cid,
                    "requirement": base.get("requirement", ""),
                    "policy": base.get("policy", ""),
                    "jurisdiction": base.get("jurisdiction", ""),
                    "status": "unknown",
                    "risk": "medium",
                    "explanation": "评估未能返回该控制措施的结果",
                    "recommendation": "",
                    "evidence_needed": base.get("evidence", []),
                }
            )

    summary = {
        "total": len(gaps),
        "gaps": sum(1 for g in gaps if g["status"] == "gap"),
        "partial": sum(1 for g in gaps if g["status"] == "partial"),
        "conformant": sum(1 for g in gaps if g["status"] == "conformant"),
        "unknown": sum(1 for g in gaps if g["status"] == "unknown"),
    }
    return {
        "fact": fact,
        "policies": [
            {"id": p.get("id"), "title": p.get("title"), "jurisdiction": p.get("jurisdiction")}
            for p in policies
        ],
        "gaps": gaps,
        "summary": summary,
        "disclaimer": config.DISCLAIMER,
    }
