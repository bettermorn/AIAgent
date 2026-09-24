"""合同审查：提取关键条款并与基线条款比较"""
import json

from app import config
from app.services.llm import chat_json

REVIEW_SYSTEM = (
    "你是一名合同审查助理。用户会提供一份合同文本和一组基线条款要求。"
    "请提取合同中的关键条款，并与基线要求逐项比较，指出缺失、冲突或对己方不利的条款。"
    "严格以 JSON 输出，不要输出其他内容，格式为："
    '{"clauses": [{"type": "条款类型（如 保密、责任限制、争议解决、数据安全、终止等）", '
    '"excerpt": "合同原文摘录（简短）", "assessment": "有利/中性/不利/缺失", '
    '"issues": ["问题描述"], "suggestions": ["修改建议"]}], '
    '"overall_risk": "low/medium/high", "summary": "总体中文评价"}'
)


def extract_text(filename: str, content: bytes) -> str:
    """从上传的文件中提取纯文本（支持 txt/md/pdf/docx）"""
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    if lower.endswith((".doc", ".docx")):
        import io

        from docx import Document

        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    # 默认按 UTF-8 文本处理
    return content.decode("utf-8", errors="replace")


def review_contract(contract_text: str) -> dict:
    baseline = ""
    if config.BASELINE_CLAUSES_FILE.exists():
        baseline = config.BASELINE_CLAUSES_FILE.read_text(encoding="utf-8")

    user_payload = {
        "合同文本": contract_text[:8000],
        "基线条款要求": baseline or "（无）",
    }
    result = chat_json(REVIEW_SYSTEM, json.dumps(user_payload, ensure_ascii=False))

    clauses = result.get("clauses", []) if isinstance(result, dict) else []
    valid_clauses = []
    for c in clauses:
        if isinstance(c, dict) and c.get("type"):
            valid_clauses.append(
                {
                    "type": c.get("type", "其他"),
                    "excerpt": c.get("excerpt", ""),
                    "assessment": c.get("assessment", "中性"),
                    "issues": c.get("issues", []) or [],
                    "suggestions": c.get("suggestions", []) or [],
                }
            )
    return {
        "clauses": valid_clauses,
        "overall_risk": result.get("overall_risk", "medium") if isinstance(result, dict) else "medium",
        "summary": result.get("summary", "") if isinstance(result, dict) else "",
        "disclaimer": config.DISCLAIMER,
    }
