# OTS Backend

## 启动

```powershell
.\.venv\Scripts\python.exe run.py
```

服务地址：<http://localhost:5353>

复制 `config.example.yaml` 为 `config.yaml` 后填写本地 MySQL 连接。`config.yaml` 已被 Git 忽略；生产环境可用 `OTS_DATABASE_URL` 环境变量覆盖它。迁移采用编号 SQL，不使用 Alembic：

```powershell
py run.py migrate
py run.py
```

初始化管理员（密码使用无回显输入；自动化部署可改用 `OTS_INITIAL_ADMIN_PASSWORD` 环境变量）：

```powershell
py run.py initialize-admin admin "初始管理员"
```

登录只校验用户名和密码；成功后使用仅包含用户 ID 的 `ots_user_id` Cookie 识别后续请求，不需要认证密钥、来源或 Cookie 时效配置。`POST /api/v1/auth/logout` 只清除当前浏览器的 Cookie，不查询业务数据、不写审计，缺失或无效 Cookie 下也会幂等成功。

## 用户与固定角色管理

具有 `admin` 角色的用户可通过 `/api/v1/users` 分页查询、创建和编辑本地用户，并可执行密码重置与停用。固定角色仅包含 `admin`、`product_owner`、`reviewer`；一个用户可以具有多个角色。

所有编辑、密码重置和停用请求都必须携带当前 `row_version`。若返回 `USER_VERSION_CONFLICT`，应重新读取用户后再提交，不能覆盖服务器上的较新版本。停用只更新状态并保留历史；按照当前认证基线，登录仍然只校验用户名和密码。

成功的用户写操作和脱敏 `audit_log` 在同一事务提交。审计只标识密码已重置，不保存明文或密码摘要。

API 文档：<http://localhost:5353/docs>

## 产品与版本范围授权

具有 `admin` 角色的用户可在用户管理中维护产品级或版本级范围：

- `GET/POST /api/v1/users/{user_id}/scopes`
- `DELETE /api/v1/users/{user_id}/scopes/{scope_id}`
- `GET /api/v1/scopes/me`

`scope_key` 只由服务端生成：产品级为 `product:<product_id>`，版本级为
`version:<product_version_id>`。产品级范围包含该产品全部有效版本；版本级范围只包含指定有效
版本；多个范围按并集计算。管理员无需显式范围即可全局读取，但范围不会替代固定角色、当前负责人、
当前审核人或禁止自审等业务条件。

产品、版本和产品版本 OTS 清单的只读接口在服务端执行范围裁剪；范围外详情或直接 ID 请求返回
`403 PRODUCT_SCOPE_FORBIDDEN`。产品、版本、OTS 主数据和产品 OTS 关联的写接口仍仅管理员可用，
前端隐藏按钮不是安全边界。实际发生的授权增删与 `audit_log` 在同一事务提交，重复幂等请求和失败
事务不产生授权审计。

数据库升级使用 `migrations/008_user_product_scope.sql`。回滚前必须先回滚应用并备份/导出授权及
审计证据；已有授权数据的环境应保留表并采用前向修复，具体限制见
`migrations/008_user_product_scope.rollback.md`。

该能力对应 `FR-USER-003`、`FR-USER-004` 和权限规则 1～9。自动化证据位于
`tests/test_scopes.py`、`tests/test_products.py`、`tests/test_ots.py` 和 `tests/test_migrations.py`。

## OTS 与产品 OTS 清单

管理员可通过 `/api/v1/ots-components` 查询、创建和编辑 OTS，通过
`/api/v1/product-versions/{version_id}/ots` 维护产品版本与 OTS 的关联。OTS 严格使用
名称、版本、官方网站和是否 EOL 四项核心业务信息，不提供状态、停用或删除；产品版本退出使用
某 OTS 时移除关联，已有下游评估历史的关联不能移除。

产品 OTS 清单 CSV 固定使用 UTF-8 和以下表头：

```csv
ots_name,ots_version,official_website,is_eol
```

`is_eol` 仅允许 `true` 或 `false`。导入会创建缺失 OTS、复用四项字段一致的已有 OTS，
但名称/版本命中而官网或 EOL 不一致时会返回包含行号、字段和原因的冲突；任一错误都会使整份
文件不写入。模板、导出和导入端点分别为：

- `GET /api/v1/product-ots/template`
- `GET /api/v1/product-versions/{version_id}/ots/export`
- `POST /api/v1/product-versions/{version_id}/ots/import`，请求体为 `text/csv`，文件名可通过 `X-File-Name` 传递

## 采集范围导出

管理员可通过 `GET /api/v1/collector-scope` 预览当前范围，通过
`GET /api/v1/collector-scope/export` 下载 `collector_scope.csv`。范围只包含关联到启用产品和
启用产品版本的 OTS，并按 OTS ID 去重；预览会与最近成功导入批次保存的范围快照比较。

CSV 使用 UTF-8 无 BOM、CRLF 和固定列顺序：

```csv
scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time
```

每次下载生成新的 UUID v4 `scope_export_id`。响应头 `X-Scope-Export-ID` 返回该 ID，
`X-Content-SHA256` 返回对实际响应字节计算的小写十六进制 SHA-256。每个 OTS 的
`last_covered_time` 从成功批次 `scope_coverage_json` 中独立选择最近一次 `succeeded`；
后续 `failed/not_run` 不推进时间，从未成功时 CSV 保持空字段。

数据库升级由 `migrations/009_import_batch.sql` 完整创建 11 表基线中的 `import_batch`；
OTS-06 只读该表，不保存导出记录且不写 `audit_log`。回滚仅允许在表为空、没有 OTS-07
及后续外键依赖时执行，详见 `migrations/009_import_batch.rollback.md`。相关自动化证据位于
`tests/test_collector_scope.py` 和 `tests/test_migrations.py`。

## 离线数据包校验

`admin` 可使用以下同步接口校验格式版本 `1.0` 的离线 ZIP；完整生成契约和最小样例见
`doc/OTS-离线数据包契约-V1.0.md` 与 `doc/samples/ots_intelligence_20260822_010203.zip`：

格式 `1.0` 根目录只包含 `manifest.csv` 和一行一个 CVE 的 `nvd_cves.csv`。每行保存来源标识、
状态、描述、全部 CVSS/CWE/参考、原始 configuration 和归一化受影响软件/版本范围；不包含
`collector_scope.csv`、`matched_ots_json` 或内部 OTS ID。KEV/EOL 暂不接收且不放置空占位文件。

- `POST /api/v1/import-packages/validate`：`multipart/form-data` 的单个 `file`；相同整包摘要返回既有结果和 200，相同批次号但内容不同返回 `PACKAGE_BATCH_CONFLICT`。
- `POST /api/v1/import-packages/{batch_id}/confirm`：管理员确认后事务写入/更新 `vulnerability`、提交一条 `batch_upsert` 审计并将批次置为 `succeeded`；不执行内部 OTS 匹配。
- `GET /api/v1/import-packages/{batch_id}`：读取批次状态与只读预览。
- `GET /api/v1/import-packages/{batch_id}/errors`：仅失败批次下载规范错误 CSV。

默认临时目录为 `backend/var/imports/incoming`，校验成功归档到
`backend/var/imports/archive`；临时名和归档相对路径由服务端生成，API 不返回服务器路径。失败、重复或
请求异常会删除临时 ZIP；失败原包不归档。归档目录应限制为应用账户读写并与数据库做同一恢复点备份，
不得作为公开静态目录。清理归档前必须先确认对应 `import_batch` 不再需要恢复。

可通过 `OTS_IMPORT_TEMP_DIR`、`OTS_IMPORT_ARCHIVE_DIR`、`OTS_IMPORT_MAX_UPLOAD_BYTES`、
`OTS_IMPORT_MAX_MEMBER_BYTES`、`OTS_IMPORT_MAX_TOTAL_BYTES`、
`OTS_IMPORT_MAX_COMPRESSION_RATIO`、`OTS_IMPORT_MAX_CSV_ROWS`、
`OTS_IMPORT_MAX_FIELD_BYTES` 和 `OTS_IMPORT_MAX_ERRORS` 收紧限制；默认值见根目录 `.env.example`。
单字段默认上限为 1 MiB，以容纳 NVD 大型 configuration；总解压 200 MiB 和 10,000 行上限保持不变。
校验和确认在请求内同步完成，自动化测试对 10,000 个 CVE 记录耗时和峰值内存并保留五分钟验收目标；
反向代理的请求体上限应不低于应用上传上限。

OTS-07 新增 `010_vulnerability.sql` 和对应回滚说明。回滚时先关闭确认入口；若第 9、10 张下游表已引用
漏洞则禁止删除第 8 张表。已成功导入的来源事实、批次和归档不能当作临时文件清理。

## 内部 OTS 漏洞候选匹配

内部与外部采集数据使用一致的 OTS 名称，因此本功能不新增 YAML、别名表或身份映射配置。名称只做
Unicode NFKC、大小写折叠和首尾空白清理，随后精确比较；不会做子串、模糊匹配或分隔符替换。
版本按确定性自然版本规则处理精确值、`*` 和开闭区间，不可比较时保守地不生成候选。

管理员可使用以下接口：

- `GET /api/v1/import-packages/{batch_id}/ots-match-preview`：按当前事实和 OTS 主数据只读预览；
- `POST /api/v1/import-packages/{batch_id}/ots-matches`：锁定 succeeded 批次并原子重算、写入候选和审计；
- `GET /api/v1/import-packages/{batch_id}/ots-match-result`：读取最近结果，尚未执行时返回当前预览；
- `GET /api/v1/vulnerabilities/{vulnerability_id}/ots-matches`：读取候选、证据或稳定未匹配原因。

响应固定带有“候选不等于产品受影响”的提示。执行失败不会改变已导入的漏洞事实，事务回滚后批次保留
`MATCH_EXECUTION_FAILED` 供重试；并发锁冲突返回 `MATCH_ALREADY_RUNNING`。日志只记录批次 ID、算法
版本、计数、耗时和错误码，不记录证据正文。数据库升级使用
`migrations/011_vulnerability_ots_match.sql`，回滚前置检查和恢复方式见对应 rollback 文档。

根据旧最近一日包重新生成测试样例：

```powershell
.\.venv\Scripts\python.exe scripts\generate_ots07_samples.py `
  --source ..\doc\samples\ots_intelligence_20260822_000009.zip `
  --output-dir ..\doc\samples
```

OTS-08 的确定性验收包见 `doc/samples/ots_intelligence_20260831_080000.zip`，准备方式和预期结果见
`doc/samples/README.md`。

## 产品评估任务生成

OTS-10 与内部候选匹配共用上述预览、执行和结果接口。响应中的 `task_generation` 会按有效
`product_ots → product_version → product` 展开任务，记录新增、待复评、更新、未变化、跳过、失败计数及
最多 100 条样例。停用产品、停用版本、不可用负责人和无有效产品关联使用稳定原因码跳过；预览不写库，
执行会按当时的候选、产品关联和负责人重新计算。

数据库升级使用 `migrations/012_product_assessment.sql`。相同输入按产品/版本/OTS/漏洞和修订号幂等；未填写的
pending 任务可安全同步负责人，已提交或审核中的任务不会被覆盖。候选依据实质变化或移除时，已完成修订会
保留原产品结论，并生成清空提交/审核事件的 current 待复评修订。候选、任务、摘要和审计在同一事务内提交；
任一阶段失败均整体回滚并可重试。日志和审计仅保留批次、版本、计数、耗时、错误码及有界摘要，不写完整证据。

回滚前置检查、导出与恢复方式见 `migrations/012_product_assessment.rollback.md`。本阶段不接入 KEV/EOL；
更广泛的 CVSS、KEV、产品上下文变化触发复评留待 OTS-16。

## 漏洞目录与实时工作台

OTS-11 提供只读查询接口：`GET /api/v1/workbench/summary` 返回当前用户四类实时待办数量，
`GET /api/v1/assessments/tasks` 按 `queue` 分页返回负责人或当前版本审核人的任务；
`GET /api/v1/vulnerabilities` 支持 CVE、产品、OTS、CVSS v3.1 严重度、KEV、当前评估状态及
来源发布/修改时间区间的交集筛选，详情接口为 `GET /api/v1/vulnerabilities/{id}`。既有候选详情接口
继续兼容管理员全局读取，普通用户则只返回其有效产品范围内的候选。

普通用户的计数、列表、详情和候选均在 SQL 查询中按有效产品/版本范围裁剪；直接请求不可见 ID 时返回
`403`，不存在返回 `404`。管理员可额外读取 `GET /api/v1/workbench/import-summary`；错误摘要会清理归档
路径等敏感值。只有成功批次中明确的逐 OTS `scope_coverage_json` 才形成覆盖截止时间；没有该数据时返回
“未提供”，不会把 NVD 来源窗口误当作逐 OTS 覆盖。所有接口只读，不写查询审计，也未新增表、索引或迁移。

OTS-11 本身不开放评估编辑/提交/审核；候选响应继续固定声明“候选不等于产品受影响”。后续 OTS-12
已补充草稿编辑，提交/审核仍由 OTS-14 完成；复评变化说明（OTS-16）、跨产品参考（OTS-17）和完整追溯
（OTS-19）仍不在当前范围。

## 产品评估草稿编辑

OTS-12 提供 `GET /api/v1/assessments/{assessment_id}` 聚合读取当前产品上下文、来源事实、候选依据和
核心草稿，以及 `PUT /api/v1/assessments/{assessment_id}/draft` 明确保存完整草稿快照。漏洞详情的
`assessment_entries` 只返回当前用户可见的当前评估 ID、状态和产品/版本/OTS 上下文，不复制草稿字段。

草稿字段包括分析摘要、触发条件、涉及功能或接口、适用性及依据、产品影响、现有控制、处置方式及说明和
证据说明。适用性枚举为 `affected/not_affected/partly_affected/pending`；处置枚举为
`patch_or_upgrade/configuration_mitigation/isolation_or_compensating_control/accept_risk/no_action/further_investigation`
或空值。非 `pending` 适用性必须填写依据，`accept_risk/no_action` 必须填写处置说明。

只有仍具有效产品范围、匹配当前 `owner_id` 且当前修订状态为 `pending/returned/reassess` 的用户可以保存。
管理员、审核人和其他用户只能按范围读取。保存必须携带 `row_version`；旧版本返回
`ASSESSMENT_VERSION_CONFLICT`，不可编辑状态返回 `ASSESSMENT_NOT_EDITABLE`，字段问题返回带路径的
`ASSESSMENT_VALIDATION_ERROR`。实际变化会递增版本，并与脱敏 `audit_log` 在同一事务提交；长文本审计只记
空值状态、长度和 SHA-256，不复制正文。无变化、校验失败、权限失败和冲突不写审计。

本能力不新增迁移或应用基础表。CVSS v3.1 环境指标和计算由 OTS-13 完成；提交、实际提交人留痕、审核和
状态转换由 OTS-14/15 完成。

## 产品评估修订与重新提交

OTS-15 扩展退回动作：审核人退回当前 `submitted` 修订时，服务在同一事务保留带审核留痕的历史修订并创建
下一条 `returned` 当前修订；新修订继承产品结论和环境评分，清空提交/审核事件，并通过 `parent_revision_id`
连接父修订。退回响应同时包含 `current_revision` 和 `reviewed_revision`，调用方必须采用新当前 ID。

当前负责人可编辑并重新提交 `returned/reassess` 修订，也可通过
`POST /api/v1/assessments/{assessment_id}/revisions` 从当前 `completed` 修订显式创建带原因的人工复评修订。
`GET /api/v1/assessments/{assessment_id}/revisions` 返回同链摘要，`GET .../revision-comparison` 返回同链字段级
差异；历史详情始终只读，过期写请求的 `ASSESSMENT_NOT_EDITABLE` 响应携带 `current_revision_id` 供显式刷新。

修订创建复用现有 `product_assessment` 修订链和唯一键。跨产品参考和全局追溯仍分别属于 OTS-17 和 OTS-19。

## 自动复评与基线初始化

OTS-16 通过 `013_automatic_reassessment.sql` 在现有表上保存规范评估基线、指纹、变化摘要，以及产品 OTS 的
`active/disabled` 状态和乐观锁。来源确认、候选匹配、关联停用/恢复共用同一基线差异和修订克隆语义；
`completed` 创建待复评子修订，进行中状态仅合并变化并递增 `row_version`。

迁移后必须先初始化所有当前评估基线：

```powershell
.\.venv\Scripts\python.exe run.py initialize-assessment-bases --dry-run
.\.venv\Scripts\python.exe run.py initialize-assessment-bases --batch-size 500
```

只有输出 `remaining_count` 为 `0` 才可开放自动入口。命令按 ID 稳定分页、每批独立提交，可在中断后安全重跑，
且不创建修订、不改变结论、状态或行版本。NVD `1.0` 没有启用可信 KEV/EOL 输入，V1 不把缺失 KEV 当作
`false`，也不把 CVSS v4.0 或 EOL 纳入自动复评指纹。

## 测试

## 数据库变更记录与运行状态

OTS-21 将现有写路径统一到不自行提交的审计构造器。用户、授权、产品、产品版本、OTS、产品 OTS、
漏洞导入/匹配和产品评估的实际变化与 `audit_log` 处于同一事务；失败、乐观锁冲突、幂等无变化、
登录、纯查询、导出及运行探测不记录。动作仅允许 `insert/update/delete/batch_upsert`，详情带
`schema_version` 并递归脱敏密码、Cookie、令牌和长文本；历史详情保持原样兼容读取。

写路径矩阵：

| 入口 | 审计对象 | 动作与粒度 | 操作者 |
| --- | --- | --- | --- |
| 用户及角色维护 | `app_user` | 单对象新增/更新 | 当前管理员 |
| 产品范围授权 | `user_product_scope` | 单对象新增/删除 | 当前管理员 |
| 产品、版本、OTS、版本 OTS | 对应业务表名 | 单对象新增/更新/删除，CSV 按批次汇总 | 当前管理员 |
| 漏洞包导入与候选匹配 | `vulnerability`、`vulnerability_ots_match` | 每批次 `batch_upsert` 汇总 | 当前操作用户 |
| 任务生成、草稿、提交、审核和修订 | `product_assessment` | 批量生成汇总或单评估更新 | 当前用户或系统任务 |

管理员只读 API 为 `GET /api/v1/audit-logs`、`GET /api/v1/audit-logs/{id}` 和
`GET /api/v1/system/operations`。审计列表按 `created_at DESC, id DESC` 使用 keyset 游标，支持对象、
用户、动作和带时区闭区间筛选。运行信息分为应用、数据库、磁盘、最近备份、最近导入和最近失败；
分项失败不会掩盖其他结果。公开 `GET /api/v1/health` 仍保持最小响应。

备份状态生产者写入 `OTS_BACKUP_STATUS_FILE` 指向的 UTF-8 JSON，最大尺寸由
`OTS_BACKUP_STATUS_MAX_BYTES` 限制。契约 `schema_version` 固定为 `1.0`，必填字段为 `status`
（`success` 或 `failed`）、`started_at`、`finished_at`、不含路径分隔符的 `file_name` 和非负
`size_bytes`；失败时可增加安全 `error_code`。生产者必须先写同目录临时文件再原子替换，不能写绝对路径、
凭据或错误正文。OTS-21 不创建、枚举或执行备份。

```powershell
.\.venv\Scripts\python.exe -m pytest
```
