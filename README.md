# 疾病辅助诊断智能体

基于 **Neo4j 知识图谱 + 大模型**的症状自查 / 疾病百科智能体。
用户用自然语言描述身体不适，系统沿「感知 → 图谱检索 → 诊断 → 报告」四角色流水线，
输出疑似疾病（含常用名）、判断依据、治疗方案、预防措施、推荐就诊科室与就医提示。

前后端形态参考课程项目 `professional-training`（Django REST + Vue3/Vite），
本项目的**领域、图谱、算法、界面与创新点均为自主实现**。

> ⚠️ 本项目为课程作品，仅作辅助自查参考，**不能替代执业医师诊断**。

---

## 一、知识图谱设计

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

## 二、项目结构

```
disease-diagnosis-agent/
├── config.py                  # 统一配置（从 .env 读取，兼容多种变量名写法）
├── .env / .env.example
├── requirements.txt
├── main.py                    # 命令行交互入口
├── data/
│   ├── disease_entities.csv   # 节点表（31）
│   └── disease_relations.csv  # 关系表（42）
├── neo4j_tools/
│   ├── connection.py          # Neo4j 单例连接
│   ├── import_disease.py      # 一键导入（按 domain 隔离，不动库内其它数据）
│   └── retriever.py           # 检索层：疾病档案 / 多症状反查 / 鉴别诊断 / 证据链 / 子图
├── agents/
│   ├── llm.py                 # 大模型入口（阿里云百炼 OpenAI 兼容模式）
│   ├── perception.py          # ① 感知：意图 + 实体（含口语同义词归一）
│   ├── tools.py               # 图谱检索工具（LangChain tool）
│   ├── diagnosis_agent.py     # ③ 诊断：结构化 JSON（含置信度钳位）
│   ├── report.py              # ④ 报告 + 剂量安全护栏
│   ├── memory.py / chain.py   # 多会话记忆 / 带记忆对话
│   └── pipeline.py            # 四角色流水线编排
├── backend/                   # Django + DRF 接口层
│   ├── manage.py
│   ├── server/                # settings（跨域、DRF、项目根入 sys.path）
│   ├── api/
│   │   ├── views.py           # 9 个接口
│   │   ├── services.py        # 服务层（间接层，便于 mock 测试）
│   │   └── hallucination.py   # 幻觉检测（创新点 4 的判定器）
│   ├── tests/check_api.py     # 接口验收脚本
│   └── requirements-web.txt
├── frontend/                  # Vue3 + Vite
│   ├── vite.config.js         # 端口 5174，/api 代理到 8001
│   └── src/
│       ├── api/client.js
│       ├── App.vue            # 状态条 + 左右两栏
│       └── components/
│           ├── SymptomPanel.vue      # 输入 + 症状联想
│           ├── ResultPanel.vue       # 候选排序 / 鉴别 / 证据链 / 报告
│           ├── SubgraphView.vue      # 手写 SVG 子图可视化
│           ├── ChatBox.vue           # 多轮会话记忆
│           ├── EvaluatePanel.vue     # 双模式对照实验
│           └── SubgraphView.spec.js
├── scripts/
│   └── repair_node_modules.py  # 依赖完整性扫描 / 回补工具
└── tests/
    ├── test_env.py            # 环境自检
    ├── test_retriever.py      # 检索层验收（17 项）
    ├── test_perception.py     # 感知层验收（7 项）
    ├── test_report.py         # 剂量护栏验收（4 项）
    └── test_pipeline.py       # 端到端（2 场景）
```

---

## 三、快速开始

### 0. 前置
Neo4j 已启动（`bolt://localhost:7687`，账号 `neo4j`），项目根 `.env` 配好 `DASHSCOPE_API_KEY`。

### 1. 智能体层（无界面）
```bash
pip install -r requirements.txt

cp .env.example .env            # 填入自己的 key

python -m neo4j_tools.import_disease   # 导入知识图谱（31 节点 / 42 关系）

python tests/test_env.py               # 环境自检（Neo4j + 大模型）
python tests/test_retriever.py         # 检索层 17 项
python tests/test_perception.py        # 感知层 7 项
python tests/test_report.py            # 剂量护栏 4 项
python tests/test_pipeline.py          # 端到端 2 场景

python main.py                         # 命令行对话（--demo 跑内置示例）
```

### 2. 后端（Django，端口 8001）
```bash
cd backend
pip install -r requirements-web.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8001
```
打开 `http://127.0.0.1:8001/api/health/` 可看到 django / neo4j / llm 三项探活结果。

### 3. 前端（Vue3 + Vite，端口 5174）
```bash
cd frontend
npm install
npm run dev            # http://localhost:5174
npm test               # 组件单元测试
```
> 端口特意与参考项目错开（前端 5174 / 后端 8001），两个项目可同时运行互不干扰。

---

## 四、接口清单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health/` | 探活（`?probe=0` 跳过 Neo4j） |
| GET | `/api/graph/stats/` | 图谱规模统计（区分疾病域与全库） |
| GET | `/api/graph/subgraph/?name=` | **自研**：命中疾病的一跳子图（前端画图） |
| GET | `/api/symptoms/` | **自研**：症状词表（联想输入 / 归一校验） |
| POST | `/api/retrieve/` | 只做感知 + 图谱检索（秒级，不烧 token） |
| POST | `/api/diagnose/` | 完整四角色流水线（含报告） |
| POST | `/api/chat/` | 带记忆多轮对话（`session_id` 隔离） |
| POST | `/api/chat/reset/` | 清空指定会话记忆 |
| POST | `/api/evaluate/` | **自研**：双模式对照实验 |

请求体统一 `{"text": "..."}`；业务异常返回 502 并带 `stage` 字段（pipeline / retrieval / llm / import）。

---

## 五、核心 Cypher

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

## 六、创新点

参考项目给的是「设备故障诊断」的四角色骨架（Equipement/Fault + Django + Vue）。
本项目在此之上做了 6 项自主设计与实测改进，每项都能在代码/实验里找到依据。

### 创新点 1：口语 → 图谱规范名的**症状归一引擎**
图谱存的是医学规范词（多饮 / 多尿 / 体重下降），用户说的是口语（口渴 / 尿多 / 瘦了）。
感知层内置约 30 条同义词映射，把口语归一后再检索。

- 没有它会出现**假阴性**：实体明明抽到了，词表过滤后却变空，检索直接失败（实测踩到过）。
- 代码：`agents/perception.py` 的 `SYNONYMS` / `normalize_symptom()`；
- 验证：`tests/test_perception.py` 三组口语用例（口渴→多饮、头疼→头痛、嗓子疼→咽痛）。

### 创新点 2：**特异度加权**的候选疾病排序
不只看「命中几个症状」，而是给每个症状算特异度权重：
`score = Σ(1 / 该症状能指示的疾病数)`。

- 「多饮」只指向糖尿病（deg=1，权重 1.0），「乏力」指向 3 个病（deg=3，权重 0.33）；
  命中前者显然是更强的证据 —— 传统「数命中个数」的算法在这里会失真。
- 同时输出 `hits`、`coverage`、`score` 三个指标与一句 `why_top` 说明，
  **排序不再是黑盒**，前端用进度条展示。
- 代码：`neo4j_tools/retriever.py` 的 `_retrieve_by_symptoms()` / `_symptom_degrees()`。

### 创新点 3：**剂量安全护栏** + 置信度钳位（医疗场景专用）
实测中大模型会在报告里写「起始剂量通常为 500mg 每日 1-2 次」，而图谱里根本没有剂量 —— 这是编造。

- `agents/report.py` 的 `guard_dosage()`：报告生成后正则校验（支持 `1-2次` 这类区间写法），
  凡图谱原文里没有的剂量/频次一律替换为「具体用量请遵医嘱」；图谱已有的（`5克`、`每周5次`）保留；
- `agents/diagnosis_agent.py` 的 `_clamp_confidence()`：自查场景强制 `confidence ≤ 0.9`，
  不允许出现「100% 确诊」；
- 验证：`tests/test_report.py` 4 项（编造剂量被替换、图谱内数字保留、生活方式数字不受影响）。

### 创新点 4：**双模式对照实验**，用数据说明图谱的价值
新增 `/api/evaluate/` 接口：同一批问题跑两遍 —— A 组纯大模型自由回答，B 组走图谱增强流水线；
再用「图谱白名单 + 实体抽取」统计两组回答里出现的**图谱外药物/疾病名**，算出越界率。

VM 实测（3 个问题）：

| 组别 | 实体提及 | 图谱外提及 | 越界率 |
|---|---|---|---|
| A 纯大模型 | 26 | 21 | **80.8%** |
| B 图谱增强 | 11 | 0 | **0.0%** |

A 组编造了 `1型糖尿病`、`尿崩症`、`房颤`、`脑卒中`、`视网膜病变` 等图谱里没有的病名；
B 组因为先查图谱、再让模型基于事实组织语言，全部提及都落在知识库范围内。

- 代码：`backend/api/hallucination.py`（抽取 + 白名单判定）、`services.evaluate()`；
- 判定器做了**双向包含**兜底：图谱存「二甲双胍口服」，回答写「二甲双胍」同样算命中，
  避免命名粒度差异造成误判；同时保证 `1型糖尿病` 与 `2型糖尿病` 不会被误判为同一个。
- ⚠️ 客观说明：该指标衡量的是「提及是否落在知识库覆盖范围内」，B 组天然受限于图谱规模
  （图谱只有 3 个病，A 组提到的其它真实疾病本来就不在库内）。它证明的是
  「图谱增强能把回答约束在可信知识内」，而不是「B 组医学上更正确」。

### 创新点 5：**证据链**与**子图可视化**（可解释性）
- 检索结果附带 `evidence`：图谱里真实走过的边（`HAS_SYMPTOM → 多饮`、`TREATED_BY → 二甲双胍口服` …），
  前端表格逐条列出 —— 结论可以回溯，不是一句「根据相关资料」；
- 新增 `/api/graph/subgraph/` 返回一跳子图，前端 `SubgraphView.vue` **手写 SVG** 绘制星形图
  （不引 echarts/vis-network，零体积、离线可用、答辩好讲）；
- 验证：`frontend/src/components/SubgraphView.spec.js`（节点数/边数/关系标签/空态）。

### 创新点 6：**症状联想输入**（把图谱能力前置到输入环节）
前端调 `/api/symptoms/` 拉取图谱里的症状词表，渲染成可点击的 chip，点一下追加到提问里。
用户能直观看到「图谱认识哪些症状」，从源头减少自由文本写出图谱不认识的词导致的检索空转。

### 另外两处工程改进
- **消除重复检索**：参考项目的 `pipeline` 先检索一次，Agent 里的工具又检索一次（同一问题跑两遍）。
  本项目把检索结果直接作为**事实**传给诊断角色（`diagnose(..., retrieval=...)`），
  只在大模型需要自主决定是否查图谱时才走 Agent 工具链 —— 省一次完整检索与一次 LLM 调用。
- **导入按域名隔离**：`import_disease.py` 只清除 `domain='disease'` 的节点，
  与库内原有数据（如参考项目的设备图谱 21 节点）共存互不干扰。

---

## 七、开发记录（实测踩到的坑）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 用户说「口渴、尿多、瘦了」，症状实体抽出后却被过滤成空，检索失败 | 大模型输出口语词，图谱存规范词，词表过滤把有效信息丢了 | 感知层加口语→规范同义词表（`SYNONYMS`）做归一 |
| 2 | 报告里出现「起始剂量通常为 500mg 每日 1-2 次」 | 图谱里根本没有剂量，模型凭常识自己编的 | 报告生成后加剂量正则护栏，图谱没有的一律替换为「具体用量请遵医嘱」 |
| 3 | 场景一给出「置信度 100%」 | 模型把「症状完全匹配」当成「医学确诊」 | 提示词明确 confidence 含义 + 代码 `_clamp_confidence` 强制 ≤0.9 |
| 4 | 别名检索失败（「消渴病」查不到） | 单靠 `d.name CONTAINS` 匹配不到别名 | 查询条件扩展为 `name/alias1/alias2` 双向包含，并按精确匹配优先级排序 |
| 5 | 对照实验首版结果「A 组 100% / B 组 100%」完全失真 | 规则抽取把「型糖尿病的典型警示症」当成疾病实体 | 改为大模型抽取 + 停用字过滤 + 规则兜底，并加双向包含判定 |
| 6 | `npm test` 报 `Cannot find module http-proxy-agent/dist/index.js` | 依赖在别处安装时丢了 14 个包的入口文件（dev 链路，不影响 dev server） | 从镜像重新拉取这 14 个包整体覆盖，并用 `scripts/repair_node_modules.py` 前置扫描缺失入口 |

---

## 八、已知限制

- 示例数据只有 3 个病种，覆盖面窄，仅用于演示完整链路；扩展只需往 CSV 追加行并重跑导入；
- 症状同义词表是手工维护的白名单，新病种带来新口语说法时需要同步补充；
- 未接入真实患者病史，`confidence` 只反映「与图谱的匹配程度」，不是医学概率；
- 图谱里没有剂量信息，因此本项目**刻意不给任何具体用法用量**，只做方案推荐与就诊科室引导；
- 对照实验（创新点 4）衡量的是「提及是否落在知识库范围内」，受图谱规模限制，详见该节说明。
