# SEKS TODO

## P0 — 上线阻塞排查
- [x] 冒烟检查 `/healthz`
- [x] 冒烟检查 `/books`
- [x] 冒烟检查 `/books/{id}`
- [x] 冒烟检查 `/search`
- [x] 冒烟检查 `/ask`
- [x] 检查 `/` 基础页面可打开
- [x] 初步核对 OpenAPI / 前后端 schema 契约
- [x] 用响应哈希确认 `GET /` 与 `GET /openapi.json` 基本跟当前仓库一致
- [x] 获得 Docker 权限后确认容器 env / mounts / images / ps
- [x] 确认是否需要 docker rebuild / recreate
- [x] 部署 `/books` 返回修补并复测 `books/items/total` 一致性
- [x] 查看运行日志确认是否存在被吞掉的 500/回退错误

## P0 — 问答能力恢复
- [x] 排查 `/ask` 的 LLM 401（当前回退 retrieval-only）
- [x] 核对 `.env` 中 LLM 配置是否真实进入运行容器（结论：未生效）
- [x] 核对 `/data/cache/ui_llm_settings.json` 是否覆盖 `.env`（结论：是，且值错误）
- [x] 以代码修补方式绕过错误持久化配置（改为 `.env` 优先）
- [x] 重启 / recreate API 容器，让 `/books` 修补生效并重新加载 LLM 配置
- [x] 复测 `/ask` 直到 `mode=llm_rag`

## P1 — UI 与可用性
- [x] 实操确认“书库管理”页完整渲染 3 本书
- [x] 实操确认“查看详情”按钮链路
- [x] 实操确认“删除”按钮链路（仅针对可再生测试书 `SEKS Smoke`；删除后已重新 ingest 恢复）
- [x] 在 UI 中更清晰展示 Ask 当前模式（retrieval_only / llm_rag）
- [x] 考虑暴露 `debug.llm_error` 的轻量提示，便于排障
- [x] 补一个最小 `favicon.ico`，消除日志里的无害 404 噪音
- [x] 将前端 Ask 模型占位示例从 `gpt-5.2` 改为 `qwen3-coder-flash`，避免误导

## P2 — 配置与部署一致性
- [x] 确认当前监听基本来自 Docker 容器（18080/15432 均为 docker-proxy）
- [x] 确认当前运行态被持久化 LLM 设置覆盖（`ui_llm_settings.json` root:root，内容指向 `http://136.115.135.147:3001/v1` + `sk-test-persist`）
- [x] 记录宿主机调试环境与容器运行环境差异（当前本机直连 DB 会鉴权失败；以容器 HTTP 冒烟为准）
- [x] 若运行态与代码不一致，记录修复步骤到 README/部署文档
