"""数据库连接与会话管理。"""
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


def init_db() -> None:
    """启动时初始化：PG 启用 pgvector 扩展并建表（一期简化，正式环境用 Alembic 迁移）。

    SQLite 演示模式（DATABASE_URL=sqlite:///...）下跳过扩展创建，
    embedding 以字符串形式存储，向量检索退化为 Python 计算。
    """
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    from . import models  # noqa: F401  确保模型已注册
    Base.metadata.create_all(bind=engine)
