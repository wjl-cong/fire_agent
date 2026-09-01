<script setup>
/**
 * 知识库 RAG 页面 — 文档管理 + 检索问答
 *
 * 后端 API: /api/v1/rag/documents (GET/POST/DELETE)
 *          /api/v1/rag/ask (POST)
 */
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import authFetch from '@/utils/authFetch'
import { speakState, speakText, recordState, startRecord, cleanupSpeech } from '@/utils/speech'

// 语音提问：识别完成自动提交
const handleMicClick = () => {
  if (recordState.recording) {
    startRecord() // 录音中再次调用 = 停止并识别
    return
  }
  startRecord((text) => {
    question.value = text
    handleAsk()
  })
}

const API_BASE = 'http://localhost:8000/api/v1/rag'

// ====== 文档管理 ======
const documents = ref([])
const loadingDocs = ref(false)
const uploadLoading = ref(false)
const showDocs = ref(true) // 左侧文档管理面板展开/折叠

const fetchDocuments = async () => {
  loadingDocs.value = true
  try {
    const res = await authFetch(`${API_BASE}/documents`)
    const json = await res.json()
    if (json.code === 200) {
      documents.value = json.data || []
    }
  } catch {
    // 静默失败
  } finally {
    loadingDocs.value = false
  }
}

const handleUpload = async (file) => {
  uploadLoading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file.raw || file)
    formData.append('category', 'other')

    const res = await authFetch(`${API_BASE}/documents`, {
      method: 'POST',
      body: formData,
    })
    const json = await res.json()
    if (json.code === 200) {
      if (json.data && json.data.status === 'failed') {
        // 文档上传成功但文本提取失败（扫描件/无文字层），明确提醒用户
        ElMessage.warning(`文档 "${file.name}" 已上传，但文本提取失败：${json.data.error || '可能为扫描件或无文字层'}`)
      } else {
        ElMessage.success(`文档 "${file.name}" 上传成功`)
      }
      await fetchDocuments()
    } else {
      ElMessage.error('上传失败: ' + (json.detail || json.message))
    }
  } catch (e) {
    ElMessage.error('上传失败: ' + e.message)
  } finally {
    uploadLoading.value = false
  }
}

const handleDelete = async (doc) => {
  try {
    await ElMessageBox.confirm(`确定删除 "${doc.title}"？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    const res = await authFetch(`${API_BASE}/documents/${doc.id}`, {
      method: 'DELETE',
    })
    const json = await res.json()
    if (json.code === 200) {
      ElMessage.success('删除成功')
      await fetchDocuments()
    }
  } catch {
    // 取消删除
  }
}

// ====== RAG 问答 ======
const question = ref('')
const asking = ref(false)
const answerResult = ref(null)
const activeSource = ref(null)

const handleAsk = async () => {
  const q = question.value.trim()
  if (!q) {
    ElMessage.warning('请输入问题')
    return
  }

  asking.value = true
  answerResult.value = null
  activeSource.value = null

  try {
    const res = await authFetch(`${API_BASE}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, top_k: 5 }),
    })
    const json = await res.json()
    if (json.code === 200) {
      answerResult.value = json.data
      loadHistory()
    } else {
      ElMessage.error('查询失败: ' + (json.detail || json.message))
    }
  } catch (e) {
    ElMessage.error('网络错误: ' + e.message)
  } finally {
    asking.value = false
  }
}

// ====== 问答历史（后端数据库持久化，按用户隔离） ======
const askHistory = ref([])

const loadHistory = async () => {
  try {
    const res = await authFetch(`${API_BASE}/history`)
    const json = await res.json()
    if (json.code === 200) {
      askHistory.value = json.data || []
    }
  } catch {
    /* 静默 */
  }
}

// ====== 点击历史：直接回显数据库存储的问答结果，不重新检索 ======
const handleHistoryClick = async (item) => {
  question.value = item.text
  try {
    const res = await authFetch(`${API_BASE}/history/${item.id}`)
    const json = await res.json()
    if (json.code === 200 && json.data.result) {
      answerResult.value = json.data.result
      return
    }
  } catch {
    /* 接口失败则回退为重新提问 */
  }
  // 旧记录无存储结果（升级前的数据），回退为重新执行提问
  handleAsk()
}

const deleteHistoryItem = async (item) => {
  try {
    const res = await authFetch(`${API_BASE}/history/${item.id}`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) {
      askHistory.value = askHistory.value.filter(h => h.id !== item.id)
    }
  } catch {
    /* 静默 */
  }
}

const clearHistory = async () => {
  try {
    const res = await authFetch(`${API_BASE}/history`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) {
      askHistory.value = []
      ElMessage.success('历史已清空')
    }
  } catch {
    /* 静默 */
  }
}

const handleKeydown = (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    handleAsk()
  }
}

// ====== 示例问题 ======
const exampleQuestions = [
  '森林火险等级如何划分？',
  '4级火险应该采取什么措施？',
  '林区封山的条件是什么？',
]

const handleExample = (ex) => {
  question.value = ex
  handleAsk()
}

// 检索方式中文标签
const retrievalMethodLabel = (m) => {
  const map = {
    hybrid: '向量 + 关键词混合',
    vector: '向量语义',
    keyword: '关键词匹配',
    none: '未命中',
  }
  return map[m] || m
}

// ====== 初始化 ======
onMounted(() => {
  fetchDocuments()
  loadHistory()
})
onUnmounted(() => {
  cleanupSpeech() // 停止语音播报/录音
})
</script>

<template>
  <div class="kb-shell">
    <!-- 页面标题 -->
    <header class="kb-header">
      <h1 class="kb-title">知识库</h1>
      <p class="kb-subtitle">上传森林防火知识文档，进行智能检索与问答</p>
    </header>

    <div class="kb-body">
      <!-- 左侧：文档管理 + 问答历史 -->
      <aside class="kb-docs" :class="{ expanded: showDocs }">
        <div class="docs-header" @click="showDocs = !showDocs" title="点击展开/收起">
          <span class="docs-title">文档管理</span>
          <span class="docs-count">{{ documents.length }}</span>
        </div>

        <!-- 上传 -->
        <div v-if="showDocs" class="upload-area">
          <el-upload
            drag
            :auto-upload="false"
            :show-file-list="false"
            accept=".pdf,.txt,.md"
            :on-change="handleUpload"
          >
            <div class="upload-inner">
              <div class="upload-icon">+</div>
              <div class="upload-text">拖拽或点击上传文档</div>
              <div class="upload-hint">支持 PDF / TXT / MD</div>
            </div>
          </el-upload>
        </div>

        <!-- 文档列表 -->
        <div v-if="showDocs" class="docs-list" v-loading="loadingDocs">
          <div v-if="documents.length === 0" class="docs-empty">
            暂无文档，请上传
          </div>
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="doc-item"
          >
            <div class="doc-info">
              <div class="doc-name">{{ doc.title }}</div>
              <div class="doc-meta">
                <span class="doc-status" :class="doc.status">{{ doc.status }}</span>
                <span class="doc-type">{{ doc.category }}</span>
              </div>
            </div>
            <button
              class="doc-delete"
              title="删除"
              @click.stop="handleDelete(doc)"
            >×</button>
          </div>
        </div>

        <!-- 问答历史 -->
        <div class="docs-header history-toggle" title="问答历史">
          <span class="docs-title">问答历史</span>
          <span class="docs-count">{{ askHistory.length }}</span>
        </div>
        <div v-if="showDocs" class="history-list">
          <div v-if="askHistory.length === 0" class="docs-empty">
            暂无提问记录
          </div>
          <div
            v-for="item in askHistory"
            :key="item.id"
            class="history-item"
            :class="{ active: item.text === question && answerResult }"
            @click="handleHistoryClick(item)"
          >
            <button
              class="doc-delete"
              title="删除"
              @click.stop="deleteHistoryItem(item)"
            >×</button>
            <div class="history-text">{{ item.text }}</div>
            <div class="history-meta">
              <span class="history-time">{{ item.time }}</span>
              <span class="history-method" :class="{ ok: item.matched > 0 }">
                {{ item.matched > 0 ? `命中 ${item.matched} 片段` : '未命中' }}
              </span>
            </div>
          </div>
          <button v-if="askHistory.length > 0" class="history-clear" @click="clearHistory">
            清空历史
          </button>
        </div>
      </aside>

      <!-- 右侧：RAG 问答 -->
      <div class="kb-qa">
        <!-- 输入区 -->
        <div class="qa-input-area">
          <div class="qa-input-row">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              placeholder="输入关于森林防火的问题..."
              class="qa-input"
              @keydown="handleKeydown"
            />
            <el-button
              type="primary"
              :loading="asking"
              @click="handleAsk"
              class="qa-btn"
            >
              提问
            </el-button>
            <el-button
              :type="recordState.recording ? 'danger' : 'default'"
              :title="recordState.recording ? '停止录音并识别' : '语音提问'"
              class="qa-mic-btn"
              @click="handleMicClick"
            >
              {{ recordState.recording ? '■ 停止' : '🎤' }}
            </el-button>
          </div>
          <div class="qa-examples">
            <span class="qa-example-label">示例：</span>
            <span
              v-for="(ex, i) in exampleQuestions"
              :key="i"
              class="qa-example-tag"
              @click="handleExample(ex)"
            >{{ ex }}</span>
          </div>
          <div class="qa-hint">Ctrl+Enter 快速提问</div>
        </div>

        <!-- 回答区 -->
      <div v-if="answerResult" class="qa-result">
        <!-- 回答正文 -->
        <div class="qa-answer">
          <div class="qa-answer-header">
            <span class="qa-answer-badge">RagAgent 回答</span>
            <span v-if="answerResult.llm_used" class="qa-llm-badge">LLM 增强</span>
            <span v-else class="qa-fallback-badge">关键词/向量检索</span>
            <el-button
              size="small"
              class="qa-speak-btn"
              :loading="speakState.loading"
              :type="speakState.speaking || speakState.loading ? 'danger' : 'default'"
              plain
              title="语音播报回答"
              @click="speakText(answerResult.answer)"
            >{{ speakState.speaking || speakState.loading ? '停止' : '🔊 播报' }}</el-button>
          </div>
          <div class="qa-answer-content">{{ answerResult.answer }}</div>
        </div>

        <!-- RagAgent 检索过程 -->
        <div v-if="answerResult.retrieval" class="qa-retrieval">
          <div class="qa-ref-header">
            <span class="qa-ref-title">RagAgent 检索过程</span>
          </div>
          <div class="qa-retrieval-body">
            <div class="qr-stat">
              <span class="qr-item">
                检索分片：<b>{{ answerResult.retrieval.total_chunks }}</b> 个
              </span>
              <span class="qr-item">
                命中片段：<b :class="answerResult.retrieval.matched_chunks > 0 ? 'ok' : 'fail'">
                  {{ answerResult.retrieval.matched_chunks }}
                </b> 个
              </span>
              <span class="qr-item">
                检索方式：<b>{{ retrievalMethodLabel(answerResult.retrieval.method) }}</b>
              </span>
              <span class="qr-item" v-if="answerResult.retrieval.vector_enabled">
                <span class="dot dot-ok"></span>向量检索已启用
              </span>
              <span class="qr-item" v-else>
                <span class="dot dot-off"></span>向量不可用（仅关键词）
              </span>
            </div>
            <div v-if="answerResult.retrieval.keywords && answerResult.retrieval.keywords.length" class="qr-keywords">
              <span class="qr-kw-label">提取关键词：</span>
              <span v-for="(kw, i) in answerResult.retrieval.keywords" :key="i" class="qr-kw">{{ kw }}</span>
            </div>
          </div>
        </div>

        <!-- 引用来源 -->
        <div
          v-if="answerResult.references && answerResult.references.length > 0"
          class="qa-references"
        >
          <div class="qa-ref-header">
            <span class="qa-ref-title">引用来源（{{ answerResult.references.length }}）</span>
          </div>
          <div class="qa-ref-list">
            <div
              v-for="(ref, i) in answerResult.references"
              :key="i"
              class="qa-ref-item"
              :class="{ active: activeSource === i }"
              @click="activeSource = activeSource === i ? null : i"
            >
              <div class="qa-ref-index">[{{ i + 1 }}]</div>
              <div class="qa-ref-body">
                <div class="qa-ref-doc">{{ ref.document_title || '未知文档' }}</div>
                <div class="qa-ref-content">{{ ref.content }}</div>
                <div class="qa-ref-scores">
                  <span class="qa-ref-score">相关性: {{ ref.score }}</span>
                  <span v-if="ref.vector_score !== undefined" class="qa-ref-score sub">向量: {{ ref.vector_score }}</span>
                  <span v-if="ref.keyword_score !== undefined" class="qa-ref-score sub">关键词: {{ ref.keyword_score }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 检索为空提示 -->
        <div v-else class="qa-no-match">
          RagAgent 在知识库中未找到相关片段，请先上传与问题相关的文档。
        </div>
      </div>

        <!-- 空状态 -->
        <div v-else class="qa-empty">
          <div class="qa-empty-icon">?</div>
          <p class="qa-empty-text">上传知识库文档后，输入问题获取智能回答</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px 24px;
  background: var(--gis-bg-deep, #020617);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}

.kb-header {
  flex-shrink: 0;
  margin-bottom: 16px;
}

.kb-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.02em;
}

.kb-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
}

.kb-body {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 16px;
}

/* ====== 左侧：文档管理 ====== */
.kb-docs {
  flex-shrink: 0;
  width: 56px;
  display: flex;
  flex-direction: column;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  overflow: hidden;
  transition: width 0.2s ease;
}

.kb-docs.expanded {
  width: 280px;
}

.docs-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 8px;
  border-bottom: 1px solid var(--gis-border, #334155);
  flex-shrink: 0;
  cursor: pointer;
  user-select: none;
}

.docs-header:hover {
  background: rgba(34, 211, 238, 0.06);
}

.docs-title {
  display: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.04em;
}

.kb-docs.expanded .docs-title {
  display: inline;
}

.docs-count {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 6px;
  background: var(--gis-accent, #0ea5e9);
  color: #020617;
  border-radius: 8px;
  font-weight: 700;
}

/* 上传区域 */
.upload-area {
  flex-shrink: 0;
  padding: 10px;
  border-bottom: 1px solid var(--gis-border, #334155);
}

.upload-area :deep(.el-upload-dragger) {
  background: rgba(2, 6, 23, 0.6) !important;
  border: 1px dashed var(--gis-border, #334155) !important;
  border-radius: 3px;
  padding: 16px;
  height: auto;
  transition: border-color 0.15s;
}

.upload-area :deep(.el-upload-dragger:hover) {
  border-color: var(--gis-accent, #0ea5e9) !important;
}

.upload-inner {
  text-align: center;
}

.upload-icon {
  font-size: 24px;
  font-weight: 300;
  color: var(--gis-accent, #0ea5e9);
  line-height: 1;
  margin-bottom: 4px;
}

.upload-text {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
}

.upload-hint {
  font-size: 9px;
  color: var(--gis-text-muted, #64748b);
  margin-top: 2px;
}

/* 文档列表 */
.docs-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

/* ====== 问答历史 ====== */
.history-toggle {
  cursor: default;
  border-top: 1px solid var(--gis-border, #334155);
}

.history-list {
  flex-shrink: 0;
  max-height: 240px;
  overflow-y: auto;
  padding: 8px;
}

.history-item {
  position: relative;
  padding: 7px 24px 7px 10px;
  border-radius: 3px;
  margin-bottom: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.history-item:hover,
.history-item.active {
  background: rgba(14, 165, 233, 0.08);
}

.history-item .doc-delete {
  position: absolute;
  top: 5px;
  right: 2px;
}

.history-text {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  line-clamp: 2;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-top: 3px;
}

.history-time {
  font-size: 9px;
  color: var(--gis-text-muted, #64748b);
  font-family: ui-monospace, "Consolas", monospace;
}

.history-method {
  font-size: 9px;
  color: var(--gis-text-muted, #94a3b8);
}

.history-method.ok {
  color: #4ade80;
}

.history-clear {
  display: block;
  width: 100%;
  margin-top: 6px;
  padding: 5px 0;
  font-size: 10px;
  color: var(--gis-text-muted, #94a3b8);
  background: transparent;
  border: 1px dashed var(--gis-border, #334155);
  border-radius: 3px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.history-clear:hover {
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.5);
}

.docs-empty {
  padding: 30px 0;
  text-align: center;
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 3px;
  margin-bottom: 4px;
  transition: background 0.15s;
}

.doc-item:hover {
  background: rgba(34, 211, 238, 0.06);
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  gap: 6px;
  margin-top: 3px;
}

.doc-status {
  font-size: 9px;
  padding: 0 4px;
  border-radius: 2px;
  text-transform: uppercase;
}

.doc-status.ready {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
}

.doc-status.processing {
  color: #facc15;
  background: rgba(250, 204, 21, 0.1);
}

.doc-status.failed {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.doc-type {
  font-size: 9px;
  color: var(--gis-text-muted, #64748b);
}

.doc-delete {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--gis-text-muted, #64748b);
  background: transparent;
  border: none;
  border-radius: 2px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.doc-delete:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

/* ====== 右侧：RAG 问答 ====== */
.kb-qa {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  gap: 12px;
  overflow-y: auto; /* 外层滚动：整列内容超高时往下滚，左侧文档/历史面板保持不动（与 Agent 中心一致） */
}

/* 输入区 */
.qa-input-area {
  flex-shrink: 0;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  padding: 14px 16px;
}

.qa-input-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.qa-input {
  flex: 1;
}

.qa-input :deep(.el-textarea__inner) {
  background: var(--gis-bg-deep, #020617) !important;
  color: var(--gis-text, #f8fafc) !important;
  border: 1px solid var(--gis-border, #334155) !important;
  border-radius: 3px;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}

.qa-input :deep(.el-textarea__inner:focus) {
  border-color: var(--gis-accent, #0ea5e9) !important;
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.15) !important;
}

.qa-btn {
  flex-shrink: 0;
  height: 74px;
  min-width: 80px;
  background: linear-gradient(135deg, #0ea5e9, #22d3ee) !important;
  border: none !important;
  color: #020617 !important;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.qa-btn:hover {
  background: linear-gradient(135deg, #38bdf8, #67e8f9) !important;
}

.qa-examples {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.qa-example-label {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  flex-shrink: 0;
}

.qa-example-tag {
  font-size: 11px;
  padding: 2px 8px;
  color: var(--gis-accent, #0ea5e9);
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid rgba(14, 165, 233, 0.2);
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s;
  white-space: nowrap;
}

.qa-example-tag:hover {
  background: rgba(14, 165, 233, 0.2);
}

.qa-hint {
  margin-top: 6px;
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  font-family: ui-monospace, "Consolas", monospace;
}

/* 回答区 */
/* 语音按钮 */
.qa-mic-btn {
  flex-shrink: 0;
  height: 62px;
  min-width: 56px;
  font-size: 17px;
}
.qa-mic-btn.is-danger {
  animation: qa-mic-pulse 1.2s ease-in-out infinite;
}
@keyframes qa-mic-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
.qa-speak-btn {
  margin-left: auto;
}
.qa-result {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  gap: 10px;
}

/* 回答正文 */
.qa-answer {
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-left: 3px solid var(--gis-accent, #0ea5e9);
  border-radius: 3px;
  padding: 14px 16px;
  flex-shrink: 0;
}

.qa-answer-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.qa-answer-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 8px;
  background: var(--gis-accent, #0ea5e9);
  color: #020617;
  border-radius: 2px;
  letter-spacing: 0.04em;
}

.qa-llm-badge {
  font-size: 9px;
  padding: 1px 6px;
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
  border-radius: 2px;
  border: 1px solid rgba(74, 222, 128, 0.3);
}

.qa-fallback-badge {
  font-size: 9px;
  padding: 1px 6px;
  background: rgba(250, 204, 21, 0.15);
  color: #facc15;
  border-radius: 2px;
  border: 1px solid rgba(250, 204, 21, 0.3);
}

.qa-answer-content {
  font-size: 13px;
  line-height: 1.7;
  color: var(--gis-text, #f8fafc);
  white-space: pre-wrap;
}

/* 引用来源 */
.qa-references {
  flex: 1 1 auto;
  min-height: 480px; /* 引用区最小高度（与 Agent 中心报告区一致），配合外层滚动条展示更多内容 */
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 3px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.qa-ref-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--gis-border, #334155);
  flex-shrink: 0;
}

/* 引用列表内部独立滚动（修复来源被截断看不到的问题） */
.qa-ref-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.qa-ref-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.04em;
}

.qa-ref-item {
  display: flex;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid rgba(51, 65, 85, 0.5);
}

.qa-ref-item:last-child {
  border-bottom: none;
}

.qa-ref-item:hover,
.qa-ref-item.active {
  background: rgba(14, 165, 233, 0.06);
}

.qa-ref-index {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: var(--gis-accent, #0ea5e9);
  font-family: ui-monospace, "Consolas", monospace;
  width: 24px;
}

.qa-ref-body {
  flex: 1;
  min-width: 0;
}

.qa-ref-content {
  font-size: 12px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  line-clamp: 3;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.qa-ref-item.active .qa-ref-content {
  -webkit-line-clamp: unset;
  line-clamp: unset;
}

.qa-ref-score {
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  margin-top: 3px;
  font-family: ui-monospace, "Consolas", monospace;
}

/* RagAgent 检索过程 */
.qa-retrieval {
  flex-shrink: 0;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-left: 3px solid rgba(250, 204, 21, 0.8);
  border-radius: 3px;
  overflow: hidden;
}

.qa-retrieval .qa-ref-header {
  border-bottom: 1px solid rgba(250, 204, 21, 0.2);
  background: rgba(250, 204, 21, 0.05);
}

.qa-retrieval-body {
  padding: 10px 14px;
}

.qr-stat {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.qr-item {
  font-size: 11px;
  color: var(--gis-text-muted, #94a3b8);
}

.qr-item b.ok {
  color: #4ade80;
}

.qr-item b.fail {
  color: #ef4444;
}

.qr-item b {
  color: var(--gis-text, #f8fafc);
}

.dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 4px;
  vertical-align: middle;
}

.dot-ok {
  background: #4ade80;
  box-shadow: 0 0 4px rgba(74, 222, 128, 0.6);
}

.dot-off {
  background: #64748b;
}

.qr-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 8px;
}

.qr-kw-label {
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  flex-shrink: 0;
}

.qr-kw {
  font-size: 10px;
  padding: 1px 6px;
  color: var(--gis-accent, #0ea5e9);
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid rgba(14, 165, 233, 0.25);
  border-radius: 8px;
}

/* 引用来源文档名 */
.qa-ref-doc {
  font-size: 10px;
  font-weight: 600;
  color: var(--gis-accent, #0ea5e9);
  margin-bottom: 3px;
}

.qa-ref-scores {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.qa-ref-score.sub {
  opacity: 0.7;
}

/* 检索为空提示 */
.qa-no-match {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
  background: var(--gis-bg-panel, #0f172a);
  border: 1px dashed var(--gis-border, #334155);
  border-radius: 3px;
}

/* 空状态 */
.qa-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
}

.qa-empty-icon {
  font-size: 48px;
  opacity: 0.3;
  color: var(--gis-text-muted, #94a3b8);
  font-family: ui-monospace, "Consolas", monospace;
}

.qa-empty-text {
  font-size: 13px;
  color: var(--gis-text-muted, #94a3b8);
  max-width: 300px;
  text-align: center;
  line-height: 1.6;
}
</style>