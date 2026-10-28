"""全局配置：从 code/config.env 与环境变量读取。参数化配置对应文档“指标参数化配置，预留评审变更余量”。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config.env", override=False)


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v.strip() if v is not None and v.strip() != "" else default


def _f(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(float(_env(name, str(default))))
    except ValueError:
        return default


def _b(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # ---- LLM（DeepSeek，OpenAI 兼容接口）----
    deepseek_api_key: str = field(default_factory=lambda: _env("DEEPSEEK_API_KEY"))
    deepseek_base_url: str = field(default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    llm_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-chat"))
    # 文档“模型路由”：推理模型用于诊断解释，轻量模型用于抽取/归一化/意图识别（可分别配置）
    llm_model_reasoning: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL_REASONING", _env("DEEPSEEK_MODEL", "deepseek-chat")))
    llm_timeout: float = field(default_factory=lambda: _f("LLM_TIMEOUT", 90))
    llm_retries: int = field(default_factory=lambda: _i("LLM_RETRIES", 2))

    # ---- PostgreSQL（沿用 config.env 的 PG* 变量；库名使用独立的 WINDOM_PGDATABASE，避免污染其他项目库）----
    pg_host: str = field(default_factory=lambda: _env("PGHOST", "localhost"))
    pg_port: int = field(default_factory=lambda: _i("PGPORT", 5432))
    pg_user: str = field(default_factory=lambda: _env("PGUSER", "postgres"))
    pg_password: str = field(default_factory=lambda: _env("PGPASSWORD", ""))
    pg_database: str = field(default_factory=lambda: _env("WINDOM_PGDATABASE", "windom_agent"))
    pg_pool_max: int = field(default_factory=lambda: _i("PG_POOL_MAX", 30))

    # ---- 安全 ----
    jwt_secret: str = field(default_factory=lambda: _env("WINDOM_JWT_SECRET", "windom-dev-secret-change-me-0123456789"))
    jwt_ttl_hours: int = field(default_factory=lambda: _i("WINDOM_JWT_TTL_HOURS", 12))
    demo_password: str = field(default_factory=lambda: _env("WINDOM_DEMO_PASSWORD", "windom123"))

    # ---- 规范指标参数（T/CEATEC XXX—2025）----
    response_sla_min: float = field(default_factory=lambda: _f("SLA_RESPONSE_MIN", 30))          # 4e 故障响应 ≤30min
    auto_dispatch_target: float = field(default_factory=lambda: _f("TARGET_AUTO_DISPATCH", 0.95))  # 4e ≥95%
    algo_accuracy_target: float = field(default_factory=lambda: _f("TARGET_ALGO_ACCURACY", 0.85))  # 6.4.2 ≥85%
    model_update_days: int = field(default_factory=lambda: _i("MODEL_UPDATE_DAYS", 30))           # 6.4.2 ≤30 天
    efficiency_err_target: float = field(default_factory=lambda: _f("TARGET_EFF_ERR", 0.02))      # 4d ±2%
    realtime_retention_hours: float = field(default_factory=lambda: _f("TS_REALTIME_RETENTION_HOURS", 90 * 24))  # 实时库保留 90 天
    emergency_level: int = field(default_factory=lambda: _i("EMERGENCY_WARNING_LEVEL", 2))        # 预警≥二级 → 紧急工单

    # ---- Agent 配额（防止失控循环）----
    max_steps: int = field(default_factory=lambda: _i("AGENT_MAX_STEPS", 40))
    max_tool_calls: int = field(default_factory=lambda: _i("AGENT_MAX_TOOL_CALLS", 60))
    max_tokens_per_task: int = field(default_factory=lambda: _i("AGENT_MAX_TOKENS", 60000))
    max_task_seconds: int = field(default_factory=lambda: _i("AGENT_MAX_SECONDS", 180))
    low_confidence: float = field(default_factory=lambda: _f("LOW_CONFIDENCE", 0.45))             # L4：低于此值转人工

    # ---- 后台作业 ----
    simulator_enabled: bool = field(default_factory=lambda: _b("WINDOM_SIMULATOR", True))
    simulator_interval_s: float = field(default_factory=lambda: _f("WINDOM_SIM_INTERVAL", 30))
    monitor_enabled: bool = field(default_factory=lambda: _b("WINDOM_MONITOR", True))
    auto_diagnose: bool = field(default_factory=lambda: _b("WINDOM_AUTO_DIAGNOSE", True))        # 预警≥二级自动触发诊断
    knowledge_auto_activate: bool = field(default_factory=lambda: _b("KNOWLEDGE_AUTO_ACTIVATE", False))
    knowledge_auto_conf: float = field(default_factory=lambda: _f("KNOWLEDGE_AUTO_CONF", 0.85))


settings = Settings()
