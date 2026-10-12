<script setup>
/**
 * 多轮对话（带会话记忆）
 *
 * 与后端 agents/memory.py 的 MemoryManager 配合：session_id 相同即共用一份记忆，
 * 前端只负责展示，记忆托管在后端。
 */
import { nextTick, ref } from 'vue'
import { postChat, postChatReset } from '../api/client.js'

const log = ref([])
const text = ref('')
const loading = ref(false)
const error = ref('')
const sessionId = ref('web')
const logEl = ref(null)

async function scrollDown() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

async function send() {
  const q = text.value.trim()
  if (!q || loading.value) return
  error.value = ''
  log.value.push({ role: 'me', text: q })
  text.value = ''
  loading.value = true
  await scrollDown()
  try {
    const res = await postChat(q, sessionId.value)
    log.value.push({ role: 'bot', text: res.answer })
  } catch (e) {
    error.value = e.message
    log.value.push({ role: 'bot', text: `[出错] ${e.message}` })
  } finally {
    loading.value = false
    await scrollDown()
  }
}

async function reset() {
  try {
    await postChatReset(sessionId.value)
    log.value = []
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <span class="step">💬</span>
      <h2>多轮对话</h2>
      <span class="tag">会话记忆</span>
    </div>

    <div class="chat-log" ref="logEl">
      <div v-if="!log.length" class="empty">
        <span class="ico">🧠</span>
        这里验证「记忆」：先说「我最近老是口渴、尿多」，<br />
        再问「它可能是什么病」，看它能不能接上上文。
      </div>

      <div v-for="(m, i) in log" :key="i" class="msg-row" :class="m.role === 'me' ? 'me' : ''">
        <div class="avatar">{{ m.role === 'me' ? '我' : '医' }}</div>
        <div class="msg" :class="m.role === 'me' ? 'me' : 'bot'">{{ m.text }}</div>
      </div>

      <div v-if="loading" class="msg-row">
        <div class="avatar">医</div>
        <div class="msg bot dots"><span></span><span></span><span></span></div>
      </div>
    </div>

    <form @submit.prevent="send" class="actions" style="margin-top: 12px">
      <input
        class="text"
        v-model="text"
        placeholder="继续追问…（例如：那我要注意什么？）"
        style="flex: 1; min-width: 160px"
      />
      <button type="submit" :disabled="loading || !text.trim()">
        <span v-if="loading" class="spinner"></span>{{ loading ? '思考中' : '发送' }}
      </button>
      <button type="button" class="ghost" @click="reset">清空记忆</button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>
    <p class="hint">当前会话 ID：<code class="k">{{ sessionId }}</code> —— 记忆按会话隔离，换 ID 即换一份独立记忆。</p>
  </section>
</template>
