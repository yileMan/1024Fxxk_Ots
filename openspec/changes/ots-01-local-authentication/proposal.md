## Why

OTS 管理平台需要先建立可信的本地用户身份，后续用户管理、角色授权和产品范围授权才能基于当前用户执行服务端校验。当前工程只有空白前后端骨架，尚无登录、退出、当前用户会话，也无法保证用户停用后立即失去访问权限。

## What Changes

- 创建数据基线规定的 `app_user` 和 `audit_log` 两张应用基础表；本变更仅使用 `app_user` 完成认证，`audit_log` 供后续业务变更复用。
- 提供幂等的初始化管理员命令，安全接收初始密码并保存 Argon2id 加盐摘要。
- 提供 `/api/v1/auth/login`、`/api/v1/auth/logout` 和 `/api/v1/auth/me`，使用固定两小时有效期的签名 HttpOnly Cookie 保存用户标识和时效信息。
- 每次认证请求从数据库重新读取用户状态和角色，使停用用户立即失效，不长期信任 Cookie 中的权限信息。
- 提供登录页、当前用户信息、退出入口、认证状态和路由守卫，并处理未登录、会话过期及停用反馈。
- 对 Cookie 认证下的非安全 HTTP 方法执行同源 `Origin` 校验，为后续写接口建立最低限度的 CSRF 防护约定。
- 登录成功更新 `last_login_at`；登录、退出、认证查询及该时间更新均不写入 `audit_log`。
- 需求追溯：部分支撑 FR-USER-001（本地用户和初始管理员）、FR-USER-002（返回固定角色身份）与 FR-USER-004（建立服务端身份基础），直接落实 NFR 12.3 的密码非明文保存要求；完整用户管理、角色分配和产品范围授权分别由 OTS-02、OTS-05 完成。
- 依赖 change：`ots-00-platform-foundation` 必须先完成并归档；本变更不吸收其 MySQL 连接、迁移执行器、TypeScript 迁移、基础布局、统一错误响应、API client 和测试框架工作。
- 非目标：用户管理、密码重置、自助改密、产品范围授权、服务端会话表、刷新令牌、记住登录、多设备会话管理、登录历史、验证码、自动锁定、MFA、SSO、LDAP、AD 和 OIDC。

## Capabilities

### New Capabilities

- `local-authentication`: 定义本地管理员初始化、账号密码登录、签名 Cookie 会话、当前用户查询、退出、停用实时失效及前端认证交互。

### Modified Capabilities

无。

## Impact

- 后端：新增认证路由、Schema、Service/Repository、认证依赖、密码与 Cookie 安全配置，以及 `app_user` 模型。
- 数据：新增 `app_user`、`audit_log` 的编号化 MySQL 迁移和回滚说明，不新增会话或登录日志表。
- 前端：新增登录路由与页面、认证状态、路由守卫、当前用户展示和退出入口；API 类型从 OpenAPI 生成。
- 依赖：后端增加 Argon2id 密码摘要和签名 Cookie 所需的最小依赖；密钥由环境配置提供，不提交真实凭据。
- 测试：增加后端单元/集成测试、前端组件测试和登录纵向 Playwright 场景，新增代码覆盖率不低于 80%。
