"""FastAPI 入口：智慧引才图谱后端（一期 MVP 单体版）。"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .database import SessionLocal, init_db
from .models import Resume
from .routers import jobs, match, resumes

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="智慧引才图谱 API", version="0.1.0",
              description="高层次人才引进「岗位需求 × 人才简历」智能匹配（内网版）")

# 一期内部工具：放开内网跨域；二期接 SSO 后收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resumes.router)
app.include_router(jobs.router)
app.include_router(match.router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    _recover_stuck_parsing()


def _recover_stuck_parsing() -> None:
    """服务重启会把后台解析任务打断，导致简历永远卡在"解析中"。
    启动时将这些记录标记为解析中断，用户可在前端一键重新解析。"""
    db = SessionLocal()
    try:
        stuck = list(db.scalars(select(Resume)))
        recovered = 0
        for r in stuck:
            conf = r.confidence or {}
            if conf.get("_parsing"):
                r.confidence = {"_error": "解析被服务重启中断，请点击「重新解析」"}
                recovered += 1
        if recovered:
            db.commit()
            logging.getLogger(__name__).info("恢复 %d 份卡在解析中的简历", recovered)
    finally:
        db.close()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
