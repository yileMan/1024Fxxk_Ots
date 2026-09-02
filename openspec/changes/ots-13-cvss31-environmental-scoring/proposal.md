## Why

OTS-12 已允许产品负责人保存核心评估草稿，但 CVSS v3.1 产品环境指标仍无法填写，环境分数与向量也没有统一的权威计算入口。现在需要补齐这一能力，确保产品评估使用来源 v3.1 向量作为计算基础，并由服务端按同一规则生成可追溯结果。

## What Changes

- 新增 CVSS v3.1 向量解析、基础指标校验、环境指标校验和环境分数/向量计算能力，并以固定计算器版本标识计算结果。
- 仅在漏洞来源提供合法 CVSS v3.1 向量时开放产品环境评分；来源未提供时明确显示“来源未提供”，不得自动生成、换算或保存环境评分。
- 扩展产品评估详情与草稿保存契约，读取并保存结构化环境指标；环境分数、环境向量、CVSS 版本和计算器版本始终由服务端重算，忽略或拒绝客户端伪造的派生结果。
- 前端在既有单页评估详情增加 v3.1 环境指标表单、来源向量展示和实时预览；保存时提交指标而非显示分数，并以服务端返回结果作为最终值。
- 使用 FIRST CVSS v3.1 官方示例和边界向量建立自动化回归，覆盖向量语法、指标组合、舍入规则、篡改请求和无来源评分场景。
- 复用既有 `product_assessment` 评分字段和草稿乐观锁/审计事务，不新增应用基础表；不实现提交审核、自动复评或评估导出。
- 明确 V1 只使用 CVSS v3.1。既有 v4.0 预留字段和索引保持不变，但不导入、不写入、不通过 API 返回、不在前端展示，也不为 v4.0 创建 capability。
- 覆盖 FR-MASTER-007、FR-ASSESS-005、FR-VULN-002、FR-VULN-003 和《OTS 信息维护平台系统方案》6；依赖已归档的 OTS-12 `ots-12-assessment-editor-core`。

## Capabilities

### New Capabilities

- `cvss31-environmental-scoring`: 定义 CVSS v3.1 来源向量前置条件、指标模型、服务端权威计算、计算器版本、前端预览与官方向量回归行为。

### Modified Capabilities

- `assessment-editor-core`: 扩展既有评估详情、草稿保存、权限、乐观锁、审计和单页交互要求，使环境指标纳入同一草稿资源和原子保存流程。

## Impact

- 后端：增加 CVSS v3.1 解析/计算模块，并扩展评估 schema、service 和响应映射；复用当前评估授权、`row_version` 条件更新及 `audit_log` 同事务写入。
- API/OpenAPI：评估详情返回来源 v3.1 状态、环境指标及服务端计算结果；草稿更新接收结构化指标但不接受客户端决定派生分数，并重新生成 TypeScript 类型。
- 数据：复用 `product_assessment.cvss_version`、`environmental_score`、`environmental_vector`、`cvss_metrics_json` 和 `calculator_version`，不新增表、字段、索引或迁移。
- 前端：扩展既有评估详情页和 API client，增加来源向量、指标表单、即时预览、字段错误和无来源提示。
- 测试：增加 FIRST 官方示例回归、后端单元/API/MySQL 集成测试、前端 Vitest/组件测试和使用系统 Chrome 的 Playwright 纵向流程；新增代码覆盖率不低于 80%。
