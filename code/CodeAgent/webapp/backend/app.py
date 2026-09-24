import os
import sys
import json
import subprocess
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# 让后端能导入 smartcoder 包
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from smartcoder.workspace import load_input_to_workspace, list_files
from smartcoder.analyzer import analyze, render_markdown_report
from smartcoder.planner import parse_instruction_to_plan
from smartcoder.editor import apply_actions
from smartcoder import llm

app = FastAPI(title="智能编程助手 Web API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    path: str
    instruction: str
    apply: bool = False


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _verify_python_files(root: str):
    """对工作区内所有 .py 文件执行语法检查。"""
    ok = True
    msgs = []
    for py in [f for f in list_files(root) if f.endswith(".py")]:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", py],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            ok = False
            msgs.append({"status": "failed", "file": py, "message": proc.stderr.strip()})
        else:
            msgs.append({"status": "passed", "file": py})
    return {"ok": ok, "files": msgs}


@app.get("/api/config")
def get_config():
    return {
        "has_api_key": bool(llm.API_KEY),
        "model": llm.MODEL,
        "base_url": llm.BASE_URL,
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/run")
def run_pipeline(req: RunRequest):
    def event_stream():
        try:
            if not llm.API_KEY:
                yield sse({"type": "error", "message": "未配置 DEEPSEEK_API_KEY。请在项目根目录创建 config.env 文件（参考 config.env.example），填入 DEEPSEEK_API_KEY=your-key 后重启后端。"})
                return

            yield sse({"type": "log", "text": f"使用模型: {llm.MODEL} @ {llm.BASE_URL}"})

            # 1. 分析
            yield sse({"type": "stage", "stage": "analyze", "status": "running"})
            root = load_input_to_workspace(req.path, None)
            analysis_data = analyze(root)
            summary = analysis_data.get("summary", {})
            file_count = summary.get("python", 0) + summary.get("js_ts", 0)
            yield sse({"type": "log", "text": f"工作区: {root}（共 {file_count} 个代码文件）"})
            yield sse({
                "type": "stage", "stage": "analyze", "status": "done",
                "data": {
                    "root": root,
                    "summary": summary,
                    "files": [
                        {
                            "path": f.get("path"),
                            "lang": f.get("lang"),
                            "functions": [x["name"] for x in f.get("functions", [])],
                            "classes": [x["name"] for x in f.get("classes", [])],
                        }
                        for f in analysis_data.get("files", [])
                    ],
                },
            })

            # 2/3. 规划 + 试运行（失败自动重试）
            max_retries = 3
            steps = []
            applied = False
            for attempt in range(1, max_retries + 1):
                yield sse({"type": "stage", "stage": "plan", "status": "running", "attempt": attempt})
                rich_md = render_markdown_report(analysis_data, include_code=True)
                steps = parse_instruction_to_plan(req.instruction, rich_md)
                yield sse({"type": "stage", "stage": "plan", "status": "done", "attempt": attempt})
                yield sse({"type": "plan", "steps": steps, "attempt": attempt})

                yield sse({"type": "stage", "stage": "dryrun", "status": "running", "attempt": attempt})
                dry_run_result = apply_actions(root, list_files(root), steps, dry_run=True)
                yield sse({"type": "dryrun", "text": dry_run_result, "attempt": attempt})
                yield sse({"type": "stage", "stage": "dryrun", "status": "done", "attempt": attempt})

                if "- 错误:" in dry_run_result or "- Error:" in dry_run_result:
                    yield sse({"type": "log", "text": f"计划应用失败（尝试 {attempt}/{max_retries}），正在重新规划..."})
                    analysis_data["files"].append(
                        {"path": "error_log", "lang": "text", "content": dry_run_result}
                    )
                    if attempt == max_retries:
                        yield sse({"type": "error", "message": "已达到最大重试次数，任务中止。"})
                        return
                    continue
                applied = True
                break

            if not req.apply:
                yield sse({"type": "log", "text": "试运行完成。勾选「应用更改」后重新执行，即可将更改写入磁盘。"})
                yield sse({"type": "done", "applied": False})
                return

            # 4. 应用更改
            yield sse({"type": "stage", "stage": "apply", "status": "running"})
            apply_result = apply_actions(root, list_files(root), steps, dry_run=False)
            yield sse({"type": "apply", "text": apply_result})
            yield sse({"type": "stage", "stage": "apply", "status": "done"})

            # 5. 验证
            yield sse({"type": "stage", "stage": "verify", "status": "running"})
            verification = _verify_python_files(root)
            yield sse({"type": "verify", "data": verification})
            yield sse({"type": "stage", "stage": "verify", "status": "done"})

            if not verification["ok"]:
                yield sse({"type": "error", "message": "验证失败：部分 Python 文件存在语法错误。"})
                return

            yield sse({"type": "done", "applied": True})

        except FileNotFoundError as e:
            yield sse({"type": "error", "message": str(e)})
        except Exception as e:
            yield sse({"type": "error", "message": f"服务器内部错误: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
