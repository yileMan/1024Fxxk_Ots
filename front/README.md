# OTS Frontend

## 启动

```powershell
npm run dev
```

终端会显示前端访问地址，默认是 <http://localhost:5173>。

## 测试和构建

```powershell
npm test
npm run build
```

完整验证还包括：

```powershell
npm run test:coverage
npm run typecheck
npm run api:check
```

健康页和认证接口均调用同源 `/api/v1`。前端只在内存中保存当前用户及其当前产品范围摘要，认证 Cookie 由浏览器管理；不得写入 `localStorage` 或 `sessionStorage`。点击侧栏底部“退出登录”后，服务端清除当前浏览器 Cookie，前端清除内存身份与范围并返回登录页。接口以 OpenAPI 为唯一契约来源，提交前运行 `npm run api:check`。

认证后的页面采用左侧导航、右侧内容布局。所有登录用户可进入“工作台、评估待办、漏洞目录、运行状态”；管理员另有产品、OTS、采集范围、数据包导入和用户管理入口，具有有效产品范围的普通用户还可进入“我的产品”。普通用户不显示管理员入口，直接访问相应路由时进入明确的 403 页面；无有效范围时只读页面呈现独立空状态，授权撤销后的 403 与服务错误使用不同反馈。视觉变量定义在 `src/App.vue`，以红、白、深灰和冷灰构成医疗科技风格，只参考公开企业视觉方向，不复用第三方商标或素材。

管理员可在“用户与角色”维护本地用户。页面支持服务器分页和筛选、固定角色多选、密码重置及停用确认。发生并发冲突时页面会保留尚未保存的输入，并提示读取最新版本后重试；停用用户不会删除任何历史记录。

用户列表的“授权”入口用于配置产品级或版本级显式范围，并展示产品级覆盖关系、重叠版本范围和
因产品/版本停用而暂时无效的记录。每次增删后页面重新读取有效摘要；403、空范围和服务失败使用
不同反馈。相关组件与纵向测试为 `src/components/ProductScopeEditor.vue`、
`src/components/ProductScopeEditor.test.ts` 和 `e2e/users.spec.ts`。

管理员可在“数据交换－采集范围”查看当前去重 OTS 数量、逐 OTS 最近成功覆盖时间、首次采集
状态及相对最近成功批次的新增/移除提示，并下载 `collector_scope.csv`。下载完成后页面只在内存中
短暂显示导出 ID 与 SHA-256 摘要，不把文件、导出 ID 或摘要写入 `localStorage`、
`sessionStorage`。相关实现与测试位于 `src/pages/CollectorScopePage.vue`、
`src/api/collectorScope.ts`、对应单元测试和 `e2e/collector-scope.spec.ts`。

管理员可在 `/system/data-exchange/import-packages` 使用“上传数据包、校验预览、确认导入、查看结果”
四步向导。四步均已开放：选择单个 ZIP、查看相对漏洞库的真实分类和来源事实样例、二次确认事务导入、
查看成功结果；失败批次可下载完整错误清单。刷新带 `batch` 查询参数的页面可重新读取
批次；选择新文件前会清除旧结果。File、批次响应和错误明细只保存在页面内存，不写
`localStorage` 或 `sessionStorage`。页面和客户端实现位于 `src/pages/ImportPackagePage.vue` 与
`src/api/importPackages.ts`，完整纵向测试位于 `e2e/import-packages.spec.ts`。

当前格式 `1.0` 固定为 `manifest.csv`、`nvd_cves.csv` 两文件。页面预览一行一个 CVE 的来源状态、
受影响软件/版本范围和 CVSS；成功结果明确提示“内部 OTS 匹配尚未执行”。KEV/EOL 未启用，也不会显示空占位区域。

导入成功后，管理员可先预览再二次确认执行内部 OTS 候选匹配。页面分别展示新增、更新、移除、未匹配
原因和有界样例；执行失败不覆盖漏洞事实结果，可原地重试。候选 CVE 链接到
`/system/vulnerabilities/{vulnerabilityId}/ots-matches`，详情展示 method、basis、版本范围证据、首次/最近
批次和可空 confidence。预览、结果和详情均固定显示“候选不等于产品受影响”；无候选时显示原因，
不会把它表述成“无漏洞”。这些入口仅对管理员显示，后端接口仍独立执行权限校验。

OTS-10 在同一匹配结果区增加“产品评估任务”账本，展示新任务、待复评、已更新、未变化、已跳过和失败
统计，以及有界产品样例与稳定跳过原因。旧 OTS-08 成功结果会显示“产品任务待生成”，可重新执行幂等补齐；
执行失败明确提示候选和产品任务均已回滚，可原地重试。页面始终保留“候选不等于产品受影响”和“待产品独立
评估”边界。本阶段不显示 KEV/EOL，也不实现 OTS-16 的扩展复评触发。

OTS-11 在 `/system` 展示按当前身份实时计算的四类待办卡片，并通过 `queue` 查询参数进入分页待办；管理员
额外看到最近成功/失败导入及逐 OTS 覆盖摘要。`/system/vulnerabilities` 提供 CVE、产品 ID、OTS ID、
CVSS v3.1 严重度、KEV、评估状态和来源时间区间筛选，筛选与页码保存在 URL 中，可刷新恢复。
`/system/vulnerabilities/{id}` 将来源事实、CVSS v3.1、CWE、KEV、范围、引用、AI 通用建议和权限范围内
候选分区展示；空评分/置信度显示“未提供”，候选区域固定显示“候选不等于产品受影响”。没有明确逐 OTS
覆盖数据时，管理员摘要显示“未提供”。这些页面均为只读，不包含评估编辑、提交、审核、EOL 确认、跨产品
参考或完整追溯动作。

本项目不自动下载 Playwright Chromium。E2E 优先使用系统 Chrome：

```powershell
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:e2e
```

若系统 Chrome 不可用，可将 `PLAYWRIGHT_CHANNEL` 改为 `msedge` 使用系统 Edge；两者均不可用时应报告环境阻塞。
