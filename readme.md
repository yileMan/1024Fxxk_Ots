## 后端
端口5353
``` 
cd .\backend

# 首次启动或数据库结构有变化时执行
.\.venv\Scripts\python.exe run.py migrate

# 首次创建管理员
.\.venv\Scripts\python.exe run.py initialize-admin admin "初始管理员"

# 启动后端
.\.venv\Scripts\python.exe run.py
```


## 前端
端口：5173
```
cd .\front
npm run dev 
```

## 在线接口文档
```
http://localhost:5353/docs
```


## Mysql配置
本地配置文件：`/backend/config.yaml`（已加入 Git 忽略）
- 端口：3306
- 账号与密码仅保存在本机配置文件中
