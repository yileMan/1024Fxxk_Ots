# assessment-editor-core Specification

## Purpose

本能力让产品负责人在单页评估详情中读取当前产品上下文并安全保存核心评估草稿，同时以服务端权限、条件校验、乐观锁和同事务审计保证草稿不会被越权或静默覆盖。

## Requirements

### Requirement: 独立评估详情
系统 SHALL 按评估 ID 返回唯一“产品版本 + 产品 OTS + CVE”的当前评估修订，并将来源事实、候选匹配与当前产品结论明确分区；响应 SHALL 包含产品、版本、OTS、CVE、修订号、状态、责任人、`row_version`、可编辑标志、核心草稿字段，以及适用的退回或复评原因。

#### Scenario: 负责人打开当前草稿
- **WHEN** 当前责任人在有效产品范围内打开状态为 `pending`、`returned` 或 `reassess` 的当前评估
- **THEN** 系统返回当前修订、产品上下文、来源事实、候选依据和全部核心草稿字段
- **AND** 系统标记该记录可编辑

#### Scenario: 退回或复评原因置顶展示
- **WHEN** 当前修订状态为 `returned` 或 `reassess` 且存在对应原因
- **THEN** 页面在当前产品结论之前显著展示原因
- **AND** 原因内容按不可信纯文本渲染

#### Scenario: 读取越权与不存在资源
- **WHEN** 用户读取存在但不在其有效产品范围内的评估
- **THEN** 系统返回 `403` 且不泄露产品、OTS、CVE 或草稿内容
- **WHEN** 评估 ID 不存在
- **THEN** 系统返回 `404`

#### Scenario: 历史或非草稿状态只读
- **WHEN** 用户打开非当前修订，或当前修订状态为 `submitted` 或 `completed`
- **THEN** 系统可在其有权读取时返回详情但标记为只读
- **AND** 页面不显示可用的草稿保存操作

### Requirement: 核心草稿字段
系统 SHALL 支持保存 `analysis_summary`、`trigger_conditions`、`affected_functions`、`applicability`、`applicability_basis`、`product_impact`、`existing_controls`、`treatment`、`treatment_detail` 和 `evidence_text`；适用性仅允许 `affected`、`not_affected`、`partly_affected`、`pending`，处置仅允许 `patch_or_upgrade`、`configuration_mitigation`、`isolation_or_compensating_control`、`accept_risk`、`no_action`、`further_investigation` 或空值。

#### Scenario: 保存未完成草稿
- **WHEN** 当前负责人保存尚未满足最终提交完整性的草稿且已填写字段本身合法
- **THEN** 系统保存该部分草稿
- **AND** 不因尚缺产品影响、现有控制、处置或证据而执行提交级完整性校验
- **AND** 评估状态保持不变

#### Scenario: 适用性结论必须有依据
- **WHEN** 用户将适用性从 `pending` 改为 `affected`、`not_affected` 或 `partly_affected` 但 `applicability_basis` 为空白
- **THEN** 系统返回 `422`、稳定校验错误码和 `applicability_basis` 字段路径
- **AND** 不保存任何草稿字段

#### Scenario: 高风险处置必须有说明
- **WHEN** 用户选择 `accept_risk` 或 `no_action` 但 `treatment_detail` 为空白
- **THEN** 系统返回 `422`、稳定校验错误码和 `treatment_detail` 字段路径
- **AND** 不保存任何草稿字段

#### Scenario: 非法枚举或超限文本
- **WHEN** 请求包含不支持的适用性、处置值或超过契约上限的文本
- **THEN** 系统返回 `422` 和对应字段路径
- **AND** 不修改评估或审计记录

#### Scenario: 空白归一化与证据安全展示
- **WHEN** 用户保存只含空白的可空文本或包含类似 HTML 的证据说明
- **THEN** 系统将只含空白的可空文本规范化为空值
- **AND** 后续页面将证据说明作为纯文本展示而不执行其中内容

### Requirement: 草稿编辑授权
系统 MUST 仅允许同时满足“当前修订、状态为 `pending`/`returned`/`reassess`、请求用户等于当前 `owner_id`、用户仍具有效产品范围”的记录更新草稿；管理员、指定审核人或拥有范围的其他用户均不得代替负责人编辑。

#### Scenario: 当前负责人成功更新
- **WHEN** 当前修订的当前负责人在有效产品范围内提交合法草稿和匹配的 `row_version`
- **THEN** 系统原子保存草稿、保持状态与修订号不变并返回更新后的详情

#### Scenario: 非负责人不能编辑
- **WHEN** 管理员、指定审核人或其他非当前负责人尝试更新草稿
- **THEN** 系统返回 `403`
- **AND** 不修改评估或审计记录

#### Scenario: 产品范围已撤销
- **WHEN** 当前 `owner_id` 对应用户的产品范围在页面加载后被撤销并尝试保存
- **THEN** 系统在保存时重新校验范围并返回 `403`
- **AND** 不修改评估或审计记录

#### Scenario: 状态或当前修订已变化
- **WHEN** 页面加载后目标记录已不再是当前可编辑草稿或状态已离开可编辑集合
- **THEN** 系统拒绝更新并返回稳定冲突错误
- **AND** 提示用户刷新当前修订

### Requirement: 乐观锁与幂等保存
每次草稿更新请求 MUST 携带客户端已读取的 `row_version`。系统 SHALL 只在评估 ID、当前修订、可编辑状态和 `row_version` 同时匹配时更新；实际数据变化成功后 SHALL 将 `row_version` 增加一，无数据变化的重复保存 SHALL 保持版本不变。

#### Scenario: 匹配版本成功保存
- **WHEN** 当前负责人以最新 `row_version` 保存发生变化的合法草稿
- **THEN** 系统保存变化并将 `row_version` 增加一
- **AND** 响应返回新的 `row_version`

#### Scenario: 并发版本冲突
- **WHEN** 两个客户端读取相同版本且第二个客户端在第一个客户端成功保存后仍使用旧 `row_version` 保存
- **THEN** 第二次保存返回 `409` 和稳定并发冲突错误码
- **AND** 系统不覆盖第一个客户端的修改
- **AND** 页面保留本地未保存内容并提示刷新获取最新数据

#### Scenario: 无变化重复保存
- **WHEN** 当前负责人以最新 `row_version` 保存与数据库规范化后完全相同的草稿
- **THEN** 系统返回成功和当前详情
- **AND** 不增加 `row_version`、不改变 `updated_at` 且不写审计记录

### Requirement: 草稿变更审计
系统 SHALL 在实际草稿变化成功时，于同一数据库事务追加一条 `product_assessment` 更新审计，记录操作者、评估 ID、修订号、变更字段及必要的非敏感前后摘要；系统 MUST NOT 单独保存“填写人”，也 MUST NOT 在审计中复制完整长文本、证据正文、Cookie 或产品外部敏感上下文。

#### Scenario: 业务更新与审计原子提交
- **WHEN** 合法草稿包含实际数据变化并成功提交事务
- **THEN** 评估更新和对应 `audit_log` 记录同时可见
- **AND** 审计操作者为实际请求用户

#### Scenario: 失败不留审计
- **WHEN** 保存因校验、权限、并发冲突或数据库事务失败而未生效
- **THEN** 系统不保留对应草稿变更审计
- **AND** 不产生部分字段更新

### Requirement: 单页明确保存交互
前端 SHALL 从待办列表和允许的漏洞上下文进入单页评估详情，以明确保存按钮编辑当前产品结论，并 SHALL 区分首次加载、保存中、保存成功、字段校验、服务失败、并发冲突和只读状态。

#### Scenario: 明确保存成功
- **WHEN** 当前负责人修改字段并选择保存
- **THEN** 页面在请求期间禁用重复保存并显示保存中状态
- **AND** 成功后使用服务端返回值更新表单与 `row_version` 并显示保存成功反馈

#### Scenario: 字段校验反馈
- **WHEN** 服务端返回带字段路径的 `422` 校验错误
- **THEN** 页面在对应字段附近显示错误并保留用户输入
- **AND** 页面焦点可移动到首个错误字段

#### Scenario: 服务失败与重试
- **WHEN** 保存因非校验类服务错误失败
- **THEN** 页面保留用户输入、显示可重试错误且不得显示保存成功

#### Scenario: 只读状态变化
- **WHEN** 保存返回目标已不可编辑的冲突，或重新加载后详情标记只读
- **THEN** 页面停止后续编辑并提示当前状态
- **AND** 用户可刷新到服务器当前修订而不会被告知旧草稿已保存

### Requirement: 漏洞详情提供范围安全的评估入口
系统 SHALL 在漏洞详情中返回当前用户可见的当前评估入口元数据；每个入口 SHALL 包含明确的评估 ID、状态、产品、版本和产品 OTS 上下文，但 MUST NOT 包含评估草稿字段。入口可见性 SHALL 复用漏洞详情的有效产品范围，是否可编辑 SHALL 由评估详情服务端判定，前端不得根据漏洞或产品参数猜测评估 ID。

#### Scenario: 范围内当前评估提供入口
- **WHEN** 用户打开漏洞详情且该漏洞存在位于其有效产品范围内的当前评估
- **THEN** 系统返回该评估的入口元数据
- **AND** 页面提供指向 `/system/assessments/:assessmentId` 的入口

#### Scenario: 范围外评估不泄露
- **WHEN** 漏洞还存在不在当前用户有效产品范围内的评估
- **THEN** 普通用户的漏洞详情不返回这些评估的 ID、状态或产品上下文
- **AND** 页面不为这些评估生成入口

#### Scenario: 没有可见评估时不猜测入口
- **WHEN** 当前用户对该漏洞没有可见的当前评估
- **THEN** 漏洞详情返回空的评估入口集合
- **AND** 页面不根据漏洞、产品或版本参数猜测评估 ID

#### Scenario: 非负责人通过入口只读查看
- **WHEN** 管理员、审核人或其他非负责人通过可见入口打开评估详情
- **THEN** 评估详情按服务端判定返回只读状态
- **AND** 页面不提供可用的草稿保存操作
