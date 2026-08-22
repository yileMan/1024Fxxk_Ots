# package-contract-validation Specification

## Purpose

为 OTS 信息维护平台建立可版本化、可安全校验且能事务导入原始 NVD 漏洞事实的离线 ZIP/CSV 契约，使受影响软件和版本范围先进入内网，再由后续能力匹配内部 OTS 并生成产品评估任务。

## Requirements

### Requirement: 接受唯一的原始 NVD 两文件包
系统 SHALL 仅接受文件名符合 `ots_intelligence_YYYYMMDD_HHMMSS.zip` 且格式版本受支持的 ZIP。格式 `1.0` 根目录 MUST 且只能包含 `manifest.csv` 和 `nvd_cves.csv` 两个普通文件；MUST NOT 包含 `collector_scope.csv`、`matched_ots_json`、KEV/EOL 占位文件或拆分后的漏洞子文件。`nvd_cves.csv` MUST 一行表示一个 CVE。

#### Scenario: 上传完整兼容包
- **GIVEN** 管理员选择名称合法、恰好包含两个固定文件且 manifest 声明 `format_version=1.0` 的 ZIP
- **WHEN** 系统接收数据包
- **THEN** 系统创建或返回上传批次并继续执行内容校验

#### Scenario: 上传旧三文件包
- **GIVEN** ZIP 包含 `collector_scope.csv` 或使用旧的 `matched_ots_json` 表头
- **WHEN** 系统检查包目录和表头
- **THEN** 系统以稳定的不兼容结构错误拒绝该包，不猜测或静默转换旧草案

### Requirement: 在解析前限制恶意 ZIP 和资源消耗
系统 MUST 在解析业务记录前拒绝绝对路径、驱动器路径、反斜杠路径、`.`/`..` 路径段、符号链接、目录、重复或其他非普通文件，并 MUST 对上传字节数、成员数、单成员解压大小、总解压大小、压缩比、CSV 行数和字段大小应用服务端上限。默认单字段 UTF-8 上限 MUST 为 1 MiB，其他上限沿用部署契约；系统不得把成员路径直接解压到用户提供的位置。

#### Scenario: 路径穿越或压缩炸弹
- **GIVEN** ZIP 含逃逸路径、伪装链接、超限声明大小、超限实际大小或异常压缩比
- **WHEN** 系统执行安全预检查和受限读取
- **THEN** 系统停止处理、清理本次临时内容并返回不泄露服务器路径的包级错误

#### Scenario: 大型 NVD configuration
- **GIVEN** `configurations_json` 大于 64 KiB但不超过 1 MiB，且 ZIP 总量和其余内容符合契约
- **WHEN** 系统解析该 CVE 行
- **THEN** 系统继续执行 JSON 与领域校验，不得仅因超过旧 64 KiB 草案限制而拒绝

### Requirement: 固定一行一个 CVE 的来源事实 Schema
`nvd_cves.csv` MUST 使用 UTF-8 无 BOM、逗号分隔、双引号转义、CRLF 记录分隔符和精确表头 `cve_id,source_identifier,vuln_status,published_at,last_modified_at,description,affected_software_json,cvss_json,cwes_json,references_json,configurations_json`。双引号字段内部 MAY 包含 LF 或 CRLF；系统 MUST 区分字段内换行与记录分隔符。五个 `*_json` 字段 MUST 是合法标准 JSON 数组。时间 MUST 是含时区的 ISO 8601/RFC 3339；`cve_id` MUST 规范化为大写 `CVE-YYYY-NNNN...`。

#### Scenario: 合规 CVE 行
- **GIVEN** 一行包含规范 CVE ID、NVD 原始来源状态、来源标识、时间、描述以及五个合法 JSON 数组
- **WHEN** 系统解析并校验该行
- **THEN** 系统保留该 CVE 的来源事实并进入数据库差异分类

#### Scenario: 描述包含合法字段内换行
- **GIVEN** `description` 使用标准 CSV 双引号包裹且内部包含 LF 或 CRLF
- **WHEN** 系统解析 CSV
- **THEN** 系统接受该字段并将字段内换行规范化，不得误报记录分隔符错误

#### Scenario: 非法编码、表头或 JSON
- **GIVEN** CSV 带 BOM、不是 UTF-8、表头缺失/多余/乱序，或任一 JSON 字段不是标准 JSON 数组
- **WHEN** 系统校验物理和字段契约
- **THEN** 系统拒绝该包，并将错误定位到文件、物理行和字段

### Requirement: 明确表达受影响软件和版本
`affected_software_json` 的每个对象 MUST 包含 `part`、`vendor`、`product`、`version`、`version_start_including`、`version_start_excluding`、`version_end_including`、`version_end_excluding`、`cpe`、`match_criteria_id` 和 `vulnerable`；可空版本边界 MUST 使用 JSON `null`。该数组 SHALL 由 NVD configuration/CPE 和可用的 CNA affected 信息规范化得到，MUST 保留精确版本、闭开区间、通配范围和易受影响标记。`configurations_json` MUST 同时保留 NVD 原始逻辑结构，避免扁平化后丢失 AND/OR 与环境条件。

#### Scenario: 一个 CVE 影响多个软件或版本范围
- **GIVEN** NVD 为同一 CVE 提供多个产品、精确版本或版本区间
- **WHEN** 外部生成端写入一行 CVE
- **THEN** 所有范围均保存在同一行的 `affected_software_json` 数组中，不复制 CVE 主记录

#### Scenario: Rejected 或尚无 applicability
- **GIVEN** CVE 状态为 Rejected，或 NVD 尚未提供 configuration/affected 信息
- **WHEN** `affected_software_json=[]` 且其他来源字段合法
- **THEN** 系统接受并分类该 CVE，不要求内部 OTS 候选匹配

### Requirement: 验证 manifest 与 NVD 文件一致性
`manifest.csv` MUST 使用固定表头 `record_type,format_version,batch_no,generated_at,producer_version,source_name,source_release,window_start,window_end,file_name,file_sha256`，且只包含一个 `package` 记录和一个声明 `nvd_cves.csv` 的 `file` 记录。两行 MUST 使用相同公共元数据；`source_name` MUST 为 `nvd`，系统 MUST 验证实际文件 SHA-256、唯一批次号、来源发布标识和含时区的采集窗口。

#### Scenario: manifest 与文件一致
- **GIVEN** package/file 记录唯一、公共元数据一致且摘要匹配实际 `nvd_cves.csv`
- **WHEN** 系统完成包级校验
- **THEN** 系统保存规范化 manifest 并进入记录分类

#### Scenario: 摘要或窗口不合法
- **GIVEN** manifest 摘要不符、记录重复、来源名错误或采集窗口结束早于开始
- **WHEN** 系统校验 manifest
- **THEN** 系统拒绝整个数据包且不产生漏洞业务写入

### Requirement: 依据漏洞当前事实提供导入预览
系统 SHALL 按 `cve_id` 和规范化来源内容哈希与 `vulnerability` 比较，提供 `new`、`update`、`duplicate`、`conflict`、`error` 分类及有限样例。数据库不存在的合法 CVE 为 `new`；内容哈希相同为 `duplicate`；来源修改时间更新且内容变化为 `update`；同一或更旧来源时间却内容不同为 `conflict`。任何 conflict/error MUST 阻止确认导入。

#### Scenario: 预览新增、更新和重复
- **GIVEN** 数据包同时包含数据库未见 CVE、来源时间更新的已知 CVE和内容完全相同的已知 CVE
- **WHEN** 管理员查看校验预览
- **THEN** 系统分别显示 new/update/duplicate 数量、来源状态、受影响软件范围及评分摘要

#### Scenario: 旧来源覆盖新事实
- **GIVEN** 数据包某 CVE 的来源修改时间早于或等于数据库当前值但内容哈希不同
- **WHEN** 系统分类该行
- **THEN** 系统标记 conflict 并禁用确认导入，不静默覆盖当前事实

### Requirement: 管理员确认后事务导入漏洞事实
系统 SHALL 提供管理员确认导入动作，将 new/update CVE 在单一数据库事务中新增或更新到 `vulnerability`，将批次更新为 `succeeded`，并写入一条 `batch_upsert` 审计摘要。导入 MUST 保存来源状态、来源标识、描述、时间、CWE、引用、全部 CVSS JSON、规范化受影响软件范围、原始 configuration、内容哈希和最近批次；同时按确定性来源优先规则选择一组 CVSS v3.1 当前展示字段。duplicate SHALL 不改写漏洞；Rejected SHALL 更新来源状态但不得物理删除记录。

#### Scenario: 确认导入成功
- **GIVEN** 批次状态为 `validated`、无 conflict/error 且当前管理员确认导入
- **WHEN** 系统提交导入事务
- **THEN** new/update 漏洞事实、批次 succeeded 状态和审计摘要同时提交，返回实际新增/更新/重复数量

#### Scenario: 导入中任一写入失败
- **GIVEN** 批量写入、内容哈希、约束或审计写入中的任一步失败
- **WHEN** 事务回滚
- **THEN** 系统不留下部分漏洞或审计记录，将批次保持为可识别失败状态并允许使用新批次修复重试

#### Scenario: 不提前执行内部匹配
- **GIVEN** 漏洞事实导入成功且受影响软件范围中存在 Linux、OpenSSL 等产品和版本
- **WHEN** OTS-07 完成事务
- **THEN** 系统不创建 `vulnerability_ots_match` 或 `product_assessment`，这些行为分别由 OTS-08 和 OTS-10 实现

### Requirement: 保持批次幂等和可恢复状态
系统 SHALL 复用 `import_batch` 的 `uploaded → validated → importing → succeeded|failed` 状态。相同整包 SHA-256 重复上传 MUST 返回既有批次；相同可信 `batch_no` 但不同 SHA-256 MUST 返回批次冲突而不是旧错误回放或新建第二条业务批次。已 succeeded 批次重复确认 MUST 返回既有结果且不得重复更新漏洞或写审计。

#### Scenario: 相同包重复上传
- **GIVEN** 数据库已有相同 package SHA-256 的批次
- **WHEN** 管理员再次上传
- **THEN** 系统返回既有批次、状态和 duplicate 标记，不重新校验或写业务数据

#### Scenario: 同批次号不同内容
- **GIVEN** 数据库已有相同 batch_no 但新上传包摘要不同
- **WHEN** 系统解析到可信 batch_no
- **THEN** 系统明确返回批次号冲突和两个摘要的非敏感提示，不返回旧批次错误作为本次校验结果

### Requirement: 提供完整管理员导入向导和有界错误
系统 SHALL 仅允许管理员上传、预览、确认导入、查看结果和下载错误清单。前端 SHALL 完整支持“上传数据包 → 校验预览 → 确认导入 → 查看结果”，展示来源状态、软件/版本范围、CVSS、分类和冲突；不得把候选匹配或产品受影响结论作为 OTS-07 结果。错误 MUST 包含稳定错误码、文件、可空物理行、字段、原因和截断值，并可下载 UTF-8 无 BOM、CRLF 的固定错误 CSV。

#### Scenario: 管理员完成四步导入
- **GIVEN** 管理员上传合规包并通过预览确认
- **WHEN** 事务导入成功
- **THEN** 页面显示批次 succeeded、实际新增/更新/重复数量和“内部 OTS 匹配尚未执行”提示

#### Scenario: 非管理员或失败批次
- **GIVEN** 用户未认证、非管理员，或包校验失败
- **WHEN** 用户调用接口或操作页面
- **THEN** 系统分别返回现有 401/403 或有界校验错误，且失败批次不能进入确认导入

### Requirement: 导入保持内网、安全和可验证
系统 MUST NOT 在校验或导入时访问互联网、执行包内内容或保存外部 API Key。系统 SHALL 对不超过 10,000 个 CVE 的合规包提供五分钟内可重复验证证据，并保持新增代码覆盖率不低于 80%。日志仅记录关联 ID、阶段、文件、数量、耗时和错误码，不记录原始包、完整描述、查询参数或服务器绝对路径。

#### Scenario: 最近一日真实 NVD 包
- **GIVEN** 包含 Rejected、无 configuration、多软件范围和大型 configuration 的最近一日真实 NVD 包
- **WHEN** 系统校验、预览并确认导入
- **THEN** 系统在资源上限内完成，保留全部合规来源事实且不要求预先存在内部 OTS
