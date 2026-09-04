# 013 自动复评字段回滚说明

本迁移为既有 `product_ots` 和 `product_assessment` 增加状态、评估基线及变化摘要，不新增应用基础表。

启用自动复评后，`disabled` 关联、基线、变化摘要和由此创建的修订均属于业务历史，**不得**通过自动脚本删除、合并或恢复旧 current。回滚应用代码前必须停止导入、候选匹配和产品 OTS 写入，完成数据库备份，并确认旧应用能够忽略新增字段和正确过滤关联状态。

只有在自动复评从未启用、没有 `disabled` 关联、没有非空基线或变化摘要，并经人工核对备份后，才可执行：

```sql
ALTER TABLE product_assessment
    DROP COLUMN reassess_changes_json,
    DROP COLUMN assessment_basis_json,
    DROP COLUMN assessment_basis_sha256;

ALTER TABLE product_ots
    DROP INDEX idx_product_ots_status,
    DROP CHECK ck_product_ots_status,
    DROP COLUMN row_version,
    DROP COLUMN status;
```

若已产生任何自动复评数据，只允许停用触发逻辑并保留这些列；后续数据处置必须单独评审，不能把删除字段作为普通代码回滚步骤。
