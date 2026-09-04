## MODIFIED Requirements

### Requirement: 仅当前负责人可提交当前初始或后续修订
系统 MUST 仅允许同时满足 `product_owner` 固定角色、目标产品版本有效范围、当前产品版本指定负责人、当前修订 `owner_id`、`is_current=1`、状态为 `pending`、`returned` 或 `reassess` 且匹配 `row_version` 的用户提交或重新提交。管理员、审核人、范围外用户以及 `submitted`、`completed` 或历史修订均不得通过该动作。每次成功提交 SHALL 基于当前修订重新执行完整性、环境结果一致性和禁止自审校验，原子写入本修订实际 `submitted_by`、`submitted_at` 并转为 `submitted`，不得覆盖父修订的提交或审核事件。

#### Scenario: 当前负责人提交并冻结初始修订
- **GIVEN** 用户满足提交角色、范围、分配、当前修订、`pending` 状态和行版本条件，且当前指定审核人与该用户不同
- **WHEN** 用户确认提交
- **THEN** 系统原子地将状态从 `pending` 改为 `submitted`，写入实际 `submitted_by` 和 `submitted_at`，并将 `row_version` 增加一
- **AND** 该修订随后对所有用户保持只读

#### Scenario: 当前负责人重新提交退回或待复评修订
- **GIVEN** 当前 `returned` 或 `reassess` 修订已完成合法修改且满足初始提交的全部最终校验
- **WHEN** 当前负责人以匹配 `row_version` 确认重新提交
- **THEN** 系统仅冻结并提交当前修订，记录本修订的实际提交人和时间
- **AND** 父修订及更早修订的结论、提交和审核留痕保持不变

#### Scenario: 非负责人或范围失效
- **WHEN** 管理员、审核人、非当前负责人、缺少 `product_owner` 角色或产品范围已失效的用户尝试提交
- **THEN** 系统返回 `403` 且不泄露范围外详情
- **AND** 评估和审计记录不改变

#### Scenario: 状态、当前修订或行版本已变化
- **WHEN** 页面加载后目标已不是当前可提交修订、状态不属于 `pending`、`returned`、`reassess`，或请求携带旧 `row_version`
- **THEN** 系统返回 `409` 和稳定冲突错误码并提示刷新
- **AND** 不重复提交、不覆盖新状态或新修订

#### Scenario: 当前审核人与提交人相同
- **GIVEN** 产品版本当前指定审核人与准备提交的负责人是同一用户
- **WHEN** 负责人尝试提交或重新提交
- **THEN** 系统返回 `409` 和稳定的“需重新分配审核人”错误码
- **AND** 页面明确提示先由管理员重新指定审核人，评估保持原可编辑状态

### Requirement: 审核退回记录意见并创建下一修订
系统 SHALL 通过显式 `/return` 动作审核当前 `submitted` 修订，写入 `status=returned`、`review_decision=returned`、非空白 `review_comment`、实际 `reviewer_id` 和 `reviewed_at` 并增加 `row_version`。退回动作 MUST NOT 接受或修改产品负责人结论；系统 MUST 同事务保留该已审核修订并创建继承业务快照、清空提交审核事件字段的下一当前 `returned` 修订，后续编辑和重新提交只能作用于新修订。

#### Scenario: 填写意见后退回并形成下一修订
- **GIVEN** 当前指定审核人有权审核当前 `submitted` 修订且行版本匹配
- **WHEN** 审核人填写非空白意见并二次确认退回
- **THEN** 系统在原修订保存退回决定、规范化意见、实际审核人和时间，并创建下一当前 `returned` 修订
- **AND** 提交人的原结论、提交人和提交时间保持不变，新修订可由当前负责人修改

#### Scenario: 退回意见为空或超限
- **WHEN** 审核人提交空白或超过契约上限的退回意见
- **THEN** 系统返回 `422`、稳定校验错误码和 `review_comment` 字段路径
- **AND** 不修改状态、审核字段、当前标记、修订链或审计记录

#### Scenario: 退回接口夹带结论或修订控制字段
- **WHEN** 退回请求包含适用性、影响、处置、证据、环境评分、修订号、当前标记或其他非契约字段
- **THEN** 系统以 `422` 拒绝请求
- **AND** 不允许审核人直接修改提交人的结论或客户端控制修订链

#### Scenario: 退回创建新修订发生冲突
- **WHEN** 退回处理期间当前修订、状态或行版本已变化，或另一事务已经创建下一修订
- **THEN** 系统返回 `409` 和稳定冲突错误码
- **AND** 不产生部分审核留痕、重复修订或多个当前修订
