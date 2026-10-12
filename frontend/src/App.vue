<script setup>
/**
 * 根组件：Hero 状态区 + 左右两栏 + 页脚。
 *
 * 结果流转：SymptomPanel 抛出 result → App 保存 →
 * 同时触发子图查询（创新点）→ SubgraphView 画出命中疾病的一跳子图。
 */
import { computed, onMounted, ref } from 'vue'
import { getGraphStats, getHealth, getSubgraph } from './api/client.js'
import SymptomPanel from './components/SymptomPanel.vue'
import ResultPanel from './components/ResultPanel.vue'
import SubgraphView from './components/SubgraphView.vue'
import ChatBox from './components/ChatBox.vue'
import EvaluatePanel from './components/EvaluatePanel.vue'

const health = ref(null)
const stats = ref(null)
const result = ref(null)
const subgraph = ref({ nodes: [], links: [] })
const busy = ref(false)

const FLOW = ['感知', '图谱检索', '诊断', '报告']

/** 当前进行到流程的第几步（用于顶部高亮） */
const flowStep = computed(() => {
  if (busy.value) return 2
  if (!result.value) return 0
  return result.value.report ? 4 : result.value.retrieval_hit ? 3 : 2
})

/** 关系总数（顶部指标用） */
const relTotal = computed(() => {
  const rs = stats.value?.relationships || []
  return rs.reduce((a, b) => a + (b.count || 0), 0)
})

async function loadStatus() {
  try {
    health.value = await getHealth()
  } catch (e) {
    health.value = { status: 'down', checks: {} }
  }
  try {
    stats.value = await getGraphStats()
  } catch (e) {
    stats.value = { available: false }
  }
}

async function onResult(data) {
  result.value = data
  // 命中疾病后拉子图，供可视化（创新点 5）
  const name = data?.retrieval?.disease?.name
  if (name) {
    try {
      subgraph.value = await getSubgraph(name)
    } catch (e) {
      subgraph.value = { nodes: [], links: [] }
    }
  } else {
    subgraph.value = { nodes: [], links: [] }
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="wrap">
    <header class="hero">
      <div class="hero-head">
        <div class="hero-logo">✚</div>
        <div>
          <h1>疾病辅助诊断智能体</h1>
          <div class="sub">
            Neo4j 知识图谱 + 大模型 ｜ 症状自查 · 疾病百科 · 鉴别诊断
          </div>
        </div>
      </div>

      <div class="flow">
        <span
          v-for="(f, i) in FLOW"
          :key="f"
          class="node"
          :class="{ on: flowStep >= i + 1 }"
        >{{ i + 1 }}. {{ f }}</span>
        <span class="arrow" v-if="flowStep">→ 已完成 {{ flowStep }}/4 步</span>
        <span class="arrow" v-else>四角色流水线</span>
      </div>

      <div class="status">
        <span class="pill">
          <i class="dot" :class="health?.checks?.django?.ok ? 'ok' : 'bad'"></i>
          Django <b>{{ health?.checks?.django?.ok ? '正常' : '异常' }}</b>
        </span>
        <span class="pill">
          <i class="dot" :class="health?.checks?.neo4j?.ok ? 'ok' : 'bad'"></i>
          Neo4j <b>{{ health?.checks?.neo4j?.ok ? health.checks.neo4j.detail : '不可用' }}</b>
        </span>
        <span class="pill">
          <i class="dot" :class="health?.checks?.llm?.ok ? 'ok' : 'bad'"></i>
          <b>{{ health?.checks?.llm?.detail || 'LLM 状态未知' }}</b>
        </span>
        <button class="ghost tiny" @click="loadStatus">刷新状态</button>
      </div>

      <div class="kpis" v-if="stats?.available">
        <div class="kpi">
          <div class="n">{{ stats.disease_nodes }} <em>个节点</em></div>
          <div class="l">疾病知识图谱</div>
        </div>
        <div class="kpi">
          <div class="n">{{ relTotal }} <em>条关系</em></div>
          <div class="l">图谱关系总数</div>
        </div>
        <div class="kpi">
          <div class="n">{{ stats.labels?.length || 0 }} <em>类实体</em></div>
          <div class="l">疾病 / 症状 / 方案 / 预防…</div>
        </div>
        <div class="kpi">
          <div class="n">{{ stats.total_nodes }}</div>
          <div class="l">库内节点总数（含其它域）</div>
        </div>
      </div>
    </header>

    <div class="grid">
      <div class="col">
        <SymptomPanel @result="onResult" @loading="busy = $event" />
        <SubgraphView :data="subgraph" />
        <ChatBox />
      </div>

      <div class="col">
        <ResultPanel :result="result" />
        <EvaluatePanel />
      </div>
    </div>

    <div class="foot">
      <b>疾病辅助诊断智能体</b> · 四角色流水线（感知 → 图谱检索 → 诊断 → 报告）
      · 数据来源：Neo4j 知识图谱（31 节点 / 42 关系）+ 阿里云百炼 Qwen
      <br />
      本项目为课程作品，仅作辅助自查参考，不能替代执业医师诊断。
    </div>
  </div>
</template>
