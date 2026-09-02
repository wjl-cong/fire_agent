<script setup>
/**
 * Agent 协作中心 — 任务执行 + 链路可视化 + 报告展示
 *
 * 后端 API: POST /api/v1/agent/tasks  (body: { query: string })
 *          GET  /api/v1/agent/status
 */
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import authFetch from '@/utils/authFetch'
import renderMarkdown from '@/utils/markdown'
import { useAuthStore } from '@/stores/auth'
import { API_V1 } from '@/utils/config'
import { speakState, speakText, recordState, startRecord, cleanupSpeech } from '@/utils/speech'

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
const showHistory = ref(true)

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

// ====== 5 步流水线定义 ======
const pipelineSteps = [
  { key: 'parse_task', label: '拆解任务', agent: 'Orchestrator', icon: '→' },
  { key: 'query_data', label: '查询数据', agent: 'DataAgent', icon: '→' },
  { key: 'analyze_gis', label: '分析 GIS', agent: 'GisAgent', icon: '→' },
  { key: 'retrieve_knowledge', label: '检索知识', agent: 'RagAgent', icon: '→' },
  { key: 'generate_report', label: '生成报告', agent: 'ReportAgent', icon: '→' },
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

// ====== 执行任务 ======
const handleExecute = async () => {
  const q = query.value.trim()
  if (!q) {
    ElMessage.warning('请输入分析任务')
    return
  }

  running.value = true
  taskResult.value = null
  activeStep.value = -1

  // 模拟逐步执行动画
  const stepInterval = setInterval(() => {
    activeStep.value = Math.min(
      activeStep.value + 1,
      pipelineSteps.length - 1
    )
  }, 600)

  try {
    const res = await authFetch(`${API_BASE}/tasks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q }),
    })
    const json = await res.json()

    clearInterval(stepInterval)
    activeStep.value = pipelineSteps.length // 全部完成

    if (json.code === 200) {
      taskResult.value = json.data
      // 添加到历史（使用后端任务 ID，便于数据库同步与删除）
      taskHistory.value.unshift({
        id: json.data.task_id || Date.now(),
        reportId: json.data.report_id || null,
        query: q,
        status: json.data.status,
        llm_used: json.data.llm_used,
        time: new Date().toLocaleString(),
        result: json.data,
      })
      saveHistory()
      ElMessage.success('任务执行完成')
    } else {
      ElMessage.error('执行失败: ' + json.message)
    }
  } catch (e) {
    clearInterval(stepInterval)
    ElMessage.error('网络错误: ' + e.message)
  } finally {
    running.value = false
  }
}

// ====== 加载历史任务 ======
const loadHistoryTask = async (item) => {
  query.value = item.query
  activeStep.value = pipelineSteps.length
  if (item.result) {
    taskResult.value = item.result
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
          llm_used: match ? match.llm_used : false,
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

// ====== 获取步骤状态 ======
const getStepStatus = (index) => {
  if (running.value) {
    if (index < activeStep.value) return 'completed'
    if (index === activeStep.value) return 'running'
    return 'pending'
  }
  if (taskResult.value) {
    if (index < pipelineSteps.length) return 'completed'
    return 'pending'
  }
  return 'pending'
}

// ====== 步骤关键输出转可读文本 ======
const stepOutputText = (st) => {
  const o = st && st.output
  if (!o || typeof o !== 'object') return ''
  try {
    const parts = []
    if ('total' in o) parts.push(`查询 ${o.total} 条`)
    if ('first_city' in o && o.first_city) parts.push(`首城 ${o.first_city}`)
    if ('total_hotspots' in o) parts.push(`热点 ${o.total_hotspots} 个`)
    if ('matched' in o) parts.push(`命中 ${o.matched} 段`)
    if ('method' in o && o.method) parts.push(`方式 ${o.method}`)
    if ('report_length' in o) parts.push(`报告 ${o.report_length} 字符`)
    if ('plan' in o && Array.isArray(o.plan)) parts.push(`计划 ${o.plan.length} 步`)
    if ('error' in o && o.error) parts.push(`错误: ${o.error}`)
    return parts.join(' · ')
  } catch {
    return ''
  }
}

// ====== 初始化 ======
onMounted(() => {
  fetchAgentStatus()
  syncHistoryFromApi()
})
onUnmounted(() => {
  cleanupSpeech() // 停止语音播报/录音
})
</script>

<template>
  <div class="agent-shell">
    <!-- 页面标题 -->
    <header class="agent-header">
      <h1 class="agent-title">Agent 协作中心</h1>
      <p class="agent-subtitle">多 Agent 协同分析，自动拆解任务、查询数据、GIS 分析、知识检索、生成报告</p>
    </header>

    <div class="agent-body">
      <!-- 左侧：任务历史 -->
      <aside
        class="agent-history"
        :class="{ expanded: showHistory }"
      >
        <div class="history-header" @click="showHistory = !showHistory" title="点击展开/收起">
          <span class="history-title">任务历史</span>
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
                :class="item.status === 'completed' ? 'ok' : 'fail'"
              >{{ item.status === 'completed' ? '✓' : '✗' }}</span>
              <span class="history-llm-badge" v-if="item.llm_used">LLM</span>
            </div>
            <div class="history-query">{{ item.query }}</div>
            <div class="history-time">{{ item.time }}</div>
            <button
              class="history-delete"
              title="删除"
              @click.stop="deleteHistoryItem(item)"
            >×</button>
          </div>
        </div>
      </aside>

      <!-- 右侧主区域 -->
      <div class="agent-main">
        <!-- 输入区 -->
        <div class="agent-input-area">
          <div class="input-row">
            <el-input
              v-model="query"
              type="textarea"
              :rows="2"
              placeholder="请描述需要分析的问题..."
              class="agent-input"
              @keydown="handleKeydown"
            />
            <el-button
              type="primary"
              :loading="running"
              @click="handleExecute"
              class="agent-go-btn"
            >
              开始分析
            </el-button>
            <el-button
              :type="recordState.recording ? 'danger' : 'default'"
              :title="recordState.recording ? '停止录音并识别' : '语音输入任务'"
              class="agent-mic-btn"
              @click="handleMicClick"
            >
              {{ recordState.recording ? '■ 停止' : '🎤' }}
            </el-button>
          </div>

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

        <!-- 系统状态 -->
        <div v-if="agentStatus" class="agent-system-status">
          <span class="sys-status-label">Agent 系统状态</span>
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

        <!-- 流水线可视化 -->
        <div class="agent-pipeline">
          <div class="pipeline-title">执行链路</div>
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
                  <span v-else-if="getStepStatus(i) === 'running'">⟳</span>
                  <span v-else>{{ step.icon }}</span>
                </div>
              </div>
              <div class="step-label">{{ step.label }}</div>
              <div class="step-agent">{{ step.agent }}</div>
            </div>
          </div>
        </div>

        <!-- Agent 执行过程摘要 -->
        <div v-if="taskResult" class="agent-steps-summary">
          <div class="steps-summary-title">Agent 执行过程</div>
          <div class="steps-summary-grid">
            <div
              v-for="(st, i) in taskResult.steps"
              :key="i"
              class="steps-summary-item"
              :class="st.status === 'completed' ? 'ok' : 'fail'"
            >
              <div class="ssi-head">
                <span class="ssi-agent">{{ st.agent }}</span>
                <span class="ssi-step">{{ st.step }}</span>
                <span class="ssi-status">{{ st.status === 'completed' ? '✓' : '✗' }}</span>
              </div>
              <div class="ssi-summary">{{ st.summary || '—' }}</div>
              <div v-if="stepOutputText(st)" class="ssi-output">{{ stepOutputText(st) }}</div>
            </div>
          </div>
        </div>

        <!-- 报告展示 -->
        <div v-if="taskResult" class="agent-report">
          <div class="report-header">
            <div class="report-header-left">
              <span class="report-badge">分析报告</span>
              <span
                v-if="taskResult.llm_used"
                class="report-llm-badge"
              >LLM 生成</span>
              <span
                v-else
                class="report-fallback-badge"
              >模板报告</span>
            </div>
            <div class="report-header-right">
              <el-button
                size="small"
                :loading="speakState.loading"
                :type="speakState.speaking || speakState.loading ? 'danger' : 'default'"
                plain
                title="语音播报分析报告"
                @click="speakText(taskResult.report)"
              >{{ speakState.speaking || speakState.loading ? '停止' : '🔊 播报' }}</el-button>
              <span class="report-status-label">状态: </span>
              <span class="report-status" :class="taskResult.status === 'completed' ? 'ok' : 'fail'">
                {{ taskResult.status === 'completed' ? '完成' : '失败' }}
              </span>
            </div>
          </div>
          <div class="report-content markdown-body" v-html="renderMarkdown(taskResult.report)" />
        </div>

        <!-- 空状态 -->
        <div v-else class="agent-empty">
          <div class="agent-empty-icon">⚙</div>
          <p class="agent-empty-text">输入分析任务，系统将自动执行</p>
          <p class="agent-empty-desc">编排 Agent 拆解任务 → 数据 Agent 查询 → GIS Agent 分析 → RAG Agent 检索 → 报告 Agent 生成</p>
        </div>
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
  padding: 20px 24px;
  background: var(--gis-bg-deep, #020617);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}

.agent-header {
  flex-shrink: 0;
  margin-bottom: 14px;
}

.agent-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.02em;
}

.agent-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
}

.agent-body {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 14px;
}

/* ====== 左侧：任务历史 ====== */
.agent-history {
  flex-shrink: 0;
  width: 56px;
  display: flex;
  flex-direction: column;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  position: relative;
  overflow: hidden;
  transition: width 0.2s ease;
}

.agent-history.expanded {
  width: 260px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 8px;
  border-bottom: 1px solid var(--gis-border, #334155);
  flex-shrink: 0;
  cursor: pointer;
  user-select: none;
}

.history-header:hover {
  background: rgba(34, 211, 238, 0.06);
}

.history-title {
  display: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.04em;
}

.agent-history.expanded .history-title {
  display: inline;
}

.history-count {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  background: var(--gis-accent, #0ea5e9);
  color: #020617;
  border-radius: 8px;
  font-weight: 700;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
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
  border-radius: 3px;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.history-item:hover {
  background: rgba(14, 165, 233, 0.06);
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
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
}

.history-status.fail {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.history-llm-badge {
  font-size: 8px;
  padding: 0 4px;
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
  border-radius: 2px;
  border: 1px solid rgba(74, 222, 128, 0.3);
}

.history-query {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

/* ====== 右侧主区域 ====== */
.agent-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  gap: 12px;
  overflow-y: auto; /* 内容超高时整列滚动，避免压缩报告区 */
}

/* 输入区 */
.agent-input-area {
  flex-shrink: 0;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  padding: 14px 16px;
}

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.agent-input {
  flex: 1;
}

.agent-input :deep(.el-textarea__inner) {
  background: var(--gis-bg-deep, #020617) !important;
  color: var(--gis-text, #f8fafc) !important;
  border: 1px solid var(--gis-border, #334155) !important;
  border-radius: 3px;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}

.agent-input :deep(.el-textarea__inner:focus) {
  border-color: var(--gis-accent, #0ea5e9) !important;
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.15) !important;
}

.agent-go-btn {
  flex-shrink: 0;
  height: 74px;
  min-width: 100px;
  background: linear-gradient(135deg, #0ea5e9, #22d3ee) !important;
  border: none !important;
  color: #020617 !important;
  font-weight: 600;
  letter-spacing: 0.04em;
  font-size: 14px;
}

/* 语音输入按钮 */
.agent-mic-btn {
  flex-shrink: 0;
  height: 74px;
  min-width: 60px;
  font-size: 18px;
}
.agent-mic-btn.is-danger {
  animation: agent-mic-pulse 1.2s ease-in-out infinite;
}
@keyframes agent-mic-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.agent-go-btn:hover {
  background: linear-gradient(135deg, #38bdf8, #67e8f9) !important;
}

.input-examples {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.input-example-label {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  flex-shrink: 0;
}

.input-example-tag {
  font-size: 11px;
  padding: 2px 10px;
  color: var(--gis-accent, #0ea5e9);
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid rgba(14, 165, 233, 0.2);
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
}

.input-example-tag:hover {
  background: rgba(14, 165, 233, 0.2);
}

.input-hint {
  margin-top: 6px;
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  font-family: ui-monospace, "Consolas", monospace;
}

/* 系统状态 */
.agent-system-status {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 3px;
  flex-wrap: wrap;
}

.sys-status-label {
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  letter-spacing: 0.04em;
  flex-shrink: 0;
}

.sys-status-item {
  font-size: 10px;
  color: var(--gis-text, #f8fafc);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: rgba(51, 65, 85, 0.4);
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

/* 流水线 */
.agent-pipeline {
  flex-shrink: 0;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  padding: 12px 16px;
}

.pipeline-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.04em;
  margin-bottom: 10px;
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
  background: rgba(51, 65, 85, 0.4);
  color: var(--gis-text-muted, #64748b);
  border: 2px solid var(--gis-border, #334155);
}

.pipeline-step.running .step-icon {
  background: rgba(250, 204, 21, 0.15);
  color: #facc15;
  border: 2px solid #facc15;
  animation: pulse 1s ease-in-out infinite;
}

.pipeline-step.completed .step-icon {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
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

/* ====== Agent 执行过程摘要 ====== */
.agent-steps-summary {
  flex-shrink: 0;
  max-height: 200px;
  overflow-y: auto;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
}

.steps-summary-title {
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--gis-accent, #0ea5e9);
  border-bottom: 1px solid var(--gis-border, #334155);
  letter-spacing: 0.03em;
}

.steps-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  padding: 10px 14px;
}

.steps-summary-item {
  padding: 8px 10px;
  background: rgba(2, 6, 23, 0.4);
  border: 1px solid var(--gis-border, #334155);
  border-left: 3px solid #64748b;
  border-radius: 3px;
}

.steps-summary-item.ok {
  border-left-color: #4ade80;
}

.steps-summary-item.fail {
  border-left-color: #f87171;
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
  color: #4ade80;
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
  color: #4ade80;
}

.steps-summary-item.fail .ssi-status {
  color: #f87171;
}

.ssi-summary {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
}

.ssi-output {
  margin-top: 4px;
  font-size: 10px;
  color: var(--gis-accent, #0ea5e9);
  font-family: ui-monospace, "Consolas", monospace;
  line-height: 1.4;
}

.agent-report {
  flex: 1 1 auto;
  min-height: 55vh;
  min-height: 480px;
  display: flex;
  flex-direction: column;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  overflow: hidden;
}

.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--gis-border, #334155);
  flex-shrink: 0;
}

.report-header-left {
  display: flex;
  gap: 8px;
  align-items: center;
}

.report-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  background: var(--gis-accent, #0ea5e9);
  color: #020617;
  border-radius: 2px;
  letter-spacing: 0.04em;
}

.report-llm-badge {
  font-size: 9px;
  padding: 1px 6px;
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
  border-radius: 2px;
  border: 1px solid rgba(74, 222, 128, 0.3);
}

.report-fallback-badge {
  font-size: 9px;
  padding: 1px 6px;
  background: rgba(250, 204, 21, 0.15);
  color: #facc15;
  border-radius: 2px;
  border: 1px solid rgba(250, 204, 21, 0.3);
}

.report-header-right {
  display: flex;
  align-items: center;
  gap: 4px;
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
  color: #4ade80;
}

.report-status.fail {
  color: #ef4444;
}

.report-content {
  flex: 1;
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
  background: rgba(14, 165, 233, 0.06);
  border-left: 3px solid var(--gis-accent, #0ea5e9);
  border-radius: 2px;
  color: var(--gis-text-muted, #94a3b8);
  font-size: 12px;
}

.report-content :deep(code) {
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 12px;
  background: rgba(34, 211, 238, 0.1);
  color: #7dd3fc;
  padding: 1px 5px;
  border-radius: 3px;
}

.report-content :deep(pre) {
  background: rgba(2, 6, 23, 0.7);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 8px 0;
}

.report-content :deep(pre code) {
  background: transparent;
  padding: 0;
  color: #e2e8f0;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre;
}

.report-content :deep(strong) {
  color: #f8fafc;
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
  background: #020617;
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
  background: rgba(2, 6, 23, 0.3);
}

/* 空状态 */
.agent-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
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