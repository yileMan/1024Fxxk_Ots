# OTS 离线数据包契约 V1.0

本文档规定外部数据服务向内网平台交付 NVD 漏洞事实的可执行契约。格式 `1.0` 只负责导入 CVE 来源事实；OTS/CVE 候选匹配由平台内部执行，产品评估任务在匹配完成后生成。

## 1. 数据边界

- 一条 `nvd_cves.csv` 数据记录对应一个 CVE，而不是一个内部 OTS。
- 同一 CVE 的受影响软件、精确版本或版本范围保存在 `affected_software_json`；一个 CVE 可以包含多个软件和多个范围。
- 外部包不得包含内网 `ots_id`、`collector_scope.csv` 或 `matched_ots_json`。
- 无 configuration、Rejected 或当前匹配不到内部 OTS 的 CVE仍是合法来源事实，可以导入。
- `collector_scope.csv` 仅是管理平台已有的可选采集辅助输出，不属于本契约的数据包。
- KEV/EOL 不在格式 `1.0` 中占位；确认启用时必须提出新的 `format_version`。

## 2. ZIP 物理契约

- ZIP 文件名匹配 `ots_intelligence_YYYYMMDD_HHMMSS.zip`。
- ZIP 根目录必须恰好包含 `manifest.csv` 和 `nvd_cves.csv` 两个普通文件；不得包含目录、未知/重复文件、大小写变体、绝对路径、反斜杠路径、`..` 路径或符号链接。
- CSV 使用 UTF-8 无 BOM 和标准双引号转义。记录分隔符使用 CRLF；被双引号包围的字段内部兼容 LF 或 CRLF，并在解析后归一化为 LF。
- 默认限制：上传包 50 MiB、成员 2 个、单成员解压 50 MiB、总解压 200 MiB、单成员压缩比 100:1、`nvd_cves.csv` 最多 10,000 条数据记录、单字段 UTF-8 最多 1 MiB（1,048,576 字节）。

| 文件 | 固定表头 |
| --- | --- |
| `manifest.csv` | `record_type,format_version,batch_no,generated_at,producer_version,source_name,source_release,window_start,window_end,file_name,file_sha256` |
| `nvd_cves.csv` | `cve_id,source_identifier,vuln_status,published_at,last_modified_at,description,affected_software_json,cvss_json,cwes_json,references_json,configurations_json` |

## 3. `manifest.csv`

`manifest.csv` 必须恰好包含两条数据记录：一条 `package` 和一条声明 `nvd_cves.csv` 的 `file`。两条记录使用相同的 `format_version`、`batch_no`、`generated_at`、`producer_version`、`source_name`、`source_release`、`window_start` 和 `window_end`。

| 字段 | 规则 |
| --- | --- |
| `format_version` | 固定为 `1.0` |
| `batch_no` | 必填，UTF-8 不超过 100 字节 |
| `generated_at` | 含时区 ISO 8601 时间，推荐 UTC `Z` |
| `producer_version` | 数据包生成程序版本 |
| `source_name` | 固定来源名称，NVD 包使用小写 `nvd` |
| `source_release` | 来源发布标识，例如上游仓库提交或快照标识 |
| `window_start`、`window_end` | 本包覆盖的来源时间窗口，含时区且开始时间不晚于结束时间 |
| `file_name` | `file` 记录固定为 `nvd_cves.csv`；`package` 记录为空 |
| `file_sha256` | `file` 记录为原始 `nvd_cves.csv` 字节的小写十六进制 SHA-256；`package` 记录为空 |

manifest 不声明自身摘要，避免循环。来源时间窗口只说明本包覆盖的 NVD 数据区间，不证明某个内部 OTS 没有漏洞。

## 4. `nvd_cves.csv`

每条数据记录表示一个 CVE，业务键为规范化大写 `cve_id`。同一 CVE 的一对多信息使用 JSON 数组保存，不拆成多张 CSV。

| 字段 | 规则 |
| --- | --- |
| `cve_id` | 匹配 `CVE-YYYY-NNNN...` |
| `source_identifier` | NVD/CNA 提供的来源标识 |
| `vuln_status` | 来源状态原值，包括但不限于 `Analyzed`、`Modified`、`Rejected` |
| `published_at`、`last_modified_at` | 含时区 ISO 8601 时间 |
| `description` | 来源主描述；Rejected 记录可保存拒绝说明 |
| `affected_software_json` | 归一化受影响软件、精确版本或版本区间数组；允许空数组 |
| `cvss_json` | 来源提供的全部 CVSS 对象数组；允许空数组 |
| `cwes_json` | 来源提供的 CWE 对象数组；允许空数组 |
| `references_json` | 来源提供的参考链接及标签对象数组；允许空数组 |
| `configurations_json` | NVD 原始 configuration 数组；允许空数组 |

五个 JSON 字段的顶层必须是数组。JSON 建议使用紧凑 UTF-8；CSV 中的 JSON 双引号按 RFC 4180 规则写成 `""`。

### 4.1 受影响软件对象

`affected_software_json` 中每个对象只允许以下字段：

```json
{
  "part": "a",
  "vendor": "openssl",
  "product": "openssl",
  "version": "*",
  "version_start_including": "1.0.0",
  "version_start_excluding": null,
  "version_end_including": null,
  "version_end_excluding": "1.0.2",
  "cpe": "cpe:2.3:a:openssl:openssl:*:*:*:*:*:*:*:*",
  "match_criteria_id": "来源匹配条件标识",
  "vulnerable": true
}
```

- `part`、`vendor`、`product`、`vulnerable` 必填。
- `version` 表示精确版本或 `*`；版本上下界按 NVD 的 including/excluding 语义保存。
- 同一个对象可以表达精确版本、开闭区间或通配版本；互相矛盾的表达拒绝导入。
- 一个 CVE 可包含多个对象，以表达多个产品或多个不连续范围。
- `cpe` 和 `match_criteria_id` 用于追溯及后续内部身份匹配，不得替换为内网 OTS ID。

## 5. 校验、预览与确认导入

平台先校验 ZIP 路径、成员类型、成员集合和资源上限，再以支持引号内换行的 CSV 解析器读取记录。错误返回文件、记录号、字段、错误码、原因和截断后的拒绝值。

预览使用第 8 张表 `vulnerability` 的真实当前数据，按 `cve_id` 和规范化内容哈希分类：

- `new`：数据库中不存在该 CVE；
- `update`：存在该 CVE，来源事实发生合法变化；
- `duplicate`：数据库中的规范化事实完全相同；
- `conflict`：业务唯一键或来源规则冲突，不能自动覆盖；
- `error`：文件或记录不满足契约。

管理员确认后，平台在事务内锁定批次并重新分类，批量 upsert 第 8 张表。任何失败都回滚本批次的漏洞写入和审计；成功后批次状态为 `succeeded`，并在同一事务写入一条 `batch_upsert` 审计摘要。`duplicate` 不重写记录；Rejected 更新来源状态但不物理删除历史。

批次状态为 `uploaded → validated → importing → succeeded | failed`。相同整包 SHA-256 返回已有批次；相同 `batch_no` 但 SHA-256 不同返回 `PACKAGE_BATCH_CONFLICT`，不得回放旧包的校验错误。

OTS-07 不创建或更新第 9 张表 `vulnerability_ots_match` 和第 10 张表 `product_assessment`。OTS-08 使用 `affected_software_json` 匹配内部 OTS；OTS-10 再为相关产品生成任务。

## 6. 安全和性能

- 不把 ZIP 成员路径直接解压到文件系统；在读取前拒绝路径穿越、符号链接、重复文件和压缩炸弹。
- 管理平台不联网，不保存外网 API Key，不信任描述、引用或 JSON 中的 HTML。
- 导入仅允许管理员执行；错误和预览不回显服务器绝对路径或未截断的恶意字段。
- 10,000 条 CVE 的包应在需求规定的 5 分钟内完成校验和导入；实现需覆盖 1 MiB 字段边界。

## 7. 样例与版本说明

`doc/samples/ots_intelligence_20260822_010203.zip` 是单 CVE 最小合规包；
`ots_intelligence_20260822_120000.zip` 是从旧最近一日输入完整转换得到的 1,215 条真实 NVD 包；
`120001` 是非法 JSON 错误包；`120002` 是 1 MiB 字段边界包。各包摘要、预期结果、解压参考目录和
重复生成命令见 `doc/samples/README.md`。旧 `ots_intelligence_20260822_000009.zip` 仅作为三文件
转换源和不兼容测试，不再是合规包。

若确认启用 KEV/EOL，OTS-09 必须提出 `1.1` 或后续格式及兼容策略；不得改变本契约 `1.0` 的两文件集合和字段语义。

## 8. 需求追溯

| 需求 | 契约落实 |
| --- | --- |
| `FR-EXCH-003` | 单行 CVE 保存来源标识、状态、描述、时间、受影响软件/范围、全部 CVSS/CWE/参考和原始 configuration |
| `FR-EXCH-008～011` | 真实数据库分类、管理员确认、事务 upsert、重复包幂等和批次冲突 |
| `FR-EXCH-012～014` | 固定两文件 ZIP、manifest 来源窗口/摘要、精确到记录和字段的错误 |
| `FR-VULN-001～003、006` | CVE 当前事实、来源评分、无评分语义和 CVE/OTS 分离 |
| `NFR 12.3` | 无联网、管理员权限、受限 ZIP/CSV 流水线和同事务审计 |
