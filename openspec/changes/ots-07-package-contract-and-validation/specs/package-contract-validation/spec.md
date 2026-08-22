## Purpose

为 OTS 信息维护平台建立可版本化、可追溯且能抵御恶意文件的离线 ZIP/CSV 数据包接收契约，使管理员在任何正式业务写入之前完成上传、结构与范围校验、分类预览和精确错误导出。

## ADDED Requirements

### Requirement: 接受唯一的版本化数据包结构
系统 SHALL 仅接受文件名符合 `ots_intelligence_YYYYMMDD_HHMMSS.zip` 且格式版本受支持的 ZIP 数据包。格式版本 `1.0` 的 ZIP 根目录 MUST 且只能包含 `manifest.csv`、`collector_scope.csv` 和 `nvd_cves.csv`。`nvd_cves.csv` MUST 一行表示一个 NVD CVE；格式 `1.0` MUST NOT 包含 KEV、EOL 或拆分后的漏洞子文件，未来数据源只能通过新的格式版本引入。

#### Scenario: 上传完整兼容包
- **GIVEN** 管理员选择名称合法、包含三个固定根目录文件且 manifest 声明 `format_version=1.0` 的 ZIP
- **WHEN** 系统接收数据包
- **THEN** 系统创建或返回对应上传批次并继续执行内容校验

#### Scenario: 缺失、未知或嵌套文件
- **GIVEN** ZIP 缺少必需文件、包含额外文件、目录项、重复文件名或将文件放在子目录
- **WHEN** 系统检查包目录
- **THEN** 系统拒绝该包并报告对应文件级错误，不解析领域记录

#### Scenario: 不兼容格式版本
- **GIVEN** manifest 声明缺失、格式非法或不是 `1.0` 的 `format_version`
- **WHEN** 系统校验包版本
- **THEN** 系统将批次标记为校验失败并返回稳定的不兼容版本错误，不尝试按相近版本猜测字段

### Requirement: 在解析前限制恶意 ZIP 和资源消耗
系统 MUST 在读取 CSV 内容前拒绝绝对路径、驱动器路径、反斜杠路径、`.`/`..` 路径段、符号链接或其他非普通文件条目，并 MUST 对上传字节数、条目数、单文件解压大小、总解压大小、压缩比和 CSV 数据行数应用服务端上限。系统 SHALL 先检查 ZIP 元数据，再以受限流式读取验证实际字节数；不得依赖把成员直接解压到用户提供的路径。

#### Scenario: ZIP 路径穿越
- **GIVEN** ZIP 成员名称为 `../manifest.csv`、`/manifest.csv`、`C:\manifest.csv` 或等价的逃逸路径
- **WHEN** 系统检查成员路径
- **THEN** 系统在写出任何成员前拒绝整个数据包，并返回不包含服务器绝对路径的文件安全错误

#### Scenario: 压缩炸弹或超限文件
- **GIVEN** ZIP 的声明或实际解压大小、压缩比、文件数、单文件大小或 CSV 行数超过配置上限
- **WHEN** 系统执行预检查或受限读取
- **THEN** 系统立即停止处理，将批次记录为失败，清理本次临时内容且不返回部分预览

#### Scenario: 伪装文件和符号链接
- **GIVEN** 允许文件名对应的成员不是普通文件，或 ZIP 实际内容不是可解析的 CSV/ZIP
- **WHEN** 系统识别成员类型与内容
- **THEN** 系统拒绝整个数据包且不跟随链接、不读取包外文件

### Requirement: 固定 CSV 编码、表头与公共字段规则
格式版本 `1.0` 的所有 CSV MUST 使用 UTF-8 无 BOM、逗号分隔、双引号转义和 CRLF 换行，MUST 使用契约规定的精确表头顺序，且不得包含未声明列、重复表头、NUL 字节或 UTF-8 编码后超过 1 MiB（1,048,576 字节）的字段值。`nvd_cves.csv` 的固定表头 MUST 为 `cve_id,status,published_at,last_modified_at,description,cvss_json,cwes_json,references_json,configurations_json,matched_ots_json`；其中五个 `*_json` 字段 MUST 是合法 JSON，`cvss_json`、`cwes_json`、`references_json`、`configurations_json` MUST 为数组，`matched_ots_json` MUST 为非空对象数组。时间字段 MUST 使用带时区的 ISO 8601/RFC 3339，标识符、枚举、数值和空值 MUST 按 Schema 校验；系统 SHALL NOT 自动映射历史或相似列名。

#### Scenario: 合规 CSV 字节与表头
- **GIVEN** 所有 CSV 使用规范编码、换行、转义、精确表头和有效字段值
- **WHEN** 系统逐文件解析
- **THEN** 系统按稳定行号产生记录并继续摘要、引用和范围校验

#### Scenario: 非 UTF-8、BOM 或错误表头
- **GIVEN** 任一 CSV 使用其他编码、带 BOM、缺列、多列、乱序列、重复列或相似但非规范的列名
- **WHEN** 系统校验 CSV 契约
- **THEN** 系统拒绝该包，并把错误定位到对应文件及表头字段

#### Scenario: 非法字段和超长内容
- **GIVEN** 某数据行含 NUL、非法时间/枚举/标识符/数值、无法完成 CSV 转义解析或超过字段长度上限的值
- **WHEN** 系统校验该行
- **THEN** 系统记录实际文件、数据行号、字段和原因，且不把该行计为可写入记录

#### Scenario: 接收真实的大型 NVD configuration
- **GIVEN** 某个 `configurations_json` 字段 UTF-8 编码后大于 64 KiB 但不超过 1 MiB，且 JSON 与其余字段均符合契约
- **WHEN** 系统校验该 CVE 行
- **THEN** 系统不得仅因字段超过 64 KiB 拒绝该行，并继续执行 JSON、候选匹配和范围校验

#### Scenario: 非法或不兼容的 JSON 列
- **GIVEN** `nvd_cves.csv` 某个 JSON 字段无法解析、不是规定的数组结构，或候选匹配对象缺少必填字段
- **WHEN** 系统校验该 CVE 行
- **THEN** 系统把错误定位到 `nvd_cves.csv` 的物理行和对应 JSON 字段，不接受该行

### Requirement: 验证 manifest、范围快照和文件摘要一致性
`manifest.csv` MUST 包含且只包含一个 `package` 记录、`collector_scope.csv` 与 `nvd_cves.csv` 各一个 `file` 记录，以及 `collector_scope.csv` 中每个 OTS 一个 `scope_result` 记录。所有 manifest 记录 MUST 使用同一 `batch_no`、`format_version`、`scope_export_id` 与范围摘要；系统 MUST 验证范围 CSV 内唯一导出 ID、manifest 导出 ID 和 SHA-256 一致，MUST 对两个非 manifest 文件实际字节计算 SHA-256 并与 manifest 小写十六进制摘要逐一比较，并 MUST 验证包文件名时间与生成时间格式有效但不得把文件名当作可信来源。

#### Scenario: manifest 与文件完全一致
- **GIVEN** manifest 的批次元数据、范围导出 ID、范围摘要、文件清单和各 SHA-256 均与 ZIP 内实际字节一致
- **WHEN** 系统验证 manifest
- **THEN** 系统保存规范化 manifest 与实际范围快照，并继续记录级校验

#### Scenario: 范围摘要或文件摘要不符
- **GIVEN** `collector_scope.csv` 或任一领域 CSV 的实际字节摘要与 manifest 声明不同
- **WHEN** 系统重新计算 SHA-256
- **THEN** 系统拒绝整个数据包并报告具体文件的摘要不一致，不解析被篡改文件的业务含义

#### Scenario: manifest 记录缺失或重复
- **GIVEN** manifest 缺少 package/file/scope_result 记录、重复声明文件或 OTS、声明未知文件或未覆盖实际文件
- **WHEN** 系统比对 manifest 与 ZIP 目录和范围快照
- **THEN** 系统拒绝整个数据包，并将每项差异列为文件级或 manifest 行级错误

### Requirement: 校验批次唯一性并保存可恢复状态
系统 SHALL 复用 `import_batch` 保存上传和校验状态。首次接收合法 ZIP 外壳时状态为 `uploaded`；全部校验通过后状态为 `validated` 并保存 manifest、范围快照、逐 OTS 采集结果和预览统计；任一校验失败时状态为 `failed` 并保存有界错误摘要。相同 `batch_no` 或相同整包 SHA-256 再次上传时 MUST 返回已存在批次的稳定结果，不得创建第二条批次、正式导入数据、评估任务或审计记录。

#### Scenario: 首次上传并校验成功
- **GIVEN** 管理员上传此前未出现且全部校验通过的数据包
- **WHEN** 校验完成
- **THEN** 系统仅创建一条状态为 `validated` 的批次，关联当前管理员并返回批次预览

#### Scenario: 首次上传但校验失败
- **GIVEN** 管理员上传此前未出现但内容校验失败的数据包
- **WHEN** 校验终止
- **THEN** 系统保留一条可识别的 `failed` 批次和有界错误摘要，不产生任何漏洞、候选匹配、覆盖推进、评估任务或 `audit_log`

#### Scenario: 重复批次号或相同包摘要
- **GIVEN** 数据库已有相同 `batch_no` 或 `package_sha256` 的批次
- **WHEN** 管理员再次上传
- **THEN** 系统返回既有批次 ID、当前状态和稳定重复提示，不重复校验或新建记录

### Requirement: 校验范围内 OTS 与 CVE 候选匹配
系统 MUST 验证 `collector_scope.csv` 每行使用同一个 manifest `scope_export_id`，OTS ID 不重复且能在管理平台识别。`nvd_cves.csv` 每行 MUST 使用唯一且规范的 `cve_id`，其 `matched_ots_json` MUST 至少包含一个候选匹配对象；每个对象 MUST 提供正整数 `ots_id`、非空 `match_method`、非空 `match_evidence` 和可空的 0～1 `confidence`，且 `ots_id` MUST 存在于该范围快照。候选匹配 MUST 始终标记为候选，不得形成产品受影响结论。

#### Scenario: 合法候选匹配
- **GIVEN** 每个 NVD CVE 的 `matched_ots_json` 至少包含一个结构合法且指向范围内 OTS 的候选匹配
- **WHEN** 系统执行范围与候选匹配校验
- **THEN** 系统接受该 CVE 并按 `nvd_cves.csv` 统计可预览记录

#### Scenario: 范围外或不可识别 OTS
- **GIVEN** `matched_ots_json` 引用不在范围快照中的 OTS，或范围快照 OTS 已无法由平台识别
- **WHEN** 系统执行范围校验
- **THEN** 系统拒绝整个数据包，并把错误定位到 `nvd_cves.csv` 的行和 `matched_ots_json`

#### Scenario: 无匹配 CVE
- **GIVEN** `nvd_cves.csv` 某 CVE 的候选匹配为空，或所有候选匹配均不指向范围内 OTS
- **WHEN** 系统完成候选匹配校验
- **THEN** 系统拒绝该包并把错误定位到该 CVE 记录，不允许把无关漏洞作为普通新增项预览

### Requirement: 提供只读分类预览而不执行正式导入
系统 SHALL 在校验阶段提供按文件及全包汇总的 `new`、`update`、`duplicate`、`conflict` 和 `error` 数量，并提供有限样例。OTS-07 的分类 MUST 表示包内结构与当前可识别主键的预校验结果；在 OTS-08～10 增加完整领域持久化前，系统 MUST 明确标记该预览不等同于最终导入差异，且确认导入动作 MUST 保持不可用。查看或刷新预览 SHALL NOT 改变批次状态或业务数据。

#### Scenario: 校验成功后查看预览
- **GIVEN** 批次状态为 `validated`
- **WHEN** 管理员查看预览
- **THEN** 系统返回各分类总数、文件级统计、有限样例、范围 OTS 数量及“尚未正式写入”提示

#### Scenario: 包内重复与冲突
- **GIVEN** 同一文件或跨文件出现业务键与内容完全相同的重复记录，或同一业务键对应不同内容
- **WHEN** 系统分类记录
- **THEN** 系统分别计入 `duplicate` 与 `conflict`，冲突使批次校验失败且不得被静默覆盖

#### Scenario: 尝试确认导入
- **GIVEN** OTS-07 尚未交付正式导入能力
- **WHEN** 管理员到达向导“确认导入”步骤或直接构造相关请求
- **THEN** 前端保持动作禁用，API 不提供业务写入端点，数据库中不存在领域写入或覆盖时间推进

### Requirement: 返回并导出精确且有界的错误清单
每个校验错误 MUST 包含稳定错误码、文件名、可空数据行号、可空字段、原因及不泄露敏感内容的截断错误值；文件级错误的行号和字段 SHALL 为空。系统 SHALL 为失败批次提供 UTF-8 无 BOM、CRLF 的 `package_validation_errors.csv` 下载，固定列为 `error_code,file_name,row_number,field,reason,rejected_value`，并 SHALL 在 API 与数据库 JSON 中限制错误数量和单值长度，同时保留“已截断”总数。

#### Scenario: 行字段错误可定位
- **GIVEN** 范围 CSV 或 NVD CVE 行存在字段、JSON 或候选匹配错误
- **WHEN** 校验完成并返回错误
- **THEN** 每个错误分别包含真实 ZIP 文件名、以表头下一行为 2 的数据行号、字段名和稳定原因

#### Scenario: 下载错误清单
- **GIVEN** 批次状态为 `failed` 且当前管理员有权访问
- **WHEN** 管理员下载错误清单
- **THEN** 系统返回固定文件名与列顺序的 CSV，下载内容与批次错误摘要和截断统计一致且不写 `audit_log`

#### Scenario: 错误量超过持久化上限
- **GIVEN** 恶意或严重损坏的包产生超过错误明细上限的错误
- **WHEN** 系统收集错误
- **THEN** 系统停止追加明细、保存总错误数和截断数，响应大小保持有界且仍明确批次失败

### Requirement: 仅允许管理员使用数据包导入向导
系统 SHALL 仅允许已认证管理员上传、查询批次、查看预览和下载错误清单。前端 SHALL 在“数据交换”下提供“数据包导入”入口与四步向导，完整显示上传进度、校验中、成功预览、空分类、校验失败、权限拒绝、服务失败和重新选择文件状态；隐藏入口不得作为权限边界，页面不得显示服务器归档路径或把包内容持久化到浏览器存储。

#### Scenario: 管理员完成上传与校验预览
- **GIVEN** 管理员已登录并选择合规 ZIP
- **WHEN** 上传和校验完成
- **THEN** 向导从“上传数据包”进入“校验预览”，展示分类与文件级结果，并将后两步显示为未开放

#### Scenario: 未登录或非管理员直接请求
- **GIVEN** 用户未登录或不具有 `admin` 角色
- **WHEN** 用户访问页面或直接调用任一数据包接口
- **THEN** API 分别返回现有 `401` 或 `403` 稳定错误，前端跳转登录或显示无权限状态，且不泄露批次、文件名、摘要或错误详情

#### Scenario: 上传或校验服务失败
- **GIVEN** 网络中断、数据库失败或受控文件目录不可用
- **WHEN** 管理员上传或读取预览
- **THEN** 页面显示可重试错误且不把旧结果显示为本次成功，服务端不留下不可识别的部分业务写入

### Requirement: 校验过程保持内网、可观测和可验证
校验过程 MUST NOT 主动访问互联网、执行包内内容或保存外部 API Key。系统 SHALL 使用关联 ID 记录批次 ID、阶段、耗时、文件和错误码等非敏感结构化信息；对于不超过 10,000 个 CVE 且满足大小限制的合规包，校验能力 MUST 提供可重复的性能验证证据，并 SHALL 保持新增后端与前端代码覆盖率不低于 80%。

#### Scenario: 合规大包性能验证
- **GIVEN** 合规数据包包含不超过 10,000 个 NVD CVE 并处于约定资源上限内
- **WHEN** 在项目规定的代表性环境执行校验
- **THEN** 校验在五分钟目标内完成，统计可重复且不发生互联网请求

#### Scenario: 日志不泄露敏感内容
- **GIVEN** 包内字段包含长描述、URL 查询参数或恶意文本
- **WHEN** 校验失败并写结构化日志
- **THEN** 日志仅记录关联 ID、阶段、文件和错误码等元数据，不记录原始包、整行内容、服务器绝对路径或凭据
