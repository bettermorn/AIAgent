"""轻量中文向量化：字符 uni/bi-gram 哈希嵌入（离线、无外部依赖）。

文档选型为 bge-m3 + bge-reranker（私有化 TEI 部署）。为让系统在无 GPU 环境下可直接运行，
此处提供同接口的哈希嵌入实现；生产环境可将 embed() 替换为 TEI 服务调用而不影响上层。
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np

DIM = 512
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_\.]*|[\u4e00-\u9fff]")


def tokens(text: str) -> list[str]:
    """英文数字按词(转小写)，中文按单字，再叠加中文相邻 bigram。"""
    out: list[str] = []
    prev_cn = None
    for m in _WORD.finditer(text or ""):
        w = m.group(0)
        if "\u4e00" <= w[0] <= "\u9fff":
            out.append(w)
            if prev_cn is not None and m.start() == prev_cn[1]:
                out.append(prev_cn[0] + w)
            prev_cn = (w, m.end())
        else:
            out.append(w.lower())
            prev_cn = None
    return out


def _h(tok: str) -> int:
    return int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")


def embed(text: str) -> list[float]:
    v = np.zeros(DIM, dtype=np.float32)
    for tok, c in Counter(tokens(text)).items():
        h = _h(tok)
        sign = 1.0 if (h >> 63) & 1 else -1.0
        w = (1.0 + math.log(c)) * (1.6 if len(tok) > 1 and "\u4e00" <= tok[0] <= "\u9fff" else 1.0)
        v[h % DIM] += sign * w
    n = float(np.linalg.norm(v))
    if n > 0:
        v /= n
    return v.tolist()


def cosine(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    d = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / d) if d else 0.0
