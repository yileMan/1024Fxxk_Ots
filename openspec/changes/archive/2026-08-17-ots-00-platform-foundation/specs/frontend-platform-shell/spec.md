## Purpose

为 OTS 管理平台提供基于 Vue 3 与 TypeScript 的统一管理端入口，使后续业务页面通过同一 API 契约、路由布局和错误反馈机制呈现服务状态与业务能力。

## ADDED Requirements

### Requirement: TypeScript 管理端基础壳
前端 SHALL 以 Vue 3 与 TypeScript 提供可启动的管理端基础布局、路由入口和页面容器；后续功能页面 MUST 能复用其导航、内容区和全局反馈机制。

#### Scenario: 访问根入口
- **WHEN** 用户访问管理端根入口
- **THEN** 前端加载基础布局和默认路由内容
- **AND** 页面不依赖 JavaScript 专有业务模型定义

#### Scenario: 路由目标不存在
- **WHEN** 用户访问未定义的管理端路由
- **THEN** 前端显示明确的未找到页面或反馈
- **AND** 用户可以返回可用入口

### Requirement: OpenAPI 驱动的 API 类型
前端 SHALL 使用后端 OpenAPI 契约生成或校验 API 类型，并通过统一 API client 调用后端；前端不得为同一接口维护与契约独立且可能漂移的手写数据模型。

#### Scenario: 健康接口契约变更
- **WHEN** 后端健康接口的请求或响应契约发生变更
- **THEN** API 类型生成或契约校验在构建验证中发现不一致

#### Scenario: API 调用失败
- **WHEN** 统一 API client 收到后端统一错误响应或网络失败
- **THEN** 调用方获得可识别的错误码、关联标识或网络失败信息
- **AND** 前端不会将原始内部错误对象直接展示给用户

### Requirement: 系统健康页
前端 SHALL 提供系统健康页，调用 `/api/v1/health` 并展示服务与数据库可用、不可用和加载中的状态。

#### Scenario: 健康检查成功
- **WHEN** 用户打开系统健康页且健康接口返回成功状态
- **THEN** 页面展示服务和数据库的可用状态

#### Scenario: 健康检查失败
- **WHEN** 健康接口返回失败或浏览器无法连接服务
- **THEN** 页面展示明确的不可用或连接失败反馈
- **AND** 页面不展示敏感诊断信息
