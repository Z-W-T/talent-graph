"""全局配置：全部通过环境变量注入，默认值为本地开发用。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 数据库（PostgreSQL + pgvector）
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/talent_graph"

    # 内部大模型平台（内网 API，默认按 OpenAI 兼容协议对接）
    llm_base_url: str = "http://internal-llm-platform.local/v1"
    llm_api_key: str = "internal-key"
    llm_model: str = "internal-model"
    llm_timeout: float = 120.0        # 结构化抽取输出较长（工作经历+科研成果），60s 容易超时
    llm_max_retries: int = 3          # 稳定性兜底：失败重试 3 次 + 指数退避

    # Embedding：优先走内部平台接口；未配置则本地加载 BGE-M3
    embedding_base_url: str = ""      # 留空 = 使用本地 BGE-M3
    embedding_api_key: str = ""
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024         # BGE-M3 向量维度
    embedding_local_path: str = "BAAI/bge-m3"  # 本地模型路径或 HuggingFace 名称

    # 文件存储（一期存本地磁盘，二期可换 MinIO）
    upload_dir: str = "./data/uploads"

    # 匹配参数
    match_vector_top_k: int = 30      # 向量粗排取 Top K，再交 LLM 精排
    match_final_top_n: int = 10       # 最终输出候选人数量


settings = Settings()
