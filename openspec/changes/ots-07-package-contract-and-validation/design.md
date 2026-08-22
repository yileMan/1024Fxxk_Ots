## Context

参见 `proposal.md` 的动机及 `specs/package-contract-validation/spec.md` 的行为契约。当前平台已归档 OTS-06：`collector_scope.csv` 使用固定 UTF-8/CRLF 字节契约，每次导出产生新的 `scope_export_id` 和对实际字节计算的 SHA-256；导出记录本身不落库。数据库已有完整 `import_batch` 表及 `uploaded/validated/importing/succeeded/failed` 状态，但尚无写入该表的数据包路由、Repository 或 Service，也尚未创建漏洞与评估相关表。

本设计受三个边界约束：管理平台部署在内网且不得访问外部数据源；V1 只能使用既定 11 张应用表；OTS-07 必须能验证跨文件引用和范围，但不得提前执行 OTS-08～10 的领域入库、覆盖推进或任务生成。由于 OTS-06 不保存导出 ID 与摘要，OTS-07 能证明 ZIP 内 manifest 与原始范围快照字节自洽并验证 OTS 可识别性，不能把这种自洽误称为对外部来源的数字签名或历史签发证明。

## Goals / Non-Goals

**Goals:**

- 固定 `1.0` 包级文件集合、CSV 物理 Schema、manifest 结构和兼容策略，使外部数据服务可独立生成契约样例。
- 在任何 CSV 业务解析前建立双层 ZIP 资源限制和路径安全检查。
- 复用 `import_batch` 形成 `uploaded → validated|failed` 的可恢复校验状态，并为后续正式导入保留同一批次 ID。
- 以单行 CVE 与规范 JSON 列完成 NVD 字节、Schema、摘要、范围候选匹配和包内重复/冲突分类；后续 change 在其后追加领域语义校验。
- 通过 OpenAPI 生成前端类型，交付管理员四步向导的前两步和错误清单下载。

**Non-Goals:**

- 不验证 NVD 数据是否真实，不访问其网络服务，也不实现候选匹配算法；`1.0` 不接收 KEV/EOL。
- 不把校验通过记录写入 `vulnerability`、`vulnerability_ots_match`、`product_assessment` 或 `audit_log`，不推进 `last_covered_time`。
- 不提供确认导入端点、后台队列、多 worker、对象存储、病毒扫描服务或 ZIP 数字签名。
- 不把 OTS-07 的包内结构分类承诺为最终数据库差异；完整领域对比由 OTS-08～10 在同一预览模型上扩展。

## Decisions

### 1. `1.0` 使用固定三文件根目录契约

ZIP 文件名固定为 `ots_intelligence_YYYYMMDD_HHMMSS.zip`。根目录恰好包含 `manifest.csv`、`collector_scope.csv` 和 `nvd_cves.csv` 三个普通文件。未知文件、目录、大小写变体和重复规范化名称均拒绝。KEV/EOL 是否启用尚未确定，因此 `1.0` 不提供空占位文件；若后续启用，必须通过新的 `format_version` 进入显式解析器，不在同一版本中静默增加文件或映射旧列名。

各 CSV `1.0` 固定表头如下：

| 文件 | 固定列顺序 |
| --- | --- |
| `collector_scope.csv` | `scope_export_id,ots_id,ots_name,ots_version,official_website,last_covered_time` |
| `manifest.csv` | `record_type,format_version,batch_no,generated_at,producer_version,scope_export_id,scope_sha256,file_name,file_sha256,ots_id,collection_status,covered_from,covered_to,error_message` |
| `nvd_cves.csv` | `cve_id,status,published_at,last_modified_at,description,cvss_json,cwes_json,references_json,configurations_json,matched_ots_json` |

`nvd_cves.csv` 一行对应一个 CVE，`cve_id` 是业务键。`cvss_json`、`cwes_json`、`references_json` 和 `configurations_json` 使用规范 JSON 数组保存 NVD 的一对多结构；`matched_ots_json` 使用非空对象数组保存外部采集工具基于范围得到的候选关系，每个对象固定为 `{ots_id,match_method,match_evidence,confidence}`。JSON 使用紧凑 UTF-8、对象键按契约名称输出；数组顺序属于内容的一部分，接收端不替生成端重排。单字段受 1 MiB 上限约束，以容纳 NVD 对大量下游产品枚举形成的 configuration；超过上限的异常复杂 CVE 必须作为生成失败报告，而不能产生无界包。

采用 JSON 列而非五张规范化 NVD 子表，是因为当前交换边界只需要“一行一个 CVE”的完整输入，目标领域表尚未实现，提前拆表增加生成、校验和人工排错成本。替代方案“整行只放原始 NVD JSON”虽然更少列，但会把关键批次预览字段完全隐藏在不稳定的上游结构中；保留稳定标量列与五个明确 JSON 列可以兼顾简单性和可校验性。

### 2. manifest 使用三种行类型避免摘要循环

`manifest.csv` 采用统一表头和以下行规则：

- `package`：恰好一行，填写 `format_version`、`batch_no`、`generated_at`、`producer_version`、`scope_export_id`、`scope_sha256`；文件和 OTS 专属列为空。
- `file`：对 `collector_scope.csv` 和 `nvd_cves.csv` 各一行，填写 `file_name` 与实际字节 SHA-256；公共批次列与 package 行一致。
- `scope_result`：对范围 CSV 每个 OTS 恰好一行，填写 `ots_id`、`collection_status`、覆盖区间与可空错误摘要；公共批次列一致。

不要求 manifest 自己的摘要，避免文件包含自身摘要导致循环。`collection_status` 仅允许 `succeeded/failed/not_run`；只有 `succeeded` 可提供 `covered_to`，`failed/not_run` 必须提供简短原因且不能推进覆盖。本 change 将这些结果保存到 `scope_coverage_json`，但只有 OTS-10 正式导入成功后才可让整个批次进入 `succeeded` 并成为下次范围导出的覆盖来源。

替代方案“每个元数据项一行 key/value”扩展性较强，但很难用固定表头表达唯一性与必填组合，也更容易产生重复键解释差异。

### 3. 受限内存/临时文件流水线，不调用通用解压

上传请求先以流式方式写入应用控制的临时目录并同步计算整包 SHA-256，文件名只作为元数据保存，实际临时名由服务生成。默认上限固定为：上传 ZIP 50 MiB、3 个成员、单成员解压 50 MiB、总解压 200 MiB、单成员压缩比 100:1、每个 CSV 10,000 条数据行、单字段 UTF-8 后 1 MiB、错误明细 1,000 条、错误值 256 个字符。单字段上限用于容纳真实 NVD configuration，仍由 200 MiB 总解压上限约束整包最坏资源消耗；设置允许向下收紧，不允许在同一 `format_version` 下放宽到无法满足五分钟目标的数量级。

使用 ZIP central directory 先检查条目名、Unix mode/符号链接、声明大小和压缩比，再逐成员通过有字节计数上限的 reader 读取；不调用将成员路径直接映射到文件系统的 `extract`/`extractall`。实际读取字节超过声明或上限时立即失败。CSV 可逐行解析；需要跨文件引用的稳定键集合和有限样例保存在内存，V1 10,000 行规模无需新增 staging 表。

替代方案“全部解压后再校验”会在路径和资源验证之前产生写盘风险；“为校验新增 staging 表”违反 11 表约束且给失败清理带来额外事务状态。

### 4. 校验按不可绕过的阶段执行

单次同步校验按以下顺序执行，任一安全/包级阶段失败即停止后续语义解析；记录级阶段可聚合至错误上限：

1. 请求权限、扩展名、上传流大小、整包 SHA-256；
2. ZIP 可读性、路径/类型、精确文件集合、声明与实际资源限制；
3. `manifest.csv` 自身编码、表头、行类型与公共元数据；
4. 两个非 manifest 文件逐字节 SHA-256；
5. 全部 CSV 编码、CRLF、表头、字段长度、行数和基础类型；
6. 范围 ID/摘要/OTS 可识别性、manifest scope_result 完整性；
7. CVE 主键、JSON 结构、包内重复/冲突和候选 OTS 范围闭包；
8. 统计、有限样例与规范 JSON 持久化。

公共错误对象为 `{error_code,file_name,row_number,field,reason,rejected_value}`；行号使用文件物理行号，表头为第 1 行。安全错误不回显攻击路径原文之外的服务器信息，所有 rejected value 截断并去除控制字符。API 返回最多 100 条用于页面，数据库保存最多 1,000 条及 `total_count/truncated_count`；下载从同一持久化错误对象生成，不重新解析恶意包。

### 5. 批次提交边界为“先识别上传，再原子落校验结果”

Repository 直接复用 `ImportBatch`。上传完成并得到整包摘要后，在短事务内插入 `uploaded` 批次；manifest 尚未可信时，临时使用服务生成的占位批次号，解析到受信任 `batch_no` 后在校验结果事务中更新。为避免占位与业务批次冲突，占位前缀保留为 `upload:<UUID>`，`format_version` 初始为 `pending`。校验成功原子更新为 `validated`、真实批次元数据、`manifest_json/result_json/scope_coverage_json`；失败原子更新为 `failed` 和 `error_json`。若真实批次号唯一键在更新时冲突，回滚当前更新并返回既有批次，随后删除本次未引用临时文件；不产生第二条业务批次。

同包摘要在插入前查询并由数据库唯一键兜底。对竞争上传，捕获唯一键冲突后重新查询已有记录并返回幂等响应。OTS-07 不写 `audit_log`：批次本身就是文件处理运行记录，而需求把审计限定为正式数据库业务变更；OTS-10 的 `batch_upsert` 审计在正式导入事务中实现。

替代方案“解析完 manifest 后才创建批次”无法在解析失败时保留可识别失败状态；“每个校验阶段 commit”会暴露难以恢复的中间 JSON。

### 6. 原始包存储采用受控本地归档，失败包仅保留元数据

校验通过后将 ZIP 原子移动到设置项指定的受控归档目录，路径结构按服务生成的批次 ID，而不是用户文件名；`archive_path` 只保存服务器内部相对路径。校验失败、重复或请求异常时删除临时 ZIP，仅保留数据库错误摘要和原始文件名/摘要；API 永不返回 `archive_path`。部署文档要求归档目录与数据库一起备份并限制应用账户权限。

替代方案“失败包也长期归档”增加恶意内容保留与磁盘耗尽风险；对象存储不在 V1 架构内。

### 7. API 为同步上传加只读批次查询

管理员端点：

- `POST /api/v1/import-packages/validate`：`multipart/form-data` 单文件上传；同步完成校验后返回 `201` 新批次或 `200` 既有批次，响应包含批次 ID、状态、分类摘要、范围统计、文件统计、有限错误/样例和后续动作能力。
- `GET /api/v1/import-packages/{batch_id}`：返回上传/校验结果，不返回服务器路径、原始 CSV 行或完整包内容。
- `GET /api/v1/import-packages/{batch_id}/errors`：仅失败批次下载 `package_validation_errors.csv`；没有错误时返回稳定的状态冲突错误。

V1 上限和五分钟目标允许单请求同步完成，省去后台任务/轮询状态机；前端仍展示“校验中”。若反向代理超时低于性能目标，应在部署配置提高该单端点超时，而不是引入 Redis/队列。错误沿用统一 envelope；新增稳定码至少覆盖 `PACKAGE_TYPE_INVALID`、`PACKAGE_TOO_LARGE`、`PACKAGE_ZIP_UNSAFE`、`PACKAGE_STRUCTURE_INVALID`、`PACKAGE_VERSION_UNSUPPORTED`、`PACKAGE_MANIFEST_INVALID`、`PACKAGE_DIGEST_MISMATCH`、`PACKAGE_CSV_INVALID`、`PACKAGE_REFERENCE_INVALID`、`PACKAGE_SCOPE_INVALID`、`PACKAGE_DUPLICATE` 和 `PACKAGE_VALIDATION_FAILED`。

### 8. 预览分类先表达包内结构，后续领域 change 扩展同一模型

`nvd_cves.csv` 输出 `{new,update,duplicate,conflict,error,total}`：首次出现且基础、JSON 和范围校验通过的 `cve_id` 计为 `new`；相同 `cve_id` 与整行规范内容相同的后续行计为 `duplicate`；相同 `cve_id` 内容不同计为 `conflict`；基础、JSON 或范围失败计为 `error`。当前数据库尚无漏洞表，因此 `update` 为 0，并在响应 `classification_basis=package_structure_v1` 与 `final_import_diff=false` 中明确说明。

OTS-08 在不破坏响应字段的前提下增加 NVD 领域预览和数据库对比；OTS-10 才把确认动作能力置为 true。OTS-09 若确认接收 KEV/EOL，必须先提出新格式版本，不能改变 `1.0` 的三文件集合。

### 9. 前端四步向导由服务端能力驱动

新增管理员路由 `/system/data-exchange/import-packages`，复用现有“数据交换”导航和管理员路由元数据。步骤固定为“上传数据包、校验预览、确认导入、查看结果”；OTS-07 中前两步可用，后两步显示“后续能力尚未开放”且无可触发请求。文件选择仅接受单个 `.zip`，客户端大小检查用于快速反馈，服务端仍执行全部安全校验。

页面不把 File、响应明细或批次 ID写入 localStorage/sessionStorage。刷新已带 batch ID 的页面可重新读取只读详情；上传新包前清空旧成功状态，防止服务失败时把旧预览误认为本次结果。统计卡、文件表、错误表与下载按钮全部使用 OpenAPI 生成类型；未知错误走现有统一提示。

### 10. 测试按契约夹具分层且验证无业务副作用

测试构造确定性的三文件最小合规包，再通过单一变异生成缺文件、未知文件、路径穿越、伪装符号链接、声明/实际超限、摘要篡改、BOM/编码/表头/字段错误、非法 JSON、范围外 OTS、空候选匹配和 CVE 重复/冲突。后端单元测试覆盖纯解析器，API/Repository 集成测试覆盖权限、状态、唯一键竞争、临时清理和 JSON；MySQL 测试验证现有表约束且确认表数不增加。前端组件测试覆盖所有向导状态，Playwright 使用系统 Chrome 完成“管理员上传合规三文件包 → 查看预览”和“上传损坏包 → 下载错误清单”纵向场景。

每个写批次测试同时快照漏洞/候选/评估（若测试库已有）与 `audit_log`，验证均未改变；性能夹具包含不超过 10,000 条领域行并记录耗时、峰值内存和错误上限行为。

## Risks / Trade-offs

- [范围导出未落库，manifest 与范围快照可能由同一外部方同时伪造] → 明确本 change 只验证包内一致性和 OTS 可识别性；人工离线介质是信任边界。若未来要求签发真实性，需单独变更 OTS-06 持久化或签名方案。
- [同步校验接近五分钟可能超过代理默认超时] → 文档固定上传端点超时与大小设置，先用代表性 10,000 行包测量；不以引入队列掩盖部署配置问题。
- [JSON 单元格可能包含深层或超大上游结构] → 在解析前执行 1 MiB 字段限制，并保留 200 MiB 总解压与 10,000 行限制；解析后仅接受规定的顶层数组和候选对象字段，不递归执行任何内容。
- [失败批次保留但失败原包被删除，无法事后重新提取全部错误] → 首次校验聚合到 1,000 条并保存总数；安全上优先不持久保存恶意包，用户可修复后重新上传。
- [未来确认需要 KEV/EOL] → 由 OTS-09 提出 `1.1` 或后续格式并提供迁移说明；`1.0` 继续稳定接收仅 NVD 三文件包。
- [批次占位号短暂存在] → 占位前缀是保留命名空间且只在未完成事务外可见；查询 API按批次 ID返回上传状态，不向用户承诺占位值为外部批次号。

## Migration Plan

1. 先把十文件测试夹具替换为三文件夹具并提交 RED 证据，再修改契约常量和纯校验器，验证安全、JSON 与范围场景。
2. 增加现有 `import_batch` Repository、受控目录设置和三个管理员 API；不新增 SQL 迁移，使用 MySQL 验证唯一键竞争、状态 JSON 和 11 表数量。
3. 重新生成 OpenAPI TypeScript 类型，部署向导前两步与错误清单下载；以系统 Chrome 验证管理员和越权旅程。
4. 使用 10,000 行合规包记录性能证据，并复核进程、代理上传大小/超时与归档目录权限。
5. 回滚时先回滚前端路由与后端 API；保留既有 `import_batch` 表。若已有 `validated/failed` 批次，保留其行和已验证归档以供后续版本恢复，不执行数据删除；仅清理经确认未被引用的临时文件。

## Open Questions

无。
