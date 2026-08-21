# 项目协作规则

## Playwright 浏览器运行时

- 不要执行 `npx playwright install chromium`，也不要自动下载 Playwright Chromium；该下载在当前环境中已多次因 CDN 无响应而失败。
- 运行 Playwright E2E 时，优先使用系统已安装的 Chrome，例如 PowerShell：`$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:e2e`。
- 如果系统 Chrome 不可用，再检查并使用系统 Edge。
- 如果 Chrome 和 Edge 都不可用，应保留实际错误并将 E2E 标记为环境阻塞，不得反复尝试下载浏览器，也不得把依赖安装结果当作业务测试结果。
