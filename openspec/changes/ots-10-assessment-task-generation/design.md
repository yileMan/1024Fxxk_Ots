## Context

参见 `proposal.md` 的动机和 `specs/assessment-task-generation/spec.md` 的行为契约。当前 OTS-08 已创建 `vulnerability_ots_match`，管理员通过批次预览和执行接口原子替换当前候选集合，结果保存在 `import_batch.result_json.matching`。仓库尚无 `product_assessment` 模型、迁移或服务，现有前端只展示候选新增、更新、移除和未匹配统计。

本设计以《OTS-需求规格说明》V1.6 的 FR-MATCH-003～005、FR-VULN-005，《OTS-系统方案》V1.6 第 5.2、5.3、5.5 节和《OTS-数据表结构（11 表详细关系版）》V1.0 第 10 表为基线。OTS-09 未启动，因此任务生成不读取或推断 KEV/EOL；OTS-16 以后再处理 CVSS、KEV、产品 OTS 上下文及纯文本/实质变化的完整自动复评矩阵。

## Goals / Non-Goals

**Goals:**

- 创建 11 张应用基础表中的第 10 张表，并用应用事务维护每个“产品 OTS + CVE”的单一当前修订。
- 在 OTS-08 执行路径中同时计算候选差异和产品任务差异，使首次任务、完成评估的候选依据复评、摘要和审计原子提交。
- 复用现有批次预览/执行/结果闭环，向管理员展示任务新建、待复评、未变、跳过和失败统计，不引入后台任务或通知表。
- 支持对 OTS-08 已产生的现有候选重新执行对应当前批次，幂等补齐第 1 修订。

**Non-Goals:**

- 不实现产品负责人工作台查询、评估字段编辑、提交、审核、退回或修订历史页面。
- 不实现 OTS-16 的完整自动复评：CVSS、KEV、产品/版本/关联变化和来源纯文本差异分类不在本 change 处理。
- 不在迁移 SQL 中生成业务任务，不新增匹配哈希列、通知表、消息队列、定时任务或第 12 张业务表。
- 不自动删除因产品停用或关联移除而形成的历史任务，也不把 OTS/CVE 候选转换为适用性结论。

## Decisions

### 1. 第 10 张表严格采用既有 11 表基线

新增 `backend/migrations/012_product_assessment.sql` 和回滚说明。字段、长度和空值规则采用数据表文档：修订身份字段、五态 `status`、负责人和产品分析字段、CVSS 环境字段、来源基准、提交/审核留痕、复评原因、乐观锁和时间戳。外键均使用 RESTRICT 语义；创建唯一键 `uk_assessment_revision(product_ots_id, vulnerability_id, revision_no)` 及三组工作台/审核/跨产品索引。

MySQL 不能用普通唯一键可靠表达“同一组合只有一个 `is_current=1`，但允许多个 `is_current=0`”。本 change 不增加生成列或偏离数据基线的唯一索引，而是在任务事务中按业务组合锁定现有修订、计算 `max(revision_no)+1`，先把旧当前修订设为 0，再插入新当前修订；并发由候选批次行锁、组合查询锁和唯一修订键共同阻止。测试会验证并发后只有一个当前修订。

选择应用层不变量而不是新增生成列，是为了保持文档固定的第 10 表结构。代价是所有后续写入必须复用同一 Repository/Service 事务入口；OTS-12～16 不得绕过该入口直接插入当前修订。

### 2. 任务目标从“执行时目标候选集合”展开

服务先沿用 OTS-08 计算本批次漏洞的目标候选集合和当前候选差异，再按目标候选的 `ots_component_id` 批量连接 `product_ots → product_version → product`。只有 product 和 product_version 都为 `active` 的关联进入任务目标；产品 OTS 关系本身没有状态。每个目标键为 `(product_ots_id, vulnerability_id)`，初次创建值固定为：

- `revision_no=1`、`parent_revision_id=NULL`、`is_current=1`；
- `status=pending`、`applicability=pending`、`row_version=1`；
- `owner_id=product_version.owner_id`；
- `based_on_source_modified_at` 取候选目标的来源修改时间；
- 产品分析、CVSS 环境、提交和审核字段为空。

候选未变但缺少任务时仍创建第 1 修订，用于部署后补齐 OTS-08 已有候选。已停用产品/版本不创建任务，分别计入 `PRODUCT_DISABLED`、`PRODUCT_VERSION_DISABLED`；没有有效产品关联计入 `NO_ACTIVE_PRODUCT_OTS`。负责人字段在产品版本上非空且受外键约束；若当前用户已停用或不再具有 `product_owner` 角色，事务不创建不可处理任务并计入 `OWNER_UNAVAILABLE`，由管理员先修正产品版本分配。

采用执行时目标集合而不是从前端预览回传目标 ID，可避免预览后产品关联或负责人变化造成过期写入；所有关联和修订均批量读取，禁止逐候选数据库往返。

### 3. OTS-10 只对匹配依据变化创建复评

OTS-08 的 `match_content_sha256` 包含漏洞完整 `content_sha256`，因此哈希变化只能作为“可能变化”的快速信号，不能单独代表 OTS-10 的复评条件。服务在旧候选与目标候选哈希不同时，继续比较规范 `match_method` 和 `match_evidence_json` 中会改变产品判断的身份、版本范围与规则版本：

- 证据实质变化或候选移除：已完成当前修订创建 `reassess`；
- 只有批次、来源时间、显示文案或不改变候选证据的来源文本变化：OTS-10 不创建复评；
- CVSS、KEV、漏洞状态等来源字段变化及产品上下文变化：由 OTS-16 使用专门的触发哈希和变化摘要处理。

候选移除前先为已有完成评估构造复评修订，随后删除第 9 表当前候选；第 10 表不直接外键引用第 9 表，因此历史和复评仍可保留。复评原因使用稳定类型和简短中文摘要，例如“候选受影响范围或匹配依据已变化”“OTS/CVE 候选已移除”，不保存完整证据 JSON。

新 `reassess` 修订复制原修订的产品分析、适用性、影响、控制、处置、证据和环境评分作为复评起点，更新来源基准；清空 `submitted_by/submitted_at/review_decision/review_comment/reviewer_id/reviewed_at`，`owner_id` 取执行时当前产品负责人，`row_version` 重置为 1。原 `completed` 修订除 `is_current` 切换外不改写业务与审核字段。

这种边界能满足 OTS-10 的候选依据变化验收，又不提前吞并 OTS-16 的变化分类。代价是同批次的 CVSS 变化不会在本 change 自动生成复评，文档和结果必须明确该能力尚待 OTS-16。

### 4. 进行中修订采用保守的不覆盖策略

若当前修订为没有用户内容的 `pending`，任务生成可原地更新 `owner_id`、`based_on_source_modified_at` 和 `row_version`，并写入批量审计摘要；这不会丢失用户结论。是否“没有用户内容”按所有产品分析、环境评分、提交和审核字段均为空且 applicability 仍为 `pending` 判断。

`returned`、`reassess` 或 `submitted` 可能已有用户输入或审核上下文，OTS-10 不覆盖、不创建并行当前修订，分别以 `ASSESSMENT_IN_PROGRESS` 计入跳过。后续 OTS-12～16 根据状态机和变化摘要处理这些状态。该选择优先保护用户输入；代价是已提交期间发生的变化不会由 OTS-10 自动打断审核，属于 OTS-16 的明确后续范围。

### 5. 扩展现有批次 API 和结果 JSON，而不新增并行执行入口

保持现有四个 OTS-08 路由不变，扩展 `MatchSummaryResponse`，在顶层新增版本化 `task_generation` 对象：

```json
{
  "schema_version": "1.0",
  "status": "pending|succeeded|failed",
  "task_inserted_count": 0,
  "task_reassess_count": 0,
  "task_updated_count": 0,
  "task_unchanged_count": 0,
  "task_skipped_count": 0,
  "task_failed_count": 0,
  "skip_reason_counts": {},
  "task_samples": [],
  "truncated_task_count": 0,
  "error_code": null
}
```

`GET .../ots-match-preview` 同时计算候选和任务预览但不写入；`POST .../ots-matches` 重新计算并原子提交两类差异；`GET .../ots-match-result` 返回最近持久结果，旧 OTS-08 结果没有 `task_generation` 时按当前数据返回 pending 预览语义；漏洞候选详情保持只读，不暴露全局产品任务。

样例按 CVE ID、product ID、product version ID、product_ots ID 稳定排序，最多 100 条。错误沿用 `MATCH_ALREADY_RUNNING` 和 `MATCH_EXECUTION_FAILED`，并在内部日志增加任务分类计数；响应、日志和审计摘要不包含完整产品评估、Cookie 或证据正文。

选择扩展既有编排而不是增加 `/assessment-task-generation` 全局入口，可确保候选和任务共享事务与并发锁，也避免两个入口对“当前候选”产生不同解释。部署后对每个仍承载当前漏洞事实的成功批次重新执行一次，即可补齐现有候选任务；重复执行幂等。

### 6. 单事务差异提交和审计

执行事务固定顺序为：锁定 `succeeded` 批次；读取本批次当前漏洞、OTS、候选、有效产品关联和当前评估；计算候选及任务差异；写候选新增/更新；创建或切换评估修订；删除失效候选；更新 `import_batch.result_json.matching`（内含 `task_generation`）；最后按实际变化分别加入候选和产品评估的 `batch_upsert` 审计摘要并 flush。

任何业务写入或审计失败均回滚。回滚后独立短事务把 matching 和 task_generation 标为 failed、`internal_matching_pending=true`，允许重试但不改变 `import_batch.status=succeeded`。若只发生 unchanged/skip，不写虚假的业务变更审计。审计详情只保存批次 ID、各类数量和稳定原因计数。

### 7. 前端在现有导入结果页展示任务账本

扩展 `ImportPackagePage.vue` 的内部匹配区域，在候选统计下增加任务生成统计和有限样例，明确每个任务仍是“待产品独立评估”。旧成功结果缺少 `task_generation` 时显示“产品任务待生成”，并允许管理员执行；执行失败同时说明候选与任务事务均已回滚，保留重试按钮。

页面覆盖 pending、preview、executing、succeeded、failed、empty、旧结果兼容、401 和 403。OpenAPI 仍为唯一类型来源，先更新后端 Schema，再重新生成 `front/src/api/openapi.json` 和 `generated.ts`；业务客户端只引用生成类型。

### 8. 测试与性能边界

后端先以失败测试覆盖：有效/停用产品展开、多产品版本、负责人快照、缺失任务补齐、相同输入幂等、完成修订复评、候选移除、纯显示/批次变化不复评、进行中任务保护、单一当前修订、并发 409、任务或审计故障全回滚。MySQL 集成测试验证 `012` 字段、CHECK、外键、索引、唯一修订键和回滚前置检查。

前端先补充任务账本组件失败测试，再实现页面；Playwright 使用系统 Chrome 完成“导入/匹配 → 多产品任务生成 → 重复执行未增加任务”的纵向场景。性能测试使用不超过 10,000 CVE 和代表性产品关联，要求候选与任务联合处理继续满足现有五分钟离线目标并记录峰值内存；新增前后端代码覆盖率均不低于 80%。

## Risks / Trade-offs

- [应用层单一当前修订约束可能被后续代码绕过] → 集中修订写入 Repository/Service，使用组合锁和并发集成测试，并在 OTS-12～16 复用同一入口。
- [OTS-08 的候选哈希包含非复评字段，直接比较会误触发] → 哈希只用于筛选可能变化，再比较规范匹配方式和证据；完整来源变化分类留给 OTS-16。
- [进行中任务遇到变化时保守跳过会延后提醒] → 明确返回 `ASSESSMENT_IN_PROGRESS`，不覆盖用户输入；OTS-16 在状态机完整后统一处理。
- [停用负责人会导致有效产品没有可处理任务] → 以 `OWNER_UNAVAILABLE` 明确跳过并要求先修正产品分配，不把任务静默分给无权限用户。
- [现有 OTS-08 成功批次没有任务摘要] → 结果接口兼容旧 JSON并显示 pending；部署步骤逐个重跑仍承载当前事实的批次，幂等补齐任务。
- [候选移除后复评页无法读取当前第 9 表证据] → 第 10 表保留历史结论和复评原因；本 change 不伪造当前候选，后续历史证据展示需依赖审计/修订增强。

## Migration Plan

1. 部署前确认 OTS-08 已归档且数据库最高业务迁移为 `011_vulnerability_ots_match.sql`，运行现有全量测试并备份数据库。
2. 应用 `012_product_assessment.sql`，验证字段、CHECK、六个用户/业务外键、唯一修订键、三组索引以及应用基础表总数仍为 11；部署后端编排、扩展 OpenAPI 和前端资源的同一版本。
3. 按来源时间从旧到新枚举仍包含当前 `vulnerability.import_batch_id` 的 succeeded 批次，由管理员预览并重新执行匹配；同一候选已存在时只补齐缺失任务，不重复候选或修订。
4. 抽样核对一个候选展开多个产品版本、停用产品跳过、负责人快照、重复执行、候选依据更新和移除触发完成评估复评，再开放 OTS-11 使用第 10 表。
5. 回滚前停止匹配和任务写入；若尚无需要保留的评估数据，可按 `012_product_assessment.rollback.md` 校验后删除第 10 表，再回滚应用。若已产生产品填写、提交或审核数据，必须先导出并确认业务处置，不得级联删除或直接回滚 OTS-08 第 9 表。
