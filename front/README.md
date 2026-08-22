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

认证后的页面采用左侧导航、右侧内容布局。管理员依次看到“工作台、产品管理、OTS、采集范围、数据包导入、用户与角色、运行状态”；具有有效产品范围的普通用户看到“工作台、我的产品、运行状态”，可只读查看授权产品、版本及对应 OTS 清单。普通用户不显示管理员入口，直接访问相应路由时进入明确的 403 页面；无有效范围时只读页面呈现独立空状态，授权撤销后的 403 与服务错误使用不同反馈。视觉变量定义在 `src/App.vue`，以红、白、深灰和冷灰构成医疗科技风格，只参考公开企业视觉方向，不复用第三方商标或素材。

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

本项目不自动下载 Playwright Chromium。E2E 优先使用系统 Chrome：

```powershell
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:e2e
```

若系统 Chrome 不可用，可将 `PLAYWRIGHT_CHANNEL` 改为 `msedge` 使用系统 Edge；两者均不可用时应报告环境阻塞。
