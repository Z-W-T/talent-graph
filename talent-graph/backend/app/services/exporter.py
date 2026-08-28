"""Excel 名单导出（openpyxl）。"""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import Session

from ..models import MatchRecord

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(color="FFFFFF", bold=True)


def export_match_list(db: Session, job_id: int) -> bytes:
    """导出某岗位的匹配名单（含分数与理由）为 xlsx 字节流。"""
    records = (
        db.query(MatchRecord)
        .filter(MatchRecord.job_id == job_id)
        .order_by(MatchRecord.score.desc())
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "候选名单"
    headers = ["序号", "姓名", "学历", "专业", "年龄", "研究方向", "技能",
               "综合分", "向量相似度", "匹配理由", "推送状态"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT

    for i, rec in enumerate(records, 1):
        s = rec.resume.structured or {}
        ws.append([
            i, rec.resume.name, s.get("education"), s.get("major"), s.get("age"),
            s.get("research"), "、".join(s.get("skills") or []),
            rec.score, rec.vector_score, rec.reason, rec.push_status,
        ])

    widths = [6, 10, 8, 16, 6, 30, 24, 8, 10, 50, 10]
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + idx)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_filename(job_title: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"候选名单_{job_title}_{ts}.xlsx"
