# 项目协作规则

## Git 分支

- 默认直接在当前主干分支工作；除非用户明确要求，否则不要创建功能分支、临时分支或 worktree 分支。
- 完成修改后只提交到当前主干，不自动执行 `git push`。
- 后续 Git 提交说明默认使用中文，除非用户明确要求使用其他语言。

## Playwright 浏览器运行时

- 不要执行 `npx playwright install chromium`，也不要自动下载 Playwright Chromium；该下载在当前环境中已多次因 CDN 无响应而失败。
- 运行 Playwright E2E 时，优先使用系统已安装的 Chrome，例如 PowerShell：`$env:PLAYWRIGHT_CHANNEL='chrome'; npm run test:e2e`。
- 如果系统 Chrome 不可用，再检查并使用系统 Edge。
- 如果 Chrome 和 Edge 都不可用，应保留实际错误并将 E2E 标记为环境阻塞，不得反复尝试下载浏览器，也不得把依赖安装结果当作业务测试结果。
