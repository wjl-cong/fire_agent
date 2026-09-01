<script setup>
/**
 * 报告中心 — 查看历史分析报告、预览 Markdown、导出、删除
 *
 * 后端 API:
 *   GET    /api/v1/reports/list?page=&page_size=&report_type=
 *   GET    /api/v1/reports/{id}
 *   DELETE /api/v1/reports/{id}
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Delete, Refresh } from '@element-plus/icons-vue'
import authFetch from '@/utils/authFetch'
import renderMarkdown from '@/utils/markdown'

const API_BASE = 'http://localhost:8000/api/v1/reports'

// ====== 列表状态 ======
const reports = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const reportType = ref('') // '' | daily | weekly | monthly | special
const showList = ref(true) // 左侧报告列表面板展开/折叠

// ====== 详情状态 ======
const currentReport = ref(null)
const detailLoading = ref(false)

// ====== 报告类型选项 ======
const typeOptions = [
  { value: '', label: '全部' },
  { value: 'daily', label: '日报' },
  { value: 'weekly', label: '周报' },
  { value: 'monthly', label: '月报' },
  { value: 'special', label: '专项' },
]

// ====== 拉取列表 ======
const fetchReports = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: page.value,
      page_size: pageSize.value,
    })
    if (reportType.value) params.append('report_type', reportType.value)
    const res = await authFetch(`${API_BASE}/list?${params.toString()}`)
    const json = await res.json()
    if (json.code === 200) {
      reports.value = json.data.items || []
      total.value = json.data.total || 0
    }
  } catch (e) {
    ElMessage.error('加载报告列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

// ====== 拉取详情 ======
const fetchDetail = async (id) => {
  detailLoading.value = true
  try {
    const res = await authFetch(`${API_BASE}/${id}`)
    const json = await res.json()
    if (json.code === 200) {
      currentReport.value = json.data
    } else {
      ElMessage.error(json.detail || '加载详情失败')
    }
  } catch (e) {
    ElMessage.error('加载详情失败: ' + e.message)
  } finally {
    detailLoading.value = false
  }
}

// ====== 选择报告 ======
const selectReport = async (item) => {
  await fetchDetail(item.id)
}

// ====== 删除报告 ======
const handleDelete = async (item) => {
  try {
    await ElMessageBox.confirm(`确定删除报告「${item.title}」吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    const res = await authFetch(`${API_BASE}/${item.id}`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) {
      ElMessage.success('删除成功')
      if (currentReport.value && currentReport.value.id === item.id) {
        currentReport.value = null
      }
      fetchReports()
    } else {
      ElMessage.error(json.detail || '删除失败')
    }
  } catch {
    // 用户取消
  }
}

// ====== 导出 ======
// format: html（打印/存PDF）| md（Markdown）
const handleExport = async (item, format = 'md') => {
  const id = item.id
  const fileName = `${item.title || `report_${id}`}.${format === 'md' ? 'md' : 'html'}`
  try {
    const res = await authFetch(`${API_BASE}/export/${id}?format=${format}`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      ElMessage.error(err.detail || '导出失败')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fileName
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success(format === 'md' ? '已导出 Markdown 文件' : '已导出 HTML 文件（可直接打印另存为 PDF）')
  } catch (e) {
    ElMessage.error('导出失败: ' + e.message)
  }
}

// 打开打印预览（浏览器"另存为 PDF"）——通过 authFetch 获取 HTML 再打开，避免无鉴权窗口
const handlePrint = async (item) => {
  try {
    const res = await authFetch(`${API_BASE}/export/${item.id}?format=html`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      ElMessage.error(err.detail || '获取打印内容失败')
      return
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const win = window.open('', '_blank')
    if (win) {
      win.document.write('<html><head><title>加载中…</title></head><body style="margin:0">加载打印内容…</body></html>')
      win.document.close()
      win.location.href = url
      const timer = setInterval(() => {
        if (win.document.readyState === 'complete') {
          clearInterval(timer)
          win.print()
        }
      }, 500)
    } else {
      ElMessage.warning('浏览器拦截了弹窗，请允许后重试')
    }
  } catch (e) {
    ElMessage.error('获取打印内容失败: ' + e.message)
  }
}

// ====== 分页 ======
const handlePageChange = (val) => {
  page.value = val
  fetchReports()
}

const handleTypeChange = () => {
  page.value = 1
  fetchReports()
}

// ====== Markdown 渲染（支持表格/加粗/代码块） ======
const renderHtml = computed(() => {
  const content = currentReport.value ? (currentReport.value.content || '') : ''
  return renderMarkdown(content)
})

// ====== 语音播报报告（摘要 + 正文前段） ======
import { speakState, speakText, cleanupSpeech } from '@/utils/speech'
const speakReport = () => {
  const r = currentReport.value
  if (!r) return
  const text = (r.summary ? `报告摘要：${r.summary}。` : '') + (r.content || '')
  speakText(text)
}

// ====== 类型显示 ======
const typeLabel = (t) => {
  const found = typeOptions.find(o => o.value === t)
  return found ? found.label : (t || '')
}

// ====== 是否由 Agent 自动生成（tags 含 "Agent生成"） ======
const isAgentGenerated = (item) => {
  const tags = item && item.tags
  return Array.isArray(tags) && tags.includes('Agent生成')
}

// ====== 初始化 ======
onMounted(() => {
  fetchReports()
})
onUnmounted(() => {
  cleanupSpeech() // 停止语音播报
})
</script>

<template>
  <div class="report-shell">
    <!-- 页面标题 -->
    <header class="report-header">
      <div>
        <h1 class="report-title">报告中心</h1>
        <p class="report-subtitle">查看 Agent 自动生成的分析报告，支持预览、导出与归档</p>
      </div>
      <div class="report-header-actions">
        <el-select
          v-model="reportType"
          placeholder="报告类型"
          style="width: 140px"
          @change="handleTypeChange"
        >
          <el-option
            v-for="opt in typeOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button type="primary" :icon="Refresh" @click="fetchReports">刷新</el-button>
      </div>
    </header>

    <div class="report-body">
      <!-- 左侧：报告列表 -->
      <aside class="report-list-panel" :class="{ expanded: showList }">
        <div class="list-header" @click="showList = !showList" title="点击展开/收起">
          <span class="list-title">报告列表</span>
          <span class="list-count">{{ total }}</span>
        </div>

        <div v-if="showList" v-loading="loading" class="list-content">
          <div v-if="reports.length === 0 && !loading" class="list-empty">
            <div class="empty-icon">▤</div>
            <p>暂无报告</p>
            <p class="empty-hint">在 Agent 协作中心执行任务后，报告会自动保存到这里</p>
          </div>

          <div
            v-for="item in reports"
            :key="item.id"
            class="report-list-item"
            :class="{ active: currentReport && currentReport.id === item.id }"
            @click="selectReport(item)"
          >
            <button
              class="report-item-delete"
              title="删除"
              @click.stop="handleDelete(item)"
            >×</button>
            <div class="report-item-top">
              <span class="report-type-badge">{{ typeLabel(item.report_type) }}</span>
              <span v-if="isAgentGenerated(item)" class="report-agent-badge" title="由 Agent 协作中心自动生成">
                ReportAgent
              </span>
              <span v-if="item.tags && item.tags.length" class="report-tag">{{ item.tags[0] }}</span>
            </div>
            <div class="report-item-title">{{ item.title }}</div>
            <div class="report-item-summary">{{ item.summary || '暂无摘要' }}</div>
            <div class="report-item-bottom">
              <span class="report-item-time">{{ item.created_at }}</span>
            </div>
          </div>

          <div v-if="reports.length > 0" class="list-pagination">
            <el-pagination
              small
              layout="prev, pager, next"
              :total="total"
              :page-size="pageSize"
              :current-page="page"
              @current-change="handlePageChange"
            />
          </div>
        </div>
      </aside>

      <!-- 右侧：报告详情 -->
      <main class="report-detail-panel">
        <div v-if="!currentReport" class="detail-empty">
          <div class="detail-empty-icon">📄</div>
          <h3>选择左侧报告查看详情</h3>
          <p>报告由 Agent 协作中心自动生成</p>
        </div>

        <div v-else v-loading="detailLoading" class="detail-content">
          <!-- 详情头部 -->
          <div class="detail-header">
            <div class="detail-header-left">
              <span class="detail-type-badge">{{ typeLabel(currentReport.report_type) }}</span>
              <span v-if="isAgentGenerated(currentReport)" class="report-agent-badge">ReportAgent 生成</span>
              <span class="detail-status">{{ currentReport.status }}</span>
            </div>
            <div class="detail-header-title">{{ currentReport.title }}</div>
            <div class="detail-header-meta">
              <span>创建时间：{{ currentReport.created_at }}</span>
              <span v-if="currentReport.tags && currentReport.tags.length">
                标签：{{ currentReport.tags.join(' / ') }}
              </span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="detail-actions">
            <el-button
              :loading="speakState.loading"
              :type="speakState.speaking || speakState.loading ? 'danger' : 'success'"
              plain
              title="语音播报报告（摘要 + 正文）"
              @click="speakReport"
            >
              {{ speakState.speaking || speakState.loading ? '停止播报' : '🔊 语音播报' }}
            </el-button>
            <el-button type="success" :icon="Download" @click="handleExport(currentReport, 'md')">
              导出 Markdown
            </el-button>
            <el-button type="primary" plain :icon="Download" @click="handleExport(currentReport, 'html')">
              导出 HTML
            </el-button>
            <el-button type="warning" plain :icon="Download" @click="handlePrint(currentReport)">
              打印 / 存 PDF
            </el-button>
            <el-button type="danger" plain :icon="Delete" @click="handleDelete(currentReport)">
              删除
            </el-button>
          </div>

          <!-- Markdown 正文 -->
          <div class="detail-body markdown-body">
            <div v-if="currentReport.summary" class="detail-summary">
              <strong>摘要：</strong>{{ currentReport.summary }}
            </div>
            <hr v-if="currentReport.summary" />
            <div class="detail-markdown" v-html="renderHtml" />
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.report-shell {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0a0f1e;
  color: #f8fafc;
  overflow: hidden;
}

/* 顶部 */
.report-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid #1e293b;
  background: linear-gradient(90deg, #0f172a 0%, #0a0f1e 100%);
  flex-shrink: 0;
}
.report-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.report-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #64748b;
}
.report-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 主体 */
.report-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* 左列表 */
.report-list-panel {
  width: 60px;
  flex-shrink: 0;
  border-right: 1px solid #1e293b;
  display: flex;
  flex-direction: column;
  background: #0b1120;
  overflow: hidden;
  transition: width 0.2s ease;
}
.report-list-panel.expanded {
  width: 340px;
}
.list-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 8px;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
  cursor: pointer;
  user-select: none;
}
.list-header:hover {
  background: rgba(14, 165, 233, 0.06);
}
.list-title {
  display: none;
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}
.report-list-panel.expanded .list-title {
  display: inline;
}
.list-count {
  flex-shrink: 0;
  font-size: 11px;
  color: #94a3b8;
  background: #1e293b;
  padding: 1px 8px;
  border-radius: 10px;
}
.list-content {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}
.list-empty {
  text-align: center;
  padding: 48px 20px;
  color: #64748b;
}
.empty-icon {
  font-size: 36px;
  opacity: 0.4;
  margin-bottom: 8px;
}
.empty-hint {
  font-size: 12px;
  color: #475569;
  margin-top: 4px;
}
.report-list-item {
  position: relative;
  padding: 12px 14px;
  margin-bottom: 8px;
  border: 1px solid #1e293b;
  border-radius: 8px;
  background: #0f172a;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.report-list-item:hover {
  border-color: #334155;
  background: #172033;
}
.report-list-item.active {
  border-color: #0ea5e9;
  background: rgba(14, 165, 233, 0.08);
}
.report-item-delete {
  position: absolute;
  right: 8px;
  top: 8px;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #64748b;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
  z-index: 1;
}
.report-item-delete:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}
.report-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.report-type-badge {
  font-size: 10px;
  color: #0ea5e9;
  background: rgba(14, 165, 233, 0.12);
  padding: 2px 8px;
  border-radius: 4px;
}
.report-agent-badge {
  font-size: 10px;
  font-weight: 600;
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
  border: 1px solid rgba(74, 222, 128, 0.3);
  padding: 1px 8px;
  border-radius: 10px;
  font-family: ui-monospace, "Consolas", monospace;
}
.report-tag {
  font-size: 10px;
  color: #facc15;
  background: rgba(250, 204, 21, 0.12);
  padding: 2px 8px;
  border-radius: 4px;
}
.report-item-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 4px;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.report-item-summary {
  font-size: 11px;
  color: #64748b;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.report-item-bottom {
  display: flex;
  justify-content: flex-end;
}
.report-item-time {
  font-size: 10px;
  color: #475569;
}
.list-pagination {
  padding: 10px 0;
  display: flex;
  justify-content: center;
}

/* 右详情 */
.report-detail-panel {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  background: #0a0f1e;
}
.detail-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #64748b;
}
.detail-empty-icon {
  font-size: 48px;
  opacity: 0.4;
  margin-bottom: 12px;
}
.detail-empty h3 {
  margin: 0 0 6px;
  color: #94a3b8;
  font-weight: 600;
}
.detail-empty p {
  margin: 0;
  font-size: 13px;
  color: #475569;
}
.detail-content {
  padding: 24px;
}
.detail-header {
  padding-bottom: 16px;
  border-bottom: 1px solid #1e293b;
}
.detail-header-left {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.detail-type-badge {
  font-size: 11px;
  color: #0ea5e9;
  background: rgba(14, 165, 233, 0.12);
  padding: 3px 10px;
  border-radius: 4px;
}
.detail-status {
  font-size: 11px;
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
  padding: 3px 10px;
  border-radius: 4px;
}
.detail-header-title {
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
}
.detail-header-meta {
  display: flex;
  gap: 20px;
  margin-top: 8px;
  font-size: 12px;
  color: #64748b;
}
.detail-actions {
  display: flex;
  gap: 10px;
  padding: 16px 0;
  border-bottom: 1px solid #1e293b;
}
.detail-body {
  padding-top: 20px;
  color: #cbd5e1;
}
.detail-summary {
  font-size: 13px;
  color: #94a3b8;
  line-height: 1.7;
  margin-bottom: 12px;
}
.detail-body hr {
  border: none;
  border-top: 1px solid #1e293b;
  margin: 16px 0;
}

/* Markdown — v-html 注入内容需用 :deep() 命中（与 Agent 中心一致） */
.markdown-body :deep(h1) {
  font-size: 22px;
  color: #f8fafc;
  margin: 12px 0;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 8px;
}
.markdown-body :deep(h2) {
  font-size: 18px;
  color: #e2e8f0;
  margin: 16px 0 8px;
}
.markdown-body :deep(h3) {
  font-size: 15px;
  color: #cbd5e1;
  margin: 14px 0 6px;
}
.markdown-body :deep(p) {
  font-size: 13px;
  line-height: 1.8;
  color: #cbd5e1;
}
.markdown-body :deep(li) {
  font-size: 13px;
  line-height: 1.8;
  color: #cbd5e1;
  margin-left: 20px;
}
.markdown-body :deep(li.ol-item) {
  list-style: decimal;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid #0ea5e9;
  padding: 8px 12px;
  margin: 12px 0;
  background: rgba(14, 165, 233, 0.06);
  color: #94a3b8;
  font-size: 12px;
}
.markdown-body :deep(strong) {
  color: #f8fafc;
  font-weight: 700;
}
.markdown-body :deep(em) {
  color: #cbd5e1;
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid #1e293b;
  margin: 16px 0;
}
.markdown-body :deep(a) {
  color: #0ea5e9;
}
.markdown-body :deep(code) {
  background: rgba(30, 41, 59, 0.8);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 12px;
  color: #7dd3fc;
}
.markdown-body :deep(pre) {
  background: #020617;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
  margin: 10px 0;
}
.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  color: #cbd5e1;
  white-space: pre;
}
/* Markdown 表格 */
.markdown-body :deep(.md-table-wrap) {
  overflow-x: auto;
  margin: 8px 0 12px;
}
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.markdown-body :deep(th) {
  background: #020617;
  color: #0ea5e9;
  font-weight: 600;
  padding: 6px 10px;
  border: 1px solid #334155;
  text-align: left;
  white-space: nowrap;
}
.markdown-body :deep(td) {
  padding: 6px 10px;
  border: 1px solid #334155;
  color: #f8fafc;
  vertical-align: top;
}
.markdown-body :deep(tbody tr:nth-child(even)) {
  background: rgba(2, 6, 23, 0.3);
}
</style>