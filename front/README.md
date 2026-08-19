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

健康页和认证接口均调用同源 `/api/v1`。前端只在内存中保存当前用户，认证 Cookie 由浏览器管理；不得写入 `localStorage` 或 `sessionStorage`。接口以 OpenAPI 为唯一契约来源，提交前运行 `npm run api:check`。

管理员登录后可从“系统管理 → 用户与角色”维护本地用户。页面支持服务器分页和筛选、固定角色多选、密码重置及停用确认。发生并发冲突时页面会保留尚未保存的输入，并提示读取最新版本后重试；停用用户不会删除任何历史记录。

Playwright 默认使用其缓存的 Chromium；若本机尚未安装，可运行 `npx playwright install chromium`。在已安装 Chrome 的内网开发机上，也可以使用：

```powershell
$env:PLAYWRIGHT_CHANNEL='chrome'
npm run test:e2e
```
