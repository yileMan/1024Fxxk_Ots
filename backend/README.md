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

根据旧最近一日包重新生成测试样例：

```powershell
.\.venv\Scripts\python.exe scripts\generate_ots07_samples.py `
  --source ..\doc\samples\ots_intelligence_20260822_000009.zip `
  --output-dir ..\doc\samples
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```
