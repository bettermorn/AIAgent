# DeepSeek API 助手（从 config.env 配置文件读取 DEEPSEEK_API_KEY）。
import os, json, urllib.request, sys, pathlib

def _print(s: str):
    sys.stdout.write(s + ("\n" if not s.endswith("\n") else ""))
    sys.stdout.flush()

# config.env 的查找位置：当前工作目录、项目根目录（smartcoder 的上一级）
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONFIG_CANDIDATES = [
    pathlib.Path.cwd() / "config.env",
    _PROJECT_ROOT / "config.env",
]

def _load_config_env() -> dict:
    """
    解析 config.env 文件（KEY=VALUE 格式，支持 # 注释、可选引号）。
    优先级：环境变量 > config.env。
    """
    values = {}
    for cfg_path in _CONFIG_CANDIDATES:
        if cfg_path.is_file():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key:
                            values[key] = val
            except OSError as e:
                _print(f"警告: 读取配置文件 {cfg_path} 失败: {e}")
            break  # 只加载找到的第一个 config.env
    return values

_CFG = _load_config_env()

def _get(name: str, default: str = "") -> str:
    # 环境变量优先于配置文件
    return os.environ.get(name) or _CFG.get(name) or default

API_KEY = _get("DEEPSEEK_API_KEY") or _get("OPENAI_API_KEY")
BASE_URL = _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = _get("DEEPSEEK_MODEL", "deepseek-chat")
CONFIG_LOADED = bool(_CFG)

# 分析摘要最大字符数（防止超出模型上下文导致 HTTP 400）
MAX_ANALYSIS_CHARS = int(_get("DEEPSEEK_MAX_ANALYSIS_CHARS", "60000"))

def _truncate_analysis(summary: str) -> str:
    if len(summary) <= MAX_ANALYSIS_CHARS:
        return summary
    return summary[:MAX_ANALYSIS_CHARS] + "\n\n...[注: 代码库较大，分析内容已截断。请只针对上文列出的文件生成修改计划]"

def _extract_json(text: str):
    """从模型输出中提取JSON（容忍markdown代码块包裹）。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)

def suggest_plan_with_llm(instruction: str, analysis_summary: str) -> dict:
    if not API_KEY:
        return {}
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    analysis_summary = _truncate_analysis(analysis_summary)

    system_prompt = """你是一个专业的Python开发者AI智能体。你可以分析代码、建议更改，并提供详细的修改来实现所需功能或修复问题。

请密切注意用户的意图。例如，"来自Alice的问候"与"向Alice问候"是不同的。请仔细分析用户的指令，以理解参与者和操作的方向。

请只输出JSON，不要输出其他内容。"""

    user_prompt = f"""指令:
{instruction}

现有代码分析:
{analysis_summary}

请以以下JSON格式提供计划和实现:
{{
  "plan": ["步骤1", "步骤2", ...],
  "changes": [
    {{
      "file": "path/to/file.py",
      "description": "此更改的作用",
      "code_before": "要替换的精确代码",
      "code_after": "要插入的新代码"
    }}
  ],
  "explanation": "更改的详细说明"
}}

确保code_before与现有代码完全匹配，包括正确的缩进。"""

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 读取API返回的具体错误信息，便于定位问题
        detail = ""
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            pass
        raise RuntimeError(f"DeepSeek API 请求失败 (HTTP {e.code}): {detail or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 DeepSeek API ({BASE_URL}): {e.reason}") from e
    text = data["choices"][0]["message"]["content"]
    try:
        steps = _extract_json(text)
        if steps:
            _print(f"LLM生成的计划: {json.dumps(steps, indent=2, ensure_ascii=False)}")
        return steps
    except Exception as e:
        _print(f"解析LLM响应时出错: {text}")
        _print(f"错误: {str(e)}")
        return {}
