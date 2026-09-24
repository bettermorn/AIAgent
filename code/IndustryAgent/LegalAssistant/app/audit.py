"""审计日志：记录每次请求的提示/响应哈希与时间戳"""
import hashlib
import json
from datetime import datetime, timezone

from app import config

LOG_FILE = config.REPORTS_DIR / "audit_log.jsonl"


def log_event(endpoint: str, prompt: str, response: str, extra: dict | None = None) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest()[:16],
        "extra": extra or {},
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
