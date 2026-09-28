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
import { API_V1 } from '@/utils/config'

const API_BASE = `${API_V1}/reports`



// ====== 列表状态 ======
const reports = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const reportType = ref('') // '' | daily | weekly | monthly | special

// ====== 详情状态 ======
const currentReport = ref(null)
const detailLoading = ref(false)
const detailError = ref('') // 详情加载错误（404 / 请求失败）
let detailSeq = 0 // 请求序号：快速切换报告时丢弃过期响应，防竞态覆盖

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
  const seq = ++detailSeq // 本次请求序号
  detailLoading.value = true
  detailError.value = ''
  try {
    const res = await authFetch(`${API_BASE}/${id}`)
    if (seq !== detailSeq) return // 已被更新的请求取代，丢弃本次结果
    if (res.status === 404) {
      currentReport.value = null
      detailError.value = '报告不存在或无权限查看'
      return
    }
    const json = await res.json().catch(() => ({}))
    if (seq !== detailSeq) return
    if (json.code === 200 && json.data) {
      currentReport.value = json.data
    } else {
      currentReport.value = null
      detailError.value = json.detail || json.message || '加载详情失败'
    }
  } catch (e) {
    if (seq !== detailSeq) return
    currentReport.value = null
    detailError.value = '加载详情失败：' + e.message
  } finally {
    if (seq === detailSeq) detailLoading.value = false
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
        detailError.value = ''
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
// 防御：renderMarkdown 对「以 | 开头但不是合法表格」的行会陷入死循环，
// 导致详情页整页卡死/空白。渲染前先把这类"悬空表格行"转义为普通文本。
const isTableSep = (s) =>
  typeof s === 'string' && s.includes('-') && /^\s*\|?[\s:|-]+\|?\s*$/.test(s)

const sanitizeMarkdown = (md) => {
  const lines = String(md).replace(/\r\n/g, '\n').split('\n')
  const isPipe = (l) => typeof l === 'string' && l.trim().startsWith('|')
  const out = lines.slice()
  let i = 0
  while (i < lines.length) {
    if (!isPipe(lines[i])) {
      i++
      continue
    }
    let j = i
    while (j < lines.length && isPipe(lines[j])) j++ // 连续以 | 开头的行块
    // 仅当该块是合法表格（首行紧跟分隔行）时才原样保留，否则整块转义
    const validTable = j - i >= 2 && isTableSep(lines[i + 1])
    if (!validTable) {
      for (let k = i; k < j; k++) out[k] = lines[k].replace(/^(\s*)\|/, '$1\\|')
    }
    i = j
  }
  return out.join('\n')
}

const renderHtml = computed(() => {
  const raw =
    currentReport.value && typeof currentReport.value.content === 'string'
      ? currentReport.value.content
      : ''
  if (!raw.trim()) return ''
  try {
    return renderMarkdown(sanitizeMarkdown(raw))
  } catch (e) {
    return '' // 渲染异常交由模板显示空态，避免整页空白
  }
})

// 正文是否有可渲染内容
const hasContent = computed(
  () =>
    !!(currentReport.value &&
      typeof currentReport.value.content === 'string' &&
      currentReport.value.content.trim()),
)

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

// ====== LLM 审计元数据（模型来源 / Token / 降级） ======
const PROVIDER_LABELS = {
  aliyun: '阿里百炼',
  bailian: '阿里百炼',
  amd: 'AMD GPU Cloud',
  ollama: '本地 Ollama',
  deepseek: 'DeepSeek',
  openai: 'OpenAI',
}
// 完整名称（详情头部）；无 provider 说明是模板兜底
const providerLabel = (p) => (p ? PROVIDER_LABELS[p] || p : '模板生成')
// 列表内短标签
const providerShort = (p) => (p ? PROVIDER_LABELS[p] || p : '模板')

// updated_at 与 created_at 不同才展示"更新于"
const showUpdated = computed(() => {
  const r = currentReport.value
  return !!(r && r.updated_at && r.updated_at !== r.created_at)
})

// Token 总量（优先 total_tokens，否则用 prompt+completion 求和），无则 null
const tokenTotal = computed(() => {
  const t = currentReport.value && currentReport.value.llm_tokens
  if (!t) return null
  if (t.total_tokens != null) return t.total_tokens
  const sum = (t.prompt_tokens || 0) + (t.completion_tokens || 0)
  return sum > 0 ? sum : null
})

// Token 明细（tooltip）
const tokenDetail = computed(() => {
  const t = currentReport.value && currentReport.value.llm_tokens
  if (!t) return ''
  return `输入 ${t.prompt_tokens ?? '—'} / 输出 ${t.completion_tokens ?? '—'}`
})

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
    <header class="report-header gis-glass">
      <div class="report-header-left">
        <h1 class="report-title">报告中心</h1>
        <p class="report-subtitle">查看 Agent 自动生成的分析报告，支持预览、导出与归档</p>
        <p class="datav-en">Report Archive · Agent Generated</p>
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
      <aside class="report-list-panel gis-glass">
        <div class="card-header">
          <span class="card-bar" />
          <span class="card-title">报告列表</span>
          <span class="list-count">{{ total }}</span>
        </div>

        <div v-loading="loading" class="list-content">
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
              <span class="report-provider-badge" :title="`模型来源：${item.llm_model || providerLabel(item.llm_provider)}`">
                {{ item.llm_model || providerShort(item.llm_provider) }}
              </span>
              <span v-if="isAgentGenerated(item)" class="report-agent-badge" title="由 Agent 协作中心自动生成">
                ReportAgent
              </span>
              <span v-if="item.tags && item.tags.length" class="report-tag">{{ item.tags[0] }}</span>
            </div>
            <div class="report-item-title">{{ item.title }}</div>
            <div class="report-item-summary">{{ item.summary || '暂无摘要' }}</div>
            <div class="report-item-bottom">
              <!-- 重生成走 upsert：created_at 不变、updated_at 刷新，优先展示更新时间避免"新报告像旧的" -->
              <span class="report-item-time">{{ item.updated_at && item.updated_at !== item.created_at ? '更新于 ' + item.updated_at : item.created_at }}</span>
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
      <main class="report-detail-panel gis-glass" v-loading="detailLoading">
        <div class="card-header">
          <span class="card-bar" />
          <span class="card-title">报告详情</span>
        </div>

        <div class="detail-scroll">
        <div v-if="detailError" class="detail-empty">
          <div class="detail-empty-icon">⚠️</div>
          <h3>{{ detailError }}</h3>
          <p>该报告可能已被删除，或您没有查看权限</p>
        </div>

        <div v-else-if="!currentReport" class="detail-empty">
          <div class="detail-empty-icon">📄</div>
          <h3>请从左侧选择一份报告</h3>
          <p>报告由 Agent 协作中心自动生成</p>
        </div>

        <div v-else class="detail-content">
          <!-- 详情头部 -->
          <div class="detail-header">
            <div class="detail-header-left">
              <span class="detail-type-badge">{{ typeLabel(currentReport.report_type) }}</span>
              <span class="provider-badge" :title="`模型来源：${currentReport.llm_model || providerLabel(currentReport.llm_provider)}`">
                {{ currentReport.llm_model || providerLabel(currentReport.llm_provider) }}
              </span>
              <span
                v-if="currentReport.llm_degraded"
                class="degrade-badge"
                title="本次生成发生降级（模板兜底或换用备用 Provider）"
              >降级产出</span>
              <span v-if="isAgentGenerated(currentReport)" class="report-agent-badge">ReportAgent 生成</span>
              <span class="detail-status">{{ currentReport.status }}</span>
            </div>
            <div class="detail-header-title">{{ currentReport.title }}</div>
            <!-- 元信息栏：模型来源 / 生成时间 / Token / 标签 -->
            <div class="detail-header-meta">
              <span class="meta-item">
                <span class="meta-label">模型来源</span>
                <span class="meta-value">{{ currentReport.llm_model || providerLabel(currentReport.llm_provider) }}</span>
              </span>
              <span class="meta-item">
                <span class="meta-label">生成时间</span>
                <span class="meta-value">{{ currentReport.created_at || '—' }}</span>
              </span>
              <span v-if="showUpdated" class="meta-item">
                <span class="meta-label">更新于</span>
                <span class="meta-value">{{ currentReport.updated_at }}</span>
              </span>
              <span class="meta-item">
                <span class="meta-label">Token 用量</span>
                <el-tooltip v-if="tokenTotal != null" :content="tokenDetail || '无明细'" placement="top">
                  <span class="meta-value">{{ tokenTotal }}</span>
                </el-tooltip>
                <span v-else class="meta-value">—</span>
              </span>
              <span v-if="currentReport.tags && currentReport.tags.length" class="meta-item">
                <span class="meta-label">标签</span>
                <span class="meta-value">{{ currentReport.tags.join(' / ') }}</span>
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
            <div v-if="hasContent" class="detail-markdown" v-html="renderHtml" />
            <div v-else class="detail-body-empty">报告内容为空</div>
          </div>
        </div>
        </div><!-- /detail-scroll -->
      </main>
    </div>
  </div>
</template>

<style scoped>
.report-shell {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
  background:
    radial-gradient(120% 90% at 50% 0%, transparent 60%, rgba(15, 23, 42, 0.05) 100%),
    var(--gis-atmo-bg);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}

/* 顶部通栏页头卡（sc-datav TitleWrapper 基准：高约 64px） */
.report-header {
  flex-shrink: 0;
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  border-radius: var(--gis-radius-md, 10px);
}
.report-header-left {
  min-width: 0;
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
  color: var(--gis-text-muted, #64748b);
}
.report-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 主体：380px 列表列 + 弹性详情列（sc-datav 两栏网格基准） */
.report-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 20px;
}

/* 通用卡内标题条：accent 竖条 + 加粗标题 + 底部分隔线 */
.card-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--gis-border);
  font-weight: 600;
  font-size: 14px;
  color: var(--gis-text, #f8fafc);
}
.card-bar {
  flex-shrink: 0;
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--gis-accent, #0ea5e9);
  box-shadow: 0 0 6px var(--gis-accent-dim, rgba(34, 211, 238, 0.45));
}

/* 左列：报告列表卡 */
.report-list-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  border-radius: var(--gis-radius-md, 10px);
}
.list-count {
  flex-shrink: 0;
  margin-left: auto;
  font-size: 11px;
  color: var(--gis-text-muted, #94a3b8);
  background: rgba(148, 163, 184, 0.12);
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
  color: var(--gis-text-muted, #64748b);
}
.empty-icon {
  font-size: 36px;
  opacity: 0.4;
  margin-bottom: 8px;
}
.empty-hint {
  font-size: 12px;
  color: var(--gis-text-muted, #475569);
  margin-top: 4px;
}
.report-list-item {
  position: relative;
  padding: 12px 14px;
  margin-bottom: 8px;
  border: 1px solid var(--gis-border);
  border-radius: var(--gis-radius-sm, 8px);
  background: var(--gis-glass-2);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.report-list-item:hover {
  border-color: var(--gis-accent-dim);
  background: var(--gis-hover-tint);
}
.report-list-item.active {
  border-color: var(--gis-accent, #0ea5e9);
  background: var(--gis-hover-tint);
  box-shadow: var(--gis-glow);
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
  color: var(--gis-text-muted, #64748b);
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
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}
.report-type-badge {
  font-size: 10px;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft);
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
.report-provider-badge {
  font-size: 10px;
  color: var(--gis-text-muted, #94a3b8);
  background: var(--gis-hover-tint);
  padding: 2px 8px;
  border-radius: 4px;
}
.report-item-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  margin-bottom: 4px;
  display: -webkit-box;
  line-clamp: 1;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.report-item-summary {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
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
  color: var(--gis-text-muted, #475569);
}
.list-pagination {
  padding: 10px 0;
  display: flex;
  justify-content: center;
}

/* 右列：报告详情卡 */
.report-detail-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  border-radius: var(--gis-radius-md, 10px);
}
.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.detail-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--gis-text-muted, #64748b);
}
.detail-empty-icon {
  font-size: 48px;
  opacity: 0.4;
  margin-bottom: 12px;
}
.detail-empty h3 {
  margin: 0 0 6px;
  color: var(--gis-text-muted, #94a3b8);
  font-weight: 600;
}
.detail-empty p {
  margin: 0;
  font-size: 13px;
  color: var(--gis-text-muted, #475569);
}
.detail-content {
  padding: 24px;
}
.detail-header {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--gis-border, #1e293b);
}
.detail-header-left {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.detail-type-badge {
  font-size: 11px;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft);
  padding: 3px 10px;
  border-radius: 4px;
}
.provider-badge {
  font-size: 11px;
  color: var(--gis-text-muted, #94a3b8);
  background: var(--gis-hover-tint);
  border: 1px solid var(--gis-border);
  padding: 3px 10px;
  border-radius: 4px;
}
.degrade-badge {
  font-size: 11px;
  font-weight: 600;
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.14);
  border: 1px solid rgba(245, 158, 11, 0.4);
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
  color: var(--gis-text, #f8fafc);
  text-shadow: var(--gis-text-glow);
}
.detail-header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--gis-text-muted, #64748b);
}
.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.meta-label {
  color: var(--gis-text-muted, #94a3b8);
}
.meta-value {
  color: var(--gis-text, #f8fafc);
  font-family: ui-monospace, "Consolas", monospace;
}
.detail-actions {
  display: flex;
  gap: 10px;
  padding: 16px 0;
  border-bottom: 1px solid var(--gis-border, #1e293b);
}
.detail-body {
  padding-top: 20px;
  color: var(--el-text-color-regular, #cbd5e1);
}
.detail-summary {
  font-size: 13px;
  color: var(--gis-text-muted, #94a3b8);
  line-height: 1.7;
  margin-bottom: 12px;
}
.detail-body hr {
  border: none;
  border-top: 1px solid var(--gis-border, #1e293b);
  margin: 16px 0;
}
.detail-body-empty {
  padding: 32px;
  text-align: center;
  font-size: 13px;
  color: var(--gis-text-muted, #94a3b8);
  border: 1px dashed var(--gis-border);
  border-radius: var(--gis-radius-sm, 8px);
}

/* Markdown — v-html 注入内容需用 :deep() 命中（与 Agent 中心一致） */
.markdown-body :deep(h1) {
  font-size: 22px;
  color: var(--gis-text);
  margin: 12px 0;
  border-bottom: 1px solid var(--gis-border, #1e293b);
  padding-bottom: 8px;
}
.markdown-body :deep(h2) {
  font-size: 18px;
  color: var(--gis-text, #f8fafc);
  margin: 16px 0 8px;
}
.markdown-body :deep(h3) {
  font-size: 15px;
  color: var(--el-text-color-regular, #cbd5e1);
  margin: 14px 0 6px;
}
.markdown-body :deep(p) {
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular, #cbd5e1);
}
.markdown-body :deep(li) {
  font-size: 13px;
  line-height: 1.8;
  color: var(--el-text-color-regular, #cbd5e1);
  margin-left: 20px;
}
.markdown-body :deep(li.ol-item) {
  list-style: decimal;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--gis-accent, #0ea5e9);
  padding: 8px 12px;
  margin: 12px 0;
  background: var(--gis-hover-tint);
  color: var(--gis-text-muted, #94a3b8);
  font-size: 12px;
}
.markdown-body :deep(strong) {
  color: var(--gis-text);
  font-weight: 700;
}
.markdown-body :deep(em) {
  color: var(--el-text-color-regular, #cbd5e1);
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--gis-border, #1e293b);
  margin: 16px 0;
}
.markdown-body :deep(a) {
  color: var(--gis-accent, #0ea5e9);
}
.markdown-body :deep(code) {
  background: var(--gis-glass-solid);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 12px;
  color: var(--gis-accent, #0ea5e9);
}
.markdown-body :deep(pre) {
  background: var(--gis-bg-deep);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
  margin: 10px 0;
}
.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
  color: var(--el-text-color-regular, #cbd5e1);
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
  background: var(--gis-bg-deep);
  color: var(--gis-accent, #0ea5e9);
  font-weight: 600;
  padding: 6px 10px;
  border: 1px solid var(--gis-border, #334155);
  text-align: left;
  white-space: nowrap;
}
.markdown-body :deep(td) {
  padding: 6px 10px;
  border: 1px solid var(--gis-border, #334155);
  color: var(--gis-text);
  vertical-align: top;
}
.markdown-body :deep(tbody tr:nth-child(even)) {
  background: var(--gis-bg-deep);
}
</style>