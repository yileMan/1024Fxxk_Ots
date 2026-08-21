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

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```
