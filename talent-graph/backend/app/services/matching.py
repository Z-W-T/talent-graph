"""两级匹配引擎：
第一级 硬性过滤 —— SQL 精确条件（学历/年龄/专业关键词），透明可审计；
第二级 择优排序 —— pgvector 余弦相似度粗排 Top K，再 LLM 逐条精排并生成理由。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import JobRequest, MatchRecord, Resume
from . import llm

logger = logging.getLogger(__name__)

_EDU_RANK = {"其他": 0, "大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def _edu_pass(resume_edu: str | None, required: str | None) -> bool:
    if not required:
        return True
    if not resume_edu:
        return False  # 硬性条件缺失不放行，交由人工补录后再匹配
    return _EDU_RANK.get(resume_edu, -1) >= _EDU_RANK.get(required, 99)


def hard_filter(db: Session, job: JobRequest) -> list[Resume]:
    """第一级：硬性过滤。学历/年龄走内存精确比对（字段在 JSON 中，先按状态粗筛），
    专业用关键词模糊匹配。未通过即排除，绝不误杀之外的简历。"""
    hard = job.hard_conditions or {}
    required_edu = hard.get("education")
    max_age = hard.get("max_age")
    majors: list[str] = [m for m in (hard.get("majors") or []) if m]

    # 只让"在库/未选中"的简历参与匹配，已退出/被选中不再消费
    stmt = select(Resume).where(Resume.status.in_(["in_pool", "rejected"]))
    candidates = list(db.scalars(stmt))

    passed: list[Resume] = []
    for r in candidates:
        s = r.structured or {}
        if not _edu_pass(s.get("education"), required_edu):
            continue
        if max_age and s.get("age") and int(s["age"]) > int(max_age):
            continue
        if majors:
            major_text = (s.get("major") or "") + " " + (s.get("research") or "")
            if not any(m in major_text for m in majors):
                continue
        passed.append(r)
    return passed


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


def vector_rank(db: Session, job: JobRequest, candidates: list[Resume]) -> list[tuple[Resume, float]]:
    """第二级·粗排：余弦相似度取 Top K。

    PostgreSQL 走 pgvector SQL 检索；SQLite 演示模式退化为 Python 内存计算。
    无 embedding 的简历跳过。
    """
    if job.embedding is None:
        logger.warning("岗位 %s 无 embedding，跳过向量粗排", job.id)
        return [(r, 0.0) for r in candidates[: settings.match_vector_top_k]]

    if db.bind.dialect.name != "postgresql":  # SQLite 演示模式
        job_vec = [float(v) for v in job.embedding]
        scored = [(r, _cosine(job_vec, [float(v) for v in r.embedding]))
                  for r in candidates if r.embedding is not None]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(r, round(s, 4)) for r, s in scored[: settings.match_vector_top_k]]

    ids = [r.id for r in candidates if r.embedding is not None]
    if not ids:
        return []
    distance = Resume.embedding.cosine_distance(job.embedding).label("distance")
    stmt = (
        select(Resume, distance)
        .where(Resume.id.in_(ids))
        .order_by(distance)
        .limit(settings.match_vector_top_k)
    )
    rows = db.execute(stmt).all()
    return [(r, round(1 - float(d), 4)) for r, d in rows]


def llm_rerank(job: JobRequest, ranked: list[tuple[Resume, float]]) -> list[dict]:
    """第二级·精排：LLM 逐条打分 + 生成理由。并发调用内部平台提升速度。"""
    job_payload = {
        "title": job.title,
        "hard_conditions": job.hard_conditions,
        "soft_conditions": job.soft_conditions,
    }

    def _score(item: tuple[Resume, float]) -> dict:
        resume, vec_score = item
        try:
            score, reason = llm.generate_match_reason(job_payload, resume.structured or {})
        except Exception as e:  # 单条失败不拖垮整批
            logger.error("LLM 精排失败 resume_id=%s: %s", resume.id, e)
            score, reason = 0.0, f"LLM 评估失败: {e}"
        return {"resume": resume, "vector_score": vec_score, "score": score, "reason": reason}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_score, ranked))
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[: settings.match_final_top_n]


def run_match(db: Session, job: JobRequest) -> tuple[int, list[MatchRecord]]:
    """完整匹配流程，落库 MatchRecord 并返回 (硬过滤通过数, 候选记录)。"""
    candidates = hard_filter(db, job)
    ranked = vector_rank(db, job, candidates)
    scored = llm_rerank(job, ranked)

    # 同一岗位重跑时清掉旧的未推送记录，避免重复
    db.query(MatchRecord).filter(
        MatchRecord.job_id == job.id, MatchRecord.push_status == "pending"
    ).delete(synchronize_session=False)

    records: list[MatchRecord] = []
    for item in scored:
        rec = MatchRecord(
            job_id=job.id,
            resume_id=item["resume"].id,
            vector_score=item["vector_score"],
            score=item["score"],
            reason=item["reason"],
        )
        db.add(rec)
        records.append(rec)
    db.commit()
    for rec in records:
        db.refresh(rec)
    return len(candidates), records
