## Context

参见 `proposal.md` 和 `specs/package-contract-validation/spec.md`。现有实现已具备受限 ZIP/CSV 读取、`import_batch` 状态、上传预览页面和错误下载，但它按旧假设要求外部包携带内部 OTS 范围及匹配。当前数据库迁移只到第 7 张逻辑表 `import_batch`；11 表基线中的第 8～10 张表尚未创建。

正确的数据边界是：外部包只表达 NVD 来源事实与受影响软件/版本；内网先导入 `vulnerability`，OTS-08 再使用内部 `ots_component` 建立候选关系，OTS-10 最后生成产品评估任务。这样外部系统不需要知道内部主键，Rejected 和尚未完成 NVD applicability 分析的 CVE 也能保留来源状态。

## Goals / Non-Goals

**Goals:**

- 用两文件包稳定表达一行一个 CVE及其多软件、多版本范围。
- 将结构预览升级为相对 `vulnerability` 当前事实的真实数据库差异预览。
- 在管理员确认后事务性 upsert 漏洞来源事实和批次状态，并写审计摘要。
- 保持 ZIP 安全、错误定位、批次幂等、1 MiB 字段和五分钟目标。
- 为 OTS-08 提供无需重新解析外部包的规范化受影响范围。

**Non-Goals:**

- 不在外部包或 OTS-07 中引用内部 `ots_id`。
- 不在 OTS-07 创建 `vulnerability_ots_match`、`product_assessment` 或负责人待办。
- 不访问 NVD 网络、不实现采集分页和限流；样例从公开 feed 离线生成。
- 不接收 KEV/EOL，不导入或展示 CVSS v4.0 当前值，不覆盖任何产品评估结论。

## Decisions

### 1. 格式 `1.0` 重置为两文件原始 NVD 包

ZIP 只包含 `manifest.csv` 和 `nvd_cves.csv`。旧草案没有发布给外部兼容方，因此直接重置 `1.0`，并通过精确文件集合和表头明确拒绝三文件草案；不为错误方向永久保留兼容解析器。

`manifest.csv` 表头固定为：

```text
record_type,format_version,batch_no,generated_at,producer_version,source_name,source_release,window_start,window_end,file_name,file_sha256
```

它只有一个 package 行和一个 nvd_cves.csv file 行。来源窗口替代 OTS 范围和逐 OTS 覆盖结果；`import_batch.covered_to` 保存本批次 NVD 窗口结束时间，`scope_coverage_json` 在本格式中为空。

`nvd_cves.csv` 表头固定为：

```text
cve_id,source_identifier,vuln_status,published_at,last_modified_at,description,affected_software_json,cvss_json,cwes_json,references_json,configurations_json
```

### 2. 一行一个 CVE，多软件和版本范围使用规范 JSON 数组

一个 CVE 可影响多个产品和版本范围，不能把 CVE 行扩展成“CVE + 具体软件版本”重复事实。生成端从 NVD `configurations[].nodes[].cpeMatch[]` 和可用的 CNA affected 信息形成 `affected_software_json`，每个对象固定字段：

```json
{
  "part": "o",
  "vendor": "linux",
  "product": "linux_kernel",
  "version": null,
  "version_start_including": "3.0",
  "version_start_excluding": null,
  "version_end_including": null,
  "version_end_excluding": "3.4.20",
  "cpe": "cpe:2.3:o:linux:linux_kernel:*:*:*:*:*:*:*:*",
  "match_criteria_id": "...",
  "vulnerable": true
}
```

精确版本写 `version`，范围边界写对应 start/end 字段，通配全版本允许所有版本字段为 null。原始 `configurations_json` 同时保留，以免扁平化丢失 AND/OR、negate 和非易受攻击环境条件。替代方案“只保存原始 configuration”字段更少，但会把 CPE 解析和上游结构兼容推迟到内网每次匹配；规范化加原始结构更适合后续稳定索引。

### 3. CSV 物理检查必须感知引号上下文

记录分隔符继续要求 CRLF，但引号字段内部允许 LF 或 CRLF。校验器使用轻量状态扫描区分引号外记录边界和引号内内容，再交给严格 CSV 解析器；解析后字段内 CRLF/CR 统一为 LF。不能继续使用“删除所有 CRLF 后搜索 LF”的全文件判断，因为 NVD 描述天然可能包含段落换行。

ZIP 上传 50 MiB、2 个成员、单成员 50 MiB、总解压 200 MiB、压缩比 100:1、10,000 行、单字段 1 MiB、错误 1,000 条等边界保持。CSV 解析器技术字符上限不得低于业务字段字节上限，最终仍按 UTF-8 字节精确校验。

### 4. 第 8 张表保存完整来源事实和当前展示字段

新增编号 `010_vulnerability.sql` 及回滚说明，创建既有 11 表基线中的 `vulnerability`。为避免导入后丢失 NVD 信息，表 8 增加或明确以下字段：

- `source_identifier`：CNA/NVD 来源标识；
- `cvss_json`：全部来源 CVSS 数组；
- `affected_ranges_json`：规范化 `affected_software_json`；
- `configurations_json`：NVD 原始 configuration 数组；
- 既有 `cwe_json`、`references_json`、来源状态/时间和内容哈希；
- CVSS v3.1 标量字段作为查询和展示当前值。

CVSS v3.1 当前值选择顺序固定为：NVD 标记 Primary 的 v3.1 指标优先，其次其他 Primary v3.1，再按 source 和向量稳定排序取第一项；所有原始指标仍保存在 `cvss_json`。没有 v3.1 时标量为空，不换算 v2/v4。

Rejected 只更新 `source_status`、时间和合法来源内容，不删除漏洞。`ai_analysis_suggestion`、KEV 和 CVSS v4.0 字段不属于本次来源哈希的可写输入；新记录的 `is_kev=false`。

### 5. 规范内容哈希驱动真实预览和幂等 upsert

内容哈希对以下规范字段计算：CVE ID、来源标识/状态、描述、时间、排序规范化的受影响范围、CVSS、CWE、引用和原始 configuration。对象键排序；无语义数组如 CWE/引用/评分按稳定键排序；NVD configuration 中有逻辑意义的数组保持来源顺序。哈希不包含数据库 ID、批次 ID、人工字段或时间戳。

分类规则：

- 数据库无 CVE：new；
- 哈希相同：duplicate；
- 数据包 `last_modified_at` 更新且哈希不同：update；
- 同一/更旧来源时间但哈希不同：conflict；
- 包内同 CVE 同内容为 duplicate、不同内容为 conflict。

预览在 validated 批次中保存有限样例和规范化待写入摘要；确认时必须在事务内重新锁定相关 CVE并重算分类，防止预览后并发更新。发现漂移则回到 conflict/failed，不按过期预览写入。

### 6. 确认导入是单事务，OTS 匹配不在该事务内

新增 `POST /api/v1/import-packages/{batch_id}/confirm`。事务顺序为：锁定 validated 批次 → 标记 importing → 锁定相关 CVE → 重算分类 → bulk insert/update vulnerability → 更新批次 succeeded/result_json → 插入一条 `audit_log(operation=batch_upsert)` 摘要 → commit。任何一步失败整批回滚，再用独立短事务把批次标为 failed 并保存非敏感错误。

归档 ZIP 在 validated 时保留，确认失败可基于同一归档诊断但不可重复确认；修复数据必须生成新 batch_no。成功响应只显示漏洞新增/更新/重复/Rejected 数量，不宣称已匹配 OTS 或已生成产品任务。

### 7. 同 batch_no 不同内容必须报告冲突

整包 SHA 相同继续返回既有批次。解析出可信 batch_no 后，若数据库已有相同 batch_no 且 SHA 不同，返回稳定 `PACKAGE_BATCH_CONFLICT`，包含既有批次 ID和两个摘要前缀，不复用旧批次错误作为本次结果。这样既保留业务幂等，也避免样例重建后出现“旧错误回放”。

### 8. 后续 change 按数据依赖拆分

- OTS-08 创建/维护第 9 张表 `vulnerability_ots_match`：读取已导入 `affected_ranges_json`，按 CPE 标准标识、名称归一化和版本区间匹配内部 `ots_component`，只形成候选关系。
- OTS-09 仅在确认 KEV/EOL 后扩展来源导入；不阻塞纯 NVD 主链。
- OTS-10 创建第 10 张表 `product_assessment`：读取第 9 张表候选关系，经 `product_ots` 找到有效产品版本和负责人，幂等创建 pending/reassess 修订。
- OTS-11 在第 8～10 张表可用后提供漏洞目录、候选依据和工作台查询。

内网 OTS 目前只有名称/版本/官网，不能保证 `Linux` 与 `linux_kernel` 等名称稳定对应。OTS-08 必须明确标准 CPE vendor/product 或受控别名策略；该问题不应让 OTS-07 再次依赖内部 ID。

### 9. 前端完成来源事实导入闭环

四步向导全部可用。预览按 CVE 展示来源状态、软件/vendor/product、精确版本或版本区间、CVSS v3.1 摘要和 new/update/duplicate/conflict/error。Rejected 和没有 affected 范围使用明确空状态，不显示为数据错误。确认页展示实际写入影响并二次确认；结果页明确“漏洞事实已导入，内部 OTS 匹配尚未执行”。

## Risks / Trade-offs

- [NVD configuration 逻辑复杂，扁平化可能产生过宽候选] → 同时保存原始 configuration；OTS-08 将规范范围作为召回候选、把原始逻辑作为匹配证据，不自动形成产品受影响结论。
- [OTS 名称和 CPE product 不一致] → OTS-08 引入明确标准标识/别名策略并保留 match_basis；禁止静默模糊匹配直接形成任务。
- [完整 NVD 日增量包含无 applicability 与 Rejected] → 作为来源状态正常导入；仅有可用受影响范围的 CVE进入 OTS-08 匹配。
- [预览与确认间数据库发生变化] → 确认事务重新分类并锁定，漂移阻止写入。
- [1 MiB JSON 字段和 10,000 行造成内存峰值] → 保留 200 MiB 总解压、有限样例和五分钟性能测试；正式写入分批执行但处于同一事务。
- [旧三文件包和已存失败批次] → 明确为未发布草案，不兼容；保留旧批次历史但不得把它们当作新格式成功输入。

## Migration Plan

1. 先用 RED 测试替换两文件夹具，覆盖字段内换行、空 affected、Rejected、真实版本范围、数据库分类和 batch_no 冲突。
2. 重构校验器与 manifest，保留现有安全上传和错误清单；旧三文件包得到稳定不兼容错误。
3. 增加 `010_vulnerability.sql`、回滚说明、模型/Repository 和 MySQL 8.x 验证，不新增第 11 张表之外的表。
4. 实现确认导入事务、审计摘要和前端四步闭环；以系统 Chrome验证上传、预览、确认、结果和失败回滚。
5. 重建最小合规包和最近一日真实 NVD 包，执行覆盖率、性能、OpenAPI 漂移和 OpenSpec 严格校验。
6. 回滚时先关闭确认端点和前端动作，再回滚应用；若 `vulnerability` 已被后续表引用则禁止执行 010 回滚，保留成功批次和来源事实。

## Open Questions

无。
