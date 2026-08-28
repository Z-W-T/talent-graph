"""简历上传解析 / 检索 / 人工修正 / 状态流转。"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Resume
from ..schemas import ResumeOut, ResumeUpdate
from ..services import embedding, llm, parser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resumes", tags=["resumes"])

ALLOWED_SUFFIX = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".webp"}

# resumes.name 列为 VARCHAR(64)：超长文件名（如猎头推荐报告 PDF）直接 INSERT 会触发
# StringDataRightTruncation 导致整个上传请求 500，入库前必须截断
MAX_NAME_LEN = 64


def _process_resume(resume_id: int, file_path: str) -> None:
    """后台任务：提取文本 -> LLM 结构化 -> 生成 embedding -> 更新入库。"""
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        raw_text = parser.extract_text(file_path)
        structured, confidence = llm.extract_resume_fields(raw_text)
        emb = embedding.embed_one(embedding.resume_to_text(structured, raw_text))

        resume = db.get(Resume, resume_id)
        if resume is None:
            return
        resume.raw_text = raw_text
        resume.structured = structured
        resume.confidence = confidence
        resume.embedding = emb
        resume.name = (structured.get("name") or resume.name)[:MAX_NAME_LEN]
        db.commit()
        logger.info("简历解析完成 id=%s name=%s", resume_id, resume.name)
    except Exception as e:
        logger.exception("简历解析失败 id=%s: %s", resume_id, e)
        resume = db.get(Resume, resume_id)
        if resume is not None:
            resume.confidence = {"_error": str(e)}
            db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=list[ResumeOut])
def upload_resumes(
    files: list[UploadFile],
    background_tasks: BackgroundTasks,
    source: str = Query("", description="渠道：猎头/校园/邮箱/交流会"),
    db: Session = Depends(get_db),
):
    """批量上传简历，立即返回占位记录，解析走后台任务（一期免 Celery）。"""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 先整体校验文件类型，避免"部分入库后报错"的半截状态
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in ALLOWED_SUFFIX:
            raise HTTPException(400, f"不支持的文件类型: {f.filename}")

    created: list[Resume] = []
    failed: list[str] = []
    for f in files:
        # 逐文件容错：单个文件失败不影响同批其他文件
        try:
            suffix = Path(f.filename or "").suffix.lower()
            save_path = upload_dir / f"{uuid.uuid4().hex}{suffix}"
            save_path.write_bytes(f.file.read())

            resume = Resume(
                name=Path(f.filename or "未命名").stem[:MAX_NAME_LEN],
                file_path=str(save_path),
                source=source,
                status="in_pool",
                confidence={"_parsing": True},  # 标记解析中
            )
            db.add(resume)
            db.commit()
            db.refresh(resume)
            background_tasks.add_task(_process_resume, resume.id, str(save_path))
            created.append(resume)
        except Exception as e:
            db.rollback()
            logger.exception("简历入库失败 file=%s: %s", f.filename, e)
            failed.append(f"{f.filename}: {e}")

    if not created:
        raise HTTPException(400, "全部上传失败；" + "；".join(failed))
    if failed:
        logger.warning("部分简历上传失败: %s", failed)
    return created


@router.get("", response_model=list[ResumeOut])
def list_resumes(
    keyword: str = Query("", description="姓名/专业/研究方向/技能关键词"),
    status: str = Query("", description="状态过滤"),
    low_confidence_only: bool = Query(False, description="只看低置信待修正"),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Resume).order_by(Resume.created_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Resume.status == status)
    resumes = list(db.scalars(stmt))

    if keyword:
        kw = keyword.lower()
        def hit(r: Resume) -> bool:
            s = r.structured or {}
            hay = " ".join([
                r.name, str(s.get("major") or ""), str(s.get("research") or ""),
                " ".join(s.get("skills") or []), str(s.get("work_history") or ""),
            ]).lower()
            return kw in hay
        resumes = [r for r in resumes if hit(r)]

    if low_confidence_only:
        resumes = [
            r for r in resumes
            if any(isinstance(v, (int, float)) and v < 0.7 for v in (r.confidence or {}).values())
        ]
    return resumes


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    return resume


@router.get("/{resume_id}/raw")
def get_resume_raw(resume_id: int, db: Session = Depends(get_db)):
    """查看解析原文（匹配理由可追溯用）。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    return {"id": resume.id, "raw_text": resume.raw_text}


@router.patch("/{resume_id}", response_model=ResumeOut)
def update_resume(resume_id: int, body: ResumeUpdate, db: Session = Depends(get_db)):
    """人工修正低置信字段 / 更新状态标签。修正后重新生成 embedding。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")

    if body.status:
        if body.status not in ("in_pool", "pushed", "selected", "rejected", "withdrawn"):
            raise HTTPException(400, "非法状态")
        resume.status = body.status
    if body.source is not None:
        resume.source = body.source
    if body.structured:
        resume.structured = {**(resume.structured or {}), **body.structured}
        resume.confidence = {k: v for k, v in (resume.confidence or {}).items()
                             if k not in body.structured}  # 修正过的字段清掉低置信标记
        resume.embedding = embedding.embed_one(
            embedding.resume_to_text(resume.structured, resume.raw_text)
        )
    db.commit()
    db.refresh(resume)
    return resume


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    file_path = resume.file_path
    db.delete(resume)  # 关联匹配记录随 cascade 一并删除
    db.commit()
    if file_path:  # 原件一并清理，失败不影响删除结果
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("原件删除失败 path=%s: %s", file_path, e)
    return {"ok": True}


@router.post("/{resume_id}/reparse", response_model=ResumeOut)
def reparse_resume(resume_id: int, background_tasks: BackgroundTasks,
                   db: Session = Depends(get_db)):
    """对解析失败 / 卡在解析中的简历重新触发解析。"""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(404, "简历不存在")
    if not resume.file_path or not Path(resume.file_path).exists():
        raise HTTPException(400, "原件文件已丢失，无法重新解析")
    resume.confidence = {"_parsing": True}
    db.commit()
    db.refresh(resume)
    background_tasks.add_task(_process_resume, resume.id, resume.file_path)
    return resume
