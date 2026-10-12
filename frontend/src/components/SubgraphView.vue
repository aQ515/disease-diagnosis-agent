<script setup>
/**
 * 创新点：知识子图可视化
 *
 * 不引入 echarts / vis-network（体积大、要联网装包），
 * 直接用 Vue 计算坐标 + 手写 SVG 画出「疾病中心 → 一跳邻居」的星形子图，
 * 离线可用、体积为零，答辩时也好讲清楚。
 */
import { computed } from 'vue'

const props = defineProps({
  data: { type: Object, default: () => ({ nodes: [], links: [] }) },
})

const W = 460
const H = 320
const R = 112

// 各标签配色（浅色主题下保证对比度）
const COLOR = {
  Disease: '#2f6fed',
  Symptom: '#0ea5b7',
  Solution: '#16a34a',
  Prevention: '#7c3aed',
  Cause: '#e08c00',
  Department: '#db2777',
  Other: '#64748b',
}
const colorOf = (g) => COLOR[g] || COLOR.Other

const layout = computed(() => {
  const nodes = props.data.nodes || []
  const links = props.data.links || []
  if (!nodes.length) return { nodes: [], edges: [], cx: W / 2, cy: H / 2 }

  const cx = W / 2
  const cy = H / 2
  const center = nodes.find((n) => n.group === 'Disease') || nodes[0]
  const others = nodes.filter((n) => n.id !== center.id)

  const placed = others.map((n, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(others.length, 1) - Math.PI / 2
    return { ...n, x: cx + R * Math.cos(angle), y: cy + R * 0.86 * Math.sin(angle) }
  })

  const pos = { [center.id]: { x: cx, y: cy } }
  placed.forEach((n) => { pos[n.id] = { x: n.x, y: n.y } })

  const edges = links
    .filter((l) => pos[l.source] && pos[l.target])
    .map((l) => ({
      ...l,
      x1: pos[l.source].x, y1: pos[l.source].y,
      x2: pos[l.target].x, y2: pos[l.target].y,
      mx: (pos[l.source].x + pos[l.target].x) / 2,
      my: (pos[l.source].y + pos[l.target].y) / 2,
    }))

  return {
    cx, cy,
    nodes: [
      { ...center, x: cx, y: cy, r: 26, isCenter: true },
      ...placed.map((n) => ({ ...n, r: 13 })),
    ],
    edges,
  }
})

/** 图例：按标签统计节点数 */
const legend = computed(() => {
  const m = {}
  for (const n of props.data.nodes || []) {
    m[n.group] = (m[n.group] || 0) + 1
  }
  return Object.entries(m).map(([g, c]) => ({ g, c, color: colorOf(g) }))
})
</script>

<template>
  <section class="card">
    <div class="card-head">
      <span class="step">◆</span>
      <h2>图谱子图</h2>
      <span class="tag">可视化</span>
    </div>

    <div v-if="!data.nodes || !data.nodes.length" class="empty">
      <span class="ico">🕸️</span>
      先做一次检索，这里会画出命中疾病的一跳子图。
    </div>

    <template v-else>
      <svg :viewBox="`0 0 ${W} ${H}`" width="100%" height="320" role="img">
        <defs>
          <linearGradient id="gCenter" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#2f6fed" />
            <stop offset="100%" stop-color="#12b3a8" />
          </linearGradient>
          <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <!-- 边 -->
        <g>
          <line
            v-for="(e, i) in layout.edges"
            :key="'l' + i"
            :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
            stroke="#c9d6e8" stroke-width="1.3"
          />
          <text
            v-for="(e, i) in layout.edges"
            :key="'lt' + i"
            :x="e.mx" :y="e.my - 4"
            font-size="8.5" fill="#8b9ab0" text-anchor="middle"
            stroke="#ffffff" stroke-width="2.6" paint-order="stroke"
          >{{ e.rel }}</text>
        </g>

        <!-- 节点 -->
        <g v-for="n in layout.nodes" :key="n.id">
          <title>{{ n.label }}{{ n.alias ? '（' + n.alias + '）' : '' }}{{ n.desc ? ' · ' + n.desc : '' }}</title>
          <circle
            :cx="n.x" :cy="n.y" :r="n.r"
            :fill="n.isCenter ? 'url(#gCenter)' : colorOf(n.group)"
            :filter="n.isCenter ? 'url(#glow)' : null"
            stroke="#ffffff" stroke-width="2"
            opacity="0.96"
          />
          <text
            :x="n.x" :y="n.y + 4" :font-size="n.isCenter ? 13 : 10" fill="#fff"
            text-anchor="middle" font-weight="600"
          >{{ n.isCenter ? '病' : n.label.slice(0, 1) }}</text>
          <text
            :x="n.x" :y="n.y + n.r + 13" font-size="10" fill="#40506b"
            text-anchor="middle"
          >{{ n.label.length > 6 ? n.label.slice(0, 6) + '…' : n.label }}</text>
        </g>
      </svg>

      <div class="chips" style="margin-top: 4px">
        <span
          v-for="l in legend"
          :key="l.g"
          class="chip"
          :style="{ borderColor: l.color, color: l.color, background: '#fff' }"
        >{{ l.g }} · {{ l.c }}</span>
      </div>

      <p class="hint">
        共 {{ data.nodes.length }} 个节点 / {{ data.links.length }} 条边 —— 数据来自 Neo4j 实时查询，
        不是写死的静态图；鼠标悬停节点可看详情。
      </p>
    </template>
  </section>
</template>
