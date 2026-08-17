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
```

健康页调用同源 `/api/v1/health`。后续接口以 OpenAPI 为唯一契约来源，必须同步更新 API 类型生成或契约校验。
