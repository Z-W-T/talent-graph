"""向量化服务：优先走内部平台 Embedding 接口；未配置时本地加载 BGE-M3。

两种实现输出维度必须一致（默认 1024），与 resumes/job_requests 表的 Vector 列对齐。
"""
from __future__ import annotations

import logging

from ..config import settings

logger = logging.getLogger(__name__)

_local_model = None  # 懒加载，避免未装 sentence-transformers 的环境启动失败


def _embed_via_platform(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(base_url=settings.embedding_base_url, api_key=settings.embedding_api_key,
                    timeout=settings.llm_timeout)
    # 显式声明 encoding_format=float：SiliconFlow 等平台的 bge-m3 不传该参数会报 20015
    resp = client.embeddings.create(model=settings.embedding_model, input=texts,
                                    encoding_format="float")
    return [item.embedding for item in resp.data]


def _embed_local(texts: list[str]) -> list[list[float]]:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("加载本地 Embedding 模型: %s", settings.embedding_local_path)
        _local_model = SentenceTransformer(settings.embedding_local_path)
    vecs = _local_model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def embed_texts(texts: list[str]) -> list[list[float]]:
    if settings.embedding_base_url:
        return _embed_via_platform(texts)
    return _embed_local(texts)


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]


def _work_experiences_to_text(exps: list) -> str:
    lines = []
    for e in exps or []:
        if isinstance(e, dict):
            lines.append(" ".join(str(e.get(k) or "") for k in ("company", "title", "period", "description")).strip())
        else:
            lines.append(str(e))
    return "\n".join(x for x in lines if x)


def _achievements_to_text(ach: dict) -> str:
    if not isinstance(ach, dict):
        return str(ach or "")
    parts = []
    for key in ("papers", "patents", "projects", "awards"):
        vals = ach.get(key) or []
        parts.extend(str(v) for v in vals if v)
    return "\n".join(parts)


def _intention_to_text(structured: dict) -> str:
    detail = structured.get("intention_detail")
    parts = [str(structured.get("intention") or "")]
    if isinstance(detail, dict):
        parts.extend(str(v) for v in detail.values() if v)
    return " ".join(p for p in parts if p)


def resume_to_text(structured: dict, raw_text: str) -> str:
    """把简历揉成一段用于向量化的文本。"""
    parts = [
        str(structured.get("research") or ""),
        " ".join(structured.get("skills") or []),
        str(structured.get("work_history") or ""),
        _work_experiences_to_text(structured.get("work_experiences")),
        _achievements_to_text(structured.get("achievements")),
        _intention_to_text(structured),
        str(structured.get("major") or ""),
        raw_text[:500],
    ]
    return "\n".join(p for p in parts if p)


def job_to_text(title: str, soft: dict, summary: str = "") -> str:
    parts = [
        title, summary,
        str(soft.get("research") or ""),
        " ".join(soft.get("skills") or []),
        str(soft.get("experience") or ""),
        str(soft.get("intention") or ""),
    ]
    return "\n".join(p for p in parts if p)
