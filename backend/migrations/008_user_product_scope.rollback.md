# 008 用户产品范围回滚说明

先回滚前端和后端到不读取 `user_product_scope` 的版本。生产或已有授权数据的环境默认只回滚应用，不删除授权表。

仅在已完成数据库备份、导出授权配置和相关 `audit_log` 证据，并经确认允许丢弃本 change 授权数据后执行：

```sql
DROP TABLE user_product_scope;
```

删除前应确认没有后续业务表引用该表；删除不会也不得级联删除 `app_user`、`product`、`product_version` 或 `audit_log`。有业务数据且需要保留授权的环境应采用前向修复。
