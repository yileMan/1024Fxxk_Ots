## Context

参见 `proposal.md` 的动机及 `specs/collector-scope-export/spec.md` 的行为契约。当前平台已具备 `product`、`product_version`、`ots_component`、`product_ots`、`user_product_scope` 与 `audit_log`，并已有 FastAPI 分层、统一认证/管理员依赖、OpenAPI 类型生成和 Vue 管理端路由。OTS-06 依赖已归档的 OTS-04/05，不改变其主数据或授权语义。

需求基线为《OTS 信息维护平台需求规格说明》V1.6 的 `FR-EXCH-001`、`FR-EXCH-002`、`FR-EXCH-016`、`FR-EXCH-017`；方案基线为《OTS 信息维护平台系统方案》V1.6 第 3.1、8.1、13 章；数据基线为《OTS 信息维护平台数据表结构（11 表详细关系版）》V1.0 的第 7 张表与“生成外网采集范围”查询。V1 不新增采集范围、覆盖状态、导出历史或任务表。

原任务规划把 `import_batch` 建表归入 OTS-07，却要求 OTS-06 从该表读取覆盖时间。经确认，本设计将完整基线表提前到 OTS-06；OTS-07 只在既有表上实现写入和数据包契约。OTS-06 本身不产生导入批次，因此全新环境中的覆盖时间为空。

## Goals / Non-Goals

**Goals:**

- 用一次一致的只读视图生成预览或下载所需的当前有效 OTS 范围、逐 OTS 最近成功覆盖时间和范围变化摘要。
- 固定可由 OTS-07 校验和引用的 CSV 字节契约、导出 ID 与 SHA-256 语义。
- 通过完整 `import_batch` 基线模型和迁移消除 OTS-06/07 的数据依赖倒置，同时保持 11 张应用基础表上限。
- 在管理端提供管理员可验收的范围预览、变化提示、错误状态和文件下载纵向切片。

**Non-Goals:**

- 不保存导出快照或摘要；本 change 的“上次范围”仅指最近成功导入批次中实际使用并保存的范围快照。
- 不实现 OTS-07 的上传、包格式校验、批次状态写入，不伪造成功批次来提供演示覆盖时间。
- 不实现外部服务的初始回溯配置、联网采集、匹配、游标或日志。
- 不改变 OTS/产品版本停用、关联删除和历史引用保护规则。

## Decisions

### 1. OTS-06 创建完整 `import_batch` 基线表

新增下一编号的迁移，一次性创建数据基线定义的全部字段：批次标识与格式、文件与摘要、归档路径、整体覆盖时间、状态、`result_json`、`error_json`、`scope_coverage_json`、`manifest_json`、导入人及各时间字段；同时创建 `batch_no`、`package_sha256` 唯一键，`status + created_at`、`covered_to` 索引和 `imported_by → app_user.id` 外键。新增对应 SQLAlchemy 模型，但 OTS-06 只读取 `status`、两个 JSON 字段和排序时间。

选择完整建表而不是只建 OTS-06 所需列，原因是数据基线已经固定表结构，分两次补列会增加迁移和回滚复杂度，也会让 OTS-07 面对临时 Schema。替代方案“等待 OTS-07 建表并在表不存在时返回空覆盖时间”无法满足 OTS-06 的覆盖时间契约，已否决。`doc/Task.md` 在实施验收时同步修改 OTS-06/07 的建表归属，需求和 11 表基线本身不变。

### 2. 采用一个预览资源和一个下载动作

- `GET /api/v1/collector-scope`：返回 JSON 预览，包含 `scope_count`、`items`、`comparison_baseline` 和 `changes`。每项包含 `ots_id`、`ots_name`、`ots_version`、`official_website`、可空 `last_covered_time` 与 `is_initial_collection`。
- `GET /api/v1/collector-scope/export`：重新读取同一领域快照并返回 `text/csv; charset=utf-8`，文件名固定为 `collector_scope.csv`。响应头 `X-Scope-Export-ID` 返回 UUID v4，`X-Content-SHA256` 返回对响应完整字节计算的小写十六进制 SHA-256。

下载动作不接收客户端提供的范围或导出 ID，防止客户端把过期预览转换为看似最新的文件。预览与下载之间主数据发生变化时，下载以请求当时数据为准；前端下载后刷新预览。两个接口均复用现有 `require_admin`，不使用普通用户产品范围授权，因为采集范围是跨全部启用产品的系统级离线交换信息。

替代方案“一个接口通过 `Accept` 协商 JSON/CSV”会使 OpenAPI、浏览器下载和错误响应更难区分；因此使用显式 `/export`。

### 3. 在 Repository 中分别读取当前范围与历史批次，在 Service 中组合

当前范围查询按 `product.status='active' → product_version.status='active' → product_ots → ots_component` 连接，直接以 OTS 主键去重并按 `ots_component.id` 升序返回。筛选和去重在 SQL 完成，避免先加载产品关联再在应用层裁剪。

历史批次按 `status='succeeded'` 且 `finished_at DESC, created_at DESC, id DESC` 分页读取。Service 对受信任 JSON 契约做结构和时间校验：

- 范围比较基线取排序最靠前且 `manifest_json` 含有效范围快照的成功批次；当前 OTS ID 集与快照 ID 集做差，返回新增/移除 ID 和数量。没有有效快照时返回 `available=false`，不把当前范围视为全量新增。
- 每个当前 OTS 独立选择排序扫描中第一条状态为 `succeeded` 且具有有效 `covered_to` 的覆盖记录。`failed`、`not_run`、缺少时间的记录均不推进覆盖位置；找不到则返回 `null` 和 `is_initial_collection=true`。
- JSON 结构或时间值违反已保存成功批次契约时终止请求，记录不含敏感内容的结构化错误，并返回 `COLLECTOR_SCOPE_HISTORY_INVALID`；不静默使用可能错误的覆盖位置。

V1 当前范围最多约 200 个 OTS，分页扫描成功批次直到找到比较基线且已为所有当前 OTS 找到覆盖时间；若仍有首次采集 OTS则扫描到批次结束。该方案利用现有 `idx_import_status_time`，避免引入覆盖状态表或 MySQL 专用 `JSON_TABLE` 查询，也保持测试数据库与 MySQL 行为一致。后续性能证据若显示批次数增长导致超标，应在不改变行为契约的前提下评估 JSON 查询优化，不能先增加第 12 张表。

### 4. 预览与导出使用请求级一致读和纯内存结果

每个请求在同一 SQLAlchemy Session/事务中读取当前范围及历史批次，并在事务结束前构造不可变领域快照。MySQL 使用既有 InnoDB 一致读语义，保证单个响应不会混合两个时点的关联和批次数据。请求不调用 `commit`、不实例化审计服务，也不保存导出 ID。

CSV 在内存中以标准 CSV 转义生成。固定 UTF-8 无 BOM、CRLF、表头与 OTS ID 升序；时间统一序列化为 UTC RFC 3339，精确到毫秒并以 `Z` 结尾，空覆盖时间输出空字段。先生成完整字节，再计算摘要并一次性返回，因此失败时不会发送部分文件。V1 上限约 200 行，不需要流式导出。

### 5. 前端使用生成类型展示预览，用 Blob 完成下载

新增管理员路由 `/system/data-exchange/collector-scope` 和“数据交换”导航入口，路由元数据继续使用 `requiresAuthentication + requiresAdmin`。页面首次进入和手动刷新时请求预览：顶部展示范围数量和比较基线，变化区域分别显示新增/移除数量及 OTS，表格展示 OTS、官网、最近覆盖时间或“首次采集”。无基线、空范围、加载失败和 403 分别显示独立状态。

OpenAPI 更新后重新生成 TypeScript 类型；JSON client 只组合生成类型。下载 client 读取 Blob、`Content-Disposition` 和摘要响应头后触发浏览器保存，不把文件内容或导出 ID 写入浏览器持久存储。下载失败沿用统一错误反馈，成功后显示导出 ID 和摘要的短确认并刷新预览。

### 6. 错误、隐私和审计边界

认证失败沿用 `401 AUTH_SESSION_INVALID`，非管理员沿用 `403 AUTH_FORBIDDEN`。历史 JSON 不合法使用 `500 COLLECTOR_SCOPE_HISTORY_INVALID`，数据库或未分类失败保持统一 `500 INTERNAL_ERROR`，所有错误包含关联 ID但不回显 JSON、SQL、文件路径或凭据。

预览和 CSV 仅包含规格列出的 OTS 信息及必要范围元数据；查询不选择产品描述、人员、授权、漏洞或评估字段。成功与失败请求都不写 `audit_log`，测试通过请求前后行数和关键表快照验证，而不是仅断言未调用某个 mock。

## Risks / Trade-offs

- [提前创建 `import_batch` 会改变 OTS-07 原任务描述] → 在本 change 的设计、任务和 `doc/Task.md` 追溯中明确所有权，OTS-07 只能复用和验证既有表，不重复建表。
- [扫描历史 JSON 的成本随批次数增长] → 使用状态时间索引、降序分页与已找到 OTS 集合提前结束；在代表性批次规模上记录查询数和耗时。
- [成功批次 JSON 损坏会阻止全部范围导出] → 导入阶段必须先验证后写成功状态；本 change 对损坏数据显式失败，避免外部服务从错误覆盖位置采集。
- [预览后再下载可能遇到范围变化] → 下载始终重新生成权威快照并返回独立导出 ID/摘要，前端下载后刷新预览。
- [CSV 中名称或网址含逗号、引号、换行] → 使用标准 CSV 转义并以字节级契约测试；不通过手工字符串拼接生成。
- [回滚 `import_batch` 会删除未来批次历史] → 回滚文档要求仅在后续依赖尚未部署且表为空时执行；存在数据或下游外键时先停止并备份，不自动级联。

## Migration Plan

1. 新增完整 `import_batch` 编号 SQL 迁移和回滚说明，先在空库与包含 001～008 的升级库验证字段、JSON 类型、索引、唯一键、外键和重复执行检测。
2. 部署后端模型与只读接口；此时表为空，现有业务不受影响，所有当前范围 OTS 均显示首次采集。
3. 更新 OpenAPI、生成前端类型并部署采集范围页面；验证管理员纵向下载和非管理员拒绝。
4. 实施 OTS-07 时直接使用该表，不再创建或重定义表结构，并按本 change 的 CSV/摘要契约保存实际范围快照。
5. 回滚时先回滚前端与后端引用；仅确认无批次数据且无后续表外键依赖后执行删表。若已有数据或已部署 OTS-07 及后续迁移，禁止直接删表，应恢复应用版本或制定独立向前修复迁移。
