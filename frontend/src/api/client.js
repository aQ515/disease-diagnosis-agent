import axios from 'axios'

// 开发期 baseURL = /api（走 Vite 代理到 Django 8001），生产由 .env.production 指定
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 180000, // 大模型链路慢，给足 3 分钟
  headers: { 'Content-Type': 'application/json' },
})

// 统一把后端 {detail, hint} 转成 Error.message，前端只处理 err.message
client.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    const data = err.response && err.response.data
    const detail = (data && (data.detail || data.message)) || err.message || '请求失败'
    const stage = data && data.stage ? `（阶段：${data.stage}）` : ''
    return Promise.reject(new Error(detail + stage))
  }
)

// —— 基础接口（与参考项目一致）——
export const getHealth = () => client.get('/health/')
export const getGraphStats = () => client.get('/graph/stats/')
export const postRetrieve = (text) => client.post('/retrieve/', { text })
export const postDiagnose = (text, verbose = false) => client.post('/diagnose/', { text, verbose })
export const postChat = (text, sessionId) => client.post('/chat/', { text, session_id: sessionId })
export const postChatReset = (sessionId) => client.post('/chat/reset/', { session_id: sessionId })

// —— 自研接口（创新点）——
// 一跳子图：前端手绘 SVG 可视化
export const getSubgraph = (name) => client.get('/graph/subgraph/', { params: { name } })
// 症状词表：联想输入 + 口语归一校验
export const getSymptoms = () => client.get('/symptoms/')
// 双模式对照实验：纯大模型 vs 图谱增强
export const postEvaluate = (questions) => client.post('/evaluate/', { questions })

export default client
