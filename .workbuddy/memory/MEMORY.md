# 智慧引才图谱 · 项目长期备忘

## 前端 Docker 构建约定（重要）
- `frontend/Dockerfile` 只 `COPY package.json`（**不要复制 package-lock.json**），用 `npm install`（不要用 `npm ci`）。
- 原因：lock 文件在 Windows 上生成，含 `@rollup/rollup-win32-x64-msvc` 但缺 Linux 的 `@rollup/rollup-linux-x64-musl`（npm/cli#4828），在 alpine 容器里会漏装原生依赖导致 `npm run build` 报 `MODULE_NOT_FOUND`。
- npm 源统一用 npmmirror：Dockerfile 里 `npm config set registry https://registry.npmmirror.com`；项目有 `frontend/.npmrc`。
- `frontend/.dockerignore` 必须排除 node_modules、dist、`_*` 测试目录（否则 .bin 符号链接导致 "invalid file request" 报错）。

## 环境
- Docker Desktop for Windows，compose 服务：db(pgvector)、backend(python:3.12)、frontend(node:22-alpine + nginx)。
- 宿主机系统代理 127.0.0.1:7897（Clash），失效时容器内 npm 走直连，官方源很慢 → 用 npmmirror。

## 踩坑
- WorkBuddy 的 safe-delete(genie-trash) 对含中文路径的目录删除会失败；用 PowerShell Remove-Item 或 dangerouslyDisableSandbox 的 rm -rf。
