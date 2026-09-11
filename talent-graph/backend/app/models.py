"""核心数据表：resumes / job_requests / match_results / departments。"""
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import settings
from .database import Base

# 简历状态机：在库 -> 已推送 -> 被选中 / 未选中(回退在库) / 已退出
RESUME_STATUS = ("in_pool", "pushed", "selected", "rejected", "withdrawn")

# 匹配结果触发来源：简历解析完成 / 岗位新建导入 / 人工重跑
MATCH_SOURCE = ("resume_upload", "job_create", "manual")

# PostgreSQL 用 pgvector 列；SQLite 演示模式退化为 JSON 存储
EMBEDDING_TYPE = (Vector(settings.embedding_dim) if settings.database_url.startswith("postgresql")
                  else JSON)


class Department(Base):
    """组织架构部门节点（邻接表）：多层级需求部门的持久化数据源。

    岗位（job_requests.department / department_path）保存的是节点名称路径的
    快照字符串；本表用于统一维护层级树，供前端级联选择，可经 Excel 批量导入。
    节点自带的 province 为该节点的所在省份；子节点留空时默认继承最近有省份的祖先，
    因此岗位的省份完全由所选部门路径决定，无需在前端另行选择。
    """
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_departments_parent_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True)
    province: Mapped[str] = mapped_column(String(64), default="")   # 所在省份（留空则由上级继承）
    sort: Mapped[int] = mapped_column(Integer, default=0)   # 同级展示顺序
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    children: Mapped[list["Department"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", order_by="Department.sort")
    parent: Mapped[Optional["Department"]] = relationship(
        back_populates="children", remote_side=[id])


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

    matches: Mapped[list["MatchResult"]] = relationship(back_populates="resume", cascade="all, delete-orphan")


class JobRequest(Base):
    __tablename__ = "job_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128), index=True)
    department: Mapped[str] = mapped_column(String(255), default="")   # 部门级联路径字符串（/ 分隔，兼容旧数据与展示）
    department_path: Mapped[list] = mapped_column(JSON, default=list)  # 部门多级级联路径（["集团","人力资源部","人才引进处"]）
    province: Mapped[str] = mapped_column(String(64), default="")      # 岗位所在省份
    majors: Mapped[list] = mapped_column(JSON, default=list)           # 岗位所需专业（显式录入，合并进 hard_conditions.majors）
    raw_text: Mapped[str] = mapped_column(Text, default="")          # 对话/表单原始输入
    hard_conditions: Mapped[dict] = mapped_column(JSON, default=dict)  # 学历/专业/年龄等硬性条件
    soft_conditions: Mapped[dict] = mapped_column(JSON, default=dict)  # 研究方向/技能/履历/意愿
    embedding = mapped_column(EMBEDDING_TYPE, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open / closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    matches: Mapped[list["MatchResult"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class MatchResult(Base):
    """匹配结果表：简历 × 岗位 两两匹配的预计算结果。

    写入时机（均为幂等 upsert，按 job_id + resume_id 去重）：
    - 简历上传解析完成（含重新解析）→ 与所有「招聘中」岗位匹配，来源 resume_upload；
    - 岗位新建 / Excel 导入成功 → 与库内在池简历匹配，来源 job_create；
    - 匹配页手动点「执行匹配」重跑 → 来源 manual。

    匹配页面只查询本表，不再实时跑两级引擎；`score` 为 LLM 综合分（0-100），
    `vector_score` 为向量粗排相似度，`reason` 为可追溯的逐条匹配理由。
    推送 / 反馈状态保存在本表 push_status，简历状态同步回流到 resumes.status。
    """
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint("job_id", "resume_id", name="uq_match_results_job_resume"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job_requests.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True)
    # 简历原件在服务器上的完整路径快照：导出名单时据此把简历一并打包，
    # 即使简历行之后被删除/改名，历史匹配记录仍能定位当时的原件。
    resume_path: Mapped[str] = mapped_column(String(512), default="")
    vector_score: Mapped[float] = mapped_column(Float, default=0.0)  # 向量粗排相似度
    score: Mapped[float] = mapped_column(Float, default=0.0)         # LLM 精排综合分 0-100
    reason: Mapped[str] = mapped_column(Text, default="")            # 逐条匹配理由（可追溯）
    match_source: Mapped[str] = mapped_column(String(16), default="manual")  # 触发来源
    push_status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True)  # pending/pushed/selected/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job: Mapped[JobRequest] = relationship(back_populates="matches")
    resume: Mapped[Resume] = relationship(back_populates="matches")
