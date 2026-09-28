<script setup>
/**
 * 系统能力面板 — 后端 P0/P1/P2 能力一览
 *
 * 数据源: GET /api/v1/agent/capabilities（需登录，{code,message,data}）
 * 自包含：自带 loading / 失败降级提示（不抛错、不白屏）/ 可折叠（默认展开）
 */
import { ref, computed, onMounted } from 'vue'
import authFetch from '@/utils/authFetch'
import { API_V1 } from '@/utils/config'

const loading = ref(true)
const loadError = ref('')
const caps = ref(null)
const collapsed = ref(false)

// LLM 供应商友好名
const PROVIDER_NAMES = { aliyun: '阿里百炼', amd: 'AMD GPU Cloud', ollama: '本地 Ollama' }
const pname = (p) => PROVIDER_NAMES[p] || p || ''

const fetchCaps = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const res = await authFetch(`${API_V1}/agent/capabilities`)
    const json = await res.json()
    if (json.code === 200 && json.data) {
      caps.value = json.data
    } else {
      loadError.value = json.message || '接口返回异常'
    }
  } catch (e) {
    loadError.value = e.message || '网络错误'
  } finally {
    loading.value = false
  }
}

// ====== 派生视图 ======
// 折叠态摘要：一眼确认"能力已具备"
const summaryLine = computed(() => {
  const c = caps.value
  if (!c) return ''
  const parts = []
  if (c.llm) parts.push(`LLM ${pname(c.llm.active_provider)}${c.llm.available === false ? '（不可用）' : '可用'}`)
  if (c.checkpointer) parts.push(c.checkpointer.backend === 'postgres' ? 'Postgres 检查点' : '内存检查点')
  if (c.data?.dual_source) parts.push('双数据源')
  if (c.rag) parts.push(`RAG ${c.rag.retrieval || ''}`.trim())
  if (c.orchestration?.hitl?.required) parts.push('HITL')
  return parts.filter(Boolean).join(' · ')
})

// 熔断器条目：{ name, open, consecutive_failures, threshold, cooldown, remaining }
const breakerEntries = computed(() => {
  const b = caps.value?.llm?.breakers
  if (!b || typeof b !== 'object') return []
  return Object.entries(b).map(([k, v]) => ({ name: pname(k), ...(v || {}) }))
})

// 编排拓扑：拆分 '∥' 并行段为 { text, sep } 流
const topoFlow = computed(() => {
  const t = caps.value?.orchestration?.topology
  if (!Array.isArray(t)) return []
  const out = []
  t.forEach((item, i) => {
    String(item).split('∥').forEach((seg, j) => {
      out.push({ text: seg.trim(), sep: j === 0 ? (i === 0 ? '' : '→') : '∥' })
    })
  })
  return out.filter(x => x.text)
})

// 降级矩阵条目
const DEGRADE_LABELS = { llm: 'LLM', checkpointer: '检查点', rerank: 'Rerank', mcp: 'MCP', preferences: '偏好记忆' }
const degradationList = computed(() => {
  const d = caps.value?.degradation
  if (!d || typeof d !== 'object') return []
  return Object.entries(d).map(([k, v]) => ({ key: DEGRADE_LABELS[k] || k, value: String(v ?? '—') }))
})

// 数据源行
const dataSources = computed(() => (Array.isArray(caps.value?.data?.sources) ? caps.value.data.sources : []))

const yn = (v) => (v ? '✓' : '—')
const num = (v) => (v == null ? '—' : v)

onMounted(fetchCaps)
</script>

<template>
  <section class="cap-card">
    <!-- 标题条（折叠时显示摘要行，仍能一眼确认能力已具备） -->
    <div class="cap-head" @click="collapsed = !collapsed" title="点击展开/收起">
      <span class="cap-title">系统能力</span>
      <span class="cap-en">Capabilities</span>
      <span v-if="collapsed && summaryLine" class="cap-summary">{{ summaryLine }}</span>
      <span class="cap-toggle">{{ collapsed ? '展开 ▾' : '收起 ▴' }}</span>
    </div>

    <div v-if="!collapsed" class="cap-body">
      <div v-if="loading" class="cap-hint">能力清单加载中…</div>

      <div v-else-if="loadError" class="cap-error">
        <span>能力加载失败：{{ loadError }}</span>
        <button class="cap-retry" @click="fetchCaps">重试</button>
      </div>

      <template v-else-if="caps">
        <!-- 大模型 -->
        <div v-if="caps.llm" class="cap-group">
          <div class="cap-group-title">大模型</div>
          <div class="cap-chips">
            <span class="cap-chip strong">
              {{ pname(caps.llm.active_provider) }}<template v-if="caps.llm.active_model"> · {{ caps.llm.active_model }}</template>
            </span>
            <span class="cap-chip" :class="caps.llm.available === false ? 'off' : 'ok'">
              {{ caps.llm.available === false ? '不可用' : '可用' }}
            </span>
            <span class="cap-chip" :class="{ ok: caps.llm.stream_enabled }">
              {{ caps.llm.stream_enabled ? '流式开' : '流式关' }}
            </span>
            <span v-for="p in caps.llm.provider_chain || []" :key="p" class="cap-chip">{{ pname(p) }}</span>
            <span v-if="caps.llm.retry && caps.llm.retry.delays" class="cap-chip">
              重试 {{ caps.llm.retry.delays.join('/') }}s × {{ num(caps.llm.retry.max_attempts) }}
            </span>
          </div>
          <!-- 熔断器状态：状态点 + 失败计数 / 恢复倒计时 -->
          <div v-if="breakerEntries.length" class="cap-breakers">
            <div v-for="b in breakerEntries" :key="b.name" class="cap-breaker">
              <span class="cap-dot" :class="b.open ? 'open' : 'closed'"></span>
              <span class="cap-bname">{{ b.name }}</span>
              <span class="cap-bval">{{ b.open ? `熔断中 · 恢复 ${num(b.remaining)}s` : `失败 ${num(b.consecutive_failures)}/${num(b.threshold)}` }}</span>
            </div>
          </div>
        </div>

        <!-- 检查点 -->
        <div v-if="caps.checkpointer" class="cap-group">
          <div class="cap-group-title">检查点</div>
          <div class="cap-chips">
            <span class="cap-chip strong">{{ caps.checkpointer.backend === 'postgres' ? 'Postgres' : 'Memory' }}</span>
            <span class="cap-chip" :class="{ ok: caps.checkpointer.persistent }">
              {{ caps.checkpointer.persistent ? '持久化 ✓' : '非持久化' }}
            </span>
          </div>
          <div v-if="caps.checkpointer.note" class="cap-note">{{ caps.checkpointer.note }}</div>
        </div>

        <!-- 编排 -->
        <div v-if="caps.orchestration" class="cap-group">
          <div class="cap-group-title">编排</div>
          <div v-if="topoFlow.length" class="cap-topo">
            <template v-for="(t, i) in topoFlow" :key="i">
              <span v-if="t.sep" class="cap-topo-sep" :class="{ par: t.sep === '∥' }">{{ t.sep }}</span>
              <span class="cap-topo-chip">{{ t.text }}</span>
            </template>
          </div>
          <div class="cap-chips">
            <span v-if="caps.orchestration.framework" class="cap-chip strong">{{ caps.orchestration.framework }}</span>
            <span v-if="caps.orchestration.plan_driven_routing" class="cap-chip">计划驱动路由</span>
            <span v-if="caps.orchestration.parallel_fanout" class="cap-chip">并行 Fan-out</span>
            <span v-if="caps.orchestration.reflection_retry" class="cap-chip">
              反思重试 ≤{{ num(caps.orchestration.reflection_retry.max_rounds) }} 轮
            </span>
            <span v-if="caps.orchestration.review_loop" class="cap-chip">
              评审循环 ≤{{ num(caps.orchestration.review_loop.max_revisions) }} 轮 · 底线 {{ num(caps.orchestration.review_loop.hard_guardrail_min_chars) }} 字
            </span>
            <span v-if="caps.orchestration.hitl && caps.orchestration.hitl.required" class="cap-chip warn">
              HITL：{{ (caps.orchestration.hitl.actions || []).join('/') || '审批' }}
            </span>
            <span v-if="caps.orchestration.node_progress_sse" class="cap-chip ok">节点级 SSE</span>
          </div>
        </div>

        <!-- 数据源 -->
        <div v-if="caps.data" class="cap-group">
          <div class="cap-group-title">数据源</div>
          <div class="cap-chips">
            <span v-if="caps.data.dual_source" class="cap-chip ok">双数据源</span>
            <span v-if="caps.data.gis" class="cap-chip">GIS 历史 {{ yn(caps.data.gis.historical) }} · 预测 {{ yn(caps.data.gis.predicted) }}</span>
          </div>
          <div v-for="(s, i) in dataSources" :key="i" class="cap-row">
            <span class="cap-row-label">{{ s.label || s.table }}</span>
            <span class="cap-row-val">{{ s.range || '' }}</span>
            <span v-if="s.source_tag" class="cap-chip tiny">{{ s.source_tag }}</span>
          </div>
        </div>

        <!-- 知识检索 RAG -->
        <div v-if="caps.rag" class="cap-group">
          <div class="cap-group-title">知识检索 RAG</div>
          <div class="cap-chips">
            <span v-if="caps.rag.embedding_model" class="cap-chip strong">{{ caps.rag.embedding_model }}</span>
            <span v-if="caps.rag.retrieval" class="cap-chip">{{ caps.rag.retrieval }}</span>
            <span v-if="caps.rag.rerank" class="cap-chip" :class="{ ok: caps.rag.rerank.enabled }">
              {{ caps.rag.rerank.enabled ? `Rerank ${caps.rag.rerank.model || ''}${caps.rag.rerank.fallback ? ' · 可兜底' : ''}` : 'Rerank 关' }}
            </span>
            <span v-if="caps.rag.top_k != null" class="cap-chip">Top {{ caps.rag.top_k }}</span>
            <span v-if="caps.rag.documents != null" class="cap-chip">文档 {{ caps.rag.documents }} 篇</span>
            <span v-if="caps.rag.citation" class="cap-chip">引用标注</span>
            <span v-if="caps.rag.stream" class="cap-chip">流式</span>
          </div>
        </div>

        <!-- 偏好记忆 / MCP / 观测 -->
        <div v-if="caps.memory || caps.mcp || caps.observability" class="cap-group">
          <div class="cap-group-title">记忆 · 工具 · 观测</div>
          <div class="cap-chips">
            <template v-if="caps.memory">
              <span class="cap-chip" :class="{ ok: caps.memory.preferences_enabled }">
                偏好记忆 {{ caps.memory.preferences_enabled ? '开' : '关' }}
              </span>
              <span v-if="caps.memory.store" class="cap-chip">存储 {{ caps.memory.store }}</span>
              <span v-if="caps.memory.inject" class="cap-chip">注入 {{ caps.memory.inject }}</span>
            </template>
            <template v-if="caps.mcp">
              <span class="cap-chip" :class="{ ok: caps.mcp.enabled }">MCP {{ caps.mcp.enabled ? '开' : '关' }}</span>
              <span v-for="(sv, i) in caps.mcp.servers || []" :key="'mcp' + i" class="cap-chip">{{ typeof sv === 'string' ? sv : (sv.name || JSON.stringify(sv)) }}</span>
              <span v-if="caps.mcp.fallback" class="cap-chip">兜底 {{ caps.mcp.fallback }}</span>
            </template>
            <template v-if="caps.observability">
              <span class="cap-chip" :class="{ ok: caps.observability.langfuse_enabled }">
                Langfuse {{ caps.observability.langfuse_enabled ? '开' : '关' }}
              </span>
              <span v-if="caps.observability.fallback" class="cap-chip">兜底 {{ caps.observability.fallback }}</span>
            </template>
          </div>
        </div>

        <!-- 评估回归 -->
        <div v-if="caps.evaluation" class="cap-group">
          <div class="cap-group-title">评估回归</div>
          <div class="cap-chips">
            <span v-if="caps.evaluation.golden_cases != null" class="cap-chip strong">金标 {{ caps.evaluation.golden_cases }} 例</span>
            <span v-for="(m, i) in caps.evaluation.metrics || []" :key="'m' + i" class="cap-chip">{{ m }}</span>
            <span v-for="(m, i) in caps.evaluation.modes || []" :key="'md' + i" class="cap-chip">{{ m }}</span>
          </div>
        </div>

        <!-- 降级矩阵 -->
        <div v-if="degradationList.length" class="cap-group">
          <div class="cap-group-title">降级矩阵</div>
          <div class="cap-chips">
            <span v-for="d in degradationList" :key="d.key" class="cap-chip">{{ d.key }} → {{ d.value }}</span>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.cap-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--gis-glass);
  backdrop-filter: blur(var(--gis-glass-blur)) saturate(var(--gis-glass-saturate));
  border: 1px solid var(--gis-glass-border);
  box-shadow: inset 0 1px 0 var(--gis-glass-highlight);
  border-radius: var(--gis-radius-md, 10px);
  overflow: hidden;
  animation: cap-in 0.35s ease both;
}

@keyframes cap-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

.cap-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--gis-border, #334155);
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.cap-head::before {
  content: '';
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--gis-accent, #0ea5e9);
  box-shadow: var(--gis-glow);
  flex-shrink: 0;
}

.cap-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.03em;
}

.cap-summary {
  flex: 1;
  min-width: 0;
  font-size: 10px;
  color: var(--gis-text-muted, #94a3b8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cap-toggle {
  margin-left: auto;
  font-size: 10px;
  color: var(--gis-text-muted, #94a3b8);
  flex-shrink: 0;
}

.cap-head:not(:hover) .cap-toggle {
  opacity: 0.6;
}

.cap-body {
  padding: 10px 14px;
  overflow-y: auto;
  /* 由父级卡片高度约束（flex:1 填满右列），内容超高时卡片内滚动 */
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cap-hint {
  font-size: 11px;
  color: var(--gis-text-muted, #94a3b8);
  padding: 8px 0;
}

.cap-error {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #f87171;
  padding: 6px 0;
}

.cap-retry {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 8px;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-hover-tint);
  border: 1px solid var(--gis-accent-dim);
  border-radius: 8px;
  cursor: pointer;
}

.cap-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cap-group-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--gis-text-muted, #94a3b8);
  letter-spacing: 0.06em;
}

.cap-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cap-chip {
  font-size: 10px;
  line-height: 1.6;
  padding: 0 7px;
  border-radius: 8px;
  white-space: nowrap;
  color: var(--gis-text, #f8fafc);
  background: var(--gis-hover-tint);
  border: 1px solid var(--gis-border, #334155);
}

.cap-chip.strong {
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft);
  border-color: var(--gis-accent-dim);
  font-weight: 600;
}

.cap-chip.ok {
  color: #4ade80;
  border-color: rgba(74, 222, 128, 0.3);
}

.cap-chip.off,
.cap-chip.warn {
  color: #facc15;
  border-color: rgba(250, 204, 21, 0.3);
}

.cap-chip.off {
  color: #f87171;
  border-color: rgba(248, 113, 113, 0.3);
}

.cap-chip.tiny {
  font-size: 9px;
  padding: 0 5px;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft);
  border-color: var(--gis-accent-dim);
}

.cap-note {
  font-size: 10px;
  line-height: 1.5;
  color: var(--gis-text-muted, #94a3b8);
}

/* 编排拓扑流 */
.cap-topo {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.cap-topo-chip {
  font-size: 9px;
  padding: 0 6px;
  border-radius: 7px;
  color: var(--gis-text, #f8fafc);
  background: var(--gis-glass-2);
  border: 1px solid var(--gis-border, #334155);
  font-family: ui-monospace, "Consolas", monospace;
}

.cap-topo-sep {
  font-size: 9px;
  color: var(--gis-text-muted, #94a3b8);
}

.cap-topo-sep.par {
  color: var(--gis-accent, #0ea5e9);
  font-weight: 700;
}

/* 数据源行 */
.cap-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  line-height: 1.6;
}

.cap-row-label {
  color: var(--gis-text, #f8fafc);
  font-weight: 600;
  flex-shrink: 0;
}

.cap-row-val {
  color: var(--gis-text-muted, #94a3b8);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 熔断器 */
.cap-breakers {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 8px;
  background: var(--gis-bg-deep);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 6px;
}

.cap-breaker {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  line-height: 1.6;
}

.cap-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.cap-dot.closed {
  background: #4ade80;
  box-shadow: 0 0 4px rgba(74, 222, 128, 0.5);
}

.cap-dot.open {
  background: #f87171;
  box-shadow: 0 0 4px rgba(248, 113, 113, 0.5);
  animation: cap-blink 1.2s ease-in-out infinite;
}

@keyframes cap-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

.cap-bname {
  color: var(--gis-text, #f8fafc);
  font-weight: 600;
  flex-shrink: 0;
}

.cap-bval {
  margin-left: auto;
  color: var(--gis-text-muted, #94a3b8);
  font-family: ui-monospace, "Consolas", monospace;
}
</style>
