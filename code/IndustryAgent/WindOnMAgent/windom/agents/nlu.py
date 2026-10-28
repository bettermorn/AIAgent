"""感知层辅助：意图识别(规则优先 + LLM 兜底)、实体识别(设备号/部件/故障/风场)、术语归一化。"""
from __future__ import annotations

import re
from typing import Optional

from .. import db, llm
from ..ontology import COMP_NAME, FAULTS
from ..services import terms

ASSET_RE = re.compile(r"(?<![A-Za-z])(WT2|WT|OSS|CAB|MAST)[-_ ]?(\d{1,3})(?:[-_](\d{1,2}))?", re.I)
FARM_ALIASES = {"EH-01": ["东海一号", "东海1号", "eh-01", "一号场", "1号场"], "EH-02": ["东海二号", "东海2号", "eh-02", "二号场", "2号场"]}

INTENT_RULES: list[tuple[str, re.Pattern]] = [
    ("report", re.compile(r"月报|季报|年报|周报|报表|绩效报告|KPI报告|运维报告")),
    ("improve", re.compile(r"RCA|根因分析|复盘|模型评估|模型准确|模型迭代|算法准确|模型更新", re.I)),
    ("schedule", re.compile(r"跨场|多风场|统一调度|协同调配|人员调度|统一运维策略|两个风场|各风场")),
    ("efficiency", re.compile(r"发电效率|能效|功率曲线|发电量|效率损失|效率低|发电性能")),
    ("stats", re.compile(r"几张|几个|统计|KPI|平均响应|自动派发率|MTTR|修复时长|平均修复|响应时间|排名|当前告警|未关闭|待审批|清单|概况|监控覆盖|标准化率"
                          r"|(?:工单|告警|报警|风机|备件|人员|船舶|任务).{0,12}(?:多少|数量|有哪些|列表)|(?:多少|有哪些).{0,6}(?:工单|告警|报警|风机|备件|人员)")),
]
DIAG_WORDS = re.compile(r"诊断|分析|告警|报警|异常|故障|处置|处理建议|怎么办|为什么|偏高|过高|超限|温高|振动|压力低|检查|排查|原因|出问题|不正常|怎么了|发烫|过热|欠压|预警|工单")
QA_WORDS = re.compile(r"规程|依据|要求|标准|规定|流程|作业票|资质|限值|阈值|如何|怎么|什么是|是什么|哪些|步骤|注意|安全|手册|条款")


def normalize_asset(m: re.Match) -> str:
    kind, n, k = m.group(1).upper(), int(m.group(2)), m.group(3)
    if kind == "WT":
        return f"WT-{n:03d}"
    if kind == "WT2":
        return f"WT2-{n:03d}"
    if kind == "OSS":
        return f"OSS-{n:02d}"
    if kind == "MAST":
        return f"MAST-{n:02d}"
    return f"CAB-{n:02d}-{int(k or 1):02d}"


def extract_assets(text: str) -> tuple[list[str], list[str]]:
    """返回(台账存在的设备, 台账不存在的编码)。"""
    found, missing = [], []
    for m in ASSET_RE.finditer(text or ""):
        code = normalize_asset(m)
        if code in found or code in missing:
            continue
        (found if db.q1("SELECT 1 FROM assets WHERE code=%s", (code,)) else missing).append(code)
    return found, missing


def extract_farm(text: str) -> Optional[str]:
    t = (text or "").lower()
    for code, names in FARM_ALIASES.items():
        if any(n.lower() in t for n in names):
            return code
    return None


def extract_component(text: str) -> Optional[str]:
    best = None
    for key, name, syns in terms.dictionary("component"):
        for cand in [name, *syns]:
            if cand and len(cand) >= 2 and cand.lower() in (text or "").lower():
                if best is None or len(cand) > best[1]:
                    best = (key, len(cand))
    return best[0] if best else None


_SYM = [("TempHigh", re.compile(r"温|热|烫")), ("VibHigh", re.compile(r"振|抖")), ("PressLow", re.compile(r"压力|欠压"))]


def resolve_fault(text: str, comp: Optional[str] = None, use_llm: bool = False) -> Optional[str]:
    """文本 → 标准故障键。先同义词最长匹配；再 部件+症状；最后(可选) LLM 判别。"""
    t = terms.n(text)
    best, best_len = None, 0
    for key, name, syns in terms.dictionary("fault"):
        for cand in [name, *syns]:
            c = terms.n(cand)
            if len(c) >= 4 and c in t and len(c) > best_len:
                best, best_len = key, len(c)
    if best:
        return best
    comp = comp or extract_component(text)
    cands = [k for k, f in FAULTS.items() if comp and f["comp"] == comp]
    if len(cands) == 1:
        return cands[0]
    if cands:
        for sym, rx in _SYM:
            if rx.search(text):
                for k in cands:
                    want = {"TempHigh": "Temp", "VibHigh": "Vibration", "PressLow": "Pressure"}[sym]
                    if want in k:
                        return k
    if use_llm and llm.available():
        r = terms.normalize(text, "fault", use_llm=True, record=False)
        return r["std_key"]
    return None


def classify_intent(text: str, has_asset: bool, use_llm: bool = True) -> dict:
    """规则优先；规则未决且文本较长时用 LLM 分类。返回 {'intent','by','strength'}"""
    for name, rx in INTENT_RULES:
        if rx.search(text):
            if name == "stats" and has_asset and DIAG_WORDS.search(text) and not re.search(r"多少|几张|统计|数量|有哪些|列表|清单", text):
                break
            return {"intent": name, "by": "rule", "strength": "strong"}
    if has_asset and DIAG_WORDS.search(text):
        return {"intent": "diagnose", "by": "rule", "strength": "strong"}
    if has_asset:
        return {"intent": "diagnose", "by": "rule", "strength": "weak"}
    if QA_WORDS.search(text) or len(text) < 40 or not use_llm or not llm.available():
        return {"intent": "qa", "by": "rule", "strength": "weak"}
    try:
        r = llm.chat_json([
            {"role": "system", "content": "判断风电运维用户问题的意图，只能从 qa(知识/规程问答)、diagnose(故障诊断)、stats(统计查询)、efficiency(发电效率)、report(报表)、schedule(跨场调度)、improve(根因分析/模型评估) 中选择。输出 JSON：{\"intent\":\"...\"}"},
            {"role": "user", "content": text}], max_tokens=60, retries=0)
        it = r.get("intent")
        if it in {"qa", "diagnose", "stats", "efficiency", "report", "schedule", "improve"}:
            return {"intent": it, "by": "llm", "strength": "llm"}
    except Exception:
        pass
    return {"intent": "qa", "by": "rule", "strength": "weak"}


def sensors_hint(text: str) -> Optional[str]:
    return None
