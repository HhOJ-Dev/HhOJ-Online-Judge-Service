# HhOJ Online Judge Service

基于 GitHub Actions 的在线评测系统。

## 架构

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│   前端 OJ   │────▶│  后端服务(Node) │────▶│  GitHub Actions  │
│             │     │                 │     │    (评测机)      │
└─────────────┘     └─────────────────┘     └──────────────────┘
```

## 目录结构

```
.
├── .github/
│   └── workflows/
│       ├── judge-1.yml      # GitHub Actions 评测工作流 (Worker 1)
│       ├── judge-2.yml      # GitHub Actions 评测工作流 (Worker 2)
│       └── judge-3.yml      # GitHub Actions 评测工作流 (Worker 3)
├── backend/
│   ├── routes/
│   │   ├── judge.js         # 评测提交路由
│   │   └── result.js        # 结果查询路由
│   ├── services/
│   │   ├── github.js        # GitHub API 服务
│   │   └── store.js         # 数据存储服务
│   ├── examples/
│   │   └── test-api.js      # API 测试示例
│   ├── config.js            # 配置文件
│   ├── server.js            # 服务入口
│   └── package.json
├── frontend-sdk/
│   └── hhoj-sdk.js          # 前端 SDK
└── README.md
```

## 支持的语言

- **C++** (cpp)
- **C** (c)
- **Python** (python)
- **Java** (java)
- **Go** (go)
- **Rust** (rust)
- **JavaScript** (javascript)
- **C#** (csharp)

## 快速开始

### 1. 配置 GitHub Token

1. 前往 [GitHub Settings > Tokens](https://github.com/settings/tokens)
2. 创建 Personal Access Token，勾选 `repo` 和 `workflow` 权限
3. 复制生成的 token

### 2. 配置后端

```bash
cd backend

# 安装依赖
npm install

# 复制环境配置
cp .env.example .env

# 编辑 .env 文件，填入配置
# GITHUB_OWNER=your-github-username
# GITHUB_REPO=HhOJ-Online-Judge-Service
# GITHUB_TOKEN=ghp_xxxx
```

### 3. 启动后端服务

```bash
npm start
```

服务将在 `http://localhost:3000` 启动。

### 4. 在前端中使用

```javascript
import { HhOJClient } from './hhoj-sdk.js';

const client = new HhOJClient('http://localhost:3000');

// 提交代码并等待结果
const result = await client.judge('cpp', code, testcases, {
  timeLimit: 2000,
  memoryLimit: 256
}, (status) => {
  console.log('状态:', status.status);
});

console.log('评测结果:', result);
```

## API 接口

### POST /api/judge

提交代码进行评测。

**请求体:**
```json
{
  "language": "cpp",
  "code": "#include <iostream>...",
  "testcases": [
    { "input": "1 2", "output": "3" },
    { "input": "5 10", "output": "15" }
  ],
  "config": {
    "timeLimit": 2000,
    "memoryLimit": 256
  }
}
```

**响应:**
```json
{
  "success": true,
  "data": {
    "judgeId": "abc123",
    "status": "queued"
  }
}
```

### GET /api/status/:judgeId

查询评测状态。

**响应:**
```json
{
  "success": true,
  "data": {
    "judgeId": "abc123",
    "status": "completed",
    "conclusion": "success"
  }
}
```

### GET /api/result/:judgeId

获取评测结果。

**响应:**
```json
{
  "success": true,
  "data": {
    "judgeId": "abc123",
    "status": "completed",
    "result": {
      "status": "AC",
      "total": 2,
      "passed": 2
    }
  }
}
```

## 评测结果状态码

| 状态码 | 说明 |
|--------|------|
| AC | Accepted - 通过 |
| WA | Wrong Answer - 答案错误 |
| TLE | Time Limit Exceeded - 时间超限 |
| MLE | Memory Limit Exceeded - 内存超限 |
| RE | Runtime Error - 运行时错误 |
| CE | Compilation Error - 编译错误 |
| UKE | Unknown Error - 未知错误 |

## 部署

### 后端部署

可以部署到任何支持 Node.js 的平台：
- Vercel
- Railway
- Heroku
- 自建服务器

### GitHub Actions 配置

确保仓库已启用 GitHub Actions，工作流文件位于 `.github/workflows/judge-1.yml`。

## 许可证

MIT