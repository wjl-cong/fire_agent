<script setup>
/**
 * Agent 协作中心 — 任务执行 + 链路可视化 + 报告展示
 *
 * 后端 API: POST /api/v1/agent/tasks  (body: { query: string })
 *          GET  /api/v1/agent/status
 *          GET  /api/v1/agent/tasks/{id}/stream?token=<JWT>  (SSE)
 *
 * 布局：sc-datav 空间逻辑 — 顶部通栏页头卡 + 340/1fr/340 三列网格
 */
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import authFetch from '@/utils/authFetch'
import renderMarkdown from '@/utils/markdown'
import { useAuthStore } from '@/stores/auth'
import { API_V1 } from '@/utils/config'
import { speakState, speakText, recordState, startRecord, cleanupSpeech } from '@/utils/speech'
import SystemCapabilities from '@/components/SystemCapabilities.vue'

const API_BASE = `${API_V1}/agent`
const auth = useAuthStore()

// 语音输入任务：识别完成自动执行
const handleMicClick = () => {
  if (recordState.recording) {
    startRecord() // 录音中再次调用 = 停止并识别
    return
  }
  startRecord((text) => {
    query.value = text
    handleExecute()
  })
}

// ====== 任务状态 ======
const query = ref('')
const running = ref(false)
const taskResult = ref(null)
const agentStatus = ref(null)
const activeStep = ref(-1)

// ====== HITL 审批状态（P1） ======
const currentTaskId = ref(null)
const approving = ref(false)
const approvalMode = ref('approve')       // approve | edit | reject
const approvalEditContent = ref('')       // edit 模式的编辑内容
const approvalComment = ref('')           // reject 模式的驳回意见

// 审批相关派生态：草稿/评审意见来自后端 approval 步骤行（output.draft_report）
const approvalStep = computed(() => (taskResult.value?.steps || []).find(s => s.step === 'approval'))
const showApproval = computed(() => taskResult.value?.status === 'awaiting_approval' && !!approvalStep.value)
const draftReport = computed(() => approvalStep.value?.output?.draft_report || '')
const approvalReview = computed(() => approvalStep.value?.output?.review || {})

// ====== 报告流式渲染（SSE report_delta 打字机）======
// 通道易失：断线不重放历史 delta，终态完整内容以 DB 为准（report 事件兜底）
const streamReport = ref('')       // 增量累积缓冲区
const streamRun = ref(0)           // 报告生成轮次（评审退回/驳回重写时后端递增，前端据此清缓冲）
const streamActive = ref(false)    // 是否处于流式生成中（收到 delta 才点亮，终态后关闭）
const streamBodyRef = ref(null)    // 流式正文容器（自动滚动到底部）
const showStreamReport = computed(() => streamActive.value && !!streamReport.value)

// 流式正文自动滚动到底部
const scrollStreamToEnd = () => {
  nextTick(() => {
    const el = streamBodyRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

// ====== 步骤状态映射（key → status，驱动流水线 skipped/failed 展示） ======
const stepStatusMap = computed(() => {
  const m = {}
  for (const st of (taskResult.value?.steps || [])) {
    if (st && st.step) m[st.step] = st.status || 'completed'
  }
  return m
})

// ====== 任务历史 ======
const taskHistory = ref([])

// 任务历史持久化（localStorage，按用户隔离，避免多账号同浏览器串数据）
const HISTORY_KEY = () => `agent_task_history_${(auth.user && auth.user.username) || 'guest'}`
const loadHistory = () => {
  try {
    taskHistory.value = JSON.parse(localStorage.getItem(HISTORY_KEY()) || '[]')
  } catch {
    taskHistory.value = []
  }
}
const saveHistory = () => {
  try {
    localStorage.setItem(HISTORY_KEY(), JSON.stringify(taskHistory.value.slice(0, 50)))
  } catch {
    /* 忽略 */
  }
}
loadHistory()

// ====== 6 步流水线定义（P1：+质量评审；skipped/failed 由后端步骤状态驱动） ======
const pipelineSteps = [
  { key: 'parse_task', label: '拆解任务', agent: 'Orchestrator', icon: '→' },
  { key: 'query_data', label: '查询数据', agent: 'DataAgent', icon: '→' },
  { key: 'analyze_gis', label: '分析 GIS', agent: 'GisAgent', icon: '→' },
  { key: 'retrieve_knowledge', label: '检索知识', agent: 'RagAgent', icon: '→' },
  { key: 'generate_report', label: '生成报告', agent: 'ReportAgent', icon: '→' },
  { key: 'review_report', label: '质量评审', agent: 'Reviewer', icon: '→' },
]

// ====== 示例任务 ======
const exampleTasks = [
  '分析2026年4月云南高风险区域，给出重点巡防建议并输出报告',
  '查询普洱市2025年历史火点情况',
  '2026年春季哪些州市风险最高？',
  '近3年高置信度火点最多的5个州市是哪些？',
]

// ====== 获取 Agent 状态 ======
const fetchAgentStatus = async () => {
  try {
    const res = await authFetch(`${API_BASE}/status`)
    const json = await res.json()
    if (json.code === 200) {
      agentStatus.value = json.data
    }
  } catch {
    // 静默
  }
}

// ====== 执行任务（SSE 真实进度） ======
let eventSource = null

const finishRun = () => {
  running.value = false
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

// 历史入列（SSE report 事件与断线兜底共用；流式增量不写入历史）
const pushHistoryItem = (d, q) => {
  taskHistory.value.unshift({
    id: d.id || Date.now(),
    reportId: d.report_id || null,
    query: q,
    status: d.status,
    llm_used: !!d.llm_used,
    llm_provider: d.llm_provider || null,
    llm_model: d.llm_model || null,
    time: d.created_at || new Date().toLocaleString(),
    result: {
      status: d.status,
      steps: d.steps || [],
      report: d.report || '',
      llm_used: !!d.llm_used,
      llm_provider: d.llm_provider || null,
      llm_model: d.llm_model || null,
    },
  })
  saveHistory()
}

// SSE 断开后的兜底：直接查任务详情（任务可能仍在后台执行/待审批/已完成）
const loadTaskDetailFallback = async (taskId, q) => {
  try {
    const res = await authFetch(`${API_BASE}/tasks/${taskId}`)
    const json = await res.json()
    if (json.code === 200 && json.data) {
      const d = json.data
      if (d.status === 'running') {
        ElMessage.info('连接中断，任务仍在后台执行，可稍后在历史记录中查看结果')
        return
      }
      activeStep.value = pipelineSteps.length
      currentTaskId.value = taskId
      taskResult.value = {
        status: d.status,
        steps: d.steps || [],
        report: d.report || '',
        llm_used: !!d.llm_used,
      }
      if (d.status === 'awaiting_approval') {
        approvalEditContent.value = draftReport.value
        approvalMode.value = 'approve'
        ElMessage.warning('报告已生成，等待人工审批')
        return
      }
      pushHistoryItem(d, q)
      if (d.status === 'failed') ElMessage.error('任务执行失败')
      else ElMessage.success('任务执行完成')
    }
  } catch {
    /* 静默 */
  }
}

// SSE 订阅（创建任务与审批恢复共用）：真实节点进度 + 审批事件 + 终态报告
const subscribeSse = (taskId, q) => {
  const es = new EventSource(`${API_BASE}/tasks/${taskId}/stream?token=${encodeURIComponent(auth.token || '')}`)
  eventSource = es

  es.onmessage = (ev) => {
    let payload
    try { payload = JSON.parse(ev.data) } catch { return } // ': ping' 注释帧不进 onmessage，非 JSON data 帧静默丢弃

    if (payload.type === 'step') {
      // 三态：running=节点真正开始（转圈）；终态完成 → 推进到下一步
      const st = payload.step || {}
      const idx = pipelineSteps.findIndex(s => s.key === st.step)
      if (idx >= 0) {
        const status = st.status || 'completed'
        if (status === 'running' || status === 'awaiting') {
          activeStep.value = Math.max(activeStep.value, idx)
        } else if (status !== 'failed') {
          activeStep.value = Math.max(activeStep.value, idx + 1)
        }
      }
    } else if (payload.type === 'report_delta') {
      // 报告增量打字机；run 轮次变化（评审退回/驳回重写）时清空缓冲重新累积
      if (payload.run !== streamRun.value) {
        streamRun.value = payload.run
        streamReport.value = ''
      }
      streamReport.value += payload.text || ''
      streamActive.value = true
      scrollStreamToEnd()
    } else if (payload.type === 'approval') {
      // HITL：任务在审批闸口暂停（草稿在 approval 步骤的 draft_report 中，未落报告中心）
      const d = payload.data || {}
      activeStep.value = pipelineSteps.length
      currentTaskId.value = d.id || taskId
      taskResult.value = {
        status: d.status || 'awaiting_approval',
        steps: d.steps || [],
        report: d.report || '',
        llm_used: !!d.llm_used,
      }
      streamReport.value = draftReport.value  // 用审批草稿替换流式缓冲
      streamActive.value = false
      approvalMode.value = 'approve'
      approvalEditContent.value = draftReport.value
      ElMessage.warning('报告已生成，等待人工审批')
      finishRun()
    } else if (payload.type === 'report') {
      // 终态（completed/failed）：完整报告以 DB 内容为准，替换流式缓冲
      const d = payload.data || {}
      streamReport.value = d.report || ''
      streamActive.value = false
      activeStep.value = pipelineSteps.length
      taskResult.value = {
        status: d.status,
        steps: d.steps || [],
        report: d.report || '',
        llm_used: !!d.llm_used,
      }
      pushHistoryItem(d, q)
      if (d.status === 'failed') ElMessage.error('任务执行失败')
      else ElMessage.success('任务执行完成')
      finishRun()
    } else if (payload.type === 'error') {
      ElMessage.error(payload.message || '进度推送异常')
      streamActive.value = false
      finishRun()
      syncHistoryFromApi()
    }
  }
  es.onerror = () => {
    streamActive.value = false
    finishRun()
    loadTaskDetailFallback(taskId, q)
  }
}

const handleExecute = async () => {
  const q = query.value.trim()
  if (!q) {
    ElMessage.warning('请输入分析任务')
    return
  }

  running.value = true
  taskResult.value = null
  activeStep.value = -1
  approvalMode.value = 'approve'
  approvalComment.value = ''
  streamReport.value = ''
  streamRun.value = 0
  streamActive.value = false

  try {
    // 1) 创建任务：后端立即返回 task_id，LangGraph 工作流在后台执行
    const res = await authFetch(`${API_BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q }),
    })
    const json = await res.json()
    if (json.code !== 200 || !json.data || !json.data.task_id) {
      ElMessage.error('创建任务失败: ' + (json.message || '未知错误'))
      finishRun()
      return
    }
    const taskId = json.data.task_id
    currentTaskId.value = taskId

    // 2) SSE 订阅真实节点进度（EventSource 无法携带 Authorization，token 走查询参数）
    subscribeSse(taskId, q)
  } catch (e) {
    ElMessage.error('网络错误: ' + e.message)
    finishRun()
  }
}

// ====== HITL 审批提交（approve / edit / reject），成功后重新订阅 SSE 续收进度 ======
const handleResume = async (action) => {
  if (!currentTaskId.value) return
  if (action === 'edit' && !approvalEditContent.value.trim()) {
    ElMessage.warning('请输入修改后的报告内容')
    return
  }
  if (action === 'reject' && !approvalComment.value.trim()) {
    ElMessage.warning('请填写驳回意见')
    return
  }
  approving.value = true
  try {
    const res = await authFetch(`${API_BASE}/tasks/${currentTaskId.value}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, content: approvalEditContent.value, comment: approvalComment.value }),
    })
    const json = await res.json()
    if (json.code !== 200) {
      ElMessage.error(json.detail || json.message || '提交审批失败')
      return
    }
    ElMessage.success(action === 'reject' ? '已驳回，报告将按意见重写' : '审批已提交，任务继续执行')
    approvalComment.value = ''
    running.value = true
    activeStep.value = pipelineSteps.length - 1
    streamActive.value = false  // 续订后由新轮次的 report_delta 重新点亮
    // 重新订阅 SSE：reject 时收重写进度与再次审批事件；approve/edit 时收终态报告
    subscribeSse(currentTaskId.value, query.value.trim())
  } catch (e) {
    ElMessage.error('网络错误: ' + e.message)
  } finally {
    approving.value = false
  }
}

// ====== 加载历史任务 ======
const loadHistoryTask = async (item) => {
  query.value = item.query
  activeStep.value = pipelineSteps.length
  currentTaskId.value = item.id
  approvalMode.value = 'approve'
  approvalComment.value = ''
  if (item.result) {
    taskResult.value = item.result
    if (item.result.status === 'awaiting_approval') {
      approvalEditContent.value = draftReport.value
    }
    return
  }
  // 本地无缓存结果 → 从后端拉取任务详情（执行步骤持久化于 agent_task_steps 表）
  try {
    const res = await authFetch(`${API_BASE}/tasks/${item.id}`)
    const json = await res.json()
    if (json.code === 200 && json.data) {
      const d = json.data
      if ((d.steps && d.steps.length) || d.report) {
        taskResult.value = {
          status: d.status,
          steps: d.steps || [],
          report: d.report || '',
          llm_used: !!d.llm_used,
        }
        if (d.status === 'awaiting_approval') {
          approvalEditContent.value = draftReport.value
          ElMessage.warning('该任务报告待审批，可在右侧完成审批')
        }
        return
      }
    }
  } catch {
    /* 静默，走报告兜底 */
  }
  // 兜底：从报告中心拉取该任务生成的报告
  if (item.reportId) {
    try {
      const res = await authFetch(`${API_V1}/reports/${item.reportId}`)
      const json = await res.json()
      if (json.code === 200) {
        taskResult.value = {
          status: item.status,
          steps: [],
          report: json.data.content || '',
          llm_used: (json.data.tags || []).includes('LLM'),
        }
        return
      }
    } catch {
      /* 静默 */
    }
  }
  taskResult.value = null
}

// ====== 删除历史任务（后端数据库 + 本地缓存） ======
const deleteHistoryItem = async (item) => {
  try {
    const res = await authFetch(`${API_BASE}/tasks/${item.id}`, { method: 'DELETE' })
    await res.json() // 404（旧本地记录无对应库记录）时也继续删除本地
  } catch {
    /* 网络异常仍删除本地 */
  }
  taskHistory.value = taskHistory.value.filter(t => t.id !== item.id)
  saveHistory()
}

// ====== 从后端数据库同步任务历史（按用户隔离） ======
const syncHistoryFromApi = async () => {
  try {
    const res = await authFetch(`${API_BASE}/tasks`)
    const json = await res.json()
    if (json.code === 200 && Array.isArray(json.data)) {
      const local = taskHistory.value
      taskHistory.value = json.data.map(t => {
        // 同一查询且同一天执行的本地记录保留完整结果（含步骤）
        const match = local.find(l => l.query === t.query && t.created_at && l.time && l.time.startsWith(t.created_at.slice(0, 10)))
        return {
          id: t.id,
          query: t.query,
          status: t.status,
          llm_used: match ? match.llm_used : !!t.llm_provider,
          llm_provider: t.llm_provider || (match ? match.llm_provider : null),
          llm_model: t.llm_model || (match ? match.llm_model : null),
          time: t.created_at || '',
          result: match ? match.result : null,
          reportId: t.report_id || null,
        }
      })
    }
  } catch {
    /* 静默 */
  }
}

// ====== 快捷键 ======
const handleKeydown = (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    handleExecute()
  }
}

// ====== 获取步骤状态（pending→running→completed 三态；skipped/failed 由后端步骤真实状态驱动） ======
const getStepStatus = (index) => {
  const key = pipelineSteps[index] && pipelineSteps[index].key
  const st = stepStatusMap.value[key]
  if (st) {
    if (st === 'skipped') return 'skipped'
    if (st === 'failed') return 'failed'
    if (st === 'running' || st === 'awaiting') return 'running'
    return 'completed'
  }
  if (running.value) {
    if (index < activeStep.value) return 'completed'
    if (index === activeStep.value) return 'running'
  }
  return 'pending'
}

// ====== 历史状态展示辅助（completed ✓ / awaiting ⏳ / failed ✗） ======
const historyStatusClass = (s) => (s === 'completed' ? 'ok' : (s === 'failed' ? 'fail' : 'wait'))
const historyStatusText = (s) => (s === 'completed' ? '✓' : (s === 'failed' ? '✗' : '⏳'))

// ====== 报告状态展示辅助 ======
const reportStatusClass = (s) => (s === 'completed' ? 'ok' : (s === 'awaiting_approval' ? 'wait' : (s === 'running' ? 'run' : 'fail')))
const reportStatusText = (s) => (s === 'completed' ? '完成' : (s === 'awaiting_approval' ? '待审批' : (s === 'running' ? '执行中' : '失败')))

// ====== 步骤审计 chips（从 step.output 提取，紧凑标签展示） ======
// LLM 供应商友好名映射
const PROVIDER_NAMES = { aliyun: '阿里百炼', amd: 'AMD GPU Cloud', ollama: '本地 Ollama' }
const providerName = (p) => PROVIDER_NAMES[p] || p || ''
// token 数紧凑格式：1234 → 1.2k
const fmtTokens = (n) => (typeof n === 'number' && isFinite(n) ? (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)) : '')

const stepChips = (st) => {
  const o = st && st.output
  if (!o || typeof o !== 'object') return []
  const chips = []
  // LLM 模型名（优先）+ 供应商 + token 用量（parse_task / generate_report 等）
  const pName = o.llm_model || providerName(o.llm_provider)
  const tok = o.tokens && o.tokens.total_tokens
  const tokText = tok != null ? `${fmtTokens(tok)} tokens` : ''
  if (pName || tokText) chips.push({ cls: 'llm', text: [pName, tokText].filter(Boolean).join(' · ') })
  // LLM 降级
  if (o.llm_degraded === true) chips.push({ cls: 'warn', text: '降级' })
  // 数据查询：参数重试 / 无数据 / 命中总量 / 首城
  if (Array.isArray(o.attempts) && o.attempts.length > 1) chips.push({ cls: '', text: `重试 ${o.attempts.length} 次` })
  if (o.empty_reason) chips.push({ cls: 'warn', text: '无数据', tip: String(o.empty_reason) })
  if ('total' in o) chips.push({ cls: '', text: `查询 ${o.total} 条` })
  if (o.first_city) chips.push({ cls: '', text: `首城 ${o.first_city}` })
  // GIS：跳过 / 热点数
  if (o.skipped === true) chips.push({ cls: 'warn', text: '已跳过' })
  if ('total_hotspots' in o) chips.push({ cls: '', text: `热点 ${o.total_hotspots} 个` })
  // RAG：命中段数 + 检索方式
  if ('matched' in o) {
    const m = [o.matched != null ? `命中 ${o.matched} 段` : '', o.method || ''].filter(Boolean).join(' · ')
    if (m) chips.push({ cls: '', text: m })
  }
  // 报告长度
  if ('report_length' in o) chips.push({ cls: '', text: `${o.report_length} 字符` })
  // 计划步数
  if (Array.isArray(o.plan)) chips.push({ cls: '', text: `计划 ${o.plan.length} 步` })
  // 质量评审：通过 / 强制放行 / 退回 + 问题数
  const forced = o.forced === true || (o.review_result && o.review_result.forced === true)
  if (typeof o.passed === 'boolean') {
    if (o.passed) chips.push({ cls: 'ok', text: '评审通过' })
    else if (forced) chips.push({ cls: 'warn', text: '强制放行' })
    else chips.push({ cls: 'danger', text: '评审退回' })
  }
  if (Array.isArray(o.issues) && o.issues.length) {
    chips.push({ cls: 'warn', text: `${o.issues.length} 项问题`, tip: o.issues.join('；') })
  }
  // 错误
  if (o.error) chips.push({ cls: 'danger', text: '错误', tip: String(o.error) })
  return chips
}

// ====== 初始化 ======
onMounted(() => {
  fetchAgentStatus()
  syncHistoryFromApi()
})
onUnmounted(() => {
  finishRun() // 关闭 SSE 连接
  cleanupSpeech() // 停止语音播报/录音
})
</script>

<template>
  <div class="agent-shell">
    <!-- 氛围暗角层（极淡 radial，双主题通用） -->
    <div class="agent-vignette" aria-hidden="true"></div>

    <!-- 顶部通栏页头卡（sc-datav TitleWrapper 同构：左标题 / 右关键操作） -->
    <header class="panel-card agent-header">
      <div class="header-left">
        <h1 class="agent-title">Agent 协作中心</h1>
        <p class="agent-subtitle">多 Agent 协同：拆解任务 → 查询数据 → GIS 分析 → 知识检索 → 生成报告</p>
        <p class="agent-subtitle-en">Multi-Agent Orchestration · LangGraph Pipeline</p>
      </div>
      <div class="header-actions">
        <el-button
          type="primary"
          :loading="running"
          class="agent-go-btn"
          @click="handleExecute"
        >开始分析</el-button>
        <el-button
          :type="recordState.recording ? 'danger' : 'default'"
          :title="recordState.recording ? '停止录音并识别' : '语音输入任务'"
          class="agent-mic-btn"
          @click="handleMicClick"
        >{{ recordState.recording ? '■ 停止' : '🎤' }}</el-button>
      </div>
    </header>

    <!-- 主区三列网格：左（发起任务+历史） / 中（执行过程+报告） / 右（审批+系统能力） -->
    <div class="agent-grid">
      <!-- 左列 -->
      <div class="agent-col col-left">
        <section class="panel-card task-form-card">
          <div class="panel-card-title">发起任务</div>
          <div class="panel-card-body">
            <el-input
              v-model="query"
              type="textarea"
              :rows="4"
              placeholder="请描述需要分析的问题..."
              class="agent-input"
              @keydown="handleKeydown"
            />
            <div class="input-examples">
              <span class="input-example-label">示例：</span>
              <span
                v-for="(ex, i) in exampleTasks"
                :key="i"
                class="input-example-tag"
                @click="query = ex"
              >{{ ex }}</span>
            </div>
            <div class="input-hint">Ctrl+Enter 快速执行</div>
          </div>
        </section>

        <section class="panel-card history-card">
          <div class="panel-card-title">
            任务历史
            <span class="title-spacer"></span>
            <span class="history-count">{{ taskHistory.length }}</span>
          </div>
          <div class="history-list">
            <div v-if="taskHistory.length === 0" class="history-empty">
              暂无任务记录
            </div>
            <div
              v-for="item in taskHistory"
              :key="item.id"
              class="history-item"
              @click="loadHistoryTask(item)"
            >
              <div class="history-item-top">
                <span
                  class="history-status"
                  :class="historyStatusClass(item.status)"
                >{{ historyStatusText(item.status) }}</span>
                <!-- 生成模型徽标：优先显示详细模型名（如 qwen-max），无模型名时回退供应商名 -->
                <span
                  class="history-llm-badge model"
                  v-if="item.llm_model || item.llm_provider"
                  :title="'生成模型：' + (item.llm_model || providerName(item.llm_provider))"
                >{{ item.llm_model || providerName(item.llm_provider) }}</span>
                <span
                  class="history-llm-badge tpl"
                  v-else-if="item.status === 'completed' && !item.llm_used"
                  title="模板生成（无 LLM 参与）"
                >模板</span>
                <span class="history-llm-badge" v-else-if="item.llm_used">LLM</span>
                <button
                  class="history-delete"
                  title="删除"
                  @click.stop="deleteHistoryItem(item)"
                >×</button>
              </div>
              <div class="history-query">{{ item.query }}</div>
              <div class="history-time">{{ item.time }}</div>
            </div>
          </div>
        </section>
      </div>

      <!-- 中列 -->
      <div class="agent-col col-center">
        <section v-if="agentStatus" class="panel-card status-card">
          <div class="panel-card-title">Agent 状态<span class="title-en">Agent Status</span></div>
          <div class="panel-card-body agent-system-status">
            <span
              v-for="a in agentStatus.agents"
              :key="a.name"
              class="sys-status-item"
            >
              <span class="sys-status-dot ready"></span>
              {{ a.name }}
              <span class="sys-status-framework">{{ a.framework }}</span>
            </span>
          </div>
        </section>

        <section class="panel-card pipeline-card">
          <div class="panel-card-title">执行链路</div>
          <div class="panel-card-body">
            <div class="pipeline-flow">
              <div
                v-for="(step, i) in pipelineSteps"
                :key="step.key"
                class="pipeline-step"
                :class="getStepStatus(i)"
              >
                <div class="step-node">
                  <div class="step-icon">
                    <span v-if="getStepStatus(i) === 'completed'">✓</span>
                    <span v-else-if="getStepStatus(i) === 'skipped'">⤼</span>
                    <span v-else-if="getStepStatus(i) === 'failed'">✗</span>
                    <span v-else-if="getStepStatus(i) === 'running'">⟳</span>
                    <span v-else>{{ step.icon }}</span>
                  </div>
                </div>
                <div class="step-label">{{ step.label }}</div>
                <div class="step-agent">{{ step.agent }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- Agent 执行过程（每步审计 chips） -->
        <section v-if="taskResult" class="panel-card steps-card">
          <div class="panel-card-title">Agent 执行过程</div>
          <div class="steps-summary-grid">
            <div
              v-for="(st, i) in taskResult.steps"
              :key="i"
              class="steps-summary-item"
              :class="st.status === 'completed' ? 'ok' : (st.status === 'skipped' ? 'skip' : 'fail')"
            >
              <div class="ssi-head">
                <span class="ssi-agent">{{ st.agent }}</span>
                <span class="ssi-step">{{ st.step }}</span>
                <span class="ssi-status">{{ st.status === 'completed' ? '✓' : (st.status === 'skipped' ? '⤼' : '✗') }}</span>
              </div>
              <div class="ssi-summary">{{ st.summary || '—' }}</div>
              <div v-if="stepChips(st).length" class="ssi-chips">
                <span
                  v-for="(c, ci) in stepChips(st)"
                  :key="ci"
                  class="ssi-chip"
                  :class="c.cls"
                  :title="c.tip || ''"
                >{{ c.text }}</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 报告正文（实时生成中）：SSE report_delta 打字机，通道易失故无 delta 不显示 -->
        <section v-if="showStreamReport" class="panel-card stream-card">
          <div class="panel-card-title">
            报告正文（实时生成中）
            <span class="title-spacer"></span>
            <span class="stream-badge">● 生成中</span>
          </div>
          <pre ref="streamBodyRef" class="stream-body">{{ streamReport }}<span class="stream-cursor">▍</span></pre>
        </section>

        <!-- 报告展示（待审批时隐藏报告区，避免与审批卡草稿混淆） -->
        <section v-if="taskResult && taskResult.status !== 'awaiting_approval'" class="panel-card agent-report">
          <div class="panel-card-title report-title-bar">
            <span class="report-badge">分析报告</span>
            <span v-if="taskResult.llm_used" class="report-llm-badge">LLM 生成</span>
            <span v-else class="report-fallback-badge">模板报告</span>
            <span class="title-spacer"></span>
            <el-button
              size="small"
              :loading="speakState.loading"
              :type="speakState.speaking || speakState.loading ? 'danger' : 'default'"
              plain
              title="语音播报分析报告"
              @click="speakText(taskResult.report)"
            >{{ speakState.speaking || speakState.loading ? '停止' : '🔊 播报' }}</el-button>
            <span class="report-status-label">状态:</span>
            <span class="report-status" :class="reportStatusClass(taskResult.status)">
              {{ reportStatusText(taskResult.status) }}
            </span>
          </div>
          <div class="report-content markdown-body" v-html="renderMarkdown(taskResult.report)" />
        </section>

        <!-- 空状态 -->
        <section v-if="!taskResult && !showStreamReport" class="panel-card agent-empty">
          <div class="agent-empty-icon">⚙</div>
          <p class="agent-empty-text">输入分析任务，系统将自动执行</p>
          <p class="agent-empty-desc">编排 Agent 拆解任务 → 数据 Agent 查询 → GIS Agent 分析 → RAG Agent 检索 → 报告 Agent 生成</p>
        </section>
      </div>

      <!-- 右列：审批卡 + 系统能力 -->
      <div class="agent-col col-right">
        <section v-if="showApproval" class="panel-card title-warn approval-card">
          <div class="panel-card-title">
            <span class="approval-badge">人工审批</span>
            <span class="title-en">Approval</span>
            <span class="approval-title">报告草稿已生成，请审批后定稿</span>
            <span
              v-if="approvalStep.output && approvalStep.output.revisions > 0"
              class="approval-round"
            >第 {{ approvalStep.output.revisions }} 轮修订</span>
          </div>
          <div class="approval-body">
            <div v-if="approvalReview.issues && approvalReview.issues.length" class="approval-review">
              <span class="approval-review-label">评审意见：</span>{{ approvalReview.issues.join('；') }}
            </div>
            <div class="approval-mode">
              <el-radio-group v-model="approvalMode" size="small">
                <el-radio-button value="approve">通过</el-radio-button>
                <el-radio-button value="edit">编辑后通过</el-radio-button>
                <el-radio-button value="reject">驳回重写</el-radio-button>
              </el-radio-group>
            </div>
            <div v-if="approvalMode === 'approve'" class="approval-draft markdown-body" v-html="renderMarkdown(draftReport)" />
            <el-input
              v-else-if="approvalMode === 'edit'"
              v-model="approvalEditContent"
              type="textarea"
              :rows="10"
              class="approval-edit"
              placeholder="可直接编辑报告内容，提交后以编辑稿定稿"
            />
            <el-input
              v-else
              v-model="approvalComment"
              type="textarea"
              :rows="3"
              class="approval-comment"
              placeholder="请填写驳回意见（将作为重写要求，例如：补充玉溪市数据、巡防建议要具体到路段）"
            />
            <div class="approval-actions">
              <el-button
                type="primary"
                size="small"
                :loading="approving"
                @click="handleResume(approvalMode)"
              >{{ approvalMode === 'reject' ? '提交驳回' : (approvalMode === 'edit' ? '以编辑稿定稿' : '通过并定稿') }}</el-button>
            </div>
          </div>
        </section>

        <!-- 系统能力面板（P0/P1/P2 能力一览，自包含组件，默认展开） -->
        <SystemCapabilities />
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
  background: var(--gis-atmo-bg);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}

/* 氛围暗角：中心透明 → 边缘极淡染色，深浅主题均可读 */
.agent-vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(ellipse 90% 70% at 50% -10%, transparent 60%, rgba(15, 23, 42, 0.05) 100%);
  z-index: 0;
}

/* ====== 统一卡片（sc-datav 卡片同构：玻璃底 + 标题条） ====== */
.panel-card {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--gis-glass);
  backdrop-filter: blur(var(--gis-glass-blur)) saturate(var(--gis-glass-saturate));
  border: 1px solid var(--gis-glass-border);
  box-shadow: inset 0 1px 0 var(--gis-glass-highlight);
  border-radius: var(--gis-radius-md, 10px);
  overflow: hidden;
  animation: card-in 0.35s ease both;
}

@keyframes card-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

.panel-card-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--gis-border, #334155);
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

.panel-card-title::before {
  content: '';
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--gis-accent, #0ea5e9);
  box-shadow: var(--gis-glow);
  flex-shrink: 0;
}

.panel-card.title-warn .panel-card-title::before {
  background: #facc15;
  box-shadow: none;
}

.panel-card-body {
  padding: 12px 16px;
}

.title-spacer {
  flex: 1;
}

/* ====== 顶部通栏页头 ====== */
.agent-header {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 64px;
  padding: 10px 20px;
  flex-shrink: 0;
  margin-bottom: 20px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.agent-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.02em;
  text-shadow: var(--gis-text-glow);
}

.agent-subtitle {
  margin: 0;
  font-size: 11px;
  color: var(--gis-text-muted, #94a3b8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* sc-datav 横幅签名：标题下英文小字角标 */
.agent-subtitle-en {
  margin: 0;
  font-size: 9px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--gis-accent, #0ea5e9);
  opacity: 0.75;
  font-family: ui-monospace, "Consolas", monospace;
}

/* 卡片标题英文角标（sc-datav CardTitle 右缀英文） */
.title-en {
  font-size: 9px;
  font-weight: 400;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--gis-text-muted, #94a3b8);
  opacity: 0.85;
  font-family: ui-monospace, "Consolas", monospace;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.agent-go-btn {
  min-width: 110px;
  height: 36px;
  background: var(--gis-metal-accent) !important;
  border: none !important;
  color: var(--gis-on-accent) !important;
  font-weight: 600;
  letter-spacing: 0.04em;
  font-size: 14px;
  transition: filter 0.15s, box-shadow 0.15s;
}

.agent-go-btn:hover {
  filter: brightness(1.1) !important;
  box-shadow: var(--gis-glow-strong) !important;
}

.agent-mic-btn {
  height: 36px;
  min-width: 60px;
  font-size: 15px;
}

.agent-mic-btn.is-danger {
  animation: agent-mic-pulse 1.2s ease-in-out infinite;
}

@keyframes agent-mic-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

/* ====== 主区三列网格（340 / 1fr / 340，gap 20） ====== */
/* SystemCapabilities 根卡片填满右列剩余高度（内容超高时卡片内滚动），消除下方空白 */
.col-right > :deep(.cap-card) {
  flex: 1 1 auto;
  min-height: 280px;
}

.agent-grid {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr) minmax(280px, 340px);
  gap: 20px;
}

.agent-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
  min-width: 0;
  overflow-y: auto;
}

/* 窄屏降级：右列并入整行，再窄改单列 */
@media (max-width: 1440px) {
  .agent-grid {
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
  }
  .col-right {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    align-items: start;
    overflow: visible;
  }
}

@media (max-width: 960px) {
  .agent-grid {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }
  .agent-col {
    overflow: visible;
  }
}

/* ====== 左列：发起任务 ====== */
.task-form-card {
  flex-shrink: 0;
}

.agent-input :deep(.el-textarea__inner) {
  background: var(--gis-bg-deep) !important;
  color: var(--gis-text, #f8fafc) !important;
  border: 1px solid var(--gis-border, #334155) !important;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}

.agent-input :deep(.el-textarea__inner:focus) {
  border-color: var(--gis-accent, #0ea5e9) !important;
  box-shadow: 0 0 0 2px var(--gis-accent-soft) !important;
}

.input-examples {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.input-example-label {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  flex-shrink: 0;
  line-height: 22px;
}

.input-example-tag {
  font-size: 11px;
  line-height: 20px;
  padding: 0 10px;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-hover-tint);
  border: 1px solid var(--gis-accent-dim);
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.input-example-tag:hover {
  background: var(--gis-accent-dim);
}

.input-hint {
  margin-top: 8px;
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  font-family: ui-monospace, "Consolas", monospace;
}

/* ====== 左列：任务历史 ====== */
.history-card {
  flex: 1;
}

.history-count {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 7px;
  background: var(--gis-accent, #0ea5e9);
  color: var(--gis-on-accent);
  border-radius: 8px;
  font-weight: 700;
}

.history-list {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  padding: 8px;
}

.history-empty {
  padding: 30px 0;
  text-align: center;
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
}

.history-item {
  position: relative;
  padding: 8px 10px;
  border-radius: 6px;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.history-item:hover {
  background: var(--gis-hover-tint);
}

.history-item-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}

.history-status {
  font-size: 10px;
  font-weight: 700;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}

.history-status.ok {
  color: var(--el-color-success, #4ade80);
  background: rgba(74, 222, 128, 0.1);
}

.history-status.fail {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.history-status.wait {
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.1);
}

.history-llm-badge {
  font-size: 8px;
  padding: 0 4px;
  background: rgba(74, 222, 128, 0.15);
  color: var(--el-color-success, #4ade80);
  border-radius: 2px;
  border: 1px solid rgba(74, 222, 128, 0.3);
}

/* 生成模型徽标：强调色芯片；模板生成用警示色 */
.history-llm-badge.model {
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft, rgba(14, 165, 233, 0.12));
  border-color: var(--gis-accent-dim, rgba(14, 165, 233, 0.35));
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-llm-badge.tpl {
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.12);
  border-color: rgba(250, 204, 21, 0.3);
}

.history-query {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 18px;
}

.history-time {
  font-size: 9px;
  color: var(--gis-text-muted, #64748b);
  margin-top: 2px;
  font-family: ui-monospace, "Consolas", monospace;
}

.history-delete {
  position: absolute;
  right: 4px;
  top: 4px;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--gis-text-muted, #64748b);
  background: transparent;
  border: none;
  border-radius: 2px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.history-delete:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

/* ====== 中列：Agent 状态 ====== */
.status-card {
  flex-shrink: 0;
}

.agent-system-status {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sys-status-item {
  font-size: 10px;
  color: var(--gis-text, #f8fafc);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--gis-glass-2);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 8px;
}

.sys-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sys-status-dot.ready {
  background: #4ade80;
  box-shadow: 0 0 4px rgba(74, 222, 128, 0.5);
}

.sys-status-framework {
  font-size: 8px;
  color: var(--gis-text-muted, #64748b);
  margin-left: 2px;
}

/* ====== 中列：执行链路 ====== */
.pipeline-card {
  flex-shrink: 0;
}

.pipeline-flow {
  display: flex;
  align-items: flex-start;
  gap: 0;
}

.pipeline-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  position: relative;
  min-width: 0;
}

.pipeline-step::after {
  content: '';
  position: absolute;
  top: 16px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: var(--gis-border, #334155);
  z-index: 0;
}

.pipeline-step:last-child::after {
  display: none;
}

.pipeline-step.completed::after {
  background: #4ade80;
}

.pipeline-step.running::after {
  background: linear-gradient(90deg, #4ade80, #facc15);
}

.pipeline-step.skipped .step-icon {
  background: var(--gis-glass-2);
  color: var(--gis-text-muted, #94a3b8);
  border: 2px dashed var(--gis-text-muted, #64748b);
}

.pipeline-step.failed .step-icon {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 2px solid #ef4444;
}

.step-node {
  position: relative;
  z-index: 1;
  margin-bottom: 6px;
}

.step-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  transition: all 0.3s;
}

.pipeline-step.pending .step-icon {
  background: var(--gis-glass-2);
  color: var(--gis-text-muted, #64748b);
  border: 2px solid var(--gis-border, #334155);
}

.pipeline-step.running .step-icon {
  background: rgba(250, 204, 21, 0.15);
  color: var(--el-color-warning, #facc15);
  border: 2px solid #facc15;
  animation: pulse 1s ease-in-out infinite;
}

.pipeline-step.completed .step-icon {
  background: rgba(74, 222, 128, 0.15);
  color: var(--el-color-success, #4ade80);
  border: 2px solid #4ade80;
}

@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(250, 204, 21, 0.4); }
  50% { box-shadow: 0 0 8px 4px rgba(250, 204, 21, 0.2); }
}

.step-label {
  font-size: 10px;
  color: var(--gis-text, #f8fafc);
  text-align: center;
  line-height: 1.3;
}

.pipeline-step.pending .step-label {
  color: var(--gis-text-muted, #64748b);
}

.step-agent {
  font-size: 8px;
  color: var(--gis-text-muted, #64748b);
  margin-top: 2px;
  font-family: ui-monospace, "Consolas", monospace;
}

/* ====== 中列：执行过程（审计 chips） ====== */
.steps-card {
  flex-shrink: 0;
}

.steps-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
  padding: 12px 16px;
}

.steps-summary-item {
  padding: 8px 10px;
  background: var(--gis-bg-deep);
  border: 1px solid var(--gis-border, #334155);
  border-left: 3px solid var(--gis-text-muted, #64748b);
  border-radius: 6px;
}

.steps-summary-item.ok {
  border-left-color: #4ade80;
}

.steps-summary-item.fail {
  border-left-color: #f87171;
}

.steps-summary-item.skip {
  border-left-color: var(--gis-text-muted, #94a3b8);
  opacity: 0.75;
}

.ssi-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.ssi-agent {
  font-size: 10px;
  font-weight: 700;
  color: var(--el-color-success, #4ade80);
  background: rgba(74, 222, 128, 0.12);
  padding: 1px 6px;
  border-radius: 8px;
  font-family: ui-monospace, "Consolas", monospace;
}

.steps-summary-item.fail .ssi-agent {
  color: #f87171;
  background: rgba(248, 113, 113, 0.12);
}

.ssi-step {
  font-size: 10px;
  color: var(--gis-text-muted, #94a3b8);
  font-family: ui-monospace, "Consolas", monospace;
}

.ssi-status {
  margin-left: auto;
  font-size: 11px;
  font-weight: 700;
  color: var(--el-color-success, #4ade80);
}

.steps-summary-item.fail .ssi-status {
  color: #f87171;
}

.ssi-summary {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
}

.ssi-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.ssi-chip {
  font-size: 9px;
  line-height: 1.6;
  padding: 0 6px;
  border-radius: 8px;
  white-space: nowrap;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-hover-tint);
  border: 1px solid var(--gis-accent-soft);
  font-family: ui-monospace, "Consolas", monospace;
}

.ssi-chip.llm {
  background: var(--gis-accent-soft);
  border-color: var(--gis-accent-dim);
}

.ssi-chip.ok {
  color: var(--el-color-success, #4ade80);
  background: rgba(74, 222, 128, 0.12);
  border-color: rgba(74, 222, 128, 0.28);
}

.ssi-chip.warn {
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.12);
  border-color: rgba(250, 204, 21, 0.28);
}

.ssi-chip.danger {
  color: #f87171;
  background: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.28);
}

/* ====== 中列：报告流式渲染（report_delta 打字机） ====== */
.stream-card {
  flex-shrink: 0;
  border-color: var(--gis-accent-dim);
}

.stream-badge {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 400;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft);
  border: 1px solid var(--gis-accent-dim);
  animation: stream-pulse 1.2s ease-in-out infinite;
}

.stream-body {
  flex: 1;
  min-height: 0;
  max-height: 300px;
  margin: 0;
  overflow-y: auto;
  padding: 12px 16px;
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 12px;
  line-height: 1.7;
  color: var(--gis-text, #f8fafc);
  white-space: pre-wrap;
  word-break: break-word;
}

.stream-cursor {
  display: inline-block;
  color: var(--gis-accent, #0ea5e9);
  animation: stream-blink 1s step-start infinite;
}

@keyframes stream-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

@keyframes stream-blink {
  50% { opacity: 0; }
}

/* ====== 中列：分析报告 ====== */
.agent-report {
  flex: 1 1 auto;
  min-height: 380px;
}

.report-title-bar :deep(.el-button) {
  flex-shrink: 0;
}

.report-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  background: var(--gis-accent, #0ea5e9);
  color: var(--gis-on-accent);
  border-radius: 2px;
  letter-spacing: 0.04em;
}

.report-llm-badge {
  font-size: 9px;
  padding: 1px 6px;
  background: rgba(74, 222, 128, 0.15);
  color: var(--el-color-success, #4ade80);
  border-radius: 2px;
  border: 1px solid rgba(74, 222, 128, 0.3);
}

.report-fallback-badge {
  font-size: 9px;
  padding: 1px 6px;
  background: rgba(250, 204, 21, 0.15);
  color: var(--el-color-warning, #facc15);
  border-radius: 2px;
  border: 1px solid rgba(250, 204, 21, 0.3);
}

.report-status-label {
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
}

.report-status {
  font-size: 10px;
  font-weight: 600;
}

.report-status.ok {
  color: var(--el-color-success, #4ade80);
}

.report-status.fail {
  color: #ef4444;
}

.report-status.wait {
  color: var(--el-color-warning, #facc15);
}

.report-status.run {
  color: var(--gis-accent, #38bdf8);
}

.report-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--gis-text, #f8fafc);
}

/* v-html 注入的 Markdown 内容需用 :deep() 命中 */
.report-content :deep(h1) {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 14px;
  color: var(--gis-text, #f8fafc);
  border-bottom: 1px solid var(--gis-border, #334155);
  padding-bottom: 8px;
}

.report-content :deep(h2) {
  font-size: 15px;
  font-weight: 600;
  margin: 16px 0 10px;
  color: var(--gis-accent, #0ea5e9);
}

.report-content :deep(h3) {
  font-size: 13px;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--gis-text, #f8fafc);
}

.report-content :deep(h4) {
  font-size: 12px;
  font-weight: 600;
  margin: 10px 0 6px;
  color: var(--gis-text, #f8fafc);
}

.report-content :deep(p) {
  margin: 0 0 8px;
}

.report-content :deep(ul),
.report-content :deep(ol) {
  margin: 4px 0 10px;
  padding-left: 22px;
}

.report-content :deep(li) {
  margin: 0 0 4px;
  list-style-type: disc;
}

.report-content :deep(ol > li) {
  list-style-type: decimal;
}

.report-content :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 14px;
  background: var(--gis-hover-tint);
  border-left: 3px solid var(--gis-accent, #0ea5e9);
  border-radius: 2px;
  color: var(--gis-text-muted, #94a3b8);
  font-size: 12px;
}

.report-content :deep(code) {
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 12px;
  background: var(--gis-hover-tint);
  color: var(--gis-accent, #7dd3fc);
  padding: 1px 5px;
  border-radius: 3px;
}

.report-content :deep(pre) {
  background: var(--gis-bg-deep);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 8px 0;
}

.report-content :deep(pre code) {
  background: transparent;
  padding: 0;
  color: var(--gis-text, #f8fafc);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre;
}

.report-content :deep(strong) {
  color: var(--gis-text);
  font-weight: 700;
}

.report-content :deep(em) {
  color: var(--gis-text, #f8fafc);
}

.report-content :deep(hr) {
  border: none;
  border-top: 1px solid var(--gis-border, #334155);
  margin: 16px 0;
}

.report-content :deep(a) {
  color: var(--gis-accent, #0ea5e9);
}

/* Markdown 表格 */
.report-content :deep(.md-table-wrap) {
  overflow-x: auto;
  margin: 8px 0 12px;
}

.report-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.report-content :deep(th) {
  background: var(--gis-bg-deep);
  color: var(--gis-accent, #0ea5e9);
  font-weight: 600;
  padding: 6px 10px;
  border: 1px solid var(--gis-border, #334155);
  text-align: left;
  white-space: nowrap;
}

.report-content :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--gis-border, #334155);
  color: var(--gis-text, #f8fafc);
  vertical-align: top;
}

.report-content :deep(tbody tr:nth-child(even)) {
  background: var(--gis-bg-deep);
}

/* ====== 右列：HITL 审批卡 ====== */
.approval-card {
  flex-shrink: 0;
  border-color: rgba(250, 204, 21, 0.4);
}

.approval-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 16px;
}

.approval-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  background: #facc15;
  color: #020617;
  border-radius: 2px;
  letter-spacing: 0.04em;
}

.approval-title {
  font-size: 12px;
  color: var(--gis-text, #f8fafc);
  font-weight: 600;
}

.approval-round {
  font-size: 10px;
  color: var(--el-color-warning, #facc15);
  padding: 1px 6px;
  border: 1px solid rgba(250, 204, 21, 0.3);
  border-radius: 8px;
}

.approval-review {
  font-size: 11px;
  line-height: 1.5;
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.06);
  border: 1px solid rgba(250, 204, 21, 0.2);
  border-radius: 6px;
  padding: 6px 10px;
}

.approval-review-label {
  font-weight: 600;
}

.approval-mode {
  flex-shrink: 0;
}

.approval-draft {
  max-height: 300px;
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.7;
  color: var(--gis-text, #f8fafc);
  background: var(--gis-bg-deep);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 6px;
  padding: 10px 14px;
}

.approval-actions {
  display: flex;
  justify-content: flex-end;
}

/* ====== 中列：空状态 ====== */
.agent-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 30px 20px;
}

.agent-empty-icon {
  font-size: 42px;
  opacity: 0.3;
  color: var(--gis-text-muted, #94a3b8);
}

.agent-empty-text {
  font-size: 14px;
  color: var(--gis-text-muted, #94a3b8);
  max-width: 400px;
  text-align: center;
  margin: 0;
}

.agent-empty-desc {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  max-width: 500px;
  text-align: center;
  margin: 0;
  line-height: 1.6;
}
</style>
