## Purpose

为 OTS 管理平台提供可验证的本地账号认证边界，使启用用户可以安全登录、恢复当前身份和退出，并确保后续角色及产品范围授权始终建立在服务端实时读取的用户状态之上。

## ADDED Requirements

### Requirement: 初始化本地管理员
系统 SHALL 提供幂等的初始化管理员能力，创建具有 `admin` 固定角色的启用用户；初始密码 SHALL 至少包含 12 个字符，并且 SHALL 仅以加盐密码摘要保存。

#### Scenario: 首次初始化管理员
- **GIVEN** 数据库中不存在指定登录名的用户
- **WHEN** 运维人员使用有效登录名、显示名称和合规密码执行初始化命令
- **THEN** 系统创建一个状态为 `active` 且具有 `admin` 角色的用户
- **AND** 数据库和命令输出均不包含明文密码

#### Scenario: 重复执行初始化
- **GIVEN** 数据库中已经存在指定登录名的用户
- **WHEN** 运维人员再次执行初始化命令
- **THEN** 系统不创建重复用户，也不覆盖现有用户的密码、角色或状态
- **AND** 命令以明确的“用户已存在”结果结束

#### Scenario: 初始密码不合规
- **GIVEN** 运维人员准备初始化管理员
- **WHEN** 提供少于 12 个字符的密码
- **THEN** 系统拒绝创建用户并返回明确的密码长度错误

### Requirement: 本地账号登录
系统 SHALL 允许启用用户使用登录名和密码登录；成功后 SHALL 返回当前用户公开身份并设置认证 Cookie，失败时 SHALL 不设置认证 Cookie。

#### Scenario: 启用用户成功登录
- **GIVEN** 指定登录名对应启用用户且密码正确
- **WHEN** 用户提交登录请求
- **THEN** 系统返回用户 ID、登录名、显示名称和固定角色
- **AND** 系统设置认证 Cookie 并更新该用户的 `last_login_at`

#### Scenario: 账号或密码无效
- **GIVEN** 登录名不存在或提交的密码错误
- **WHEN** 用户提交登录请求
- **THEN** 系统返回稳定错误码 `AUTH_INVALID_CREDENTIALS` 和统一的“账号或密码错误”提示
- **AND** 响应不披露账号是否存在且不设置认证 Cookie

#### Scenario: 停用用户尝试登录
- **GIVEN** 登录名和密码正确但用户状态为 `disabled`
- **WHEN** 用户提交登录请求
- **THEN** 系统返回 `AUTH_INVALID_CREDENTIALS`，不披露停用状态且不设置认证 Cookie

### Requirement: 安全的认证 Cookie
系统 SHALL 使用签名且固定两小时到期的 Cookie 保存最小会话标识和时效信息；Cookie SHALL 设置 `HttpOnly`、`SameSite=Lax` 和 `Path=/`，正式 HTTPS 环境 SHALL 设置 `Secure`，且不得包含密码或作为权限依据的角色快照。

#### Scenario: 登录签发 Cookie
- **GIVEN** 用户成功登录
- **WHEN** 系统生成认证响应
- **THEN** Cookie 包含可验证的用户标识、签发时间和固定过期时间
- **AND** Cookie 具备当前环境要求的全部安全属性

#### Scenario: Cookie 被篡改或已经过期
- **GIVEN** 请求携带签名无效或超过固定两小时有效期的认证 Cookie
- **WHEN** 用户访问需要认证的接口
- **THEN** 系统返回稳定错误码 `AUTH_SESSION_INVALID`
- **AND** 响应清除失效 Cookie，不返回受保护内容

### Requirement: 实时解析当前用户
系统 MUST 在每次认证请求中依据 Cookie 的用户标识重新读取 `app_user`，并以数据库中的当前状态、显示名称和角色作为身份来源。

#### Scenario: 查询当前用户
- **GIVEN** 请求携带有效认证 Cookie 且对应用户处于启用状态
- **WHEN** 用户请求 `/api/v1/auth/me`
- **THEN** 系统返回用户 ID、登录名、显示名称和当前固定角色
- **AND** 响应不包含密码摘要或其他敏感配置

#### Scenario: 已登录用户随后被停用
- **GIVEN** 用户持有尚未过期的有效 Cookie，但数据库中的用户状态已改为 `disabled`
- **WHEN** 用户发起下一次认证请求
- **THEN** 系统返回稳定错误码 `AUTH_USER_DISABLED`
- **AND** 响应清除认证 Cookie 且不返回受保护内容

#### Scenario: Cookie 对应用户不存在
- **GIVEN** 有效签名 Cookie 中的用户标识在数据库中不存在
- **WHEN** 用户发起认证请求
- **THEN** 系统返回 `AUTH_SESSION_INVALID` 并清除认证 Cookie

### Requirement: 用户退出
系统 SHALL 允许已登录用户退出并清除当前浏览器的认证 Cookie；在不保存服务端会话状态的前提下，系统不保证撤销已复制到其他客户端的 Cookie。

#### Scenario: 当前浏览器退出
- **GIVEN** 用户持有有效认证 Cookie
- **WHEN** 用户请求 `/api/v1/auth/logout`
- **THEN** 系统返回成功并以匹配的 Cookie 属性清除认证 Cookie
- **AND** 当前浏览器后续访问受保护接口时被视为未登录

#### Scenario: 未登录用户退出
- **GIVEN** 请求未携带认证 Cookie 或携带失效 Cookie
- **WHEN** 用户请求退出
- **THEN** 系统仍返回成功并发送清除 Cookie 的响应

### Requirement: Cookie 写请求同源保护
系统 MUST 对使用认证 Cookie 的非安全 HTTP 方法校验 `Origin` 是否与配置的管理平台来源一致；缺少或不匹配的来源 SHALL 被拒绝，可信的同源非浏览器运维调用可以通过明确配置处理。

#### Scenario: 同源写请求
- **GIVEN** 已认证请求使用 `POST`、`PUT`、`PATCH` 或 `DELETE` 方法且 `Origin` 与配置来源一致
- **WHEN** 请求进入受保护接口
- **THEN** 系统允许请求继续执行后续身份和业务授权校验

#### Scenario: 跨来源写请求
- **GIVEN** 已认证的非安全方法请求携带不匹配的 `Origin`
- **WHEN** 请求进入受保护接口
- **THEN** 系统返回稳定错误码 `AUTH_ORIGIN_REJECTED`
- **AND** 请求不得执行任何业务写入

### Requirement: 前端认证体验
前端 SHALL 提供登录页、当前用户信息、退出入口和路由守卫，并 SHALL 在首次加载时通过当前用户接口恢复身份，而不是信任浏览器存储中的身份或权限数据。

#### Scenario: 登录后返回目标页面
- **GIVEN** 未登录用户访问需要认证的页面并被引导到登录页
- **WHEN** 用户成功登录
- **THEN** 前端恢复到用户最初计划访问的站内页面

#### Scenario: 刷新已登录页面
- **GIVEN** 浏览器持有有效认证 Cookie
- **WHEN** 用户刷新需要认证的页面
- **THEN** 前端先调用当前用户接口恢复身份，再展示受保护页面

#### Scenario: 会话失效反馈
- **GIVEN** 用户停留在受保护页面且会话过期、无效或用户被停用
- **WHEN** API 返回对应认证错误
- **THEN** 前端清除内存中的身份状态并跳转登录页
- **AND** 前端显示区分“会话已失效”和“账号已停用”的用户提示

### Requirement: 认证行为不进入数据库变更审计
系统 MUST NOT 为登录、退出、当前用户查询或登录成功时更新 `last_login_at` 写入 `audit_log`；认证故障诊断仅使用不含密码、Cookie 和签名密钥的应用日志。

#### Scenario: 完整登录与退出流程
- **GIVEN** `audit_log` 表可用且用户成功登录、查询当前身份并退出
- **WHEN** 整个认证流程完成
- **THEN** `audit_log` 中不新增与这些认证行为相关的记录

#### Scenario: 认证失败日志脱敏
- **GIVEN** 登录失败或 Cookie 校验失败
- **WHEN** 系统写入应用诊断日志
- **THEN** 日志不包含提交的密码、完整 Cookie 或 Cookie 签名密钥
