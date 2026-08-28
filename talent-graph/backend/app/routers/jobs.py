"""岗位需求录入（对话式描述 -> 结构化硬性+择优条件）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import JobRequest
from ..schemas import JobCreate, JobOut
from ..services import embedding, llm

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobOut)
def create_job(body: JobCreate, db: Session = Depends(get_db)):
    """提交自然语言岗位需求，LLM 结构化为硬性/择优条件并生成 embedding。"""
    result = llm.structure_job_request(body.raw_text)
    hard = result.get("hard_conditions") or {}
    soft = result.get("soft_conditions") or {}
    summary = result.get("summary") or ""

    job = JobRequest(
        title=body.title,
        department=body.department,
        raw_text=body.raw_text,
        hard_conditions=hard,
        soft_conditions=soft,
        embedding=embedding.embed_one(embedding.job_to_text(body.title, soft, summary)),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    return list(db.scalars(select(JobRequest).order_by(JobRequest.created_at.desc())))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobRequest, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    return job


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobRequest, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    db.delete(job)
    db.commit()
    return {"ok": True}
