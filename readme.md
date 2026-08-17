## 后端
端口5353
``` 
cd .\backend
py run.py migrate // 同步数据库
py run.py
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
