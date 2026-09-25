"""
Web 后端服务：FastAPI + DeepSeek LLM
为 React 前端提供 REST API：学习会话、判分、报告、AI建议、AI对话
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from edu_agent.questions import QuestionBank
from edu_agent.memory import MemoryDB, QARecord, StudentProfile
from edu_agent.adapt import AdaptivePolicy
from edu_agent.engine import grade
from edu_agent.llm_assistant import get_llm_assistant

# ---------------- 数据与组件加载 ----------------
DATA_DIR = Path(__file__).resolve().parent / "data"
MEM_PATH = DATA_DIR / "memory.json"

bank = QuestionBank.load(DATA_DIR / "questions_en.json")
db = MemoryDB(MEM_PATH)
policy = AdaptivePolicy(review_ratio=0.6)

# 动态生成题目缓存：LLM 生成的题目不在题库中，出题时缓存，判分时查找
generated_questions: Dict[str, Any] = {}

app = FastAPI(title="EduAssistant API", version="1.0.0")

# 开发环境允许本地前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- 数据模型 ----------------
class SessionReq(BaseModel):
    user_id: str
    name: Optional[str] = None

class AnswerReq(BaseModel):
    user_id: str
    name: Optional[str] = None
    question_id: str
    answer: Any  # 选择题为索引(int)，开放题为文本

class ChatReq(BaseModel):
    user_id: str
    message: str

# ---------------- 工具函数 ----------------
def profile_summary(profile: StudentProfile) -> Dict:
    """将学生档案序列化为前端友好的结构"""
    skills = [
        {
            "tag": tag,
            "mastery": round(s.mastery, 2),
            "correct": s.correct,
            "wrong": s.wrong,
            "next_review": s.next_review,
        }
        for tag, s in sorted(profile.skills.items(), key=lambda kv: kv[1].mastery, reverse=True)
    ]
    return {
        "user_id": profile.user_id,
        "name": profile.name,
        "level": profile.level,
        "total": len(profile.history),
        "correct": sum(1 for r in profile.history if r.is_correct),
        "skills": skills,
    }

def question_payload(q) -> Dict:
    """题目数据（不泄露正确答案）"""
    return {
        "id": q.id,
        "stem": q.stem,
        "options": q.options,
        "cefr": q.cefr,
        "tags": q.tags,
        "difficulty": q.difficulty,
        "is_choice": q.options is not None,
    }

# ---------------- API 路由 ----------------
@app.get("/api/health")
def health():
    llm = get_llm_assistant()
    return {
        "status": "ok",
        "llm_enabled": llm is not None,
        "question_count": len(bank.by_id),
    }

@app.post("/api/session")
def start_session(req: SessionReq):
    """开始/恢复学习会话，返回学生档案"""
    profile = db.get_student(req.user_id, req.name or req.user_id)
    # 已存在的用户传入新姓名时，原子化更新档案中的姓名
    if req.name and req.name.strip() and profile.name != req.name.strip():
        profile = db.rename_student(req.user_id, req.name.strip())
    return {"profile": profile_summary(profile)}

@app.get("/api/question/{user_id}")
def next_question(user_id: str):
    """自适应选择下一道题"""
    profile = db.get_student(user_id)
    q = policy.select_question(bank, profile)
    if not q:
        raise HTTPException(status_code=404, detail="暂无可用题目，请扩充题库")
    # LLM 动态生成的题目不在题库中，缓存以便提交答案时查找
    if q.id not in bank.by_id:
        if len(generated_questions) >= 1000:  # 防止缓存无限增长
            generated_questions.clear()
        generated_questions[q.id] = q
    return {"question": question_payload(q)}

@app.post("/api/answer")
def submit_answer(req: AnswerReq):
    """提交答案：判分（优先 DeepSeek 智能判分）并更新学习记忆"""
    # 优先查题库，其次查动态生成的题目缓存
    q = bank.by_id.get(req.question_id) or generated_questions.get(req.question_id)
    if not q:
        raise HTTPException(status_code=404, detail=f"题目不存在或已过期，请刷新获取新题目 (id={req.question_id})")

    # 先判分（LLM调用可能耗时数秒），完成后再记录，
    # log_interaction 会在锁内重新读取最新档案，避免并发覆盖
    is_correct, explain = grade(q, req.answer)
    profile = db.get_student(req.user_id, req.name or req.user_id)

    rec = QARecord(
        qid=q.id,
        ts=datetime.utcnow().isoformat(timespec="seconds"),
        is_correct=is_correct,
        cefr=q.cefr,
        tags=q.tags,
        difficulty=q.difficulty,
        user_answer=req.answer,
        correct_answer=q.answer,
    )
    profile = db.log_interaction(profile, rec)

    return {
        "is_correct": is_correct,
        "explanation": explain,
        "correct_answer": q.answer if not q.options else q.options[q.answer],
        "level": profile.level,
        "profile": profile_summary(profile),
    }

@app.get("/api/report/{user_id}")
def get_report(user_id: str):
    """查看学习报告"""
    profile = db.get_student(user_id)
    return {"profile": profile_summary(profile)}

@app.get("/api/advice/{user_id}")
def ai_advice(user_id: str):
    """基于 DeepSeek 生成个性化学习建议"""
    profile = db.get_student(user_id)
    llm = get_llm_assistant()
    if not llm:
        return {"advice": "AI 助手未启用：请在 config.env 中配置 DEEPSEEK_API_KEY。", "llm_enabled": False}
    try:
        advice = llm.generate_learning_advice(profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI建议生成失败: {e}")
    return {"advice": advice, "llm_enabled": True}

@app.post("/api/chat")
def chat(req: ChatReq):
    """与 DeepSeek AI 学习助手对话"""
    profile = db.get_student(req.user_id)
    llm = get_llm_assistant()
    if not llm:
        return {"reply": "AI 助手未启用：请在 config.env 中配置 DEEPSEEK_API_KEY。", "llm_enabled": False}
    try:
        reply = llm.chat_with_student(req.message, profile)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话生成失败: {e}")
    return {"reply": reply, "llm_enabled": True}

# ---------------- 启动 ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
