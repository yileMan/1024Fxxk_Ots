## 1. 两文件原始 NVD 契约 RED

- [ ] 1.1 将确定性夹具重建为 `manifest.csv`、`nvd_cves.csv` 两文件，固定新 manifest 和一行一个 CVE 表头，并先确认旧三文件包 RED
- [ ] 1.2 先编写字段内 LF/CRLF 合法、引号外记录分隔符错误、UTF-8/BOM、1 MiB 字段、非法 JSON 和精确物理行定位测试
- [ ] 1.3 先编写 `affected_software_json` 精确版本、闭开区间、通配范围、多软件、原始 configuration 及对象字段测试
- [ ] 1.4 先编写 Rejected、空 affected/configuration、NVD 尚未分析和没有内部 OTS 匹配仍可通过来源校验的测试
- [ ] 1.5 先编写 manifest 来源发布/窗口/摘要、包内重复冲突、相同 batch_no 不同 SHA 返回显式冲突而非旧错误回放的测试

## 2. 漏洞事实与事务导入 RED

- [ ] 2.1 先编写相对 `vulnerability` 的 new/update/duplicate/conflict 分类和规范内容哈希测试
- [ ] 2.2 先编写确认导入权限、validated 前置状态、重复确认、预览后并发漂移和失败整批回滚测试
- [ ] 2.3 先编写 CVSS v3.1 当前值选择、全部 `cvss_json` 保留、Rejected 更新不删除和人工字段不覆盖测试
- [ ] 2.4 先编写 MySQL 8.x 的第 8 张表迁移/回滚、唯一键、JSON 字段、批量 upsert、批次 succeeded 和单条审计摘要测试

## 3. 后端与数据 GREEN

- [ ] 3.1 将格式 `1.0` 文件注册表、成员数、manifest Schema 和校验流程改为两文件，并删除范围快照/候选 OTS 强制校验
- [ ] 3.2 实现引号感知的 CSV 记录换行检查、字段内换行规范化及五个 JSON 数组的字段级校验
- [ ] 3.3 实现受影响软件/CPE/版本范围 Schema、来源字段校验、包内重复冲突和相对数据库分类
- [ ] 3.4 新增 `010_vulnerability.sql` 与回滚说明、模型、Repository 和确定性内容哈希/CVSS 选择逻辑
- [ ] 3.5 新增确认导入 API和事务 Service，完成批量 upsert、状态迁移、并发重分类、失败恢复和 `batch_upsert` 审计摘要
- [ ] 3.6 保持上传临时文件、成功归档、错误下载、管理员权限、日志脱敏和零互联网访问边界

## 4. 前端与纵向旅程

- [ ] 4.1 重新生成 OpenAPI/TypeScript 类型并执行漂移检查，增加确认导入动作和真实数据库差异响应
- [ ] 4.2 更新导入页面组件测试，展示来源状态、受影响软件/版本区间、CVSS、Rejected/空范围和冲突，开放确认与结果步骤
- [ ] 4.3 使用系统 Chrome完成管理员“两文件上传 → 预览 → 二次确认 → succeeded 结果”纵向旅程
- [ ] 4.4 增加旧三文件、字段错误、批次号冲突、事务失败、非管理员和重复确认的系统 Chrome 失败旅程

## 5. 样例、文档与验收

- [ ] 5.1 重建两文件最小合规 ZIP和最近一日真实 NVD ZIP，确认 CVE ID集合、软件/版本范围、manifest 摘要和确定性字节
- [ ] 5.2 使用不超过 10,000 个 CVE 的合规包记录校验、预览、确认导入耗时和峰值内存，满足五分钟目标
- [ ] 5.3 同步外部契约、需求、系统方案、11 表结构、后端/前端说明和 `doc/Task.md`，确认 OTS-08～11 依赖边界一致
- [ ] 5.4 运行后端 pytest/MySQL 覆盖率、前端 Vitest 覆盖率、类型检查、生产构建和完整系统 Chrome Playwright，新增代码覆盖率不低于 80%
- [ ] 5.5 执行 `openspec validate ots-07-package-contract-and-validation --strict --no-interactive`、一致性检索和代码审阅，确认全部任务完成
