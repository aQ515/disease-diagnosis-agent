<script setup>
/**
 * 创新点：双模式对照实验
 *
 * 同一批问题跑两遍：
 *   A 组 —— 不给图谱，纯大模型自由回答
 *   B 组 —— 走四角色流水线（图谱增强）
 * 后端用「图谱白名单 + 实体抽取」统计两组回答里出现的图谱外药物/疾病名，
 * 算出越界提及率（≈ 编造率）。用数据说明图谱的价值，而不是空口说"减少幻觉"。
 */
import { computed, ref } from 'vue'
import { postEvaluate } from '../api/client.js'

const DEFAULT_Q = '我最近老是口渴、尿多，还瘦了，是不是糖尿病？\n头晕、心悸、头痛，需要看什么科？'
const questions = ref(DEFAULT_Q)
const loading = ref(false)
const error = ref('')
const data = ref(null)

const pct = (v) => `${Math.round((v || 0) * 100)}%`

/** 越界率下降幅度（相对 A 组） */
const drop = computed(() => {
  const a = data.value?.summary?.plain?.illegal_rate || 0
  const b = data.value?.summary?.graph?.illegal_rate || 0
  if (!a) return 0
  return Math.max(0, Math.round((1 - b / a) * 100))
})

async function run() {
  if (loading.value) return
  const list = questions.value.split('\n').map((s) => s.trim()).filter(Boolean)
  if (!list.length) {
    error.value = '至少写一个问题'
    return
  }
  error.value = ''
  loading.value = true
  try {
    data.value = await postEvaluate(list)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <span class="step">⚖</span>
      <h2>对照实验</h2>
      <span class="tag">图谱 vs 纯大模型</span>
    </div>

    <p class="hint" style="margin-top: 0">
      同一批问题分别让「纯大模型」和「图谱增强」回答，再统计回答里出现的
      <b>图谱外药物 / 疾病名</b>（疑似编造）。每行一个问题，跑完约 1~2 分钟。
    </p>

    <textarea v-model="questions" rows="3" maxlength="1000"></textarea>

    <div class="actions">
      <button :disabled="loading" @click="run">
        <span v-if="loading" class="spinner"></span>
        {{ loading ? '实验中，约 1~2 分钟…' : '开始对照实验' }}
      </button>
      <button type="button" class="ghost" :disabled="loading" @click="questions = DEFAULT_Q">恢复默认问题</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="data">
      <h3>越界提及率对比</h3>
      <div class="vs">
        <div class="vs-card a">
          <div class="who">A · 纯大模型</div>
          <div class="big">{{ pct(data.summary.plain.illegal_rate) }}</div>
          <div class="muted">
            提及 {{ data.summary.plain.mentions }} 个，其中
            <b>{{ data.summary.plain.illegal }}</b> 个不在图谱内
          </div>
        </div>
        <div class="vs-mid">对比</div>
        <div class="vs-card b">
          <div class="who">B · 图谱增强</div>
          <div class="big">{{ pct(data.summary.graph.illegal_rate) }}</div>
          <div class="muted">
            提及 {{ data.summary.graph.mentions }} 个，其中
            <b>{{ data.summary.graph.illegal }}</b> 个不在图谱内
          </div>
        </div>
      </div>

      <p class="hint">
        <span class="badge ok">下降 {{ drop }}%</span>
        {{ data.note }}（白名单规模 {{ data.summary.whitelist_size }} 个实体）
      </p>

      <h3>逐题明细</h3>
      <div v-for="(q, i) in data.questions" :key="i" style="margin-bottom: 14px">
        <p style="margin: 6px 0; font-size: 13px"><b>Q{{ i + 1 }}：{{ q.question }}</b></p>
        <table>
          <thead>
            <tr>
              <th style="width: 104px">组别</th>
              <th style="width: 210px">图谱外提及</th>
              <th>回答（截断）</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span class="badge bad">A 纯大模型</span></td>
              <td>
                <span v-if="!q.plain.illegal.length" class="muted">无</span>
                <span v-for="t in q.plain.illegal.slice(0, 6)" :key="t" class="badge bad" style="margin: 0 4px 4px 0">{{ t }}</span>
                <span v-if="q.plain.illegal.length > 6" class="muted">+{{ q.plain.illegal.length - 6 }}</span>
              </td>
              <td class="muted">{{ q.plain.answer.slice(0, 110) }}…</td>
            </tr>
            <tr>
              <td><span class="badge ok">B 图谱增强</span></td>
              <td>
                <span v-if="!q.graph.illegal.length" class="muted">无</span>
                <span v-for="t in q.graph.illegal.slice(0, 6)" :key="t" class="badge warn" style="margin: 0 4px 4px 0">{{ t }}</span>
              </td>
              <td class="muted">{{ q.graph.answer.slice(0, 110) }}…</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>
