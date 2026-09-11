"""数据库连接与会话管理。"""
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_add_missing_columns() -> None:
    """SQLite 无 ALTER 之外的自动迁移：旧 .db 升级时给已有表补新增列。

    模型新增列（province / department_path / majors、match_results.resume_path）
    不会由 create_all 追加到已存在的表，这里按需 ALTER TABLE ADD COLUMN，
    保证旧库升级后字段齐全不报错。
    """
    if engine.dialect.name != "sqlite":
        return
    additions = {
        "job_requests": [
            ("department_path", "TEXT"),
            ("province", "VARCHAR(64)"),
            ("majors", "TEXT"),
        ],
        "match_results": [
            ("resume_path", "VARCHAR(512)"),
        ],
        "departments": [
            ("province", "VARCHAR(64)"),
        ],
    }
    with engine.begin() as conn:
        for table, cols in additions.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in cols:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db() -> None:
    """启动时初始化：PG 启用 pgvector 扩展并建表（一期简化，正式环境用 Alembic 迁移）。

    SQLite 模式（DATABASE_URL=sqlite:///...）跳过扩展创建，embedding 以 JSON 存储、
    向量检索退化为 Python 计算；.db 文件所在目录不存在时自动创建。
    """
    if engine.dialect.name == "sqlite":
        # sqlite:///./data/talent_graph.db -> ./data 目录须存在，否则 SQLAlchemy 建库失败
        db_file = settings.database_url.replace("sqlite:///", "", 1)
        if db_file and not db_file.startswith(":"):
            Path(db_file).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    elif engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()
