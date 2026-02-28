# douyin-processor API 接口文档

## 概述

douyin-processor 提供 REST API 接口，用于处理 WAV 音频文件的 ASR 识别。

**服务地址**：
- 直连：`http://localhost:8093`
- 通过网关：`http://localhost:8010/api/douyin`

## 接口列表

### 1. 处理所有音频

**描述**：获取 file-system-go 中的所有 WAV 音频，进行 ASR 识别

**请求**：
```
POST /api/process
```

**响应**：
```json
{
  "success": true,
  "message": "处理完成",
  "data": {
    "total": 10,
    "processed": 10,
    "success": 8,
    "failed": 2
  }
}
```

**字段说明**：
| 字段 | 类型 | 说明 |
|------|------|------|
| total | int | 总音频数量 |
| processed | int | 已处理数量（包括跳过） |
| success | int | 成功数量 |
| failed | int | 失败数量 |

---

### 2. 查询处理结果

**描述**：查询指定视频的 ASR 识别结果

**请求**：
```
GET /api/videos/{aweme_id}/result
```

**路径参数**：
| 参数 | 类型 | 说明 |
|------|------|------|
| aweme_id | string | 视频 ID |

**响应（处理中）**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7609169800750206794",
    "status": "processing",
    "message": "视频正在处理中"
  }
}
```

**响应（已完成）**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7609169800750206794",
    "status": "completed",
    "text": "识别的完整文本内容",
    "segments": [
      {
        "start_time": 0.0,
        "end_time": 2.5,
        "text": "第一段文本",
        "confidence": 0.95
      }
    ],
    "confidence": 0.92,
    "audio_duration": 60.5
  }
}
```

**响应（失败）**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7609169800750206794",
    "status": "failed",
    "error": "FILE_DOWNLOAD_FAILED"
  }
}
```

**响应（未处理）**：
```json
{
  "success": true,
  "data": {
    "aweme_id": "7609169800750206794",
    "status": "pending",
    "message": "视频尚未处理"
  }
}
```

**状态值**：
| 状态 | 说明 |
|------|------|
| pending | 等待处理 |
| processing | 处理中 |
| completed | 处理完成 |
| failed | 处理失败 |

---

### 3. 健康检查

**描述**：检查服务健康状态

**请求**：
```
GET /health
```

**响应**：
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "processor_ready": true
}
```

---

### 4. 根路径

**描述**：获取服务基本信息

**请求**：
```
GET /
```

**响应**：
```json
{
  "service": "douyin-processor",
  "version": "1.0.0",
  "docs": "/docs",
  "health": "/health"
}
```

---

### 5. API 文档

**描述**：自动生成的 Swagger API 文档

**访问**：
```
GET /docs
```

---

## 通过 API 网关访问

当服务部署在 ECS 并对接 api-gateway 时，使用以下路径：

| 功能 | 网关路由 | 说明 |
|------|----------|------|
| 处理音频 | `POST /api/douyin/process` | 转发到 /api/process |
| 查询结果 | `GET /api/douyin/videos/{id}/result` | 转发到 /api/videos/{id}/result |
| 健康检查 | `GET /api/douyin/health` | 转发到 /health |

**网关地址**：`http://your-ecs-ip:8010`

---

## 错误响应

**格式**：
```json
{
  "detail": "错误描述信息"
}
```

**常见错误**：
| HTTP 状态码 | 说明 |
|-------------|------|
| 404 | 接口不存在 |
| 500 | 服务器内部错误 |
| 503 | 处理器未初始化 |

---

## 请求示例

### 使用 curl

```bash
# 处理所有音频
curl -X POST http://localhost:8093/api/process

# 查询处理结果
curl http://localhost:8093/api/videos/7609169800750206794/result

# 健康检查
curl http://localhost:8093/health
```

### 使用 Python

```python
import httpx

# 处理音频
async with httpx.AsyncClient() as client:
    response = await client.post("http://localhost:8093/api/process")
    result = response.json()

# 查询结果
response = await client.get("http://localhost:8093/api/videos/7609169800750206794/result")
result = response.json()
```

### 使用 JavaScript

```javascript
// 处理音频
fetch('http://localhost:8093/api/process', { method: 'POST' })
  .then(res => res.json())
  .then(data => console.log(data));

// 查询结果
fetch('http://localhost:8093/api/videos/7609169800750206794/result')
  .then(res => res.json())
  .then(data => console.log(data));
```

---

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.1.0 | 2026-02-28 | 架构调整：直接使用 URL，不下载音频 |
| 1.0.0 | 2026-02-27 | 初始版本 |
