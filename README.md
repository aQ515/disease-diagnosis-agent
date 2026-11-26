# 医疗 AI 智能导诊与用药助手

基于医疗知识图谱的多轮问答系统：Neo4j 存疾病图谱，LangGraph 编排检索与诊断，
FastAPI 提供 SSE 流式接口，Redis 缓存高频问答。

---

## 一、架构

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

## 二、快速开始

### 方式 A：本地跑（推荐先看这个）

**1. 前置**：Neo4j 已启动（见附录「环境准备」）、`.env` 已配 Key。

**2. 装依赖**
```powershell
cd disease-diagnosis-agent
.\.venv\Scripts\activate
pip install fastapi uvicorn redis httpx langgraph==0.6.11 -i https://pypi.org/simple
```

> langgraph 需锁 0.6.11：1.x 要求 langchain-core ≥1.0，与本项目 langchain 0.3 不兼容。

**3. 启动**
```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8002
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

## 三、接口清单

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

## 四、核心实现

### SSE 流式打字机
后端 `StreamingResponse` 按 2 字一片推送 `token` 事件；阶段事件让用户看到
「理解 → 检索 → 生成」的进度，而不是干等 5 秒。前端用 `ReadableStream` 逐块解析。

### LangGraph 条件编排
`backend/graph_flow.py` 用 `StateGraph` 定义 6 个节点 + 1 个条件边：
- 感知节点后按意图路由：用药类 → RAG 分支，症状类 → Neo4j 分支，闲聊 → 直接对话
- 三条分支汇合到诊断 → 报告 → END
- 每步写入 `trace`（耗时），前端 done 事件可展示全链路轨迹

### Redis 缓存降级
`backend/cache.py`：Redis 优先，`ping` 不通自动降级内存字典。
键 = 问题文本 md5，命中直接流式吐历史答案（25s → 2s）。
Redis 不可用时服务仍可用。

### 全链路降级
图谱不可用 → `_empty_result()` + 通用模式继续回答；
LangGraph 不可用 → 回退原四角色流水线；
模型输出带剂量 → `guard_dosage()` 正则替换为「具体用量请遵医嘱」。
各层异常都有兜底，不会直接抛给用户。

---

## 五、已知限制

- Redis 缓存按「问题文本 md5」做键，表述不同的同义问题不会命中（未做语义缓存）；
- LangGraph 的 RAG 分支当前是 graph-backed 占位（项目未内置独立向量库），
  真正 RAG 在 `Medical-RAG-QA` 仓库；
- 前端是单文件原生 HTML/CSS/JS，无构建步骤；
- 未实现 MySQL 用户系统，会话历史存本地 JSON。

---

## 六、目录

```
backend/
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

---

# 附录：技术与踩坑记录

### 环境准备

**JDK 版本**

Neo4j 3.5.x 只支持 Java 8 / 11，用 JDK 17 启动会崩溃并自动 shutdown。
机器只有 JDK 17 时无需卸载，单独放一份 JDK 11 即可（如 `C:\Users\86181\java\jdk-11.0.33+10`）。

**启动 Neo4j**（PowerShell，依次执行）

```powershell
$env:JAVA_HOME = "C:\Users\86181\java\jdk-11.0.33+10"
cd "D:\vm\neo4j-community-3.5.28-windows\neo4j-community-3.5.28\bin"
.\neo4j.bat console
```

看到 `Remote interface available at http://localhost:7474/` 即启动成功。该窗口不能关，
否则服务停止；也可 `neo4j.bat install-service` + `neo4j.bat start` 装成后台服务。

> 浏览器打开 `:7474` 若报 `NotFoundError: removeChild`，是 Neo4j 3.5 老版 Browser
> 与新版浏览器内核不兼容，服务本身正常，用代码验证即可。

**忘记密码时重置**（数据不丢）

```powershell
# 停服务后执行
Remove-Item "D:\vm\neo4j-community-3.5.28-windows\neo4j-community-3.5.28\data\dbms\auth" -Force
cd "D:\vm\neo4j-community-3.5.28-windows\neo4j-community-3.5.28\bin"
$env:JAVA_HOME = "C:\Users\86181\java\jdk-11.0.33+10"
.\neo4j-admin.bat set-initial-password 123456
```

**Python 环境与编码**

```powershell
cd <项目根目录>
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt -i https://pypi.org/simple
$env:PYTHONIOENCODING = "utf-8"   # Windows 终端中文输出
```

> pip 全局源若连不上，用 `pip config set global.index-url https://pypi.org/simple` 改掉。

---

### 知识图谱设计

采用「中心辐射式」结构，以 `Disease` 为单中心向外发散：

```
        Cause ──CAUSED_BY──┐
                            │
   Symptom ──HAS_SYMPTOM──[Disease]──TREATED_BY── Solution
      │                     │
      └──INDICATES──────────┴──PREVENTED_BY── Prevention
                            │
                            └──BELONGS_TO── Department
```

| 标签 | 含义 | 关键属性 |
|---|---|---|
| `Disease` | 疾病（核心） | `name` `alias1` `alias2` `type` `severity` `department` `description` |
| `Symptom` | 症状表现 | `name` `type` `description` |
| `Solution` | 治疗方案 | `name` `type` `description` `steps` `cost` |
| `Prevention` | 预防措施 | `name` `type` `description` `frequency` |
| `Cause` | 病因 · 危险因素 | `name` `type` `description` |
| `Department` | 就诊科室 | `name` `description` |

| 关系 | 方向 | 用途 |
|---|---|---|
| `HAS_SYMPTOM` | Disease → Symptom | 疾病有哪些临床表现 |
| `TREATED_BY` | Disease → Solution | 给出治疗方案 |
| `PREVENTED_BY` | Disease → Prevention | 给出预防建议 |
| `CAUSED_BY` | Disease → Cause | 解释发病原因 |
| `BELONGS_TO` | Disease → Department | 推荐就诊科室 |
| `INDICATES` | Symptom → Disease | **反向边**，症状反查疾病（检索主力） |

三个关键设计点：

1. **疾病节点带别名**（`alias1` / `alias2`）——「消渴病」「血压升高」这类口语输入也能命中；
2. **保留 `INDICATES` 反向边**——主流程是「症状 → 疾病」，反向边让语义与性能都更清晰；
3. **症状被多个疾病共用**（「乏力」同属糖尿病、高血压、流感），这正是图结构相对表格的优势，
   天然支持「同症异病」的鉴别诊断。

**示例规模**：3 病种 → **31 节点 / 42 关系**（2型糖尿病、原发性高血压、流行性感冒）。
扩展只需按同样列格式往 `data/*.csv` 追加行，再重跑导入脚本（无需改代码）。

---

### 项目结构

```
disease-diagnosis-agent/
├── config.py                  # 统一配置（从 .env 读取）
├── .env / .env.example
├── requirements.txt           # 核心依赖
├── requirements-api.txt       # API 层依赖
├── main.py                    # 命令行交互入口
├── data/
│   ├── disease_entities.csv   # 节点表（31）
│   └── disease_relations.csv  # 关系表（42）
├── neo4j_tools/
│   ├── connection.py          # Neo4j 单例连接
│   ├── import_disease.py      # 图谱导入（按 domain 隔离）
│   └── retriever.py           # 检索层：疾病档案 / 多症状反查 / 鉴别诊断 / 证据链 / 子图
├── agents/
│   ├── llm.py                 # 大模型入口（阿里云百炼 OpenAI 兼容模式）
│   ├── perception.py          # 感知：意图 + 实体（含口语同义词归一）
│   ├── tools.py               # 图谱检索工具（LangChain tool）
│   ├── diagnosis_agent.py     # 诊断：结构化 JSON（含置信度钳位）
│   ├── report.py              # 报告 + 剂量安全护栏
│   ├── memory.py / chain.py   # 多会话记忆 / 带记忆对话
│   └── pipeline.py            # 四角色流水线编排
├── backend/                   # FastAPI 接口层
│   ├── main.py                # SSE 接口 + 前端页面
│   ├── graph_flow.py          # LangGraph 状态图编排
│   ├── pipeline.py            # 引擎选择 + 降级
│   ├── cache.py               # Redis → 内存缓存
│   ├── history.py             # 会话历史（JSON）
│   ├── config.py              # API 层配置
│   └── static/index.html      # 前端页面
├── scripts/
│   └── repair_node_modules.py
├── tests/
│   ├── test_env.py            # 环境自检
│   ├── test_retriever.py      # 检索层验收（17 项）
│   ├── test_perception.py     # 感知层验收（7 项）
│   ├── test_report.py         # 剂量护栏验收（4 项）
│   └── test_pipeline.py       # 端到端（2 场景）
├── Dockerfile
└── docker-compose.yml
```

---

### 核心 Cypher

**别名检索疾病档案**
```cypher
MATCH (d:Disease {domain:'disease'})
WHERE d.name = $text OR d.alias1 = $text OR d.alias2 = $text
   OR $text CONTAINS d.name OR $text CONTAINS d.alias1 OR $text CONTAINS d.alias2
WITH d ORDER BY (d.name = $text OR d.alias1 = $text OR d.alias2 = $text) DESC LIMIT 1
OPTIONAL MATCH (d)-[:HAS_SYMPTOM]->(s:Symptom)
OPTIONAL MATCH (d)-[:TREATED_BY]->(sol:Solution)
RETURN d.name, d.alias1, collect(DISTINCT s.name) AS 症状, collect(DISTINCT sol.name) AS 方案
```

**多症状反查（按命中数排序）**
```cypher
UNWIND $symptoms AS sn
MATCH (s:Symptom {name: sn})-[:INDICATES]->(d:Disease)
WITH d, count(DISTINCT s) AS hits, collect(DISTINCT s.name) AS matched
ORDER BY hits DESC LIMIT 3
RETURN d.name, hits, matched
```

**鉴别诊断（症状重叠）**
```cypher
MATCH (d:Disease {name:$name})-[:HAS_SYMPTOM]->(s:Symptom)<-[:HAS_SYMPTOM]-(o:Disease)
WHERE o <> d
RETURN o.name, collect(DISTINCT s.name) AS shared
ORDER BY size(shared) DESC
```

**证据链（结论可回溯到具体的边）**
```cypher
MATCH (d:Disease {name:$name})-[r]->(n)
RETURN d.name AS disease, type(r) AS rel, n.name AS target, labels(n)[0] AS target_label
```

---

### 设计与改进

以下是几处基于实测结果的设计选择。

### 口语 → 图谱规范名的**症状归一引擎**
图谱存的是医学规范词（多饮 / 多尿 / 体重下降），用户说的是口语（口渴 / 尿多 / 瘦了）。
感知层内置约 30 条同义词映射，把口语归一后再检索。

- 没有它会出现**假阴性**：实体明明抽到了，词表过滤后却变空，检索直接失败（实测踩到过）。
- 代码：`agents/perception.py` 的 `SYNONYMS` / `normalize_symptom()`；
- 验证：`tests/test_perception.py` 三组口语用例（口渴→多饮、头疼→头痛、嗓子疼→咽痛）。

### **特异度加权**的候选疾病排序
不只看「命中几个症状」，而是给每个症状算特异度权重：
`score = Σ(1 / 该症状能指示的疾病数)`。

- 「多饮」只指向糖尿病（deg=1，权重 1.0），「乏力」指向 3 个病（deg=3，权重 0.33）；
  命中前者显然是更强的证据 —— 传统「数命中个数」的算法在这里会失真。
- 同时输出 `hits`、`coverage`、`score` 三个指标与一句 `why_top` 说明，
  **排序不再是黑盒**，前端用进度条展示。
- 代码：`neo4j_tools/retriever.py` 的 `_retrieve_by_symptoms()` / `_symptom_degrees()`。

### **剂量安全护栏** + 置信度钳位（医疗场景专用）
实测中大模型会在报告里写「起始剂量通常为 500mg 每日 1-2 次」，而图谱里根本没有剂量 —— 这是编造。

- `agents/report.py` 的 `guard_dosage()`：报告生成后正则校验（支持 `1-2次` 这类区间写法），
  凡图谱原文里没有的剂量/频次一律替换为「具体用量请遵医嘱」；图谱已有的（`5克`、`每周5次`）保留；
- `agents/diagnosis_agent.py` 的 `_clamp_confidence()`：自查场景强制 `confidence ≤ 0.9`，
  不允许出现「100% 确诊」；
- 验证：`tests/test_report.py` 4 项（编造剂量被替换、图谱内数字保留、生活方式数字不受影响）。

### 双模式对照实验
同一批问题跑两遍 —— A 组纯大模型自由回答，B 组走图谱增强流水线；
再用「图谱白名单 + 实体抽取」统计两组回答里出现的**图谱外药物/疾病名**，算出越界率。

VM 实测（3 个问题）：

| 组别 | 实体提及 | 图谱外提及 | 越界率 |
|---|---|---|---|
| A 纯大模型 | 26 | 21 | **80.8%** |
| B 图谱增强 | 11 | 0 | **0.0%** |

A 组编造了 `1型糖尿病`、`尿崩症`、`房颤`、`脑卒中`、`视网膜病变` 等图谱里没有的病名；
B 组因为先查图谱、再让模型基于事实组织语言，全部提及都落在知识库范围内。

- 判定器做了**双向包含**兜底：图谱存「二甲双胍口服」，回答写「二甲双胍」同样算命中，
  避免命名粒度差异造成误判；同时保证 `1型糖尿病` 与 `2型糖尿病` 不会被误判为同一个。
- 说明：该指标衡量的是「提及是否落在知识库覆盖范围内」，B 组天然受限于图谱规模
  （图谱只有 3 个病，A 组提到的其它真实疾病本来就不在库内）。它证明的是
  「图谱增强能把回答约束在可信知识内」，而不是「B 组医学上更正确」。

### 证据链与子图可视化
- 检索结果附带 `evidence`：图谱里真实走过的边（`HAS_SYMPTOM → 多饮`、`TREATED_BY → 二甲双胍口服` …），
  前端表格逐条列出 —— 结论可以回溯，不是一句「根据相关资料」；
- 新增 `/api/graph/subgraph/` 返回一跳子图，前端手写 SVG 绘制星形图（不引第三方可视化库）；

### 症状联想输入
前端拉取图谱里的症状词表，渲染成可点击的 chip，点一下追加到提问里。
用户能直观看到「图谱认识哪些症状」，从源头减少自由文本写出图谱不认识的词导致的检索空转。

### 另外两处工程改进
- **消除重复检索**：`pipeline` 先检索一次，Agent 里的工具又检索一次（同一问题跑两遍）。
  本项目把检索结果直接作为**事实**传给诊断角色（`diagnose(..., retrieval=...)`），
  只在大模型需要自主决定是否查图谱时才走 Agent 工具链 —— 省一次完整检索与一次 LLM 调用。
- **导入按域名隔离**：`import_disease.py` 只清除 `domain='disease'` 的节点，不影响库内其它数据。

---

### 开发记录

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 用户说「口渴、尿多、瘦了」，症状实体抽出后却被过滤成空，检索失败 | 大模型输出口语词，图谱存规范词，词表过滤把有效信息丢了 | 感知层加口语→规范同义词表（`SYNONYMS`）做归一 |
| 2 | 报告里出现「起始剂量通常为 500mg 每日 1-2 次」 | 图谱里根本没有剂量，模型凭常识自己编的 | 报告生成后加剂量正则护栏，图谱没有的一律替换为「具体用量请遵医嘱」 |
| 3 | 场景一给出「置信度 100%」 | 模型把「症状完全匹配」当成「医学确诊」 | 提示词明确 confidence 含义 + 代码 `_clamp_confidence` 强制 ≤0.9 |
| 4 | 别名检索失败（「消渴病」查不到） | 单靠 `d.name CONTAINS` 匹配不到别名 | 查询条件扩展为 `name/alias1/alias2` 双向包含，并按精确匹配优先级排序 |
| 5 | 对照实验首版结果「A 组 100% / B 组 100%」完全失真 | 规则抽取把「型糖尿病的典型警示症」当成疾病实体 | 改为大模型抽取 + 停用字过滤 + 规则兜底，并加双向包含判定 |
| 7 | Neo4j 启动即自动 shutdown（日志 `shutdown initiated by request` + 一栈 Java 异常） | 机器只有 JDK 17，Neo4j 3.5.x 不兼容 Java 17 | 装独立 JDK 11，启动前设 `$env:JAVA_HOME` 指向它（见附录「环境准备」） |
| 8 | 浏览器打开 `:7474` 报 `NotFoundError: removeChild` | Neo4j 3.5 老版 Browser 前端与现代浏览器内核不兼容 | 服务本身正常，忽略该页面，用代码验证连接 |
| 9 | `import_disease` 报 `py2neo.errors.ClientError: [Security.Unauthorized]` | `.env` 里 `NEO4J_PASSWORD` 是旧密码，与重置后的不一致 | 把 `.env` 的 `NEO4J_PASSWORD` 改成实际密码；另注意要用 `.venv` 的解释器而非全局 `python` |
| 10 | `pip install` 报 `Could not find a version... (from versions: none)` | 全局 pip 配的清华源在本机连不上（网络问题，不是没包） | `pip install -r requirements.txt -i https://pypi.org/simple`；或 `pip config set global.index-url https://pypi.org/simple` |
| 11 | 打印中文报 `'ascii' codec can't encode characters` | Windows 终端默认编码不支持中文 | `$env:PYTHONIOENCODING = "utf-8"`，或设用户级环境变量永久生效 |

---

## 八、已知限制

- 示例数据只有 3 个病种，覆盖面窄，仅用于演示完整链路；扩展只需往 CSV 追加行并重跑导入；
- 症状同义词表是手工维护的白名单，新病种带来新口语说法时需要同步补充；
- 未接入真实患者病史，`confidence` 只反映「与图谱的匹配程度」，不是医学概率；
- 图谱里没有剂量信息，因此本项目**刻意不给任何具体用法用量**，只做方案推荐与就诊科室引导；
- 对照实验衡量的是「提及是否落在知识库范围内」，受图谱规模限制，详见该节说明。
