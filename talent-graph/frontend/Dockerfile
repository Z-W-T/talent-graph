FROM node:22-alpine AS build
WORKDIR /app

# 只复制 package.json（不复制 package-lock.json）：lock 文件是在 Windows 上生成的，
# 会漏装 Linux 平台的 rollup 原生二进制（@rollup/rollup-linux-x64-musl，npm/cli#4828）
COPY package.json ./

# 使用国内镜像源（npmmirror）加速，规避 npmjs 官方源慢/超时问题
RUN npm config set registry https://registry.npmmirror.com \
    && npm install --no-audit --no-fund

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
