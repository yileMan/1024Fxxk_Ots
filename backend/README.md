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

登录只校验用户名和密码；成功后使用仅包含用户 ID 的 `ots_user_id` Cookie 识别后续请求，不需要认证密钥、来源或 Cookie 时效配置。

API 文档：<http://localhost:5353/docs>

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```
