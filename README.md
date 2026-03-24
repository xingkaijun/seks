# SEKS

轻量级造船/工程资料知识检索与问答工具，适合在 x270 这类本地机器上运行。

## 当前能力

- 文档入库：`POST /ingest`
- 混合检索：`POST /search`（全文检索 + 向量检索）
- 问答整理：`POST /ask`
  - 未配置 LLM 时：`retrieval_only`
  - 配置 LLM 后：`llm_rag`
- 单页中文 Web UI：`GET /`

## 组件

- PostgreSQL 16 + pgvector
- FastAPI API 服务
- 单文件前端页面（`app/static/index.html`）
- 本机监听（默认只绑定 `127.0.0.1`）

## API

- `GET /healthz`
- `POST /ingest`
- `POST /search`
- `POST /ask`

## 快速启动

```bash
cd /home/kjxing/workspace/seks
cp .env.example .env
docker compose up -d --build
```

健康检查：

```bash
curl http://127.0.0.1:18080/healthz
```

打开页面：

- <http://127.0.0.1:18080/>

## 目录映射与 `file_path` 怎么填

这是最容易踩坑的点：

- **宿主机目录**：`/home/kjxing/data/bookrag/library/`
- **容器内目录**：`/data/library/`

SEKS 的 `/ingest` 读取的是 **API 容器内路径**，所以请求里的 `file_path` 应该写：

```json
{
  "file_path": "/data/library/你的文件.pdf"
}
```

而不是宿主机路径：

```json
{
  "file_path": "/home/kjxing/data/bookrag/library/你的文件.pdf"
}
```

### 正确示例

先把文件放到宿主机：

```bash
/home/kjxing/data/bookrag/library/spec.pdf
```

然后调用：

```bash
curl -fsS -X POST http://127.0.0.1:18080/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "/data/library/spec.pdf",
    "title": "Spec PDF",
    "author": null,
    "edition": null,
    "publish_year": null,
    "domain_tags": ["spec"]
  }' | python -m json.tool
```

## `/ask` 的 LLM 配置

SEKS 现在支持给 `/ask` 挂一个 **OpenAI-compatible** LLM。

### 支持的配置项

在 `.env` 中配置：

```env
LLM_ENABLED=true
LLM_BASE_URL=https://example.com/v1
LLM_API_KEY=your_key_here
LLM_MODEL=qwen3-coder-flash
LLM_TEMPERATURE=0.2
LLM_TIMEOUT=60
```

### 字段说明

- `LLM_ENABLED`
  - `true`：启用 LLM
  - `false` 或留空：关闭 LLM，`/ask` 自动退回 retrieval-only
- `LLM_BASE_URL`
  - OpenAI-compatible 基础地址
  - 例如：`https://api.openai.com/v1`
  - 或自建网关：`https://<your-gateway>/v1`
- `LLM_API_KEY`
  - 对应的 API key
  - 如果你的自托管网关不需要 key，可留空
- `LLM_MODEL`
  - 要调用的模型名
  - 例如：`qwen3-coder-flash`、`glm4.7`、`gpt-4o`、`deepseek-chat`
- `LLM_TEMPERATURE`
  - 温度参数，默认 `0.2`
- `LLM_TIMEOUT`
  - 请求超时（秒），默认 `60`

### 行为说明

- 当 LLM 配置完整且可用时，`/ask` 返回 `mode="llm_rag"`
- 当 LLM 未配置、关闭、或调用失败时，`/ask` 自动回退为 `mode="retrieval_only"`
- 返回结构里会包含：
  - `answer`
  - `citations`
  - `sources`
  - `mode`
  - `debug`

## 示例：问答请求

```bash
curl -fsS -X POST http://127.0.0.1:18080/ask \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "Hull welding spec 用哪个 WPS？",
    "top_k": 5
  }' | python -m json.tool
```

返回里你会看到类似：

```json
{
  "question": "Hull welding spec 用哪个 WPS？",
  "answer": "...",
  "citations": [...],
  "sources": [...],
  "mode": "llm_rag",
  "debug": {...}
}
```

如果没开 LLM，则 `mode` 会是：

```json
"retrieval_only"
```

## 最小验收流程

### 1) 启动服务

```bash
docker compose up -d --build
```

### 2) 健康检查

```bash
curl -fsS http://127.0.0.1:18080/healthz | python -m json.tool
```

期望：

```json
{"ok": true, "database": true}
```

### 3) 入库 smoke 文档

仓库默认映射：

- Host: `/home/kjxing/data/bookrag/library/seks-smoke.txt`
- Container: `/data/library/seks-smoke.txt`

```bash
curl -fsS -X POST http://127.0.0.1:18080/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "/data/library/seks-smoke.txt",
    "title": "SEKS Smoke Doc",
    "author": null,
    "edition": null,
    "publish_year": null,
    "domain_tags": ["smoke"]
  }' | python -m json.tool
```

期望：`status=ok` 且 `chunk_count >= 1`

### 4) 检索测试

```bash
curl -fsS -X POST http://127.0.0.1:18080/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"WPS-001","top_k":5}' | python -m json.tool
```

期望：`hits` 非空

### 5) 问答测试

```bash
curl -fsS -X POST http://127.0.0.1:18080/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hull welding spec 用哪个 WPS？","top_k":5}' | python -m json.tool
```

期望：

- `answer` 非空
- `citations` 至少 1 条
- 未配 LLM 时 `mode=retrieval_only`
- 配好 LLM 后 `mode=llm_rag`

## 前端页面说明

首页已经调整为：

- 上半区：**问答（Ask）**、**检索（Search）**
- 下半区：**资料入库（Ingest）**、使用说明

而且页面文案已改成中文，适合直接给中文用户使用。

## Tailscale 访问（推荐）

默认服务只绑定 localhost，不直接暴露公网。

如果要在 tailnet 内访问，可使用：

```bash
./scripts/tailscale-serve-enable.sh
```

之后可从 tailnet 内其他设备访问：

```bash
https://<this-node-magicdns-name>/
```

关闭：

```bash
./scripts/tailscale-serve-disable.sh
```

## 备注

- 默认 embedding 路线：`sentence-transformers + multilingual-e5-small + CPU`
- 当前 schema 假设 embedding 维度为 `384`，若换模型维度，需要改 SQL 并重新 ingest
- 如果切换 embedding 模型，建议重新入库，避免旧向量和新向量混用
- 当前支持入库的主要文件类型：`.txt`、`.md`、`.pdf`
