# 智慧引才图谱 · 初版代码（MVP）

高层次人才引进「岗位需求 × 人才简历」智能匹配系统。依据《技术栈选型说明》与《解决方案建议》实现一期演示主线：

**上传 → 解析 → 匹配 → 推送 → 导出**

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Ant Design 5 |
| 后端 | Python 3.12 + FastAPI + SQLAlchemy 2.0 |
| 数据库 | PostgreSQL 16 + pgvector |
| LLM | 内部大模型平台（内网 API，OpenAI 兼容协议，重试 3 次 + 指数退避） |
| Embedding | 内部平台接口（优先）或本地 BGE-M3 |
| OCR | PaddleOCR（扫描件/图片简历） |
| 文档解析 | PyMuPDF（PDF）+ python-docx（Word） |
| 导出 | openpyxl |

> 按选型说明的 MVP 裁剪：用 FastAPI BackgroundTasks 代替 Celery+Redis；原件存本地磁盘；单用户无登录。

## 目录结构

```
talent-graph/
├── docker-compose.yml          # 一键编排：PG/pgvector + 后端 + 前端
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example            # 复制为 .env 后填内部平台地址
│   └── app/
│       ├── main.py             # FastAPI 入口
│       ├── config.py           # 环境变量配置
│       ├── database.py         # 连接 + 建表（pgvector 扩展）
│       ├── models.py           # resumes / job_requests / match_records
│       ├── schemas.py
│       ├── routers/            # resumes / jobs / match 三组 API
│       └── services/
│           ├── parser.py       # PDF/Word/图片文本提取（扫描件走 OCR）
│           ├── llm.py          # 内部平台客户端 + 结构化抽取 + 匹配理由
│           ├── embedding.py    # 平台接口或本地 BGE-M3
│           ├── matching.py     # 两级匹配引擎（硬过滤→向量粗排→LLM 精排）
│           └── exporter.py     # Excel 名单导出
└── frontend/
    ├── Dockerfile / nginx.conf
    └── src/
        ├── api/client.ts       # Axios 封装 + 类型
        └── pages/              # 上传解析 / 岗位录入 / 匹配结果 / 简历库
```

## 快速启动

### 方式一：Docker Compose（推荐）

```bash
cd talent-graph
cp backend/.env.example backend/.env   # 填写内部大模型平台地址
docker compose up -d --build
```

- 前端：http://localhost:8080
- API 文档：http://localhost:8000/docs

### 方式二：本地开发

```bash
# 数据库（或本地已有 PG+pgvector）
docker compose up -d db

# 后端
cd backend
pip install -r requirements.txt
cp .env.example .env    # DATABASE_URL 改为 localhost
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev             # http://localhost:5173，已配置 /api 代理
```

## 使用流程（对应演示主线）

1. **简历上传解析**：批量上传 PDF/Word/图片 → 后台解析 → 低置信字段高亮；
2. **简历库检索**：人工修正低置信字段（保存后自动重新生成向量）；
3. **岗位需求录入**：粘贴与业务部门的对话访谈内容 → LLM 结构化为硬性/择优条件；
4. **匹配结果**：选岗位 → 执行匹配 → 查看 Top 10 候选与逐条理由（可点开简历原文溯源）→ 勾选精选 → 推送 → 导出 Excel。

## 对接内部平台前需确认（选型说明遗留 4 问）

| # | 确认项 | 代码位置 |
|---|---|---|
| 1 | 接口协议是否 OpenAI 兼容 | `services/llm.py` 的 `_chat()` |
| 2 | 是否支持 JSON 模式 | `llm.py` 已做不支持时自动降级 |
| 3 | 是否提供 Embedding 接口 | `.env` 的 `EMBEDDING_BASE_URL` |
| 4 | 并发限制 | `matching.py` 的 `ThreadPoolExecutor(max_workers=4)` |

## 二期/三期预留

- `POST /api/match/feedback` 反馈回流接口已实现（匹配页有模拟回填按钮）；
- Celery+Redis 异步队列、MinIO、SSO 登录按选型说明二期接入。

## 联调测试（已通过 20/20）

无内网平台时可用 Mock 跑通全链路（后端已完成冒烟验证）：

```bash
cd backend
pip install -r requirements.txt
pip install requests

# 终端1：启动 Mock 内部大模型平台（OpenAI 兼容，返回固定 JSON + 确定性向量）
python tests/mock_llm_server.py          # 监听 :9000

# 终端2：以 SQLite 演示模式启动后端（无需 PostgreSQL）
# Git Bash:  set -a && . ./.env.test && set +a
# PowerShell: 手动设置 .env.test 中的同名环境变量
uvicorn app.main:app --port 8000

# 终端3：全链路冒烟测试
python tests/smoke_test.py
# 覆盖：健康检查→上传docx→后台解析→置信度标记→人工修正→关键词检索
#       →岗位结构化→两级匹配(理由)→推送(状态流转)→反馈回流→导出Excel
```

SQLite 演示模式说明：`DATABASE_URL=sqlite:///...` 时无需 PG/pgvector，embedding 以 JSON 存储、
向量粗排退化为 Python 余弦计算；切回 PostgreSQL 后自动使用 pgvector SQL 检索。

## 已验证记录（2026-08-21）

- 后端 12 条 API 路由全部注册，OpenAPI 文档正常生成；
- 冒烟测试 20/20 通过（Mock LLM + SQLite 演示模式）；
- 联调中修复的两个真实缺陷：
  1. `generate_match_reason` 的 prompt 模板含 JSON 大括号，误用 `str.format` 导致精排失败 → 改为 `replace` 注入；
  2. 导出接口中文文件名未按 RFC 5987 URL 编码导致 500 → 已加 `urllib.parse.quote()`。
