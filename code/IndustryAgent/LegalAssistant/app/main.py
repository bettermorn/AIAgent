"""法律合规助手 — FastAPI 后端

- 大语言模型：DeepSeek（环境变量 DEEPSEEK_API_KEY）
- 前端：React (Vite)，开发时通过 /api 代理访问，生产环境由本服务托管 web/dist
"""
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import audit, config
from app.services import compliance, contracts, rag

app = FastAPI(title="法律合规助手", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIST = config.BASE_DIR / "web" / "dist"


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class QARequest(BaseModel):
    question: str = Field(min_length=1)
    jurisdictions: list[str] = []
    as_of: str | None = None


class FactRequest(BaseModel):
    model_config = {"extra": "allow"}

    fact: dict | None = None
    policies: list[str] | None = None


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------


@app.get("/api/healthz")
def healthz():
    return {
        "status": "ok",
        "llm": "deepseek",
        "model": config.DEEPSEEK_MODEL,
        "api_key_configured": bool(config.DEEPSEEK_API_KEY),
        "corpus_chunks": len(rag.build_or_load()["docs"]),
    }


@app.get("/api/meta")
def meta():
    return {
        "policies": [
            {"id": p.get("id"), "title": p.get("title"), "jurisdiction": p.get("jurisdiction")}
            for p in compliance.load_policies()
        ],
        "jurisdictions": [
            {"code": "EU", "name": "欧盟"},
            {"code": "US-CA", "name": "美国加利福尼亚州"},
        ],
        "disclaimer": config.DISCLAIMER,
    }


@app.post("/api/qa")
def qa(req: QARequest):
    try:
        result = rag.answer_question(
            req.question, req.jurisdictions or None, req.as_of or None
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    audit.log_event(
        "/api/qa", req.question, result["answer"], {"corpus": rag.corpus_fingerprint()}
    )
    return result


@app.post("/api/compliance/gap")
def compliance_gap(req: FactRequest):
    # 兼容两种格式：{"fact": {...}} 或直接传递扁平的企业事实对象
    fact = req.fact if req.fact is not None else dict(req.model_extra or {})
    if not fact:
        raise HTTPException(status_code=400, detail="请求体缺少企业事实数据（fact）")
    try:
        result = compliance.analyze_gap(fact, req.policies)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    audit.log_event(
        "/api/compliance/gap",
        str(sorted(fact.keys())),
        str(result["summary"]),
    )
    return result


@app.post("/api/contracts/review")
async def contracts_review(file: UploadFile | None = File(None), text: str = Form("")):
    content = text or ""
    if file is not None:
        raw = await file.read()
        try:
            content = contracts.extract_text(file.filename or "", raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"无法解析上传文件：{e}")
    if not content.strip():
        raise HTTPException(status_code=400, detail="请上传文件或直接粘贴合同文本")
    try:
        result = contracts.review_contract(content)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    audit.log_event("/api/contracts/review", content[:200], result["summary"])
    return result


# ---------------------------------------------------------------------------
# 前端托管（生产构建后生效）
# ---------------------------------------------------------------------------

if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = WEB_DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")
else:

    @app.get("/")
    def root():
        return JSONResponse(
            {
                "message": "法律合规助手 API 正在运行",
                "frontend": "开发模式下请访问 http://localhost:5173（web/ 目录下 npm run dev）",
                "docs": "/docs",
            }
        )
