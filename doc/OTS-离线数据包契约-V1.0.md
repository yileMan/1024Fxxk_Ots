# OTS 离线数据包契约 V1.0

本文档是外部数据服务生成仅含 NVD 输入的 OTS 离线回传包的可执行契约。合规最小样例见
`doc/samples/ots_intelligence_20260822_010203.zip`。

## 1. ZIP 物理契约

- ZIP 文件名必须匹配 `ots_intelligence_YYYYMMDD_HHMMSS.zip`。
- ZIP 根目录必须恰好包含 `manifest.csv`、`collector_scope.csv`、`nvd_cves.csv` 三个普通文件；不得包含目录、未知/重复文件、大小写变体、绝对/反斜杠/`..` 路径或符号链接。
- 所有 CSV 必须使用 UTF-8 无 BOM、CRLF 换行和标准双引号转义；表头必须逐字、逐序一致。
- 默认限制：上传包 50 MiB、成员 3 个、单成员解压 50 MiB、总解压 200 MiB、单成员压缩比 100:1、每个 CSV 最多 10,000 条数据行、单字段 UTF-8 最多 1 MiB（1,048,576 字节）。

| 文件 | 固定表头 |
| --- | --- |
| `manifest.csv` | `record_type,format_version,batch_no,generated_at,producer_version,scope_export_id,scope_sha256,file_name,file_sha256,ots_id,collection_status,covered_from,covered_to,error_message` |
| `collector_scope.csv` | `scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time` |
| `nvd_cves.csv` | `cve_id,status,published_at,last_modified_at,description,cvss_json,cwes_json,references_json,configurations_json,matched_ots_json` |

格式 `1.0` 只接收 NVD 数据，不包含 KEV/EOL，也不保留空占位文件。若以后启用 KEV/EOL，必须使用新的 `format_version`。

## 2. Manifest

`manifest.csv` 每行必须使用相同的 `format_version`、`batch_no`、`generated_at`、
`producer_version`、`scope_export_id` 和 `scope_sha256`。`format_version` 固定为 `1.0`；
`batch_no` 必填且 UTF-8 不超过 100 字节；时间使用含时区的 ISO 8601，推荐 UTC `Z`。

| `record_type` | 数量 | 专属字段 |
| --- | ---: | --- |
| `package` | 1 | 公共字段；`scope_sha256` 是原始 `collector_scope.csv` 字节的小写十六进制 SHA-256 |
| `file` | 2 | 分别声明 `collector_scope.csv`、`nvd_cves.csv` 的 `file_name` 和实际字节 SHA-256 |
| `scope_result` | 范围中每个 OTS 各 1 | `ots_id`、`collection_status`、覆盖区间和可空错误摘要 |

manifest 不声明自身摘要，避免循环。`collection_status` 仅允许 `succeeded`、`failed`、`not_run`；
`succeeded` 必须提供含时区的 `covered_to`；`failed/not_run` 必须提供 `error_message` 且
`covered_to` 为空。OTS-07 只保存该结果，不推进平台覆盖时间。

## 3. `nvd_cves.csv`

每一数据行表示一个 CVE，业务键为 `cve_id`。同一 CVE 的多项 CVSS、CWE、参考和 NVD
configuration 保存在 JSON 数组列中，避免为一个数据源拆分多张关联 CSV。

| 字段 | 规则 |
| --- | --- |
| `cve_id` | 匹配 `CVE-YYYY-NNNN...`，在包内按业务键分类 |
| `status` | `published`、`modified` 或 `rejected` |
| `published_at`、`last_modified_at` | 含时区的 ISO 8601 时间 |
| `description` | 必填的 NVD 主描述 |
| `cvss_json` | JSON 数组，保存 NVD 提供的一个或多个评分对象；可为空数组 |
| `cwes_json` | JSON 数组，保存 CWE；可为空数组 |
| `references_json` | JSON 数组，保存参考链接及标签对象；可为空数组 |
| `configurations_json` | JSON 数组，保存 NVD configuration/CPE 结构；可为空数组 |
| `matched_ots_json` | 非空 JSON 对象数组，保存该 CVE 与范围内 OTS 的候选匹配 |

JSON 建议使用紧凑 UTF-8。CSV 会把 JSON 内的 `"` 按标准规则写成 `""`。除
`matched_ots_json` 外，OTS-07 只固定 JSON 顶层必须为数组，具体 NVD 领域对象由 OTS-08 扩展校验。

`matched_ots_json` 每个对象必须且只能包含：

```json
{
  "ots_id": 1,
  "match_method": "cpe",
  "match_evidence": "vendor/product/version",
  "confidence": 0.95
}
```

- `ots_id` 必须是正整数，存在于 `collector_scope.csv`，并且当前能被平台识别。
- `match_method`、`match_evidence` 必须是非空字符串。
- `confidence` 可以为 `null`，否则必须是 0～1 的数值。
- 每个 CVE 至少有一个候选匹配；候选关系不等于产品受影响结论。

同 `cve_id` 同内容的后续行分类为 `duplicate`，同 `cve_id` 不同内容分类为 `conflict`。
OTS-07 没有领域目标表，因此 `update=0`、`classification_basis=package_structure_v1`、
`final_import_diff=false`。

## 4. 范围、安全与信任边界

`collector_scope.csv` 必须原样来自本次实际采集范围。其所有行使用同一 `scope_export_id`，
`ots_id` 为范围内唯一正整数；manifest 的范围 ID 和原始字节 SHA-256 必须与它一致。

接收方先校验 ZIP 路径、成员类型、成员集合和资源上限，再读取 CSV；不会把成员路径直接解压到
文件系统。错误使用物理行号（表头为第 1 行），返回错误码、文件、行、字段、原因和截断拒绝值。

校验只能证明 manifest、范围快照和 NVD 文件在包内一致，并确认 OTS 当前可识别；由于范围导出记录
不落库，它不构成历史签发证明或数字签名。OTS-07 不联网、不写漏洞/候选/评估数据、不写审计、
不推进覆盖时间，也不开放确认导入。

## 5. 最小样例与验证

样例包含一个范围内 OpenSSL OTS 和一个 NVD CVE；CVSS、CWE、参考、configuration 与候选 OTS
均位于该 CVE 行的 JSON 列。固定 ID、时间和测试域名只用于契约验证，不能作为真实情报。

样例 SHA-256：`0018a426effe31f73db52de4497196f24b6ceaee41451042181b0da3a1daf1b9`。

自动化证据位于 `backend/tests/test_package_validation.py`、
`backend/tests/test_import_packages.py`、`front/src/pages/ImportPackagePage.test.ts` 和
`front/e2e/import-packages.spec.ts`。10,000 个 CVE 实测校验 0.902 秒、峰值 51.31 MiB。

`doc/samples/ots_intelligence_20260822_000009.zip` 是最近一日 1,215 条真实 NVD 记录的边界测试包；其中 `CVE-2019-10219.configurations_json` 为 71,123 字节，用于验证大型 configuration 不再因旧 64 KiB 上限被拒绝。该包没有 OTS 范围和候选匹配，预期仍在后续引用校验阶段失败，不属于最小合规样例。

## 6. 需求追溯与后续版本

| 需求 | OTS-07 证据 |
| --- | --- |
| `FR-EXCH-003` | 单行 CVE 保存描述、时间及 NVD 的 CVSS/CWE/参考/configuration 数组 |
| `FR-EXCH-008` | 上传后展示 new/update/duplicate/conflict/error；确认导入禁用 |
| `FR-EXCH-012` | 错误精确到 ZIP 文件、CSV 行和 JSON 字段，并可下载 |
| `FR-EXCH-013` | 固定版本化三文件 ZIP、manifest、范围 ID 和 SHA-256 |
| `FR-EXCH-014` | 校验批次、范围和 `matched_ots_json` 中的 OTS 引用 |
| `NFR 12.3` | 无外网访问；受限 ZIP/CSV 流水线；管理员权限；不回显服务器路径和原始内容 |

OTS-08 可在不改变 `1.0` 表头的前提下扩展 NVD JSON 领域预览和数据库对比。OTS-09 若确认接收
KEV/EOL，必须提出 `1.1` 或后续格式，不能改变 `1.0` 的三文件集合。OTS-10 才实现正式写入、
覆盖推进、评估任务和确认导入，并沿用同一批次 ID、预览模型及幂等边界。
