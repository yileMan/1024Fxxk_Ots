# 006 OTS 与产品清单回滚说明

仅在 `product_ots` 已按 007 回滚且不存在其他下游引用的非生产环境执行：

```sql
DROP TABLE ots_component;
```

已有 OTS 或下游历史的环境不得执行破坏性回滚，应保留数据并采用前向修复。
