"""核心数据表：resumes / job_requests / match_records。"""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import settings
from .database import Base

# 简历状态机：在库 -> 已推送 -> 被选中 / 未选中(回退在库) / 已退出
RESUME_STATUS = ("in_pool", "pushed", "selected", "rejected", "withdrawn")

# PostgreSQL 用 pgvector 列；SQLite 演示模式退化为 JSON 存储
EMBEDDING_TYPE = (Vector(settings.embedding_dim) if settings.database_url.startswith("postgresql")
                  else JSON)


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")          # 解析出的原文
    structured: Mapped[dict] = mapped_column(JSON, default=dict)     # 结构化字段（硬性+择优）
    confidence: Mapped[dict] = mapped_column(JSON, default=dict)     # 各字段置信度，低置信人工修正
    embedding = mapped_column(EMBEDDING_TYPE, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="in_pool", index=True)
    source: Mapped[str] = mapped_column(String(32), default="")      # 渠道：猎头/校园/邮箱/交流会
    file_path: Mapped[str] = mapped_column(String(512), default="")  # 原件路径
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    matches: Mapped[list["MatchRecord"]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class JobRequest(Base):
    __tablename__ = "job_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), index=True)
    department: Mapped[str] = mapped_column(String(128), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")          # 对话/表单原始输入
    hard_conditions: Mapped[dict] = mapped_column(JSON, default=dict)  # 学历/专业/年龄等硬性条件
    soft_conditions: Mapped[dict] = mapped_column(JSON, default=dict)  # 研究方向/技能/履历/意愿
    embedding = mapped_column(EMBEDDING_TYPE, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open / closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    matches: Mapped[list["MatchRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class MatchRecord(Base):
    __tablename__ = "match_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_requests.id"), index=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"), index=True)
    vector_score: Mapped[float] = mapped_column(Float, default=0.0)  # 向量粗排相似度
    score: Mapped[float] = mapped_column(Float, default=0.0)         # LLM 精排综合分 0-100
    reason: Mapped[str] = mapped_column(Text, default="")            # 逐条匹配理由（可追溯）
    push_status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/pushed/selected/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[JobRequest] = relationship(back_populates="matches")
    resume: Mapped[Resume] = relationship(back_populates="matches")
