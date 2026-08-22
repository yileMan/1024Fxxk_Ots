## Why

现有 OTS-07 错把外部采集端当成内部 OTS 匹配执行者，要求数据包提前携带 `collector_scope.csv` 和内部 `ots_id`，导致完整 NVD 数据无法导入。平台的真实流程是先导入 CVE 及其受影响软件/版本来源事实，再由内网使用本地 OTS 名称、版本和标准标识形成候选匹配，最后为相关产品负责人创建评估任务。

## What Changes

- **BREAKING**：重置尚未发布的格式 `1.0` 草案。ZIP 根目录由三文件改为 `manifest.csv`、`nvd_cves.csv` 两文件；删除 `collector_scope.csv`、范围摘要、逐 OTS 采集结果和 `matched_ots_json`，旧三文件测试包不再兼容。
- 固定一行一个 CVE 的 `nvd_cves.csv`，保存 NVD 原始状态、来源标识、时间、描述、CVSS、CWE、引用、原始 configuration，以及从 CPE/CNA affected 信息规范化得到的受影响软件和精确版本/版本范围数组。
- 允许 Rejected、尚未完成 NVD 分析、没有 configuration 或尚未匹配内部 OTS 的 CVE 进入数据包；缺少内部 OTS 候选关系不再是包校验错误。
- 保留 ZIP/CSV 安全、1 MiB 字段、摘要、批次幂等、错误定位和管理员权限边界；分类预览改为与 `vulnerability` 当前来源事实比较得到 `new/update/duplicate/conflict/error`。
- 完成导入向导四步闭环。管理员确认后，在一个事务内写入或更新 `vulnerability`、更新 `import_batch` 为 `succeeded` 并写一条 `batch_upsert` 审计摘要；失败整批回滚。
- 新增第 8 张表 `vulnerability` 的编号化迁移和回滚；保留全部来源 CVSS 与 configuration JSON，同时选择一组 CVSS v3.1 当前展示值。
- OTS-07 不创建 `vulnerability_ots_match` 或 `product_assessment`。OTS-08 在内网将受影响软件/版本范围匹配 `ots_component` 并维护候选关系；OTS-10 再按候选关系和 `product_ots` 事务性创建负责人待评估/待复评任务。
- KEV/EOL 仍为条件任务 OTS-09；若启用，以后续格式版本扩展，不在 NVD `1.0` 中放空文件。

## Capabilities

### New Capabilities

- `package-contract-validation`: 定义原始 NVD 两文件离线包、可安全预览的来源事实分类，以及管理员确认后的漏洞事实事务导入。

### Modified Capabilities

无。

## Impact

- 数据：继续复用 `import_batch`，新增基线内第 8 张表 `vulnerability`；补充来源标识、完整 CVSS JSON 和原始 configuration JSON 字段，不创建第 9、10 张表。
- 后端：重构包 Schema、校验和分类，增加漏洞 Repository/Service、确认导入 API、事务幂等、内容哈希和审计摘要。
- 前端：导入向导展示受影响软件/版本范围、来源状态和评分，开放“确认导入 → 查看结果”；不展示候选 OTS 或生成任务数量。
- 后续任务：OTS-08 改为内部 OTS 候选匹配；OTS-09 保持条件性 KEV/EOL；OTS-10 改为产品评估任务生成；OTS-11 继续提供漏洞目录与工作台。
- 文件与兼容：现有三文件样例仅保留为错误方向的历史测试材料，实施时必须重建两文件合规样例和最近一日真实 NVD 样例。
