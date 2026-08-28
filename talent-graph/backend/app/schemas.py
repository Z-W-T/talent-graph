"""Pydantic 出入参模型。"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ---------- 简历 ----------
class WorkExperience(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    period: Optional[str] = None
    description: Optional[str] = None


class Achievements(BaseModel):
    papers: list[str] = []                   # 论文/著作
    patents: list[str] = []                  # 专利
    projects: list[str] = []                 # 科研项目
    awards: list[str] = []                   # 人才称号/获奖


class IntentionDetail(BaseModel):
    city: Optional[str] = None               # 期望工作地点
    salary: Optional[str] = None             # 期望薪酬
    status: Optional[str] = None             # 当前工作状态
    reason: Optional[str] = None             # 跳槽原因/求职动机


class ResumeStructured(BaseModel):
    """LLM 抽取的简历结构化字段。"""
    name: Optional[str] = None
    education: Optional[str] = None          # 学历：博士/硕士/本科...
    major: Optional[str] = None              # 专业
    birth_date: Optional[str] = None         # 出生年月（原文），年龄由后端据此推算
    age: Optional[int] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    work_history: Optional[str] = None       # 工作履历摘要
    work_experiences: list[WorkExperience] = []  # 逐段工作经历
    research: Optional[str] = None           # 研究方向
    achievements: Achievements = Achievements()  # 科研成果：论文/专利/项目/获奖
    skills: Optional[list[str]] = None
    intention: Optional[str] = None          # 求职意向概述
    intention_detail: IntentionDetail = IntentionDetail()  # 个人意愿拆分项


class ResumeOut(BaseModel):
    id: int
    name: str
    structured: dict[str, Any]
    confidence: dict[str, Any]
    status: str
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class ResumeUpdate(BaseModel):
    """人工修正低置信字段 / 更新状态。"""
    structured: Optional[dict[str, Any]] = None
    status: Optional[str] = None
    source: Optional[str] = None


# ---------- 岗位需求 ----------
class JobCreate(BaseModel):
    title: str
    department: str = ""
    raw_text: str                            # 对话式访谈汇总的自然语言需求


class JobOut(BaseModel):
    id: int
    title: str
    department: str
    raw_text: str
    hard_conditions: dict[str, Any]
    soft_conditions: dict[str, Any]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- 匹配 ----------
class MatchOut(BaseModel):
    id: int
    job_id: int
    resume_id: int
    resume_name: str
    vector_score: float
    score: float
    reason: str
    push_status: str
    created_at: datetime


class MatchRunOut(BaseModel):
    job_id: int
    total_after_hard_filter: int
    candidates: list[MatchOut]


class PushRequest(BaseModel):
    match_ids: list[int]


class FeedbackRequest(BaseModel):
    """二期预留：用人单位一键反馈 有意向/无意向。"""
    match_id: int
    result: str  # selected / rejected
