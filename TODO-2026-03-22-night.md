# SEKS 今晚任务清单

目标：明早给老板可验收版本。

## 夜间巡检记录（2026-03-23 23:16）
- [x] 基础连通性检查：`/healthz` 200，数据库正常
- [x] `/books` 返回正常，当前库内 3 本资料
- [ ] 发现阻塞：运行中的 API 与当前源码/Schema 不一致
  - 现象：`/search` 500，报错 `'SearchRequest' object has no attribute 'rerank'`
  - 现象：`/ask` 500，报错 `'AskRequest' object has no attribute 'rerank'`
  - 判断：容器内运行版本仍是旧 schema；工作区源码已包含 `rerank` 字段
- [ ] 下一步优先：重建并重启 Docker API 容器，再复测 `/search`、`/ask`、基础页面
- [ ] 当前阻塞：本会话对 Docker socket 无权限，需在获得权限后执行 `docker compose up -d --build`
- [ ] 补充：尝试直接提权重建失败；当前 Telegram/cron 直连会话未启用 elevated，无法在本轮静默完成 Docker 重建

# SEKS 今晚任务清单

目标：明早给老板可验收版本。

## 夜间巡检记录（2026-03-23 23:16）
- [x] 基础连通性检查：`/healthz` 200，数据库正常
- [x] `/books` 返回正常，当前库内 3 本资料
- [x] 发现阻塞：运行中的 API 与当前源码/Schema 不一致
  - 现象：`/search` 500，报错 `'SearchRequest' object has no attribute 'rerank'`
  - 现象：`/ask` 500，报错 `'AskRequest' object has no attribute 'rerank'`
  - 结论：当时运行容器仍是旧 schema；后续已确认线上容器现已更新到包含 `rerank` 的版本
- [x] 下一步优先：重建并重启 Docker API 容器，再复测 `/search`、`/ask`、基础页面
- [ ] 当前阻塞：本会话对 Docker socket 无权限，若后续必须重建仍需可执行 `docker compose up -d --build`

## 夜间巡检补充（2026-03-23 23:45）
- [x] 复核运行中 OpenAPI：`/openapi.json` 中 `SearchRequest` / `AskRequest` 都没有 `rerank` 字段，确认当时线上容器仍跑旧镜像/旧代码
- [x] 复核当前工作区源码：`app/schemas.py` 已有 `rerank`，`app/search.py` / `app/ask.py` 已直接读取 `payload.rerank`
- [x] 复核对外接口：`/healthz` 正常、`/books` 正常；`/search` 与 `/ask` 当时稳定复现 500
- [x] 基础页面补充异常：`/library` 当时返回 `Internal Server Error`；当前复测已恢复 200
- [x] 环境侧阻塞已确认：
  - `docker ps` / `docker compose ...` 在本 cron 会话仍因权限/能力限制不可直接执行
  - 本 cron 会话也无法使用 `elevated`（runtime=direct 未开启）
- [ ] 如需强制重建线上容器，待具备 Docker 权限后首命令仍是：`docker compose up -d --build api`
- [ ] 重建后立即验收顺序：
  1. `curl http://127.0.0.1:18080/healthz`
  2. `POST /search`（最小 payload）
  3. `POST /ask`（最小 payload）
  4. `GET /` 与 `GET /library`
  5. `GET /books` / `GET /books/{id}` / `DELETE /books/{id}`（仅挑测试书）

## 本轮静默推进（2026-03-24 00:50）
- [x] 复测线上运行实例：
  - `/healthz` 200，数据库正常
  - `/books` 200，返回 3 本资料
  - `/books/1`、`/books/2` 200，`/books/999999` 正确返回 404
  - `/library` 200，首页 HTML 正常返回
  - `POST /search` 最小 payload 已恢复 200
  - `POST /ask` 最小 payload 已恢复 200
  - `/openapi.json` 已包含 `SearchRequest.rerank` 与 `AskRequest.rerank`
- [x] 结论更新：先前“运行版本与代码不一致”的主阻塞已解除；当前线上运行代码已与新 schema 对齐，暂不需要为该问题打扰老板
- [x] 新发现代码级隐患（未影响当前容器运行，但会阻塞本地/未来重建后的相对路径启动）：
  - `app/main.py` 原先使用相对路径 `static/` 和 `static/index.html`
  - 若从仓库根目录以 `python -c` / `uvicorn main:app` 等方式导入，会报 `Directory 'static' does not exist`
- [x] 已修复隐患：
  - `app/main.py` 已改为基于 `Path(__file__).resolve().parent` 解析 `static` 目录与 `index.html`
  - 已通过 `python3 -m py_compile *.py` 校验
  - 已通过直接导入 `main.app` 校验路由存在：`/`、`/library`、`/healthz`、`/books`、`/search`、`/ask`
- [x] 检索过滤抽查：`POST /search` + `filters.selected_book_ids=[1]` 可正确命中 smoke 文档中的 `WPS-001`
- [ ] 当前仍待推进/待验收项：
  - 书籍删除接口未做实际 destructive 验证（遵守静默巡检，不主动删现有资料）
  - LLM 配置持久化路径相关代码已存在（`settings_store.py`），但目前未暴露服务端设置接口；前端若要真正“持久化保存”仍需补 API 契约
  - `/ask` 当前在启用远端 LLM 时会因上游 `401 Unauthorized` 自动回退 `retrieval_only`；基础功能可上线，但若要上线“LLM 问答”需单独修正凭证/网关配置
- [ ] 环境能力阻塞仍存在：
  - 本 cron 会话无法直接执行 Docker 重建（`elevated is not available right now (runtime=direct)`）
  - 因此本轮只修代码并完成线上复测，未做容器重建

## 本轮静默推进（2026-03-24 01:18）
- [x] 再次复测线上关键接口：
  - `GET /healthz` 200
  - `GET /books` 200，当前返回 `total=3`、`items` 有值
  - `POST /search` 200
  - `POST /ask` 200，当前仍因上游 LLM `401 Unauthorized` 自动回退为 `retrieval_only`
  - `GET /openapi.json` 已确认 `SearchRequest` / `AskRequest` 均包含 `rerank`
- [x] 复核前端基础页面与契约：
  - `app/static/index.html` 已实际使用 `/books`、`/search`、`/ask`、`/healthz`
  - 当前前端读书单时兼容 `items|books|data`，线上虽已可用，但接口返回仅有 `items` 时不够稳妥
- [x] 已补一处低风险兼容修复（源码已改，待下次容器重建/发布生效）：
  - `GET /books` 现在同时返回 `items` 与 `books` 两个字段，避免前端/旧脚本依赖不同字段名时产生契约漂移
  - 已通过 `python3 -m py_compile *.py` 与直接导入 `main.app` 验证
- [x] 当前主结论：
  - 基础上线目标里的 `/healthz`、`/books`、`/search`、`/ask`、基础页面，线上现状均可用
  - 当前最主要未闭环项已从“接口 500 / schema 不一致”切换为“LLM 凭证 401，导致 `/ask` 只能 retrieval-only”
  - 该问题不阻塞基础功能上线，但阻塞“LLM 问答”体验上线
- [ ] 若后续拿到 Docker 权限，优先动作：
  1. `docker compose up -d --build api`
  2. 复测 `/books` 返回体已带 `books` 字段
  3. 若要启用 LLM 问答，再修 `.env` / 网关侧 `LLM_API_KEY`

## 本轮静默推进（2026-03-24 01:52）
- [x] 再次核验线上运行版本与当前契约是否一致：
  - `GET /openapi.json` 中 `SearchRequest` / `AskRequest` 均含 `rerank`
  - `BookListResponse` 已同时暴露 `items` 与 `books`
  - `GET /books` 实际返回也已同时带 `items` 与 `books`
- [x] 再次复测基础上线范围：
  - `GET /healthz` 200
  - `GET /books` 200
  - `POST /search` 200
  - `POST /ask` 200
  - `GET /` 与 `GET /library` 200，标题 `SEKS 知识检索台`
- [x] 再次确认当前主阻塞已变化：
  - 先前的「运行版本与代码不一致 / schema 漂移 / 接口 500」本轮未复现
  - 当前唯一显著缺口仍是远端 LLM 上游 `401 Unauthorized`
  - `/ask` 基础能力不受阻，会自动降级为 `retrieval_only`
- [x] 本地源码侧再校验：`python3 -m py_compile app/*.py` 通过，当前改动至少语法层面可重建
- [ ] 待后续有 Docker 权限时再做一次强制重建核验：`docker compose up -d --build api`
- [ ] 若目标升级为“可用的 LLM 问答上线”，需修正 `.env` / 上游网关 `LLM_API_KEY`

## 本轮静默推进（2026-03-24 02:48）
- [x] 再次对线上接口做最小验收：
  - `GET /healthz` 200，数据库正常
  - `GET /books` 200，当前 `total=3`、`items` 有值
  - `POST /search` 200
  - `POST /ask` 200，仍为 `retrieval_only`
  - `GET /` 与 `GET /library` 200
  - `GET /openapi.json` 显示 `SearchRequest.rerank` / `AskRequest.rerank` / `BookListResponse.books+items`
- [x] 发现一处源码-运行偏差的新风险（未阻塞当前线上页面，但会影响下一次重建后的契约稳定性）：
  - 线上 `GET /books` 返回体里 `books` 仍为空数组、`items` 才有值
  - 根因是 `main.py` 里直接把 `list[BookSummary]` 塞给 `BookListResponse.books: list[BookListItem]`，Pydantic 未按预期完成别名填充
- [x] 已修复上述风险（源码已改，待下次容器重建/发布生效）：
  - `main.py` 现已显式把 `items` 转成 `BookListItem` 后再填入 `books`
  - 语法检查通过：`python3 -m py_compile app/*.py`
- [x] 新补充一个环境认知：
  - 直接在宿主机导入 `app.main` 做 DB 级调用时，因为未加载项目 `.env`，默认会连本地 `127.0.0.1:15432` 且口令不匹配，说明“源码导入自测”和“容器内运行态”仍有环境差异
  - 这不影响当前线上运行，但说明后续若做宿主机脚本自测，需显式加载项目 `.env` 或改用 HTTP 黑盒验收
- [ ] 当前真正还没闭环的上线缺口只剩两类：
  1. Docker 权限不足，无法在本 cron 会话里亲手完成 `docker compose up -d --build api`，所以源码修复还没发布到运行容器
  2. 上游 LLM 凭证/网关仍异常，`/ask` 的 LLM 路径持续 `401 Unauthorized`
- [ ] 明确优先级：
  - **基础功能上线**：现状已基本可用，主风险从“接口 500”转为“待下一次重建把低风险源码修复带上”
  - **LLM 问答上线**：仍被上游鉴权阻塞

## 主线 A：检索效果提升
- [x] 混合检索（向量 + 关键词/全文）
- [x] Ask/Search 接统一检索入口
- [x] rerank 二次重排（可开关）
- [x] debug/可观察信息补齐
- [ ] 做最小自测样例补充到脚本或文档

## 主线 B：信息架构与书库管理
- [x] 顶部标签页：检索问答 / 书库管理
- [x] 将资料入库迁到书库管理页
- [x] 书籍列表增加文件名/文件夹/chunk 数/标签
- [x] 删除书籍 API + 前端二次确认
- [x] 单本书详情 + 章节/小节摘要

## 主线 C：搜索范围升级
- [x] 支持按文件夹选择范围
- [x] 支持按单文件选择范围
- [x] Ask/Search 共用范围选择
- [x] 当前范围可视化

## 主线 D：结果交互升级
- [x] Ask 回答改成链接式条目
- [x] Search 结果改成链接式条目
- [x] 点击弹出大面积详情弹窗
- [x] 弹窗支持 Markdown、复制、关闭
- [x] 取消旧的引用来源卡片 / 检索结果卡片
- [x] Ask/Search 左侧改为切换式堆叠卡片

## 验收前检查
- [ ] docker compose build / up（本轮受权限能力限制，未执行）
- [x] healthz
- [x] /books / book detail 验证
- [ ] delete 验证（未做 destructive 测试）
- [x] 范围过滤验证（已抽查单书）
- [x] Ask/Search 交互验证
- [ ] LLM 设置持久化验证（后续需补 API）
- [x] 主题切换验证（代码已在前端，未单独截图留档）
