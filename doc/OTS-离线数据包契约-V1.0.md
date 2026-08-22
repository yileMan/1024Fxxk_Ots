# OTS 离线数据包契约 V1.0

本文档是外部数据服务生成 OTS 离线回传包的可执行契约。合规最小样例见
`doc/samples/ots_intelligence_20260822_010203.zip`。

## 1. ZIP 物理契约

- ZIP 文件名必须匹配 `ots_intelligence_YYYYMMDD_HHMMSS.zip`。
- ZIP 根目录必须恰好包含下表十个普通文件；不得包含目录、未知文件、重复文件、大小写变体、绝对路径、反斜杠路径、`..` 路径或符号链接。
- 所有 CSV 必须使用 UTF-8 无 BOM、CRLF 换行和 RFC 4180 风格双引号转义；表头必须与下表逐字、逐序一致。空领域文件仍必须包含表头。
- 默认限制：上传包 50 MiB、成员 10 个、单成员解压 50 MiB、总解压 200 MiB、单成员压缩比 100:1、每个 CSV 最多 10,000 条数据行、单字段 UTF-8 字节数最多 64 KiB。

| 文件 | 固定表头 |
| --- | --- |
| `collector_scope.csv` | `scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time` |
| `manifest.csv` | `record_type,format_version,batch_no,generated_at,producer_version,scope_export_id,scope_sha256,file_name,file_sha256,ots_id,collection_status,covered_from,covered_to,error_message` |
| `vulnerabilities.csv` | `cve_id,status,published_at,last_modified_at,description,source` |
| `affected_ranges.csv` | `cve_id,cpe,version_start_including,version_start_excluding,version_end_including,version_end_excluding` |
| `cvss_scores.csv` | `cve_id,source,cvss_version,base_score,base_severity,vector` |
| `cwes.csv` | `cve_id,cwe_id` |
| `references.csv` | `cve_id,url,tags` |
| `kev.csv` | `cve_id,date_added,due_date,known_ransomware_campaign_use,required_action` |
| `lifecycle.csv` | `ots_id,cycle,release_date,eol_date,status,source_url` |
| `matches.csv` | `cve_id,ots_id,match_method,match_evidence,confidence` |

## 2. Manifest

`manifest.csv` 的每行都必须携带相同的 `format_version`、`batch_no`、`generated_at`、
`producer_version`、`scope_export_id` 和 `scope_sha256`。`format_version` 固定为 `1.0`；
`batch_no` 必填且 UTF-8 不超过 100 字节；时间使用含时区的 ISO 8601，推荐 UTC `Z`。

| `record_type` | 数量 | 专属字段 |
| --- | ---: | --- |
| `package` | 1 | 仅公共字段；`scope_sha256` 是原始 `collector_scope.csv` 字节的小写十六进制 SHA-256 |
| `file` | 9 | 对除 `manifest.csv` 外每个文件各一行，填写 `file_name`、`file_sha256`；不为 manifest 自身计算摘要 |
| `scope_result` | 范围中每个 OTS 各 1 | 填写 `ots_id`、`collection_status`、覆盖区间和可空错误摘要 |

`collection_status` 仅允许 `succeeded`、`failed`、`not_run`。`succeeded` 必须提供含时区的
`covered_to`；`failed/not_run` 必须提供 `error_message` 且 `covered_to` 为空。该时间只是包内采集结果，
OTS-07 校验不会推进平台覆盖时间。

## 3. 字段、键与引用

- `ots_id` 必须是正整数；范围快照内唯一，且必须能由接收平台识别。`scope_export_id` 必须在范围快照和 manifest 中一致。
- `cve_id` 匹配 `CVE-YYYY-NNNN...`，`cwe_id` 匹配 `CWE-N...`。所有领域记录键均按原始字符串比较，不做历史列名或相似列名映射。
- `vulnerabilities.status` 仅允许 `published/modified/rejected`；发布时间和修改时间必须含时区。
- CVSS 只接受 3.1，分数范围 0～10，严重度仅为 `NONE/LOW/MEDIUM/HIGH/CRITICAL`，向量以 `CVSS:3.1/` 开头。
- `references.url` 必须以 `http://` 或 `https://` 开头；KEV 日期使用 ISO 日期，勒索标记仅为 `known/unknown`；生命周期状态仅为 `active/eol/unknown`；匹配置信度可空，否则为 0～1。
- 业务键：漏洞 `cve_id`；受影响范围为整行六列；评分为 `cve_id+source+cvss_version`；CWE 为 `cve_id+cwe_id`；参考为 `cve_id+url`；KEV 为 `cve_id`；生命周期为 `ots_id+cycle`；候选匹配为 `cve_id+ots_id+match_method`。
- `affected_ranges/cvss_scores/cwes/references/kev` 必须引用一个存在且至少匹配一个范围内 OTS 的 CVE；`matches.ots_id` 和 `lifecycle.ots_id` 必须位于范围快照内。包内每个 CVE 都必须至少有一条范围内候选匹配。

同键同内容的后续行分类为 `duplicate`，同键不同内容分类为 `conflict`。OTS-07 尚无领域目标表，
因此 `update` 固定为 0，`classification_basis=package_structure_v1`，
`final_import_diff=false`；候选匹配不等于产品受影响结论。

## 4. 兼容、安全与信任边界

格式版本采用显式解析器。生成方不得在 `1.0` 中增删列或依赖接收方自动映射；字段不足时应提出新
`format_version`。接收方先校验 ZIP 路径、成员类型和资源上限，再读取 CSV，且不把成员路径直接解压到
文件系统。错误定位使用物理行号（表头为第 1 行），返回错误码、文件、行、字段、原因和截断后的拒绝值。

校验能证明 manifest、范围快照和领域文件在包内一致，并确认 OTS 当前可识别；由于范围导出记录不落库，
它不能证明该范围曾由平台历史签发，也不是数字签名。离线介质的来源真实性仍属于组织信任边界。
OTS-07 不联网、不写漏洞/匹配/评估数据、不写审计、不推进覆盖时间，也不开放确认导入。

## 5. 最小样例说明

样例包含一个范围内 OTS、一个 CVE、一条候选匹配及其受影响范围、CVSS、CWE 和参考；
`kev.csv`、`lifecycle.csv` 为空表头。样例的固定时间、ID 和测试域名仅用于契约验证，不得作为真实情报导入。
外部服务应使用实际导出的 `collector_scope.csv` 原始字节生成摘要和包内容。

## 6. 需求追溯与后续边界

| 需求 | OTS-07 证据 |
| --- | --- |
| `FR-EXCH-008` | 上传后展示包内 new/update/duplicate/conflict/error 分类；确认导入保持禁用 |
| `FR-EXCH-012` | 固定 ZIP/十 CSV、manifest、摘要、主键及引用契约，提供确定性样例 |
| `FR-EXCH-013` | 校验范围 ID、范围 SHA-256、可识别 OTS 和范围外引用 |
| `FR-EXCH-014` | 管理员上传、读取批次与下载精确错误清单；失败批次可追踪 |
| `NFR 12.3` | 无外网访问；受限 ZIP/CSV 流水线；管理员权限；服务端路径和原始内容不回显 |

自动化证据位于 `backend/tests/test_package_validation.py`、
`backend/tests/test_import_packages.py`、`front/src/pages/ImportPackagePage.test.ts` 和
`front/e2e/import-packages.spec.ts`。10,000 行实测为 0.259 秒、峰值 6.35 MiB。

OTS-08/09 可在不改变 `1.0` 表头的前提下扩展领域语义和预览；若字段不足必须先升级格式。
OTS-10 才能实现正式写入、覆盖推进、评估任务和确认导入，并必须沿用同一批次 ID、预览响应模型及幂等边界。
