"""RAG 检索服务：语料加载、分块、本地 TF-IDF 向量检索

说明：DeepSeek 不提供 Embedding API，因此本演示使用基于字符二元组
的 TF-IDF 检索（无需外部服务、无需 FAISS），对小规模法规语料效果良好。
"""
import hashlib
import re
from pathlib import Path

import numpy as np

from app import config

# ---------------------------------------------------------------------------
# 语料加载与分块
# ---------------------------------------------------------------------------


def _parse_meta(text: str, path: Path) -> dict:
    """从语料文本中解析标题 / 生效日期 / 来源"""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0] if lines else path.stem
    date = ""
    url = ""
    for ln in lines:
        m = re.search(r"生效日期[：:]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", ln)
        if m and not date:
            date = m.group(1)
        m = re.search(r"来源[：:]\s*(.+)", ln)
        if m and not url:
            url = m.group(1).strip()
    return {"title": title, "date": date, "url": url}


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    step = max(size - overlap, 1)
    return [text[i : i + size] for i in range(0, len(text), step) if text[i : i + size]]


def _load_corpus() -> list[dict]:
    docs: list[dict] = []
    if not config.CORPUS_DIR.exists():
        return docs
    for path in sorted(config.CORPUS_DIR.glob("*")):
        if path.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        meta = _parse_meta(text, path)
        for idx, chunk in enumerate(
            _chunk_text(text, config.RETRIEVER_CHUNK_SIZE, config.RETRIEVER_CHUNK_OVERLAP)
        ):
            docs.append(
                {
                    "chunk_id": f"{path.stem}#{idx}",
                    "title": meta["title"],
                    "date": meta["date"],
                    "url": meta["url"],
                    "text": chunk,
                }
            )
    return docs


# ---------------------------------------------------------------------------
# TF-IDF 索引（字符二元组）
# ---------------------------------------------------------------------------

_index: dict | None = None


def _tokenize(text: str) -> list[str]:
    normalized = re.sub(r"\s+", "", text.lower())
    return [normalized[i : i + 2] for i in range(len(normalized) - 1)]


def _build_index(docs: list[dict]) -> dict:
    vocab: dict[str, int] = {}
    tokenized: list[list[str]] = []
    for doc in docs:
        tokens = _tokenize(doc["text"])
        tokenized.append(tokens)
        for tok in set(tokens):
            vocab.setdefault(tok, len(vocab))

    n_docs = len(docs)
    df = np.zeros(len(vocab))
    for tokens in tokenized:
        for tok in set(tokens):
            df[vocab[tok]] += 1
    idf = np.log((1.0 + n_docs) / (1.0 + df)) + 1.0

    matrix = np.zeros((n_docs, len(vocab)))
    for i, tokens in enumerate(tokenized):
        if not tokens:
            continue
        counts: dict[int, int] = {}
        for tok in tokens:
            idx = vocab.get(tok)
            if idx is not None:
                counts[idx] = counts.get(idx, 0) + 1
        for idx, cnt in counts.items():
            matrix[i, idx] = cnt / len(tokens) * idf[idx]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    return {"docs": docs, "vocab": vocab, "idf": idf, "matrix": matrix}


def build_or_load() -> dict:
    global _index
    if _index is None:
        docs = _load_corpus()
        if not docs:
            _index = {"docs": [], "vocab": {}, "idf": np.zeros(0), "matrix": np.zeros((0, 0))}
        else:
            _index = _build_index(docs)
    return _index


def _query_vector(query: str, index: dict) -> np.ndarray:
    vec = np.zeros(len(index["vocab"]))
    tokens = _tokenize(query)
    if not tokens or not index["vocab"]:
        return vec
    counts: dict[int, int] = {}
    for tok in tokens:
        idx = index["vocab"].get(tok)
        if idx is not None:
            counts[idx] = counts.get(idx, 0) + 1
    for idx, cnt in counts.items():
        vec[idx] = cnt / len(tokens) * index["idf"][idx]
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def search(query: str, k: int | None = None) -> list[dict]:
    """检索与 query 最相关的语料块，返回带相似度得分的结果"""
    k = k or config.RETRIEVER_TOP_K
    index = build_or_load()
    if not index["docs"]:
        return []
    vec = _query_vector(query, index)
    scores = index["matrix"] @ vec
    k = min(k, len(index["docs"]))
    top = np.argsort(-scores)[:k]
    hits = []
    for i in top:
        if scores[i] <= 0:
            continue
        doc = dict(index["docs"][i])
        doc["score"] = float(scores[i])
        hits.append(doc)
    return hits


def corpus_fingerprint() -> str:
    """语料库内容指纹（用于审计日志）"""
    index = build_or_load()
    joined = "\n".join(d["text"] for d in index["docs"])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 问答（RAG + DeepSeek）
# ---------------------------------------------------------------------------

QA_SYSTEM = (
    "你是一名严谨的法律合规研究助手。仅依据用户提供的事实来源作答，"
    "不要编造。如果事实来源不足以回答问题，请明确说明。用简体中文回答，"
    "在答案中用 [1][2] 这样的标记引用对应的事实来源编号。"
)


def answer_question(question: str, jurisdictions: list[str] | None = None,
                    as_of: str | None = None) -> dict:
    hits = search(question)
    sources = [
        {
            "index": i + 1,
            "chunk_id": h["chunk_id"],
            "title": h["title"],
            "date": h["date"],
            "url": h["url"],
            "excerpt": h["text"][:300],
            "score": round(h["score"], 3),
        }
        for i, h in enumerate(hits)
    ]
    context = "\n\n".join(f"[{s['index']}] {s['title']}\n{s['excerpt']}" for s in sources)

    parts = [f"问题：{question}"]
    if jurisdictions:
        parts.append(f"适用司法辖区：{', '.join(jurisdictions)}")
    if as_of:
        parts.append(f"答案应反映该日期时点的法规状态：{as_of}")
    parts.append(f"\n事实来源：\n{context or '（无相关语料）'}")
    parts.append("\n请依据以上事实来源回答，并标注引用编号。")

    answer = ""
    if sources:
        answer = llm_chat(QA_SYSTEM, "\n".join(parts))

    confidence = min(1.0, sum(s["score"] for s in sources[:3]) / 2.0) if sources else 0.0
    return {
        "question": question,
        "answer": answer,
        "confidence": round(confidence, 2),
        "citations": sources,
        "disclaimer": config.DISCLAIMER,
    }


# 延迟导入避免循环依赖
def llm_chat(system: str, user: str) -> str:
    from app.services.llm import chat

    return chat(system, user)
