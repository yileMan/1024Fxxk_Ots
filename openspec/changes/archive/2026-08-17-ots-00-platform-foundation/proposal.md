## Why

后续 OTS 业务模块尚缺少一致的工程结构、数据库升级路径、前后端 API 契约和自动化验证方式，导致每个 change 都可能重复决定基础技术方案并产生不兼容实现。现在先建立可在空库启动并可被 OTS-01 及后续 change 复用的平台基线，固定 `doc/Task.md` 中 ADR-01～ADR-05 的执行边界。

## What Changes

- 建立 FastAPI 后端的分层目录、环境配置、统一错误响应、结构化日志和 `/api/v1/health` 健康检查。
- 建立 MySQL 8.x 连接、事务访问边界、编号化 SQL 迁移执行器及迁移回滚说明；本 change 不创建任何业务表。
- 将前端迁移为 Vue 3 + TypeScript，确定管理端组件库、基础路由和布局、由 OpenAPI 生成的 API 类型、统一错误提示与健康页。
- 建立 pytest/MySQL 集成测试、Vitest 组件测试、Playwright 冒烟测试、前后端构建命令与新增代码 80% 覆盖率门槛。
- 提供 `.env.example`、本地开发说明和 OpenSpec capability 命名、归档约定；不提交真实凭据。

## Capabilities

### New Capabilities

- `platform-runtime`: 后端服务启动、健康检查、配置、错误响应和安全日志的统一运行时边界。
- `database-migration-foundation`: MySQL 连接、事务与编号化 SQL 迁移/回滚的基础能力。
- `frontend-platform-shell`: Vue TypeScript 管理端基础壳、API 契约消费、错误反馈和健康状态展示。
- `platform-quality-gates`: 前后端测试、构建、覆盖率和端到端冒烟验证的统一质量门禁。

### Modified Capabilities

无。

## Impact

- 受影响系统：管理平台前端、FastAPI 后端、MySQL 开发与测试环境、项目文档和 CI/本地验证命令。
- 新增稳定 API：`GET /api/v1/health`；其余业务 API 与业务表由后续 change 交付。
- 依赖：Vue 3、TypeScript、管理端组件库、FastAPI、SQLAlchemy、MySQL 8.x、pytest、Vitest、Playwright 和 OpenAPI 类型生成工具。
- 需求追溯：NFR 12.1、NFR 12.3，系统方案 2.3、9，以及 `doc/Task.md` ADR-01～ADR-05。
- 后续依赖：`ots-01-local-authentication` 及其后的所有 OTS V1 change。
