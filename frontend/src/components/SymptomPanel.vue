<script setup>
/**
 * 症状描述面板
 *
 * 创新点：症状联想输入 —— 输入框下方实时显示图谱里的症状词，
 * 点一下就追加到问题里；用户也能直观看到「图谱认识哪些症状」，
 * 避免自由文本写出图谱不认识的词导致检索空转。
 */
import { computed, onMounted, ref } from 'vue'
import { getSymptoms, postDiagnose, postRetrieve } from '../api/client.js'

const emit = defineEmits(['result', 'error', 'loading'])

const PRESETS = [
  { t: '我最近老是口渴、尿多，还瘦了，是不是糖尿病？', i: '🩸' },
  { t: '头晕、心悸、头痛，需要看什么科？', i: '💫' },
  { t: '消渴病患者平时应该注意什么？', i: '📘' },
  { t: '反复发热、咳嗽、咽痛怎么办？', i: '🤒' },
]

const text = ref('')
const loading = ref(false)
const loadingLabel = ref('处理中...')
const error = ref('')
const elapsed = ref('')
const vocab = ref([])
const expanded = ref(false)

const MAX = 500
const disabled = computed(() => loading.value || text.value.trim().length === 0)
const shownVocab = computed(() => (expanded.value ? vocab.value : vocab.value.slice(0, 8)))

onMounted(async () => {
  try {
    const res = await getSymptoms()
    vocab.value = res.symptoms || []
  } catch (e) {
    vocab.value = []
  }
})

function usePreset(item) {
  text.value = item.t
}

function appendSymptom(word) {
  const t = text.value.trim().replace(/[，,。]$/, '')
  if (t.includes(word)) return
  text.value = (t ? t + '、' : '') + word
}

async function run(task, label) {
  if (disabled.value) return
  loading.value = true
  loadingLabel.value = label
  error.value = ''
  emit('loading', true)
  const started = Date.now()
  try {
    emit('result', await task(text.value.trim()))
  } catch (err) {
    error.value = err.message
    emit('error', err.message)
  } finally {
    elapsed.value = ((Date.now() - started) / 1000).toFixed(1)
    loading.value = false
    emit('loading', false)
  }
}

const submitDiagnose = () => run((t) => postDiagnose(t), '诊断中...')
const submitRetrieve = () => run((t) => postRetrieve(t), '检索中...')
</script>

<template>
  <section class="card">
    <div class="card-head">
      <span class="step">1</span>
      <h2>描述症状</h2>
      <span class="tag">感知 + 检索</span>
    </div>

    <form @submit.prevent="submitDiagnose">
      <div class="field">
        <textarea
          data-test="input"
          v-model="text"
          :maxlength="MAX"
          placeholder="用日常语言描述即可，例如：我最近老是口渴、尿多，还瘦了"
        ></textarea>
        <span class="counter">{{ text.trim().length }}/{{ MAX }}</span>
      </div>

      <div class="presets">
        <button
          v-for="item in PRESETS"
          :key="item.t"
          type="button"
          class="preset"
          @click="usePreset(item)"
        >{{ item.i }} {{ item.t.length > 14 ? item.t.slice(0, 14) + '…' : item.t }}</button>
      </div>

      <div class="actions">
        <button type="submit" data-test="diagnose" :disabled="disabled">
          <span v-if="loading" class="spinner"></span>
          {{ loading ? loadingLabel : '开始诊断' }}
        </button>
        <button type="button" class="ghost" data-test="retrieve" :disabled="disabled" @click="submitRetrieve">
          只查图谱（秒级）
        </button>
        <span v-if="elapsed && !loading" class="muted">上次耗时 {{ elapsed }}s</span>
      </div>
    </form>

    <template v-if="vocab.length">
      <h3>图谱认识的症状 · 点击追加</h3>
      <div class="chips">
        <button
          v-for="s in shownVocab"
          :key="s"
          type="button"
          class="chip"
          @click="appendSymptom(s)"
        >{{ s }}</button>
        <button
          v-if="vocab.length > 8"
          type="button"
          class="chip"
          @click="expanded = !expanded"
        >{{ expanded ? '收起' : `+${vocab.length - 8}` }}</button>
      </div>
    </template>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading" class="hint">
      完整诊断会依次调用 感知 → 图谱检索 → 诊断 → 报告，通常 10~40 秒，请勿关闭页面。
    </p>
  </section>
</template>
