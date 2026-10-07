<script setup>
/**
 * 系统管理页 — 数据源配置 / 模型接入 / Agent 参数管理 / 系统日志 / 用户权限管理
 *
 * 后端 API: /api/v1/admin/*（需登录，用户管理需管理员）
 */
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Connection, Monitor, Setting, Document, CircleCheck, CircleClose, Promotion, Cpu, User } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { API_V1 } from '@/utils/config'
import { useRouter } from 'vue-router'

const API_BASE = `${API_V1}/admin`
const auth = useAuthStore()
const router = useRouter()


// 带鉴权的 fetch：自动附加 token，401 时回登录页
const authFetch = async (url, options = {}) => {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401) {
    auth.logout()
    router.replace('/login')
    throw new Error('登录已过期')
  }
  return res
}

// ====== 状态 ======
const activeTab = ref('overview')
const status = ref(null)
const config = ref(null)
const logs = ref([])
const loadingStatus = ref(false)
const loadingLogs = ref(false)

// ====== 可编辑配置表单 ======
const configForm = reactive({
  active_provider: 'aliyun',
  // 阿里云
  llm_api_key: '',
  llm_api_base: '',
  llm_model: '',
  embedding_model: '',
  // 视觉 / 语音模型
  vision_provider: 'aliyun',
  vision_model: '',
  asr_model: '',
  tts_model: '',
  // AMD GPU Cloud
  amd_api_key: '',
  amd_api_base: 'https://developer.amd.com.cn/radeon/v1',
  amd_model: 'DeepSeek-V4-Flash',
  qwen3_8_flash_start: '',
  qwen3_8_flash_end: '',
  // 本地 Ollama（无需 API Key）
  ollama_api_base: 'http://localhost:11434/v1',
  ollama_model: 'qwen2.5:7b',
  longcat_api_key: '',
  longcat_api_base: 'https://api.longcat.chat/openai',
  longcat_model: 'LongCat-2.5-Preview',
  // 知识库
  kb_chunk_size: 500,
  kb_chunk_overlap: 50,
  kb_top_k: 5,
})

// ====== Agent 参数表单 ======
const agentForm = reactive({
  orchestrator_temperature: 0.2,
  report_temperature: 0.4,
  max_agents: 5,
})

// ====== 测试结果 ======
const testDb = ref(null) // { ok, detail } | null
const testLlm = ref(null)
const testing = ref(false)

// ====== 拉取系统状态 ======
const fetchStatus = async () => {
  loadingStatus.value = true
  try {
    const res = await authFetch(`${API_BASE}/status`)
    const json = await res.json()
    if (json.code === 200) status.value = json.data
  } catch {
    ElMessage.error('获取系统状态失败')
  } finally {
    loadingStatus.value = false
  }
}

// ====== 拉取配置 ======
const fetchConfig = async () => {
  try {
    const res = await authFetch(`${API_BASE}/config`)
    const json = await res.json()
    if (json.code === 200) {
      config.value = json.data
      const m = json.data.model || {}
      Object.assign(configForm, {
        active_provider: m.active_provider || 'aliyun',
        // 阿里云
        llm_api_base: m.llm_api_base || '',
        llm_model: m.llm_model || '',
        embedding_model: m.embedding_model || '',
        vision_provider: m.vision_provider || 'aliyun',
        vision_model: m.vision_model || '',
        asr_model: m.asr_model || '',
        tts_model: m.tts_model || '',
        // AMD
        amd_api_base: m.amd_api_base || 'https://developer.amd.com.cn/radeon/v1',
        amd_model: m.amd_model || 'DeepSeek-V4-Flash',
        qwen3_8_flash_start: m.qwen3_8_flash_start || '',
        qwen3_8_flash_end: m.qwen3_8_flash_end || '',
        // Ollama
        ollama_api_base: m.ollama_api_base || 'http://localhost:11434/v1',
        ollama_model: m.ollama_model || 'qwen2.5:7b',
        // longcat_api_key 不回填（后端返回的是脱敏值，回填后再保存会把掩码当真实密钥写回）
        longcat_api_base: m.longcat_api_base || 'https://api.longcat.chat/openai',
        longcat_model: m.longcat_model || 'LongCat-2.5-Preview',
        // 知识库
        kb_chunk_size: json.data.rag?.kb_chunk_size || 500,
        kb_chunk_overlap: json.data.rag?.kb_chunk_overlap || 50,
        kb_top_k: json.data.rag?.kb_top_k || 5,
      })
      Object.assign(agentForm, json.data.agent || {})
    }
  } catch {
    ElMessage.error('获取配置失败')
  }
}

// ====== 拉取日志 ======
const fetchLogs = async () => {
  loadingLogs.value = true
  try {
    const res = await authFetch(`${API_BASE}/logs?limit=100`)
    const json = await res.json()
    if (json.code === 200) logs.value = json.data
  } catch {
    ElMessage.error('获取日志失败')
  } finally {
    loadingLogs.value = false
  }
}

// ====== Qwen3.8 可用性状态 ======
const qwen3_8Status = computed(() => {
  const start = configForm.qwen3_8_flash_start
  const end = configForm.qwen3_8_flash_end
  if (!start || !end) return { text: '未配置时间窗口（默认可用）', cls: 'gray' }
  try {
    const now = new Date()
    const s = new Date(start.replace(' ', 'T'))
    const e = new Date(end.replace(' ', 'T'))
    if (now >= s && now <= e) return { text: '可用', cls: 'ok' }
    if (now < s) return { text: '尚未到可用时间', cls: 'warn' }
    return { text: '已过期', cls: 'fail' }
  } catch {
    return { text: '时间格式错误', cls: 'fail' }
  }
})

// ====== AMD GPU Cloud 模型列表（动态获取 + 计费层级） ======
const amdModelList = ref(null) // { fetch_ok, available_count, current_model, models, key_info }
const loadingAmdModels = ref(false)
const amdCategory = ref('text') // 分类 Tab：text/vision

const amdCategoryTabs = [
  { key: 'text', label: '大语言模型' },
  { key: 'vision', label: '视觉模型' },
]

// 当前分类下的 AMD 模型（后端已按 免费优先 排好序）
const filteredAmdModels = computed(() => {
  if (!amdModelList.value) return []
  return amdModelList.value.models.filter(m => m.category === amdCategory.value)
})

// 各分类数量徽标
const amdCategoryCount = (key) => {
  if (!amdModelList.value) return 0
  return amdModelList.value.models.filter(m => m.category === key).length
}

const fetchAmdModels = async () => {
  loadingAmdModels.value = true
  try {
    const res = await authFetch(`${API_BASE}/llm/models?provider=amd`)
    const json = await res.json()
    if (json.code === 200) {
      amdModelList.value = json.data
      if (!json.data.fetch_ok) {
        if (json.data.key_info?.directory_ok) {
          ElMessage.warning('已获取 AMD 官方模型目录，但 /models 校验失败（请检查 API Key），可用性标记仅供参考')
        } else {
          ElMessage.warning('AMD 官方目录与 /models 均拉取失败，请检查网络与 API Key')
        }
      } else {
        ElMessage.success(`已获取 ${json.data.available_count} 个可用模型`)
      }
    } else {
      ElMessage.error('获取 AMD 模型列表失败')
    }
  } catch {
    ElMessage.error('获取 AMD 模型列表失败')
  } finally {
    loadingAmdModels.value = false
  }
}

// AMD 计费层级标签（free=免费 / limited_free=限时免费 / paid=付费专属实例）
const tierTag = (tier) => ({
  free: { text: '免费', type: 'success' },
  limited_free: { text: '限时免费', type: 'warning' },
  paid: { text: '付费', type: 'danger' },
}[tier] || { text: '未知', type: 'info' })

// 一键切换 AMD 模型：text→AMD_MODEL；vision→vision_provider='amd' + VISION_MODEL
// 均写 .env 热生效，无需重启
const applyAmdModel = async (mid, category = 'text') => {
  let payload, label
  if (category === 'vision') {
    payload = { active_provider: 'amd', vision_provider: 'amd', vision_model: mid }
    label = '视觉识别'
  } else {
    payload = { active_provider: 'amd', amd_model: mid }
    label = 'Chat'
  }
  try {
    const res = await authFetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const json = await res.json()
    if (json.code === 200) {
      if (category === 'vision') {
        configForm.vision_provider = 'amd'
        configForm.vision_model = mid
        if (amdModelList.value?.key_info) {
          amdModelList.value.key_info.vision_provider = 'amd'
          amdModelList.value.key_info.vision_model = mid
        }
      } else {
        configForm.amd_model = mid
        if (amdModelList.value?.key_info) amdModelList.value.key_info.current_model = mid
      }
      if (amdModelList.value) {
        amdModelList.value.models = amdModelList.value.models.map(m => {
          // 同分类的模型互斥更新"当前"标记
          const sameSlot = m.category === category
          return sameSlot ? { ...m, is_current: m.id === mid } : m
        })
      }
      ElMessage.success(`已切换${label}模型：${mid}（已写入 .env 并热生效）`)
      fetchStatus()
    } else {
      ElMessage.error('切换失败')
    }
  } catch {
    ElMessage.error('切换失败')
  }
}

// ====== LongCat 模型列表（官方静态目录，仅 LLM） ======
const longcatModelList = ref(null) // { fetch_ok, available_count, current_model, models, key_info }
const loadingLongcatModels = ref(false)

const fetchLongcatModels = async () => {
  loadingLongcatModels.value = true
  try {
    const res = await authFetch(`${API_BASE}/llm/models?provider=longcat`)
    const json = await res.json()
    if (json.code === 200) {
      longcatModelList.value = json.data
      if (!json.data.fetch_ok) {
        ElMessage.warning('已获取 LongCat 官方目录，但 /models 校验失败（请检查 API Key），可用性标记仅供参考')
      } else {
        ElMessage.success(`已获取 ${json.data.available_count} 个可用模型`)
      }
    } else {
      ElMessage.error('获取 LongCat 模型列表失败')
    }
  } catch {
    ElMessage.error('获取 LongCat 模型列表失败')
  } finally {
    loadingLongcatModels.value = false
  }
}

// 一键切换 LongCat 模型（仅 Chat 槽位）：写 .env 热生效
const applyLongcatModel = async (mid) => {
  try {
    const res = await authFetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active_provider: 'longcat', longcat_model: mid }),
    })
    const json = await res.json()
    if (json.code === 200) {
      configForm.longcat_model = mid
      if (longcatModelList.value) {
        longcatModelList.value.models = longcatModelList.value.models.map(m => ({
          ...m, is_current: m.id === mid,
        }))
        if (longcatModelList.value.key_info) longcatModelList.value.key_info.current_model = mid
      }
      ElMessage.success(`已切换 Chat 模型：${mid}（已写入 .env 并热生效）`)
      fetchStatus()
    } else {
      ElMessage.error('切换失败')
    }
  } catch {
    ElMessage.error('切换失败')
  }
}

// ====== 百炼模型列表 ======
const modelList = ref(null) // { fetch_ok, available_count, current_model, categories, models, key_info }
const loadingModels = ref(false)
const modelCategory = ref('text') // 分类 Tab：text/vision/multimodal/audio/embedding

const categoryTabs = [
  { key: 'text', label: '大语言模型' },
  { key: 'vision', label: '视觉模型' },
  { key: 'multimodal', label: '全模态模型' },
  { key: 'audio', label: '语音模型' },
  { key: 'embedding', label: '向量模型' },
]

// 当前分类下的模型（免费在前、有效期长在前，后端已排好序）
const filteredModels = computed(() => {
  if (!modelList.value) return []
  return modelList.value.models.filter(m => m.category === modelCategory.value)
})

// 各分类数量徽标
const categoryCount = (key) => {
  if (!modelList.value) return 0
  return modelList.value.models.filter(m => m.category === key).length
}

// 模型列表展开/收起（避免占位过大）
const modelListVisible = ref(false)

const fetchFreeModels = async () => {
  loadingModels.value = true
  try {
    const res = await authFetch(`${API_BASE}/llm/models?provider=aliyun`)
    const json = await res.json()
    if (json.code === 200) {
      modelList.value = json.data
      modelListVisible.value = true
      if (!json.data.fetch_ok) {
        if (json.data.key_info?.directory_ok) {
          ElMessage.warning('已解析官方免费额度目录，但 /models 校验失败（请检查 API Key），可用性标记仅供参考')
        } else {
          ElMessage.warning('官方目录与 /models 均拉取失败，展示内置免费额度目录（未经可用性校验）')
        }
      } else {
        ElMessage.success(`已获取 ${json.data.available_count} 个可用模型（免费额度目录 ${json.data.key_info.free_count} 个）`)
      }
    } else {
      ElMessage.error('获取模型列表失败')
    }
  } catch {
    ElMessage.error('获取模型列表失败')
  } finally {
    loadingModels.value = false
  }
}

// ====== 百炼账号免费额度（静态内置快照） ======
const bailianQuota = ref(null) // { ok, rows, counts, total, snapshot_date }
const loadingBailianQuota = ref(false)

// 加载账号免费额度（静态数据，剩余量/过期时间/状态）
const fetchBailianQuota = async () => {
  loadingBailianQuota.value = true
  try {
    const res = await authFetch(`${API_BASE}/bailian/quota`)
    const json = await res.json()
    if (json.data?.ok) {
      bailianQuota.value = json.data
      quotaVisible.value = true
      ElMessage.success(`已加载 ${json.data.total} 条账号免费额度（快照 ${json.data.snapshot_date}）`)
    } else {
      bailianQuota.value = json.data || { ok: false, rows: [] }
      ElMessage.warning('加载失败')
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loadingBailianQuota.value = false
  }
}

// 过期时间临近提醒（30 天内标橙）
const isExpiringSoon = (expire) => {
  if (!expire) return false
  const t = new Date(expire.replace(/-/g, '/')).getTime()
  if (Number.isNaN(t)) return false
  return t - Date.now() < 30 * 86400 * 1000
}

// ====== 额度快照：展开/收起、分类 Tab、用途映射、按过期时间排序 ======
const quotaVisible = ref(false)
const quotaCategory = ref('all')

const quotaTabs = [
  { key: 'all', label: '全部' },
  { key: 'text', label: '语言模型' },
  { key: 'vision', label: '视觉模型' },
  { key: 'multimodal', label: '全模态' },
  { key: 'audio', label: '语音模型' },
  { key: 'embedding', label: '向量模型' },
]

const quotaTabCount = (key) => {
  if (!bailianQuota.value?.ok) return 0
  return key === 'all'
    ? bailianQuota.value.rows.length
    : bailianQuota.value.rows.filter(r => r.category === key).length
}

// 用途映射：「使用」按钮写入哪个配置槽；null = 系统暂不支持（按钮禁用）
const quotaUsage = (row) => {
  const m = row.model || ''
  if (row.category === 'text') {
    return { field: 'llm_model', usage: 'chat', label: '对话模型' }
  }
  if (row.category === 'embedding') {
    return m.includes('rerank')
      ? null
      : { field: 'embedding_model', usage: 'embedding', label: '向量模型' }
  }
  if (row.category === 'audio') {
    if (/tts|sambert|cosyvoice/i.test(m)) return { field: 'tts_model', usage: 'tts', label: '语音合成 (TTS)' }
    if (/asr|paraformer|fun-asr/i.test(m)) return { field: 'asr_model', usage: 'asr', label: '语音识别 (ASR)' }
  }
  return null
}

// 说明列：用途去向或暂不支持原因
const quotaRemark = (row) => {
  const u = quotaUsage(row)
  if (u) return `点击使用 → 设为${u.label}`
  if (row.category === 'embedding') return '重排序模型，系统暂不支持'
  return '生图 / 视频生成模型，系统暂不支持'
}

// 当前使用标记（与配置槽比对）
const quotaIsCurrent = (row) => {
  const u = quotaUsage(row)
  return !!u && configForm[u.field] === row.model
}

// 排序：谁先过期谁在前面（2099 永久额度排最后）
const filteredQuotaRows = computed(() => {
  if (!bailianQuota.value?.ok) return []
  let rows = [...bailianQuota.value.rows]
  if (quotaCategory.value !== 'all') rows = rows.filter(r => r.category === quotaCategory.value)
  const t = (s) => {
    const v = new Date(String(s || '').replace(/-/g, '/')).getTime()
    return Number.isNaN(v) ? 8.64e15 : v
  }
  return rows.sort((a, b) => t(a.expire) - t(b.expire) || a.model.localeCompare(b.model))
})

// 一键切换模型：写 .env 热生效，无需重启
// text→Chat / embedding→Embedding / vision·multimodal→视觉 / audio→ASR·TTS（按 usage）
const applyModel = async (mid, category = 'text', usage = '') => {
  let field, label, extra = null
  if (category === 'embedding') {
    field = 'embedding_model'; label = 'Embedding'
  } else if (category === 'vision' || category === 'multimodal') {
    field = 'vision_model'; label = '视觉识别'
    extra = { vision_provider: 'aliyun' } // 视觉切回百炼
  } else if (category === 'audio') {
    if (usage === 'tts') { field = 'tts_model'; label = '语音合成' }
    else { field = 'asr_model'; label = '语音识别' }
  } else {
    field = 'llm_model'; label = 'Chat'
  }
  try {
    const res = await authFetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active_provider: 'aliyun', [field]: mid, ...(extra || {}) }),
    })
    const json = await res.json()
    if (json.code === 200) {
      if (configForm[field] !== undefined) configForm[field] = mid
      if (extra && configForm.vision_provider !== undefined) configForm.vision_provider = 'aliyun'
      if (modelList.value) {
        modelList.value.models = modelList.value.models.map(m => {
          // 同用途的模型互斥更新"当前"标记
          const sameSlot = (m.category === category) && (m.category !== 'audio' || m.usage === usage)
          return sameSlot ? { ...m, is_current: m.id === mid } : m
        })
        if (modelList.value.key_info) modelList.value.key_info[field] = mid
      }
      ElMessage.success(`已切换${label}模型：${mid}（已写入 .env 并热生效）`)
      fetchStatus()
    } else {
      ElMessage.error('切换失败')
    }
  } catch {
    ElMessage.error('切换失败')
  }
}

// ====== 保存配置 ======
const saveConfig = async () => {
  const payload = {
    active_provider: configForm.active_provider,
    // 阿里云字段
    llm_api_key: configForm.llm_api_key.trim() || null,
    llm_api_base: configForm.llm_api_base.trim() || null,
    llm_model: configForm.llm_model.trim() || null,
    embedding_model: configForm.embedding_model.trim() || null,
    // AMD 字段
    amd_api_key: configForm.amd_api_key.trim() || null,
    amd_api_base: configForm.amd_api_base.trim() || null,
    amd_model: configForm.amd_model,
    qwen3_8_flash_start: configForm.qwen3_8_flash_start.trim() || null,
    qwen3_8_flash_end: configForm.qwen3_8_flash_end.trim() || null,
    // Ollama 字段
    ollama_api_base: configForm.ollama_api_base.trim() || null,
    ollama_model: configForm.ollama_model.trim() || null,
    longcat_api_key: configForm.longcat_api_key.trim() || null,
    longcat_api_base: configForm.longcat_api_base.trim() || null,
    longcat_model: configForm.longcat_model.trim() || null,
    // 知识库
    kb_chunk_size: Number(configForm.kb_chunk_size),
    kb_chunk_overlap: Number(configForm.kb_chunk_overlap),
    kb_top_k: Number(configForm.kb_top_k),
  }
  try {
    const res = await authFetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const json = await res.json()
    if (json.code === 200) {
      ElMessage.success('模型/知识库配置已保存')
      fetchConfig()
      fetchStatus()
    } else {
      ElMessage.error('保存失败')
    }
  } catch {
    ElMessage.error('保存失败')
  }
}

// ====== 保存 Agent 参数 ======
const saveAgent = async () => {
  try {
    const res = await authFetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        orchestrator_temperature: Number(agentForm.orchestrator_temperature),
        report_temperature: Number(agentForm.report_temperature),
        max_agents: Number(agentForm.max_agents),
      }),
    })
    const json = await res.json()
    if (json.code === 200) {
      ElMessage.success('Agent 参数已保存')
      fetchConfig()
    }
  } catch {
    ElMessage.error('保存失败')
  }
}

// ====== 测试连接 ======
const testDatabase = async () => {
  testing.value = true
  testDb.value = null
  try {
    const res = await authFetch(`${API_BASE}/test/db`, { method: 'POST' })
    const json = await res.json()
    testDb.value = json.data
  } finally {
    testing.value = false
  }
}

const testLlmConn = async () => {
  testing.value = true
  testLlm.value = null
  try {
    const res = await authFetch(`${API_BASE}/test/llm`, { method: 'POST' })
    const json = await res.json()
    testLlm.value = json.data
  } finally {
    testing.value = false
  }
}

// ====== 用户管理（仅管理员） ======
const users = ref([])
const loadingUsers = ref(false)

const fetchUsers = async () => {
  loadingUsers.value = true
  try {
    const res = await authFetch(`${API_BASE}/users`)
    const json = await res.json()
    if (res.status === 403) {
      ElMessage.warning(json.detail || '需要管理员权限')
      users.value = []
      return
    }
    if (json.code === 200) users.value = json.data
  } catch {
    /* authFetch 已处理 401 */
  } finally {
    loadingUsers.value = false
  }
}

const changeRole = async (u, role) => {
  try {
    const res = await authFetch(`${API_BASE}/users/${u.id}/role`, {
      method: 'PUT',
      body: JSON.stringify({ role }),
    })
    const json = await res.json()
    if (res.ok && json.code === 200) {
      ElMessage.success(`已将 ${u.username} 的角色改为 ${role === 'admin' ? '管理员' : '普通用户'}`)
      fetchUsers()
      fetchLogs()
    } else {
      ElMessage.error(json.detail || '修改失败')
      fetchUsers()
    }
  } catch {
    fetchUsers()
  }
}

const removeUser = async (u) => {
  try {
    await ElMessageBox.confirm(
      `确定删除用户「${u.username}」吗？该操作不可恢复`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const res = await authFetch(`${API_BASE}/users/${u.id}`, { method: 'DELETE' })
    const json = await res.json()
    if (res.ok && json.code === 200) {
      ElMessage.success('用户已删除')
      fetchUsers()
      fetchLogs()
    } else {
      ElMessage.error(json.detail || '删除失败')
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

const roleLabel = (r) => (r === 'admin' ? '管理员' : '普通用户')

// ====== 日志等级样式 ======
const levelClass = (lv) => {
  if (lv === 'ERROR') return 'level-error'
  if (lv === 'WARN') return 'level-warn'
  return 'level-info'
}

// ====== 初始化 ======
let logsTimer = null
onMounted(() => {
  fetchStatus()
  fetchConfig()
  fetchLogs()
  // 管理员才拉取用户列表
  if (auth.user?.role === 'admin') {
    activeTab.value = 'overview'
  }
  // 每 30 秒刷新日志
  logsTimer = setInterval(fetchLogs, 30000)
})
onUnmounted(() => {
  if (logsTimer) clearInterval(logsTimer)
})
</script>

<template>
  <div class="admin-shell">
    <header class="admin-header">
      <h1 class="admin-title">系统管理</h1>
      <p class="admin-subtitle">数据源配置、模型接入、Agent 参数管理、系统日志</p>
    </header>

    <!-- Tab 导航 -->
    <div class="admin-tabs">
      <button class="atab" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">
        <el-icon><Monitor /></el-icon> 系统总览
      </button>
      <button class="atab" :class="{ active: activeTab === 'datasource' }" @click="activeTab = 'datasource'">
        <el-icon><Connection /></el-icon> 数据源
      </button>
      <button class="atab" :class="{ active: activeTab === 'model' }" @click="activeTab = 'model'">
        <el-icon><Setting /></el-icon> 模型接入
      </button>
      <button class="atab" :class="{ active: activeTab === 'agent' }" @click="activeTab = 'agent'">
        <el-icon><Document /></el-icon> Agent 参数
      </button>
      <button class="atab" :class="{ active: activeTab === 'logs' }" @click="activeTab = 'logs'">
        <el-icon><Refresh /></el-icon> 系统日志
      </button>
      <button v-if="auth.user?.role === 'admin'" class="atab" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'; fetchUsers()">
        <el-icon><User /></el-icon> 用户管理
      </button>
    </div>

    <!-- ====== 系统总览 ====== -->
    <div v-if="activeTab === 'overview'" v-loading="loadingStatus" class="admin-panel">
      <div v-if="status" class="overview-grid">
        <div class="overview-card">
          <div class="oc-label">项目名称</div>
          <div class="oc-value">{{ status.project }}</div>
        </div>
        <div class="overview-card">
          <div class="oc-label">版本</div>
          <div class="oc-value">{{ status.version }}</div>
        </div>
        <div class="overview-card">
          <div class="oc-label">数据库</div>
          <div class="oc-value">
            <el-icon v-if="status.database === 'connected'" style="color:#4ade80"><CircleCheck /></el-icon>
            <el-icon v-else style="color:#ef4444"><CircleClose /></el-icon>
            {{ status.database === 'connected' ? '已连接' : '未连接' }}
          </div>
        </div>
        <div class="overview-card">
          <div class="oc-label">大模型</div>
          <div class="oc-value">
            <el-icon v-if="status.llm_available" style="color: var(--el-color-success, #4ade80)"><CircleCheck /></el-icon>
            <el-icon v-else style="color: var(--gis-text-muted, #94a3b8)"><CircleClose /></el-icon>
            {{ status.llm_available ? status.llm_model : '未配置' }}
          </div>
        </div>
      </div>

      <!-- Agent 状态 -->
      <div class="block-title">Agent 运行状态</div>
      <div class="agent-grid">
        <div v-for="a in (status?.agents || [])" :key="a.name" class="agent-card">
          <div class="agent-name">{{ a.name }}</div>
          <div class="agent-framework">{{ a.framework }}</div>
          <span class="agent-status">{{ a.status }}</span>
        </div>
      </div>
    </div>

    <!-- ====== 数据源 ====== -->
    <div v-else-if="activeTab === 'datasource'" class="admin-panel">
      <div class="panel-title">
        <el-icon><Connection /></el-icon>
        数据源配置
        <el-button size="small" style="margin-left:auto" :icon="Refresh" @click="fetchStatus">刷新</el-button>
      </div>

      <div v-if="config" class="ds-card">
        <div class="ds-row">
          <span class="ds-label">数据库地址</span>
          <code class="ds-value">{{ config.datasource?.database_url }}</code>
        </div>
        <div class="ds-row">
          <span class="ds-label">高德地图 Key</span>
          <code class="ds-value">{{ config.datasource?.amap_key || '未配置' }}</code>
        </div>
      </div>

      <!-- 测试连接 -->
      <div class="ds-test">
        <el-button type="primary" :loading="testing" @click="testDatabase">测试数据库连接</el-button>
        <div v-if="testDb" class="test-result" :class="testDb.ok ? 'ok' : 'fail'">
          <el-icon v-if="testDb.ok"><CircleCheck /></el-icon>
          <el-icon v-else><CircleClose /></el-icon>
          {{ testDb.detail }}
        </div>
      </div>
    </div>

    <!-- ====== 模型接入 ====== -->
    <div v-else-if="activeTab === 'model'" class="admin-panel">
      <div class="panel-title">
        <el-icon><Setting /></el-icon>
        模型接入
      </div>

      <!-- 提供商选择 -->
      <div class="provider-switch">
        <span class="provider-label">LLM 提供商</span>
        <div class="provider-options">
          <button
            class="popt"
            :class="{ active: configForm.active_provider === 'aliyun' }"
            @click="configForm.active_provider = 'aliyun'"
          >
            <el-icon><Promotion /></el-icon>
            阿里云（百炼）
          </button>
          <button
            class="popt"
            :class="{ active: configForm.active_provider === 'amd' }"
            @click="configForm.active_provider = 'amd'"
          >
            <el-icon><Monitor /></el-icon>
            AMD GPU Cloud
          </button>
          <button
            class="popt"
            :class="{ active: configForm.active_provider === 'ollama' }"
            @click="configForm.active_provider = 'ollama'"
          >
            <el-icon><Cpu /></el-icon>
            本地 Ollama
          </button>
          <button
            class="popt"
            :class="{ active: configForm.active_provider === 'longcat' }"
            @click="configForm.active_provider = 'longcat'"
          >
            <el-icon><Connection /></el-icon>
            LongCat
          </button>
        </div>
      </div>

      <!-- ===== 阿里云配置 ===== -->
      <template v-if="configForm.active_provider === 'aliyun'">
        <div class="panel-sub">阿里云 / 通用 OpenAI 兼容配置</div>
        <div class="form-grid">
          <div class="form-item">
            <label>LLM API Key</label>
            <el-input v-model="configForm.llm_api_key" type="password" show-password placeholder="sk-..." />
          </div>
          <div class="form-item">
            <label>API Base URL</label>
            <el-input v-model="configForm.llm_api_base" placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </div>
          <div class="form-item">
            <label>Chat 模型</label>
            <el-input v-model="configForm.llm_model" placeholder="qwen-plus" />
          </div>
          <div class="form-item">
            <label>Embedding 模型</label>
            <el-input v-model="configForm.embedding_model" placeholder="text-embedding-v3" />
          </div>
        </div>

        <!-- 百炼免费额度模型选择 -->
        <div class="free-models-head">
          <div class="panel-sub" style="margin:0">
            百炼模型
            <el-button size="small" :loading="loadingModels" style="margin-left:12px" @click="fetchFreeModels">
              <el-icon><Refresh /></el-icon>&nbsp;获取模型列表
            </el-button>
            <el-button v-if="modelList" size="small" @click="modelListVisible = !modelListVisible">
              {{ modelListVisible ? '收起' : '展开' }}
            </el-button>
          </div>
          <div class="free-models-hint">
            点击「获取模型列表」，系统将根据<b>已保存的阿里云密钥</b>调用百炼
            <code>GET /compatible-mode/v1/models</code> 获取真实可用模型，同时实时解析官方计费文档的
            免费额度目录（官方新增/调整自动跟随），按 <b>大语言 / 视觉 / 全模态 / 语音 / 向量</b> 五大类展示。
            点击「使用」立即切换并热生效，无需重启。列表可随时收起以节省空间。
          </div>
        </div>

        <template v-if="modelListVisible">
        <!-- 密钥使用概况卡片 -->
        <div v-if="modelList && modelList.key_info" class="key-info-card">
          <div class="ki-row">
            <div class="ki-item">
              <span class="ki-label">提供商</span>
              <span class="ki-value">{{ modelList.key_info.provider_name }}</span>
            </div>
            <div class="ki-item">
              <span class="ki-label">API Key</span>
              <span class="ki-value mono">{{ modelList.key_info.api_key_configured ? modelList.key_info.api_key_masked : '未配置' }}</span>
            </div>
            <div class="ki-item">
              <span class="ki-label">Chat 模型</span>
              <span class="ki-value mono">{{ modelList.current_model || '-' }}</span>
            </div>
            <div class="ki-item">
              <span class="ki-label">Embedding 模型</span>
              <span class="ki-value mono">{{ modelList.key_info.embedding_model || '-' }}</span>
            </div>
            <div class="ki-item">
              <span class="ki-label">视觉识别模型</span>
              <span class="ki-value mono">{{ modelList.key_info.vision_model || '-' }}（{{ modelList.key_info.vision_provider === 'amd' ? 'AMD' : '百炼' }}）</span>
            </div>
            <div class="ki-item">
              <span class="ki-label">语音识别 / 合成</span>
              <span class="ki-value mono">{{ modelList.key_info.asr_model || '-' }} / {{ modelList.key_info.tts_model || '-' }}</span>
            </div>
            <div class="ki-item">
              <span class="ki-label">可用模型</span>
              <span class="ki-value">{{ modelList.available_count }} 个（含免费额度目录 {{ modelList.key_info.free_count }} 个）</span>
            </div>
          </div>
          <div class="ki-links">
            <span class="ki-note">{{ modelList.key_info.quota_note }}</span>
            <div class="ki-btns">
              <el-button size="small" tag="a" :href="modelList.key_info.console_urls.usage" target="_blank" rel="noopener">
                用量与额度明细
              </el-button>
              <el-button size="small" tag="a" :href="modelList.key_info.console_urls.aliyun_benefit" target="_blank" rel="noopener" type="warning">
                我的高校权益
              </el-button>
            </div>
          </div>
        </div>

        <el-alert
          v-if="modelList && !modelList.fetch_ok && !modelList.key_info?.directory_ok"
          type="warning"
          :closable="false"
          style="margin-bottom:10px"
          title="官方目录与 /models 接口均拉取失败（请检查网络 / API Key），下表为内置免费额度目录"
        />

        <!-- 分类 Tab -->
        <div v-if="modelList" class="model-category-tabs">
          <button
            v-for="tab in categoryTabs"
            :key="tab.key"
            class="cat-tab"
            :class="{ active: modelCategory === tab.key }"
            @click="modelCategory = tab.key"
          >
            {{ tab.label }}
            <span class="cat-count">{{ categoryCount(tab.key) }}</span>
          </button>
        </div>

        <el-table v-if="modelList" :data="filteredModels" size="small" max-height="380" border>
          <el-table-column prop="id" label="模型 ID" min-width="160">
            <template #default="{ row }">
              <el-tag v-if="row.is_current" type="success" size="small">当前</el-tag>
              <span style="margin-left:6px; font-family: monospace">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="130" />
          <el-table-column label="免费额度" width="110" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.is_free" type="warning" size="small">{{ row.free_quota }}</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column prop="validity" label="有效期" width="100" align="center" />
          <el-table-column label="校验" width="80" align="center">
            <template #default="{ row }">
              <el-tooltip :content="row.verified ? '已通过 /models 接口校验，当前 Key 可调用' : '未在 /models 返回中（可能下线或 Key 无权限）'">
                <el-tag :type="row.verified ? 'success' : 'info'" size="small">
                  {{ row.verified ? '已验证' : '未验证' }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="desc" label="说明" min-width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="90" fixed="right" align="center">
            <template #default="{ row }">
              <el-button size="small" type="primary" :disabled="row.is_current" @click="applyModel(row.id, row.category, row.usage)">
                使用
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        </template>

        <!-- 百炼账号免费额度（静态内置快照：剩余量/过期时间/状态） -->
        <div class="free-models-head" style="margin-top:18px">
          <div class="panel-sub" style="margin:0">
            账号免费额度（控制台快照）
            <el-button size="small" :loading="loadingBailianQuota" style="margin-left:12px" @click="fetchBailianQuota">
              <el-icon><Refresh /></el-icon>&nbsp;{{ bailianQuota ? '刷新额度' : '加载额度' }}
            </el-button>
            <el-button v-if="bailianQuota && bailianQuota.ok" size="small" @click="quotaVisible = !quotaVisible">
              {{ quotaVisible ? '收起' : '展开' }}
            </el-button>
            <span v-if="bailianQuota && bailianQuota.ok" class="quota-summary">
              语言 {{ bailianQuota.counts.text }} · 视觉 {{ bailianQuota.counts.vision }} ·
              全模态 {{ bailianQuota.counts.multimodal }} · 向量 {{ bailianQuota.counts.embedding }} ·
              语音 {{ bailianQuota.counts.audio }}，共 {{ bailianQuota.total }} 条（快照 {{ bailianQuota.snapshot_date }}）
            </span>
          </div>
          <div class="free-models-hint">
            「剩余量 / 过期时间 / 状态」是阿里云账号级数据（控制台需登录、无公开 API），已内置为静态快照；
            表格<b>按过期时间升序</b>（谁先过期谁在前面，2099 永久额度排最后）。
            「使用」可将该模型设为对应用途（对话 / 向量 / 语音识别 / 语音合成）并写入 .env 热生效；
            生图 / 视频生成、重排序类模型系统暂不支持，按钮置灰。
          </div>
        </div>

        <template v-if="quotaVisible && bailianQuota && bailianQuota.ok">
          <!-- 分类 Tab -->
          <div class="model-category-tabs">
            <button
              v-for="tab in quotaTabs"
              :key="tab.key"
              class="cat-tab"
              :class="{ active: quotaCategory === tab.key }"
              @click="quotaCategory = tab.key"
            >
              {{ tab.label }}
              <span class="cat-count">{{ quotaTabCount(tab.key) }}</span>
            </button>
          </div>

          <el-table :data="filteredQuotaRows" size="small" max-height="380" border>
            <el-table-column prop="model" label="模型 Code" min-width="210" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tag v-if="quotaIsCurrent(row)" type="success" size="small">当前</el-tag>
                <span style="margin-left:6px; font-family: monospace">{{ row.model }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="category" label="类别" width="100" align="center">
              <template #default="{ row }">
                <el-tag size="small" :type="{ text: 'primary', vision: 'warning', multimodal: 'success', embedding: 'danger', audio: 'info' }[row.category]">
                  {{ { text: '语言', vision: '视觉', multimodal: '全模态', embedding: '向量', audio: '语音' }[row.category] }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="quota" label="免费额度剩余量" min-width="170" align="center">
              <template #default="{ row }">
                <span style="font-family: monospace; font-size: 12px">{{ row.quota }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="expire" label="过期时间" width="120" align="center">
              <template #default="{ row }">
                <span :style="{ color: isExpiringSoon(row.expire) ? '#f59e0b' : '', fontWeight: isExpiringSoon(row.expire) ? 600 : '' }">
                  {{ row.expire }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status && row.status.includes('过期') ? 'info' : 'success'" size="small">
                  {{ row.status || '-' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="170" show-overflow-tooltip>
              <template #default="{ row }">
                <span style="font-size: 12px; color: var(--gis-text-muted, #94a3b8)">{{ quotaRemark(row) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right" align="center">
              <template #default="{ row }">
                <el-tooltip
                  :disabled="!!quotaUsage(row)"
                  content="该模型类型系统暂不支持（生图/视频/重排序），无法设为当前使用"
                  placement="top"
                >
                  <span>
                    <el-button size="small" type="primary" :disabled="!quotaUsage(row) || quotaIsCurrent(row)"
                      @click="applyModel(row.model, row.category, quotaUsage(row)?.usage || '')">
                      使用
                    </el-button>
                  </span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
        </template>
        <div v-else-if="!quotaVisible" class="pwd-note">
          点击上方「加载额度」查看 89 条账号免费额度（语言 14 / 视觉 11 / 全模态 0 / 向量 3 / 语音 61）
        </div>
      </template>

      <!-- ===== AMD GPU Cloud 配置 ===== -->
      <template v-if="configForm.active_provider === 'amd'">
        <div class="panel-sub">AMD GPU Cloud 配置</div>
        <div class="form-grid">
          <div class="form-item">
            <label>AMD API Key</label>
            <el-input v-model="configForm.amd_api_key" type="password" show-password placeholder="rc-..." />
          </div>
          <div class="form-item">
            <label>API Base URL</label>
            <el-input v-model="configForm.amd_api_base" placeholder="https://developer.amd.com.cn/radeon/v1" />
          </div>
          <div class="form-item">
            <label>当前 AMD 模型</label>
            <el-input v-model="configForm.amd_model" placeholder="DeepSeek-V4-Flash" />
          </div>
          <div class="form-item">
            <label>Embedding 模型</label>
            <el-input v-model="configForm.embedding_model" placeholder="text-embedding-v3" />
          </div>
        </div>

        <!-- AMD 模型列表（动态获取 + 计费层级） -->
        <div class="free-models-head">
          <div class="panel-sub" style="margin:0">
            AMD GPU Cloud 模型列表
            <el-button size="small" :loading="loadingAmdModels" style="margin-left:12px" @click="fetchAmdModels">
              <el-icon><Refresh /></el-icon>&nbsp;获取模型列表
            </el-button>
          </div>
          <div class="free-models-hint">
            点击获取后，系统实时抓取 AMD 官方 <code>tokenfactory</code> 模型目录
            （Public Free + Dedicated），并按 <b>免费 / 限时免费 / 付费（专属实例）</b> 三类计费层级标注，
            同时调用 <code>GET /radeon/v1/models</code> 校验当前 Key 可用性。
            大语言模型与视觉模型均可一键切换（视觉模型切换后视觉识别走 AMD），
            立即热生效，无需重启；Qwen3.8-Flash-Next 需在可用时间窗口内。
          </div>
        </div>

        <el-alert
          v-if="amdModelList && !amdModelList.fetch_ok && !amdModelList.key_info?.directory_ok"
          type="warning"
          :closable="false"
          style="margin-bottom:10px"
          title="AMD 官方目录与 /models 接口均拉取失败（请检查网络 / API Key）"
        />

        <!-- AMD 分类 Tab -->
        <div v-if="amdModelList" class="model-category-tabs">
          <button
            v-for="tab in amdCategoryTabs"
            :key="tab.key"
            class="cat-tab"
            :class="{ active: amdCategory === tab.key }"
            @click="amdCategory = tab.key"
          >
            {{ tab.label }}
            <span class="cat-count">{{ amdCategoryCount(tab.key) }}</span>
          </button>
        </div>

        <el-table v-if="amdModelList" :data="filteredAmdModels" size="small" max-height="380" border>
          <el-table-column prop="id" label="模型 ID" min-width="200">
            <template #default="{ row }">
              <el-tag v-if="row.is_current" type="success" size="small">当前</el-tag>
              <span style="margin-left:6px; font-family: monospace">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column label="计费" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="tierTag(row.tier).type" size="small">{{ tierTag(row.tier).text }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="校验" width="80" align="center">
            <template #default="{ row }">
              <el-tooltip :content="row.verified ? '已通过 /models 接口校验，当前 Key 可调用' : '未在 /models 返回中（可能需要专属实例部署或已下线）'">
                <el-tag :type="row.verified ? 'success' : 'info'" size="small">
                  {{ row.verified ? '已验证' : '未验证' }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="desc" label="说明" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="90" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                type="primary"
                :disabled="row.is_current"
                @click="applyAmdModel(row.id, row.category)"
              >
                使用
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Qwen3.8-Flash 系列时间窗口 -->
        <div v-if="(configForm.amd_model || '').toLowerCase().includes('qwen3.8-flash')" class="qwen3-8-section">
          <div class="panel-sub">Qwen3.8-Flash-Next 可用时间窗口</div>
          <div class="form-grid">
            <div class="form-item">
              <label>起始时间</label>
              <el-input v-model="configForm.qwen3_8_flash_start" placeholder="2026-01-01 00:00:00" />
            </div>
            <div class="form-item">
              <label>结束时间</label>
              <el-input v-model="configForm.qwen3_8_flash_end" placeholder="2026-12-31 23:59:59" />
            </div>
          </div>
          <div class="qwen-status">
            <span class="qs-label">状态：</span>
            <span class="qs-badge" :class="'qs-' + qwen3_8Status.cls">
              {{ qwen3_8Status.text }}
            </span>
          </div>
        </div>
      </template>

      <!-- ===== 本地 Ollama 配置 ===== -->
      <template v-if="configForm.active_provider === 'ollama'">
        <div class="panel-sub">本地 Ollama 配置（无需 API Key，Embedding 始终走阿里百炼）</div>
        <div class="form-grid">
          <div class="form-item">
            <label>API Base URL</label>
            <el-input v-model="configForm.ollama_api_base" placeholder="http://localhost:11434/v1" />
          </div>
          <div class="form-item">
            <label>Chat 模型</label>
            <el-input v-model="configForm.ollama_model" placeholder="qwen2.5:7b" />
          </div>
        </div>
        <div class="ollama-hint">
          提示：请先安装 Ollama 并拉取模型（如 <code>ollama pull qwen2.5:7b</code>），
          Embedding 检索不受切换影响，始终使用阿里百炼 text-embedding-v3。
        </div>
      </template>

      <!-- ===== LongCat 配置 ===== -->
      <template v-if="configForm.active_provider === 'longcat'">
        <div class="panel-sub">LongCat 配置（仅 LLM 模型，Embedding 始终走阿里百炼）</div>
        <div class="form-grid">
          <div class="form-item">
            <label>LongCat API Key</label>
            <el-input v-model="configForm.longcat_api_key" type="password" show-password placeholder="ak-..." />
          </div>
          <div class="form-item">
            <label>API Base URL</label>
            <el-input v-model="configForm.longcat_api_base" placeholder="https://api.longcat.chat/openai" />
          </div>
          <div class="form-item">
            <label>Chat 模型</label>
            <el-input v-model="configForm.longcat_model" placeholder="LongCat-2.5-Preview" />
          </div>
        </div>

        <!-- LongCat 模型列表（官方目录 + /models 校验） -->
        <div class="free-models-head">
          <div class="panel-sub" style="margin:0">
            LongCat 模型列表
            <el-button size="small" :loading="loadingLongcatModels" style="margin-left:12px" @click="fetchLongcatModels">
              <el-icon><Refresh /></el-icon>&nbsp;获取模型列表
            </el-button>
          </div>
          <div class="free-models-hint">
            点击获取后，系统将调用 LongCat OpenAI 兼容 <code>GET /models</code> 校验当前 Key 可用性，
            并按官方文档目录（<a href="https://longcat.chat/platform/docs/zh/" target="_blank">longcat.chat/platform/docs</a>）展示。
            点击「使用」立即切换并热生效，无需重启。
          </div>
        </div>

        <el-alert
          v-if="longcatModelList && !longcatModelList.fetch_ok"
          type="warning"
          :closable="false"
          style="margin-bottom:10px"
          title="LongCat /models 接口校验失败（请检查网络 / API Key），目录仅供展示"
        />

        <el-table v-if="longcatModelList" :data="longcatModelList.models" size="small" max-height="300" border>
          <el-table-column prop="id" label="模型 ID" min-width="200">
            <template #default="{ row }">
              <el-tag v-if="row.is_current" type="success" size="small">当前</el-tag>
              <span style="margin-left:6px; font-family: monospace">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="150" />
          <el-table-column label="校验" width="80" align="center">
            <template #default="{ row }">
              <el-tooltip :content="row.verified ? '已通过 /models 接口校验，当前 Key 可调用' : '未在 /models 返回中（可能已下线）'">
                <el-tag :type="row.verified ? 'success' : 'info'" size="small">
                  {{ row.verified ? '已验证' : '未验证' }}
                </el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column prop="desc" label="说明" min-width="220" show-overflow-tooltip />
          <el-table-column label="操作" width="90" fixed="right" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                type="primary"
                :disabled="row.is_current"
                @click="applyLongcatModel(row.id)"
              >
                使用
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="ollama-hint">
          提示：LongCat 仅提供对话（LLM）模型，Embedding 检索不受切换影响，始终使用阿里百炼。
        </div>
      </template>

      <!-- 知识库参数（公共） -->
      <div class="panel-sub">知识库参数</div>
      <div class="form-grid">
        <div class="form-item">
          <label>切分大小</label>
          <el-input-number v-model="configForm.kb_chunk_size" :min="100" :max="2000" :step="100" />
        </div>
        <div class="form-item">
          <label>切分重叠</label>
          <el-input-number v-model="configForm.kb_chunk_overlap" :min="0" :max="200" :step="10" />
        </div>
        <div class="form-item">
          <label>Top-K 召回</label>
          <el-input-number v-model="configForm.kb_top_k" :min="1" :max="20" />
        </div>
      </div>

      <div class="action-row">
        <el-button type="primary" @click="saveConfig">保存模型配置</el-button>
        <el-button :loading="testing" @click="testLlmConn">
          测试{{ configForm.active_provider === 'amd' ? ' AMD' : (configForm.active_provider === 'ollama' ? ' Ollama' : (configForm.active_provider === 'longcat' ? ' LongCat' : '')) }}模型连接
        </el-button>
      </div>

      <div v-if="testLlm" class="test-result" :class="testLlm.ok ? 'ok' : 'fail'" style="margin-top:12px">
        <el-icon v-if="testLlm.ok"><CircleCheck /></el-icon>
        <el-icon v-else><CircleClose /></el-icon>
        {{ testLlm.detail }}
      </div>
    </div>

    <!-- ====== Agent 参数 ====== -->
    <div v-else-if="activeTab === 'agent'" class="admin-panel">
      <div class="panel-title">
        <el-icon><Document /></el-icon>
        Agent 参数管理
      </div>

      <div class="form-grid">
        <div class="form-item">
          <label>编排 Agent 温度（temperature）</label>
          <el-slider v-model="agentForm.orchestrator_temperature" :min="0" :max="1" :step="0.1" show-input />
        </div>
        <div class="form-item">
          <label>报告 Agent 温度（temperature）</label>
          <el-slider v-model="agentForm.report_temperature" :min="0" :max="1" :step="0.1" show-input />
        </div>
        <div class="form-item">
          <label>最大并行 Agent 数</label>
          <el-input-number v-model="agentForm.max_agents" :min="1" :max="10" />
        </div>
        <div class="form-item">
          <label>报告人工审批（HITL）</label>
          <el-switch v-model="agentForm.require_approval" active-text="开启" inactive-text="关闭" />
          <div class="form-tip">开启后 Agent 报告生成并通过质量评审后，需人工审批（通过 / 编辑 / 驳回）才定稿归档</div>
        </div>
        <div class="form-item">
          <label>全链路流式输出</label>
          <el-switch v-model="agentForm.llm_stream_enabled" active-text="开启" inactive-text="关闭" />
          <div class="form-tip">P2#18：报告与 RAG 回答逐字流式推送（打字机效果）；关闭后回退整段返回</div>
        </div>
      </div>

      <div class="action-row">
        <el-button type="primary" @click="saveAgent">保存 Agent 参数</el-button>
      </div>

      <div class="panel-sub">Agent 图谱说明</div>
      <div class="graph-note">
        <p><b>Orchestrator</b>（LangGraph 编排）→ 拆解任务（plan 驱动路由）→</p>
        <p>&nbsp;&nbsp;├─ <b>DataAgent</b>：查数据库（历史火点/预测双源）→ <b>GisAgent</b>：空间分析</p>
        <p>&nbsp;&nbsp;├─ <b>RagAgent</b>：知识库 RAG 检索（Adaptive + Rerank）</p>
        <p>&nbsp;&nbsp;└─ 汇合 → <b>ReportAgent</b>：生成报告 → <b>Reviewer</b>：质量评审（不通过退回重写，最多 2 轮）</p>
        <p>→ 人工审批闸口（HITL，可配置）：通过 / 编辑 / 驳回 → 报告定稿归档</p>
      </div>
    </div>

    <!-- ====== 系统日志 ====== -->
    <div v-else-if="activeTab === 'logs'" class="admin-panel">
      <div class="panel-title">
        <el-icon><Refresh /></el-icon>
        系统日志
        <el-button size="small" style="margin-left:auto" :icon="Refresh" @click="fetchLogs" :loading="loadingLogs">刷新</el-button>
      </div>

      <div class="log-list">
        <div v-if="logs.length === 0" class="log-empty">暂无日志</div>
        <div v-for="(log, i) in logs" :key="i" class="log-item">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-level" :class="levelClass(log.level)">{{ log.level }}</span>
          <span class="log-source">{{ log.source }}</span>
          <span class="log-msg">{{ log.message }}</span>
        </div>
      </div>
    </div>

    <!-- ====== 用户管理（仅管理员） ====== -->
    <div v-else-if="activeTab === 'users'" class="admin-panel">
      <div class="panel-title">
        <el-icon><User /></el-icon>
        用户权限管理
        <el-button size="small" style="margin-left:auto" :icon="Refresh" @click="fetchUsers" :loading="loadingUsers">刷新</el-button>
      </div>

      <div class="user-table-wrap" v-loading="loadingUsers">
        <table class="user-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>用户名</th>
              <th>邮箱</th>
              <th>角色</th>
              <th>注册时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.id }}</td>
              <td>
                <span class="uname">{{ u.username }}</span>
                <span v-if="u.username === auth.user?.username" class="self-tag">当前账号</span>
              </td>
              <td>{{ u.email || '—' }}</td>
              <td>
                <span class="role-badge" :class="u.role === 'admin' ? 'role-admin' : 'role-user'">
                  {{ roleLabel(u.role) }}
                </span>
              </td>
              <td>{{ u.created_at || '—' }}</td>
              <td>
                <el-select
                  :model-value="u.role"
                  size="small"
                  style="width: 110px"
                  :disabled="u.username === auth.user?.username"
                  @change="(v) => changeRole(u, v)"
                >
                  <el-option label="普通用户" value="user" />
                  <el-option label="管理员" value="admin" />
                </el-select>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  style="margin-left: 8px"
                  :disabled="u.username === auth.user?.username"
                  @click="removeUser(u)"
                >删除</el-button>
              </td>
            </tr>
            <tr v-if="users.length === 0 && !loadingUsers">
              <td colspan="6" class="log-empty">暂无用户数据</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="perm-note">
        <b>权限说明：</b>管理员可访问全部页面（含系统管理/用户管理）；普通用户仅可访问作战大屏、智能查询、知识库、Agent 中心、报告中心。系统内置默认管理员账号 admin（不可删除、不可降级自己的角色）。
      </div>
    </div>
  </div>
</template>

<style scoped>
.admin-shell {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--gis-atmo-bg);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}
.admin-header {
  padding: 18px 24px;
  border-bottom: 1px solid var(--gis-border, #1e293b);
  flex-shrink: 0;
}
.admin-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}
.admin-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--gis-text-muted, #64748b);
}
.admin-tabs {
  display: flex;
  gap: 4px;
  padding: 10px 24px;
  border-bottom: 1px solid var(--gis-border, #1e293b);
  flex-shrink: 0;
}
.atab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--gis-text-muted, #94a3b8);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.atab:hover {
  color: var(--gis-text, #f8fafc);
  background: var(--gis-hover-tint, rgba(34, 211, 238, 0.08));
}
.atab.active {
  color: var(--gis-on-accent, #020617);
  background: var(--gis-metal-accent);
  box-shadow: var(--gis-glow);
  font-weight: 600;
}
.admin-panel {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
}
.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  margin-bottom: 16px;
}
.panel-sub {
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text-muted, #94a3b8);
  margin: 24px 0 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--gis-border, #1e293b);
}
.block-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text-muted, #94a3b8);
  margin: 24px 0 12px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.overview-card {
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  padding: 16px;
}
.oc-label {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  margin-bottom: 8px;
}
.oc-value {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
}

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}
.agent-card {
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  padding: 14px;
}
.agent-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
}
.agent-framework {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  margin: 6px 0;
}
.agent-status {
  font-size: 10px;
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
  padding: 2px 8px;
  border-radius: 8px;
}

.ds-card {
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  padding: 8px 16px;
}
.ds-row {
  display: flex;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px solid var(--gis-border, #1e293b);
}
.ds-row:last-child {
  border-bottom: none;
}
.ds-label {
  width: 120px;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
  flex-shrink: 0;
}
.ds-value {
  font-size: 12px;
  color: var(--gis-accent, #0ea5e9);
  font-family: ui-monospace, "Consolas", monospace;
}
.ds-test {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 16px;
}
.form-item label {
  display: block;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
  margin-bottom: 6px;
}
.form-tip {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  line-height: 1.5;
  margin-top: 6px;
}
.action-row {
  display: flex;
  gap: 10px;
  margin-top: 20px;
}
.action-row :deep(.el-button) {
  border-radius: 6px;
}
.action-row :deep(.el-upload) {
  margin-left: 4px;
}
.action-row :deep(.el-button--primary) {
  background: var(--gis-accent);
  border-color: var(--gis-accent);
}
.test-result {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 6px;
}
.test-result.ok {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
}
.test-result.fail {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.graph-note {
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  padding: 16px;
  font-size: 13px;
  color: var(--el-text-color-regular, #cbd5e1);
  line-height: 1.9;
  font-family: ui-monospace, "Consolas", monospace;
  white-space: pre-wrap;
}
.graph-note p {
  margin: 0;
}

/* 提供商切换 */
.provider-switch {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 14px 18px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
}
.provider-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text-muted, #94a3b8);
  flex-shrink: 0;
}
.provider-options {
  display: flex;
  gap: 8px;
}
.popt {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  font-size: 13px;
  color: var(--gis-text-muted, #94a3b8);
  background: transparent;
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.popt:hover {
  color: var(--gis-text, #f8fafc);
  background: var(--gis-hover-tint, rgba(34, 211, 238, 0.08));
}
.popt.active {
  color: var(--gis-on-accent, #020617);
  background: var(--gis-accent);
  border-color: var(--gis-accent);
  font-weight: 600;
}

/* Qwen3.8 时间窗口 */
.qwen3-8-section {
  margin-top: 8px;
  padding: 0 0 4px;
}
.ollama-hint {
  margin-top: 10px;
  padding: 8px 12px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--gis-text-muted, #94a3b8);
  background: var(--gis-accent-soft, rgba(34, 211, 238, 0.05));
  border: 1px dashed var(--gis-accent-soft, rgba(34, 211, 238, 0.25));
  border-radius: 4px;
}
.ollama-hint code {
  background: var(--gis-table-header, rgba(30, 41, 59, 0.8));
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, "Consolas", monospace;
  color: var(--gis-accent, #7dd3fc);
}
/* ====== 百炼账号免费额度快照 ====== */
.quota-login-card {
  margin-top: 12px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  padding: 14px 16px;
}
.quota-summary {
  margin-left: 14px;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
}

/* ====== 百炼模型 ====== */
.free-models-head {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.free-models-hint {
  font-size: 11px;
  line-height: 1.8;
  color: var(--gis-text-muted, #94a3b8);
  padding: 8px 12px;
  background: var(--gis-accent-soft, rgba(34, 211, 238, 0.05));
  border: 1px dashed var(--gis-accent-soft, rgba(34, 211, 238, 0.25));
  border-radius: 4px;
}
.free-models-hint code {
  background: var(--gis-table-header, rgba(30, 41, 59, 0.8));
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, "Consolas", monospace;
  color: var(--gis-accent, #7dd3fc);
}
.free-models-hint a {
  color: var(--gis-accent, #38bdf8);
}
/* ====== 密钥使用概况卡片 ====== */
.key-info-card {
  margin: 10px 0;
  padding: 12px 16px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 6px;
}
.ki-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 28px;
}
.ki-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.ki-label {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
}
.ki-value {
  font-size: 13px;
  color: var(--gis-text, #f8fafc);
  font-weight: 600;
}
.ki-value.mono {
  font-family: ui-monospace, "Consolas", monospace;
  color: var(--gis-accent, #7dd3fc);
}
.ki-links {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--gis-border, #1e293b);
  flex-wrap: wrap;
}
.ki-note {
  font-size: 11px;
  color: var(--gis-text-muted, #94a3b8);
  line-height: 1.6;
  flex: 1;
  min-width: 260px;
}
.ki-btns {
  display: flex;
  gap: 8px;
}
/* ====== 模型分类 Tab ====== */
.model-category-tabs {
  display: flex;
  gap: 8px;
  margin: 10px 0;
  flex-wrap: wrap;
}
.cat-tab {
  padding: 5px 14px;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 6px;
}
.cat-tab:hover {
  color: var(--gis-accent, #38bdf8);
  border-color: var(--gis-accent-soft, rgba(56, 189, 248, 0.4));
}
.cat-tab.active {
  color: var(--gis-accent, #fff);
  background: var(--gis-accent-soft, rgba(56, 189, 248, 0.15));
  border-color: var(--gis-accent, #38bdf8);
}
.cat-count {
  font-size: 10px;
  padding: 0 6px;
  border-radius: 8px;
  background: rgba(148, 163, 184, 0.15);
  color: var(--gis-text-muted, #94a3b8);
}
.cat-tab.active .cat-count {
  background: var(--gis-accent-soft, rgba(56, 189, 248, 0.25));
  color: var(--gis-accent, #7dd3fc);
}
.qwen3-8-section .panel-sub {
  margin-top: 16px;
}
.qwen-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 10px 14px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 6px;
}
.qs-label {
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
}
.qs-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 12px;
  border-radius: 10px;
}
.qs-ok {
  color: var(--el-color-success, #4ade80);
  background: rgba(74, 222, 128, 0.12);
  border: 1px solid rgba(74, 222, 128, 0.3);
}
.qs-warn {
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.12);
  border: 1px solid rgba(250, 204, 21, 0.3);
}
.qs-fail {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.3);
}
.qs-gray {
  color: var(--gis-text-muted, #94a3b8);
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.3);
}

.log-list {
  background: var(--gis-bg-deep);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  font-family: ui-monospace, "Consolas", monospace;
  overflow-y: auto;
  max-height: calc(100vh - 260px);
}
.log-empty {
  padding: 40px;
  text-align: center;
  color: var(--gis-text-muted, #475569);
  font-size: 12px;
}
.log-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--gis-border, #1e293b);
  font-size: 12px;
}
.log-item:last-child {
  border-bottom: none;
}
.log-time {
  color: var(--gis-text-muted, #64748b);
  flex-shrink: 0;
  min-width: 150px;
}
.log-level {
  flex-shrink: 0;
  min-width: 50px;
  text-align: center;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
}
.level-info {
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft, rgba(34, 211, 238, 0.12));
}
.level-warn {
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.12);
}
.level-error {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
}
.log-source {
  color: var(--el-color-success, #4ade80);
  flex-shrink: 0;
  min-width: 80px;
}
.log-msg {
  color: var(--el-text-color-regular, #cbd5e1);
  flex: 1;
}

/* 用户管理 */
.user-table-wrap {
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #1e293b);
  border-radius: 8px;
  overflow-x: auto;
}
.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.user-table th {
  text-align: left;
  padding: 10px 14px;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
  font-weight: 600;
  border-bottom: 1px solid var(--gis-border, #1e293b);
  background: var(--gis-table-header, rgba(30, 41, 59, 0.4));
  white-space: nowrap;
}
.user-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--gis-border, #1e293b);
  color: var(--el-text-color-regular, #cbd5e1);
  white-space: nowrap;
}
.user-table tr:last-child td {
  border-bottom: none;
}
.uname {
  color: var(--gis-text, #f8fafc);
  font-weight: 600;
}
.self-tag {
  margin-left: 8px;
  font-size: 10px;
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft, rgba(34, 211, 238, 0.12));
  border: 1px solid var(--gis-accent-soft, rgba(34, 211, 238, 0.3));
  padding: 1px 8px;
  border-radius: 8px;
}
.role-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
}
.role-admin {
  color: var(--el-color-warning, #facc15);
  background: rgba(250, 204, 21, 0.12);
  border: 1px solid rgba(250, 204, 21, 0.3);
}
.role-user {
  color: var(--gis-text-muted, #94a3b8);
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.3);
}
.perm-note {
  margin-top: 16px;
  padding: 12px 16px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--gis-text-muted, #94a3b8);
  background: var(--gis-accent-soft, rgba(34, 211, 238, 0.06));
  border: 1px solid var(--gis-accent-soft, rgba(34, 211, 238, 0.2));
  border-radius: 8px;
}
.perm-note b {
  color: var(--gis-accent, #0ea5e9);
}
</style>