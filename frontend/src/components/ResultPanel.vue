<script setup>
/**
 * 结果面板
 *
 * 展示：
 * 1) 感知结果（意图 / 实体）与命中方式
 * 2) 候选疾病排序 —— 「命中数 / 覆盖度 / 特异度加权分」三指标 + 渐变进度条
 *    （创新点 2：排序可解释，不是黑盒）
 * 3) 鉴别诊断 + 图谱证据链（可回溯）
 * 4) 诊断报告 —— 把大模型输出按「小节 / 要点」结构化渲染，比纯文本好读
 */
import { computed } from 'vue'

const props = defineProps({
  result: { type: Object, default: null },
})

const perception = computed(() => props.result?.perception || {})
const retrieval = computed(() => props.result?.retrieval || {})
const diagnosis = computed(() => props.result?.diagnosis || null)
const report = computed(() => props.result?.report || '')
const hit = computed(() => !!props.result?.retrieval_hit)

const candidates = computed(() => retrieval.value.candidates || [])
const differential = computed(() => retrieval.value.differential || [])
const evidence = computed(() => retrieval.value.evidence || [])
const symptoms = computed(() => {
  const s = retrieval.value.symptoms || []
  return Array.isArray(s) ? s : []
})
const disease = computed(() => retrieval.value.disease || null)

const REL_CN = {
  HAS_SYMPTOM: '表现为症状',
  TREATED_BY: '治疗用',
  PREVENTED_BY: '预防靠',
  CAUSED_BY: '病因是',
  BELONGS_TO: '就诊科室',
}
const relCN = (r) => REL_CN[r] || r
const pct = (v) => `${Math.round((v || 0) * 100)}%`

/** 把报告纯文本解析成小节结构，前端渲染得更好读 */
const reportSections = computed(() => {
  const raw = report.value.trim()
  if (!raw) return []
  const lines = raw.split(/\r?\n/)
  const sections = []
  let cur = null
  const HEAD = /^\s*(?:\d+[.、)]|[一二三四五六七八九十]+[、.])\s*(.+)$/

  for (const line of lines) {
    const t = line.trim()
    if (!t) continue
    const h = t.match(HEAD)
    // 只有当编号行较短时才当标题（避免把长句误判）
    if (h && t.length <= 32) {
      const title = h[1].replace(/[:：]\s*$/, '')
      cur = { title, items: [], paragraphs: [] }
      sections.push(cur)
    } else if (/^[-•·*]\s+/.test(t)) {
      const item = t.replace(/^[-•·*]\s+/, '')
      if (!cur) { cur = { title: '报告', items: [], paragraphs: [] }; sections.push(cur) }
      cur.items.push(item)
    } else {
      if (!cur) { cur = { title: '', items: [], paragraphs: [] }; sections.push(cur) }
      cur.paragraphs.push(t)
    }
  }
  // 无标题的第一个小节归并为「诊断报告」
  if (sections.length && !sections[0].title) sections[0].title = '诊断报告'
  return sections
})
</script>

<template>
  <div class="col">
    <!-- 空态 -->
    <section v-if="!result" class="card">
      <div class="card-head">
        <span class="step">2</span>
        <h2>诊断结果</h2>
        <span class="tag">等待输入</span>
      </div>
      <div class="empty">
        <span class="ico">🩺</span>
        还没有结果 —— 在左侧描述不适症状，或点击示例问题，
        <br />系统会依次输出 <b>感知结果 → 候选疾病 → 鉴别诊断 → 图谱证据 → 诊断报告</b>。
      </div>
    </section>

    <template v-else>
      <!-- 感知 + 概览 -->
      <section class="card">
        <div class="card-head">
          <span class="step">2</span>
          <h2>感知与命中</h2>
          <span class="tag">{{ perception.intent || '—' }}</span>
        </div>

        <dl class="kv">
          <dt>识别疾病</dt>
          <dd>
            <span v-if="!perception.entities?.disease" class="muted">—</span>
            <span v-else class="chip on">{{ perception.entities.disease }}</span>
          </dd>

          <dt>识别症状</dt>
          <dd>
            <span v-if="!(perception.entities?.symptom || []).length" class="muted">—</span>
            <span
              v-for="s in perception.entities?.symptom || []"
              :key="s"
              class="chip on"
              style="margin: 0 6px 6px 0"
            >{{ s }}</span>
          </dd>

          <dt>命中方式</dt>
          <dd>
            <span v-if="hit" class="badge ok">已命中图谱</span>
            <span v-else class="badge bad">未命中</span>
            <span style="margin-left: 8px">{{ retrieval.reason }}</span>
          </dd>

          <dt v-if="disease?.name">命中疾病</dt>
          <dd v-if="disease?.name">
            <b>{{ disease.name }}</b>
            <span v-if="disease.alias1" class="muted">（常用名：{{ disease.alias1 }}）</span>
            <span v-if="disease.department" class="badge info" style="margin-left: 8px">
              推荐科室 {{ disease.department }}
            </span>
          </dd>
        </dl>

        <p v-if="retrieval.why_top" class="hint" style="margin-top: 12px">
          <b>为什么排第一：</b>{{ retrieval.why_top }}
        </p>

        <p v-if="result.timing && result.timing.total_s" class="hint">
          耗时 {{ result.timing.total_s }}s —— 感知 {{ result.timing.perception_s }}s ·
          检索 {{ result.timing.retrieval_s }}s · 诊断 {{ result.timing.diagnosis_s }}s ·
          报告 {{ result.timing.report_s }}s
        </p>
      </section>

      <!-- 候选排序 -->
      <section v-if="candidates.length" class="card">
        <div class="card-head">
          <span class="step">3</span>
          <h2>候选疾病排序</h2>
          <span class="tag">特异度加权</span>
        </div>

        <div
          v-for="(c, i) in candidates"
          :key="c.name"
          class="cand"
          :class="{ top: i === 0 }"
        >
          <div class="row">
            <span class="name">
              <span class="rank">{{ i + 1 }}</span>
              {{ c.name }}
              <span v-if="c.alias1" class="alias">（{{ c.alias1 }}）</span>
            </span>
            <span class="dept">{{ c.department || '—' }}</span>
          </div>

          <div class="score-wrap">
            <div class="bar"><i :style="{ width: pct(c.score || c.coverage) }"></i></div>
            <span class="score-num">{{ (c.score ?? c.coverage ?? 0).toFixed(2) }}</span>
          </div>

          <div class="metrics">
            <span>命中 <b>{{ c.hits }}</b> 个</span>
            <span>覆盖度 <b>{{ pct(c.coverage) }}</b></span>
            <span>加权分 <b>{{ (c.score ?? 0).toFixed(2) }}</b></span>
          </div>

          <div class="chips">
            <span v-for="s in c.matched_symptoms" :key="s" class="chip on">{{ s }}</span>
            <span v-for="s in (c.missed_symptoms || [])" :key="'m' + s" class="chip miss">{{ s }}（未命中）</span>
          </div>
        </div>

        <p class="hint">
          「特异度加权分」= Σ(1 / 该症状能指示的疾病数)：命中「多饮」这类只指向一个病的症状得分更高，
          比单纯数命中个数更贴近临床判断。
        </p>
      </section>

      <!-- 鉴别诊断 -->
      <section v-if="differential.length" class="card">
        <div class="card-head">
          <span class="step">4</span>
          <h2>需要鉴别</h2>
          <span class="tag">共享症状</span>
        </div>
        <table>
          <thead>
            <tr><th>疾病</th><th style="width: 120px">常用名</th><th>与本病的共享症状</th></tr>
          </thead>
          <tbody>
            <tr v-for="d in differential" :key="d.name">
              <td><b>{{ d.name }}</b></td>
              <td class="muted">{{ d.alias1 || '—' }}</td>
              <td>
                <span v-for="s in d.shared || []" :key="s" class="chip on" style="margin-right: 6px">{{ s }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="hint">症状被多个疾病共用是「同症异病」的根源，这里列出症状重叠的疾病提醒区分。</p>
      </section>

      <!-- 证据链 -->
      <section v-if="evidence.length" class="card">
        <div class="card-head">
          <span class="step">5</span>
          <h2>图谱证据链</h2>
          <span class="tag">可回溯</span>
        </div>
        <table>
          <thead>
            <tr>
              <th style="width: 130px">关系</th>
              <th style="width: 96px">含义</th>
              <th>目标节点</th>
              <th style="width: 96px">类型</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(e, i) in evidence" :key="i">
              <td><code class="k">{{ e.rel }}</code></td>
              <td class="muted">{{ relCN(e.rel) }}</td>
              <td>{{ e.target }}</td>
              <td class="muted">{{ e.target_label }}</td>
            </tr>
          </tbody>
        </table>
        <p class="hint">结论可以逐条回溯到图谱里真实的边 —— 这是图检索相对「向量相似度」的优势。</p>
      </section>

      <!-- 报告 -->
      <section v-if="report" class="card">
        <div class="card-head">
          <span class="step">6</span>
          <h2>诊断报告</h2>
          <span class="tag">大模型生成</span>
        </div>

        <div class="report">
          <div v-for="(sec, i) in reportSections" :key="i" class="report-sec">
            <h4 v-if="sec.title">{{ sec.title }}</h4>
            <p v-for="(p, j) in sec.paragraphs" :key="'p' + j">{{ p }}</p>
            <ul v-if="sec.items.length">
              <li v-for="(it, k) in sec.items" :key="'i' + k">{{ it }}</li>
            </ul>
          </div>
        </div>

        <div class="disclaimer">
          <span>⚠️</span>
          <span>
            本结果由知识图谱 + 大模型辅助生成，仅供参考，不能替代执业医师诊断。
            报告中不含具体用法用量（图谱未收录剂量，已由安全护栏拦截模型编造的剂量）。
          </span>
        </div>
      </section>
    </template>
  </div>
</template>
