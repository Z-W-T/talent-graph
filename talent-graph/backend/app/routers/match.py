"""匹配执行 / 结果查询 / 推送 / 反馈回流 / Excel 导出。"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import JobRequest, MatchRecord, Resume
from ..schemas import FeedbackRequest, MatchOut, MatchRunOut, PushRequest
from ..services import exporter, matching

router = APIRouter(prefix="/api/match", tags=["match"])


def _to_out(rec: MatchRecord) -> MatchOut:
    return MatchOut(
        id=rec.id, job_id=rec.job_id, resume_id=rec.resume_id,
        resume_name=rec.resume.name if rec.resume else "",
        vector_score=rec.vector_score, score=rec.score,
        reason=rec.reason, push_status=rec.push_status, created_at=rec.created_at,
    )


@router.post("/run/{job_id}", response_model=MatchRunOut)
def run_match(job_id: int, db: Session = Depends(get_db)):
    """执行两级匹配：硬性过滤 -> 向量粗排 -> LLM 精排+理由。"""
    job = db.get(JobRequest, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    total, records = matching.run_match(db, job)
    return MatchRunOut(job_id=job_id, total_after_hard_filter=total,
                       candidates=[_to_out(r) for r in records])


@router.get("/{job_id}", response_model=list[MatchOut])
def list_matches(job_id: int, db: Session = Depends(get_db)):
    records = (
        db.query(MatchRecord)
        .filter(MatchRecord.job_id == job_id)
        .order_by(MatchRecord.score.desc())
        .all()
    )
    return [_to_out(r) for r in records]


@router.post("/push")
def push_candidates(body: PushRequest, db: Session = Depends(get_db)):
    """HR 复核精选后触发推送：匹配记录 -> pushed，简历状态 -> 已推送。"""
    records = db.query(MatchRecord).filter(MatchRecord.id.in_(body.match_ids)).all()
    if not records:
        raise HTTPException(404, "未找到匹配记录")
    for rec in records:
        rec.push_status = "pushed"
        if rec.resume and rec.resume.status in ("in_pool", "rejected"):
            rec.resume.status = "pushed"
    db.commit()
    return {"ok": True, "pushed": len(records)}


@router.post("/feedback")
def feedback(body: FeedbackRequest, db: Session = Depends(get_db)):
    """二期预留：用人单位一键反馈 有意向/无意向，状态自动回流。"""
    rec = db.get(MatchRecord, body.match_id)
    if rec is None:
        raise HTTPException(404, "匹配记录不存在")
    if body.result not in ("selected", "rejected"):
        raise HTTPException(400, "result 仅支持 selected / rejected")
    rec.push_status = body.result
    if rec.resume:
        # 被选中 -> selected；未选中 -> 回退在库（rejected 状态仍可参与他岗匹配）
        rec.resume.status = "selected" if body.result == "selected" else "rejected"
    db.commit()
    return {"ok": True}


@router.get("/{job_id}/export")
def export_matches(job_id: int, db: Session = Depends(get_db)):
    job = db.get(JobRequest, job_id)
    if job is None:
        raise HTTPException(404, "岗位不存在")
    data = exporter.export_match_list(db, job_id)
    # RFC 5987：中文文件名必须 URL 编码，否则 latin-1 编码报错 500
    filename = quote(exporter.export_filename(job.title))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
