# OTS Backend

## 启动

```powershell
.\.venv\Scripts\python.exe run.py
```

服务地址：<http://localhost:5353>

复制 `config.example.yaml` 为 `config.yaml` 后填写本地 MySQL 连接。`config.yaml` 已被 Git 忽略；生产环境可用 `OTS_DATABASE_URL` 环境变量覆盖它。迁移采用编号 SQL，不使用 Alembic：

```powershell
py run.py migrate
py run.py
```

初始化管理员（密码使用无回显输入；自动化部署可改用 `OTS_INITIAL_ADMIN_PASSWORD` 环境变量）：

```powershell
py run.py initialize-admin admin "初始管理员"
```

生产环境必须设置至少 32 个字符的 `OTS_AUTH_SECRET`。同时配置 `OTS_ALLOWED_ORIGIN`；HTTPS 部署保持 `OTS_COOKIE_SECURE=true`。轮换签名密钥会使所有当前会话失效。

API 文档：<http://localhost:5353/docs>

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```
