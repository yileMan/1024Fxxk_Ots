## Why

平台已经能够维护产品、产品版本、OTS 清单和产品范围授权，但尚不能把当前实际在用的 OTS 形成可供外部数据服务消费的最小采集范围。OTS-06 需要在离线数据包契约与导入能力开始前，固定范围筛选、快照标识、CSV 摘要和逐 OTS 最近覆盖时间语义，避免外部服务采集无关数据或后续导入无法追溯原始范围。

## What Changes

- 新增管理员专用的采集范围预览与 CSV 下载能力，实时从启用产品、启用产品版本及其 OTS 关联生成范围，并按 OTS ID 跨产品版本去重。
- 固定 `collector_scope.csv` 的规范字段、UTF-8 编码、稳定行序和换行规则；每次导出生成新的 `scope_export_id`，并返回对实际下载字节计算的 SHA-256。
- 为每个范围 OTS 从成功导入批次的 `scope_coverage_json` 中选择最近一次 `succeeded` 的覆盖截止时间；没有成功记录时保持为空，由外部数据服务使用其配置的初始回溯起点。
- 新增“数据交换－采集范围”页面，展示当前范围数量、OTS 明细、最近覆盖时间、首次采集状态及相对上次成功批次范围快照的增加/移除提示，并允许管理员下载 CSV。
- 提前通过编号化 MySQL 迁移创建 11 张应用基础表中的完整 `import_batch` 表，供本 change 只读覆盖时间和范围快照；后续 OTS-07 复用该表实现上传、校验和预览，不再负责首次建表。
- 范围生成与导出均为只读操作，不保存导出记录、不创建采集范围表，也不写 `audit_log`；OTS 移出当前范围不删除任何历史记录。
- 覆盖需求 `FR-EXCH-001`、`FR-EXCH-002`、`FR-EXCH-016`、`FR-EXCH-017`。
- 依赖已归档的 `ots-04-ots-bom-management` 和 `ots-05-product-scope-authorization`。
- 非目标：不实现外网数据源访问、采集游标、匹配算法、ZIP 数据包上传/校验/导入、覆盖时间推进、范围快照持久化或评估任务生成。

## Capabilities

### New Capabilities

- `collector-scope-export`: 定义实际在用 OTS 的实时去重范围、最近成功覆盖时间选择、范围变化预览、规范 CSV 下载、摘要及管理员权限边界。

### Modified Capabilities

无。

## Impact

- 数据：新增基线表 `import_batch`、外键、唯一键和查询索引及回滚说明；本 change 不写入该表或其他业务表。
- 后端：新增采集范围模型、Schema、Repository、Service 和 `/api/v1/collector-scope` 预览/下载接口；读取产品、版本、关联、OTS 及成功批次 JSON。
- 前端：新增数据交换导航与采集范围页面、API client、加载/空/错误/权限状态和 CSV 下载交互；类型继续由 OpenAPI 生成。
- 测试：增加范围筛选与去重、覆盖时间选择、确定性 CSV/摘要、无审计写入、管理员权限、前端状态及纵向下载场景。
- 后续影响：OTS-07 必须复用本 change 创建的 `import_batch` 表以及范围导出字段与摘要规则，并相应更新 `doc/Task.md` 的建表归属说明。
