# 医疗 AI 智能导诊与用药助手（FastAPI + LangGraph 版）

> 本文档对应项目的 **v2 架构升级**：在原有「Neo4j + Django + 四角色 Agent」基础上，
> 升级为 **FastAPI + SSE 流式 + LangGraph 编排 + Redis 缓存 + Docker 部署**。
> 原 Django 版本保留在 `backend/`，两套并存、互不影响。

---

## 一、为什么升级（技术决策）

| 维度 | v1（Django） | v2（FastAPI + LangGraph） |
|---|---|---|
| 接口风格 | 同步返回完整 JSON | **SSE 流式**，打字机效果，用户可见阶段进度 |
| 异步支持 | Django 同步为主 | **原生 async**，适合 LLM 长耗时 + 高并发 |
| Agent 编排 | 硬编码四步顺序调用 | **LangGraph StateGraph**，条件分支 + 状态可观测 |
| 缓存 | 无 | **Redis**（高频问答秒级返回，降级内存） |
| 部署 | 手工起 3 个终端 | **docker compose 一键** |

**面试可讲点**：这次升级不是堆技术名词，而是针对真实痛点——
LLM 推理 3-6 秒用户干等（→ SSE）、流程写死难扩展（→ LangGraph）、
重复问题反复烧 token（→ Redis）、环境难复现（→ Docker）。

---

## 二、架构

```
浏览器（Vue3 原生前端，无构建步骤）
   │  POST /chat  (SSE)
   ▼
FastAPI  ── 缓存层（Redis → 内存降级）
   │
   ▼
LangGraph StateGraph
   perception ──条件路由──┬─→ graph  (Neo4j 图谱检索)
                         ├─→ rag    (用药类 → RAG)
                         └─→ chitchat
                              ↓
                         diagnose → report → END
   │
   ▼
Neo4j（疾病图谱） + 大模型（百炼 qwen-plus）
```

---

## 三、快速开始

### 方式 A：本地跑（推荐先看这个）

**1. 前置**：Neo4j 已启动（见主 README 的 JDK 11 说明）、`.env` 已配 Key。

**2. 装依赖**
```powershell
cd disease-diagnosis-agent
.\.venv\Scripts\activate
pip install fastapi uvicorn redis httpx langgraph==0.6.11 -i https://pypi.org/simple
```

> ⚠️ **langgraph 必须锁 0.6.11**：新版 1.x 要求 langchain-core ≥1.0，会破坏本项目
> langchain 0.3 全家桶。这是实测踩过的坑。

**3. 启动**
```powershell
python -m uvicorn fastapi_app.main:app --host 0.0.0.0 --port 8002
```

**4. 打开** `http://localhost:8002`

### 方式 B：Docker 一键（含 Neo4j + Redis）

```powershell
# 1. 确认 .env 里有 DASHSCOPE_API_KEY（不会进镜像）
# 2. 一键启动
docker compose up -d

# 3. 首次需导入图谱（进容器执行一次）
docker exec -it medical-agent-api python -m neo4j_tools.import_disease

# 4. 访问 http://localhost:8002
```

停止：`docker compose down`

---

## 四、接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | **SSE 流式问答**，事件：`stage` / `token` / `done` / `error` |
| GET | `/history/{sid}` | 会话历史 |
| DELETE | `/history/{sid}` | 清空会话 |
| GET | `/sessions` | 会话列表 |
| GET | `/api/health` | 探活（neo4j / llm / cache / engine） |
| GET | `/api/engine` | 当前 Agent 引擎与 LangGraph 可用性 |

`POST /chat` 请求体：
```json
{"question": "我最近老是口渴、尿多，还瘦了", "session_id": "web-xxx", "use_cache": true}
```

SSE 事件流示例：
```
event: stage     data: {"name":"perception","msg":"正在理解你的问题…"}
event: stage     data: {"name":"retrieval","msg":"检索 命中 图谱","detail":{...}}
event: stage     data: {"name":"report","msg":"正在生成报告…"}
event: token     data: {"text":"1."}
event: token     data: {"text":" 诊断结论"}
...（逐字流式）
event: done      data: {"engine":"langgraph","route":"graph","sources":[...],"elapsed_s":4.2}
```

---

## 五、四个核心实现（面试讲这些）

### 1. SSE 流式打字机
后端 `StreamingResponse` 按 2 字一片推送 `token` 事件；阶段事件让用户看到
「理解 → 检索 → 生成」的进度，而不是干等 5 秒。前端用 `ReadableStream` 逐块解析。

### 2. LangGraph 条件编排
`fastapi_app/graph_flow.py` 用 `StateGraph` 定义 6 个节点 + 1 个条件边：
- 感知节点后按意图路由：用药类 → RAG 分支，症状类 → Neo4j 分支，闲聊 → 直接对话
- 三条分支汇合到诊断 → 报告 → END
- 每步写入 `trace`（耗时），前端 done 事件可展示全链路轨迹

### 3. Redis 缓存降级
`fastapi_app/cache.py`：Redis 优先，`ping` 不通自动降级内存字典。
键 = 问题文本 md5，命中直接流式吐历史答案（25s → 2s）。
**服务不会因为 Redis 挂掉而不可用**——这是生产环境常见降级策略。

### 4. 全链路降级
图谱不可用 → `_empty_result()` + 通用模式继续回答；
LangGraph 不可用 → 回退原四角色流水线；
模型输出带剂量 → `guard_dosage()` 正则替换为「具体用量请遵医嘱」。
**每一层都有兜底**，不会把异常直接抛给用户。

---

## 六、已知限制（诚实标注）

- Redis 缓存按「问题文本 md5」做键，表述不同的同义问题不会命中（未做语义缓存）；
- LangGraph 的 RAG 分支当前是 graph-backed 占位（项目未内置独立向量库），
  真正 RAG 在 `Medical-RAG-QA` 仓库；
- 前端是单文件原生 HTML/CSS/JS，未用 Vue3 工程化构建——为了零构建、易演示；
- MySQL 用户系统未实现（对 AI 应用岗意义有限，历史用本地 JSON 存储）。

---

## 七、目录

```
fastapi_app/
├── main.py          # FastAPI 应用 + SSE 接口
├── graph_flow.py    # LangGraph StateGraph（阶段 2 核心）
├── pipeline.py      # 统一入口：引擎选择 + 降级
├── cache.py         # Redis → 内存 缓存降级
├── history.py       # 会话历史（JSON）
├── config.py        # 配置
└── static/index.html # 前端（聊天气泡 + 打字机 + 侧边栏历史）
docker-compose.yml   # Neo4j + Redis + API 一键编排
Dockerfile
```
