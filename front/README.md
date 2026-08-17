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
