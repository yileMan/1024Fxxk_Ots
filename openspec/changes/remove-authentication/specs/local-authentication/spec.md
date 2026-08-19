## MODIFIED Requirements

### Requirement: 初始化本地管理员
系统 SHALL 提供幂等的初始化本地登录用户能力；初始化时保存登录名、显示名称和密码摘要，不强制密码长度、复杂度、固定角色或账号状态要求。

#### Scenario: 首次初始化管理员
- **GIVEN** 数据库中不存在指定登录名的用户
- **WHEN** 运维人员使用登录名、显示名称和密码执行初始化命令
- **THEN** 系统创建可供用户名和密码校验使用的用户记录
- **AND** 数据库和命令输出均不包含明文密码

#### Scenario: 重复执行初始化
- **GIVEN** 数据库中已经存在指定登录名的用户
- **WHEN** 运维人员再次执行初始化命令
- **THEN** 系统不创建重复用户，也不覆盖现有密码

#### Scenario: 初始密码不合规
- **GIVEN** 运维人员准备初始化本地登录用户
- **WHEN** 提供任意密码值
- **THEN** 系统不基于密码长度或复杂度拒绝初始化

### Requirement: 本地账号登录
系统 SHALL 允许用户提交登录名和密码；系统 MUST 仅根据该登录名对应的已存储密码摘要是否匹配来决定登录成功或失败。

#### Scenario: 启用用户成功登录
- **GIVEN** 指定登录名对应的用户记录存在且密码匹配
- **WHEN** 用户提交登录请求
- **THEN** 系统返回登录成功及该用户公开信息
- **AND** 系统设置仅包含用户 ID 的 `ots_user_id` Cookie，不设置令牌

#### Scenario: 账号或密码无效
- **GIVEN** 登录名不存在或提交的密码不匹配
- **WHEN** 用户提交登录请求
- **THEN** 系统返回登录失败
- **AND** 系统不执行账号状态、请求来源、密码策略或其他附加认证校验

#### Scenario: 停用用户尝试登录
- **GIVEN** 登录名和密码正确但用户状态为 `disabled`
- **WHEN** 用户提交登录请求
- **THEN** 系统返回登录成功及该用户公开信息
- **AND** 系统不读取或校验用户状态

### Requirement: 安全的认证 Cookie
系统 SHALL 在登录成功时设置仅包含用户 ID 的 `ots_user_id` Cookie；该 Cookie SHALL 仅用于后续请求识别用户 ID，不包含签名、固定过期时间、角色快照或其他会话信息。

#### Scenario: 登录签发 Cookie
- **GIVEN** 用户登录名和密码匹配
- **WHEN** 系统生成登录响应
- **THEN** 响应设置值为该用户 ID 的 `ots_user_id` Cookie
- **AND** Cookie 不包含签名、过期时间或角色信息

#### Scenario: Cookie 被篡改或已经过期
- **GIVEN** 请求携带任意用户 ID Cookie
- **WHEN** 请求访问需要识别用户的接口
- **THEN** 系统直接使用 Cookie 中的用户 ID 查询用户记录
- **AND** 系统不执行签名或过期校验

### Requirement: 实时解析当前用户
系统 MUST 在每次需要识别操作者的请求中读取 `ots_user_id` Cookie，并按该用户 ID 读取当前用户的公开信息、角色和产品范围；系统不校验该用户的账号状态。

#### Scenario: 查询当前用户
- **GIVEN** 请求携带对应现有用户的 `ots_user_id` Cookie
- **WHEN** 用户请求 `/api/v1/auth/me`
- **THEN** 系统返回用户 ID、登录名、显示名称和当前固定角色

#### Scenario: 已登录用户随后被停用
- **GIVEN** 请求携带对应 `disabled` 用户的 `ots_user_id` Cookie
- **WHEN** 用户发起需要识别身份的请求
- **THEN** 系统继续返回该用户身份并执行既有角色和产品范围授权
- **AND** 系统不校验用户状态

#### Scenario: Cookie 对应用户不存在
- **GIVEN** 请求携带的 `ots_user_id` 在数据库中不存在
- **WHEN** 用户发起需要识别身份的请求
- **THEN** 系统返回 `AUTH_SESSION_INVALID`
- **AND** 系统不返回受保护内容

### Requirement: 前端认证体验
前端 SHALL 提供登录页、当前用户信息和轻量路由守卫，并 SHALL 在进入需要登录的页面前通过当前用户接口恢复身份；守卫仅依据是否取得当前用户决定放行或跳转，不执行 Cookie 签名、时效、账号状态或来源校验。

#### Scenario: 登录后返回目标页面
- **GIVEN** 未获取到当前用户的访问者请求需要登录的站内页面并被引导到登录页
- **WHEN** 用户使用匹配的用户名和密码成功登录
- **THEN** 前端返回用户最初请求的站内页面

#### Scenario: 刷新已登录页面
- **GIVEN** 浏览器持有对应现有用户的 `ots_user_id` Cookie
- **WHEN** 用户刷新需要登录的页面
- **THEN** 前端调用当前用户接口恢复身份并展示目标页面

#### Scenario: 会话失效反馈
- **GIVEN** 浏览器未携带可解析为现有用户的 `ots_user_id` Cookie
- **WHEN** 用户访问需要登录的页面
- **THEN** 前端跳转到 `/login` 并携带原目标页面作为站内重定向参数
- **AND** 前端不在目标业务页面显示“会话已失效”提示

## REMOVED Requirements

### Requirement: 用户退出
**Reason**: 平台不保存登录会话。
**Migration**: 移除 `/api/v1/auth/logout` 和前端退出入口。

### Requirement: Cookie 写请求同源保护
**Reason**: 平台不再使用认证 Cookie，也不在登录流程中校验请求来源。
**Migration**: 移除认证专用来源校验配置和逻辑。

### Requirement: 认证行为不进入数据库变更审计
**Reason**: 会话相关认证行为将被移除。
**Migration**: 删除只针对登录会话、退出和当前用户查询的审计测试与日志处理。
