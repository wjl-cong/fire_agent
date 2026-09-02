<script setup>
/**
 * 智能查询页 — 自然语言 → 结构化查询 → 结果展示（摘要/表格/图表/地图）
 *
 * 调用后端 API: POST /api/v1/query/execute
 */
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import authFetch from '@/utils/authFetch'
import { API_V1 } from '@/utils/config'

// OpenLayers 地图
import Map from 'ol/Map.js'
import View from 'ol/View.js'
import TileLayer from 'ol/layer/Tile.js'
import { OSM } from 'ol/source.js'
import VectorLayer from 'ol/layer/Vector.js'
import VectorSource from 'ol/source/Vector.js'
import GeoJSON from 'ol/format/GeoJSON.js'
import { Point } from 'ol/geom.js'
import Feature from 'ol/Feature.js'
import { Style, Fill, Circle as CircleStyle, Text, Stroke } from 'ol/style.js'

// 云南省州市行政边界 GeoJSON（16 个州市）
import yunnanBorder from '@/assets/Yunnan_border.json'

// ====== 状态 ======
const queryText = ref('')
const loading = ref(false)
const activeTab = ref('summary')
const queryHistory = ref([])
const showHistory = ref(false)

// 查询结果
const currentResult = reactive({
  summary: '',
  tableData: [],
  chartData: null,
  chartType: '',
  geoData: null,
  total: 0,
  parseMethod: '', // llm / keyword
})
const parsedInfo = ref(null) // QueryAgent 解析结果（intent/params/method/explanation）

// ====== QueryAgent 解析过程展示辅助 ======
const INTENT_LABELS = {
  history: '历史火点查询',
  predict: '预测火险查询',
  summary: '数据汇总统计',
}
const PARAM_LABELS = {
  city: '城市', year: '年份', month: '月份', months: '季节月份',
  confidence: '置信度', top_k: 'TopN', sort: '排序',
}
const intentLabel = (i) => INTENT_LABELS[i] || i || '未知'
const formatParamValue = (k, v) => {
  if (Array.isArray(v)) return `${v.join(',')}月`
  if (k === 'sort') return v === 'desc' ? '降序' : '升序'
  if (k === 'confidence') return ({ high: '高', nominal: '中', low: '低' })[v] || v
  return v
}
const parsedParams = computed(() => {
  const p = (parsedInfo.value && parsedInfo.value.params) || {}
  return Object.entries(p).map(([k, v]) => ({
    key: PARAM_LABELS[k] || k,
    value: formatParamValue(k, v),
  }))
})

// ECharts 实例
let chartInstance = null
const chartRef = ref(null)

// OpenLayers 地图实例
let mapInstance = null
let mapVectorLayer = null
const mapRef = ref(null)

// 示例查询
const exampleQueries = [
  '2025年1月普洱市预测火险',
  '2025年春季哪些州市风险最高',
  '高置信度火点最多的5个州市',
  '2025年火险数据汇总',
]

// ====== 后端 API 地址 ======
const API_BASE = `${API_V1}/query`

// ====== 查询历史（后端数据库持久化，按用户隔离） ======
const loadHistory = async () => {
  try {
    const res = await authFetch(`${API_BASE}/history`)
    const json = await res.json()
    if (json.code === 200) {
      queryHistory.value = json.data || []
    }
  } catch {
    /* 静默 */
  }
}

// ====== 执行查询 ======
const handleQuery = async () => {
  const text = queryText.value.trim()
  if (!text) {
    ElMessage.warning('请输入查询内容')
    return
  }

  loading.value = true
  currentResult.summary = ''
  currentResult.tableData = []
  currentResult.chartData = null
  currentResult.chartType = ''
  currentResult.geoData = null
  currentResult.parseMethod = ''
  parsedInfo.value = null

  try {
    const res = await authFetch(`${API_BASE}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: text }),
    })
    const json = await res.json()

    if (json.code !== 200) {
      ElMessage.error('查询失败: ' + json.message)
      return
    }

    const data = json.data
    // QueryAgent 解析结果（完整保留 intent/params/method/explanation 供前端展示）
    parsedInfo.value = data.parsed || null
    const result = data.result

    currentResult.summary = result.summary || '无摘要'
    currentResult.tableData = result.table_data || []
    currentResult.chartData = result.chart_data || null
    currentResult.chartType = result.chart_type || ''
    currentResult.geoData = result.geo_data || null
    currentResult.parseMethod = data.parsed.method || 'keyword'
    currentResult.total = result.total || 0

    // 历史由后端自动保存（同文本去重），这里仅刷新列表
    loadHistory()

    // 切换到摘要 tab
    activeTab.value = 'summary'

    // 如果后端返回了图表数据，延迟渲染图表
    if (result.chart_data && result.chart_data.labels?.length > 0) {
      nextTick(() => renderChart())
    }
  } catch (e) {
    ElMessage.error('网络错误，请确认后端服务已启动: ' + e.message)
  } finally {
    loading.value = false
  }
}

// ====== 点击示例查询 ======
const handleExample = (example) => {
  queryText.value = example
  handleQuery()
}

// ====== 点击历史记录 ======
// ====== 点击历史：直接回显数据库存储的结果，不重新查询 ======
const applyResult = (data) => {
  parsedInfo.value = data.parsed || null
  const result = data.result
  currentResult.summary = result.summary || '无摘要'
  currentResult.tableData = result.table_data || []
  currentResult.chartData = result.chart_data || null
  currentResult.chartType = result.chart_type || ''
  currentResult.geoData = result.geo_data || null
  currentResult.parseMethod = (data.parsed && data.parsed.method) || 'keyword'
  currentResult.total = result.total || 0
  activeTab.value = 'summary'
  if (result.chart_data && result.chart_data.labels?.length > 0) {
    nextTick(() => renderChart())
  }
}

const handleHistoryClick = async (item) => {
  queryText.value = item.text
  try {
    const res = await authFetch(`${API_BASE}/history/${item.id}`)
    const json = await res.json()
    if (json.code === 200 && json.data.result) {
      // 直接回显存储结果（不触发后端重新查询）
      parsedInfo.value = null
      currentResult.summary = ''
      currentResult.tableData = []
      currentResult.chartData = null
      currentResult.chartType = ''
      currentResult.geoData = null
      applyResult(json.data.result)
      return
    }
  } catch {
    /* 接口失败则回退为重新查询 */
  }
  // 旧记录无存储结果（升级前的数据），回退为重新执行查询
  handleQuery()
}

// ====== 清除历史 ======
const clearHistory = async () => {
  try {
    const res = await authFetch(`${API_BASE}/history`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) {
      queryHistory.value = []
    }
  } catch {
    /* 静默 */
  }
}

// ====== 单条删除历史（与知识库/Agent/报告三页保持一致） ======
const deleteHistoryItem = async (item) => {
  try {
    const res = await authFetch(`${API_BASE}/history/${item.id}`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) {
      queryHistory.value = queryHistory.value.filter(h => h.id !== item.id)
    }
  } catch {
    /* 静默 */
  }
}

// ====== 地图渲染（OpenLayers） ======
const renderMap = () => {
  if (!mapRef.value) return
  const features = (currentResult.geoData && currentResult.geoData.features) || []
  if (!features.length) return // 无点位时由模板展示提示文案

  // 首次初始化底图
  if (!mapInstance) {
    // 云南省州市行政边界图层（描边 + 半透明填充 + 州市名标注）
    const borderLayer = new VectorLayer({
      source: new VectorSource({
        features: new GeoJSON().readFeatures(yunnanBorder, {
          dataProjection: 'EPSG:4326',
          featureProjection: 'EPSG:4326',
        }),
      }),
      style: (feature) => new Style({
        stroke: new Stroke({ color: '#22d3ee', width: 1.5 }),
        fill: new Fill({ color: 'rgba(34, 211, 238, 0.05)' }),
        text: new Text({
          text: feature.get('name') || '',
          font: '11px sans-serif',
          fill: new Fill({ color: 'rgba(148, 163, 184, 0.9)' }),
          stroke: new Stroke({ color: '#000000', width: 3 }),
        }),
      }),
    })

    mapInstance = new Map({
      target: mapRef.value,
      layers: [
        new TileLayer({
          source: new OSM(),
          opacity: 0.85,
        }),
        borderLayer,
      ],
      view: new View({
        center: [99.5, 24.5],
        zoom: 5,
        projection: 'EPSG:4326',
      }),
    })
  }

  // 清除旧图层
  if (mapVectorLayer) mapInstance.removeLayer(mapVectorLayer)

  // 构建点位 Feature
  const olFeatures = currentResult.geoData.features
    .filter(f => f.geometry && f.geometry.coordinates)
    .map(f => {
      const [lng, lat] = f.geometry.coordinates
      const feat = new Feature({ geometry: new Point([lng, lat]) })
      const props = f.properties || {}
      feat.setProperties(props)
      return feat
    })

  mapVectorLayer = new VectorLayer({
    source: new VectorSource({ features: olFeatures }),
    style: (feature) => {
      const color = feature.get('color') || '#0ea5e9'
      const name = feature.get('name') || ''
      return new Style({
        image: new CircleStyle({
          radius: 7,
          fill: new Fill({ color }),
          stroke: new Stroke({ color: '#ffffff', width: 1.5 }),
        }),
        text: new Text({
          text: name,
          font: '11px sans-serif',
          fill: new Fill({ color: '#ffffff' }),
          stroke: new Stroke({ color: '#000000', width: 3 }),
          offsetY: -14,
        }),
      })
    },
  })
  mapInstance.addLayer(mapVectorLayer)

  // 自适应视图到点位范围
  if (olFeatures.length > 0) {
    const extent = mapVectorLayer.getSource().getExtent()
    mapInstance.getView().fit(extent, { padding: [40, 40, 40, 40], maxZoom: 10, duration: 300 })
  } else {
    mapInstance.getView().setCenter([99.5, 24.5])
    mapInstance.getView().setZoom(5)
  }
  mapInstance.updateSize()
}

// ====== 图表渲染 ======
const renderChart = () => {
  if (!chartRef.value) return
  if (chartInstance) chartInstance.dispose()

  chartInstance = echarts.init(chartRef.value, undefined, { renderer: 'canvas' })

  if (!currentResult.chartData || !currentResult.chartData.labels) return

  const labels = currentResult.chartData.labels
  const values = currentResult.chartData.values

  let option = {}

  if (currentResult.chartType === 'pie') {
    option = {
      tooltip: { trigger: 'item', backgroundColor: 'rgba(15,23,42,0.95)', borderColor: '#334155' },
      legend: { textStyle: { color: '#94a3b8' }, bottom: 0 },
      series: [{
        type: 'pie',
        radius: ['35%', '60%'],
        center: ['50%', '45%'],
        itemStyle: {
          borderRadius: 4,
          borderColor: '#020617',
          borderWidth: 2,
        },
        label: { color: '#f8fafc', fontSize: 11 },
        data: labels.map((name, i) => ({
          name,
          value: values[i] || 0,
          itemStyle: { color: ['#22d3ee', '#4ade80', '#facc15', '#fb923c', '#ef4444'][i % 5] },
        })),
      }],
    }
  } else {
    option = {
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(15,23,42,0.95)',
        borderColor: '#334155',
        textStyle: { color: '#f8fafc' },
      },
      grid: { left: 50, right: 20, top: 20, bottom: 40 },
      xAxis: {
        type: 'category',
        data: labels,
        axisLabel: { color: '#94a3b8', fontSize: 10, rotate: labels.length > 8 ? 45 : 0 },
        axisLine: { lineStyle: { color: '#334155' } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#94a3b8', fontSize: 10 },
        splitLine: { lineStyle: { color: '#1e293b' } },
      },
      series: [{
        type: currentResult.chartType === 'bar' ? 'bar' : 'line',
        data: values,
        itemStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#0ea5e9' },
            { offset: 1, color: '#22d3ee' },
          ]),
          borderRadius: [3, 3, 0, 0],
        },
        lineStyle: { color: '#0ea5e9', width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(14,165,233,0.3)' },
            { offset: 1, color: 'rgba(14,165,233,0.02)' },
          ]),
        },
        smooth: true,
      }],
    }
  }

  chartInstance.setOption(option)
  chartInstance.resize()
}

// ====== 键盘快捷键 ======
const handleKeydown = (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    handleQuery()
  }
}

// ====== 语音输入（ASR）与语音播报（TTS）— 统一工具 ======
import { speakState, speakText, recordState, startRecord, cleanupSpeech } from '@/utils/speech'

const handleMicClick = () => {
  if (recordState.recording) {
    startRecord() // 录音中再次调用 = 停止并识别
    return
  }
  startRecord((text) => {
    queryText.value = text
    handleQuery() // 识别完成自动执行查询
  })
}

// ====== 窗口自适应 ======
import { onUnmounted } from 'vue'
const handleResize = () => {
  if (chartInstance) chartInstance.resize()
  if (mapInstance) setTimeout(() => mapInstance.updateSize(), 100)
}
onMounted(() => {
  window.addEventListener('resize', handleResize)
  loadHistory()
})
onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) chartInstance.dispose()
  if (mapInstance) { mapInstance.setTarget(undefined); mapInstance = null }
  cleanupSpeech() // 停止语音播报/录音
})
</script>

<template>
  <div class="query-shell">
    <!-- 页面标题 -->
    <header class="query-header">
      <h1 class="query-title">智能查询</h1>
      <p class="query-subtitle">QueryAgent 解析自然语言 → DataAgent 执行查询 → 四维展示结果</p>
    </header>

    <div class="query-body">
      <!-- 左侧：查询历史 -->
      <aside class="query-history" :class="{ expanded: showHistory }">
        <div class="history-header" @click="showHistory = !showHistory">
          <span class="history-label">查询历史</span>
          <span class="history-count">{{ queryHistory.length }}</span>
        </div>
        <div v-if="showHistory" class="history-list">
          <div
            v-for="(item, i) in queryHistory"
            :key="i"
            class="history-item"
            @click="handleHistoryClick(item)"
          >
            <button
              class="history-delete"
              title="删除"
              @click.stop="deleteHistoryItem(item)"
            >×</button>
            <div class="history-text">{{ item.text }}</div>
            <div class="history-meta">
              <span class="history-time">{{ item.time }}</span>
              <span class="history-method" :class="item.method">
                {{ item.method === 'llm' ? 'LLM' : '关键词' }}
              </span>
            </div>
          </div>
          <div v-if="queryHistory.length === 0" class="history-empty">
            暂无查询记录
          </div>
          <div v-if="queryHistory.length > 0" class="history-clear" @click.stop="clearHistory">
            清除历史
          </div>
        </div>
      </aside>

      <!-- 主内容 -->
      <div class="query-main">
        <!-- 输入区 -->
        <div class="input-area">
          <div class="input-row">
            <el-input
              v-model="queryText"
              type="textarea"
              :rows="2"
              placeholder="输入自然语言查询，例如：2025年1月普洱市预测火险"
              class="query-input"
              @keydown="handleKeydown"
            />
            <el-button
              type="primary"
              :loading="loading"
              @click="handleQuery"
              class="query-btn"
            >
              查询
            </el-button>
            <el-button
              :type="recordState.recording ? 'danger' : 'default'"
              :title="recordState.recording ? '停止录音并识别' : '语音输入'"
              class="mic-btn"
              @click="handleMicClick"
            >
              {{ recordState.recording ? '■ 停止' : '🎤' }}
            </el-button>
          </div>
          <div class="example-row">
            <span class="example-label">示例：</span>
            <span
              v-for="(ex, i) in exampleQueries"
              :key="i"
              class="example-tag"
              @click="handleExample(ex)"
            >
              {{ ex }}
            </span>
          </div>
          <div class="keyboard-hint">Ctrl+Enter 快速查询</div>
        </div>

        <!-- QueryAgent 解析过程 -->
        <div v-if="parsedInfo" class="agent-parse">
          <div class="agent-parse-head">
            <span class="ap-agent-badge">QueryAgent</span>
            <span class="ap-title">解析过程</span>
            <span class="ap-method" :class="parsedInfo.method">
              {{ parsedInfo.method === 'llm' ? 'LLM 解析' : '关键词解析' }}
            </span>
          </div>
          <div class="agent-parse-body">
            <div class="ap-row">
              <span class="ap-label">意图</span>
              <span class="ap-value intent">{{ intentLabel(parsedInfo.intent) }}</span>
            </div>
            <div v-if="parsedParams.length" class="ap-row">
              <span class="ap-label">参数</span>
              <div class="ap-chips">
                <span v-for="(param, i) in parsedParams" :key="i" class="ap-chip">
                  <em>{{ param.key }}</em>{{ param.value }}
                </span>
              </div>
            </div>
            <div v-if="parsedInfo.explanation" class="ap-row">
              <span class="ap-label">说明</span>
              <span class="ap-value">{{ parsedInfo.explanation }}</span>
            </div>
          </div>
        </div>

        <!-- 结果区 -->
        <div v-if="currentResult.summary" class="result-area">
          <!-- 摘要卡片 -->
          <div class="summary-card">
            <div class="summary-icon">i</div>
            <div class="summary-content">
              <div class="summary-text">{{ currentResult.summary }}</div>
              <div class="summary-meta">共 {{ currentResult.total }} 条记录</div>
            </div>
            <div class="summary-actions">
              <el-button
                size="small"
                :loading="speakState.loading"
                :type="speakState.speaking || speakState.loading ? 'danger' : 'default'"
                plain
                title="语音播报查询摘要"
                @click="speakText(`${currentResult.summary}，共${currentResult.total}条记录。`)"
              >{{ speakState.speaking || speakState.loading ? '停止' : '🔊 播报' }}</el-button>
            </div>
          </div>

          <!-- Tab 切换 -->
          <div class="result-tabs">
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'summary' }"
              @click="activeTab = 'summary'"
            >摘要</button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'table' }"
              @click="activeTab = 'table'"
              :disabled="currentResult.tableData.length === 0"
            >表格 ({{ currentResult.tableData.length }})</button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'chart' }"
              @click="activeTab = 'chart'; nextTick(() => renderChart())"
              :disabled="!currentResult.chartData || !currentResult.chartData.labels"
            >图表</button>
            <button
              class="tab-btn"
              :class="{ active: activeTab === 'map' }"
              @click="activeTab = 'map'; nextTick(() => renderMap())"
              :disabled="!currentResult.geoData"
            >地图</button>
            <span v-if="currentResult.parseMethod" class="method-badge" :class="currentResult.parseMethod">
              {{ currentResult.parseMethod === 'llm' ? 'LLM 解析' : '关键词解析' }}
            </span>
          </div>

          <!-- 摘要内容 -->
          <div v-if="activeTab === 'summary'" class="tab-content tab-summary">
            <div class="summary-full">{{ currentResult.summary }}</div>
          </div>

          <!-- 表格内容 -->
          <div v-if="activeTab === 'table'" class="tab-content tab-fill">
            <div class="table-wrap">
              <el-table
                :data="currentResult.tableData"
                stripe
                height="100%"
                size="small"
                class="result-table"
              >
                <el-table-column
                  v-for="col in Object.keys(currentResult.tableData[0] || {})"
                  :key="col"
                  :prop="col"
                  :label="col"
                  min-width="80"
                  show-overflow-tooltip
                />
              </el-table>
            </div>
          </div>

          <!-- 图表内容 -->
          <div v-if="activeTab === 'chart'" class="tab-content tab-fill">
            <div
              ref="chartRef"
              class="chart-container"
            />
          </div>

          <!-- 地图内容 -->
          <div v-if="activeTab === 'map'" class="tab-content tab-fill">
            <div
              v-if="currentResult.geoData && currentResult.geoData.features && currentResult.geoData.features.length"
              ref="mapRef"
              class="map-container"
            />
            <div v-else class="map-empty">
              该查询结果未包含地理坐标信息，暂无法展示地图点位
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-else class="empty-state">
          <div class="empty-icon">⌕</div>
          <p class="empty-text">输入查询内容，系统将自动分析数据并展示结果</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.query-shell {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px 24px;
  background: var(--gis-bg-deep, #020617);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}

.query-header {
  flex-shrink: 0;
  margin-bottom: 16px;
}

.query-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.02em;
}

.query-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
}

.query-body {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 16px;
}

/* ====== 左侧历史 ====== */
.query-history {
  flex-shrink: 0;
  width: 48px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  transition: width 0.2s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.query-history.expanded {
  width: 220px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 8px;
  cursor: pointer;
  border-bottom: 1px solid var(--gis-border, #334155);
  user-select: none;
  flex-shrink: 0;
}

.history-label {
  display: none;
  font-size: 12px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
  letter-spacing: 0.04em;
}

.expanded .history-label {
  display: inline;
}

.history-count {
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
  padding: 8px;
  display: none;
}

.expanded .history-list {
  display: block;
}

.history-item {
  position: relative;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 2px;
  margin-bottom: 4px;
  transition: background 0.15s;
}

.history-item:hover {
  background: rgba(34, 211, 238, 0.08);
}

.history-delete {
  position: absolute;
  top: 4px;
  right: 4px;
  display: none;
  width: 16px;
  height: 16px;
  line-height: 14px;
  text-align: center;
  font-size: 12px;
  color: var(--gis-text-muted, #64748b);
  background: rgba(2, 6, 23, 0.7);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 2px;
  cursor: pointer;
  padding: 0;
}

.history-item:hover .history-delete {
  display: block;
}

.history-delete:hover {
  color: #f87171;
  border-color: #f87171;
}

.history-text {
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.history-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}

.history-time {
  font-size: 9px;
  color: var(--gis-text-muted, #64748b);
}

.history-method {
  font-size: 9px;
  padding: 0 5px;
  border-radius: 8px;
  font-weight: 600;
}
.history-method.llm {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
}
.history-method.keyword {
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.12);
}

.history-empty {
  padding: 20px 8px;
  text-align: center;
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
}

.history-clear {
  padding: 8px;
  text-align: center;
  font-size: 10px;
  color: var(--gis-accent, #0ea5e9);
  cursor: pointer;
  border-top: 1px solid var(--gis-border, #334155);
}

/* ====== 主内容 ====== */
.query-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  gap: 12px;
  overflow-y: auto; /* 外层滚动：整列内容超高时往下滚，左侧历史保持不动（与 Agent 中心一致） */
}

/* 输入区 */
.input-area {
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

.query-input {
  flex: 1;
}

.query-input :deep(.el-textarea__inner) {
  background: var(--gis-bg-deep, #020617) !important;
  color: var(--gis-text, #f8fafc) !important;
  border: 1px solid var(--gis-border, #334155) !important;
  border-radius: 3px;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
}

.query-input :deep(.el-textarea__inner:focus) {
  border-color: var(--gis-accent, #0ea5e9) !important;
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.15) !important;
}

.query-btn {
  flex-shrink: 0;
  height: 74px;
  min-width: 80px;
  background: var(--gis-accent, #0ea5e9) !important;
  border-color: var(--gis-accent, #0ea5e9) !important;
  color: #020617 !important;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.query-btn:hover {
  background: #38bdf8 !important;
}

/* 语音输入按钮 */
.mic-btn {
  flex-shrink: 0;
  height: 74px;
  min-width: 64px;
  font-size: 18px;
}
.mic-btn.is-danger {
  animation: mic-pulse 1.2s ease-in-out infinite;
}
@keyframes mic-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

/* 摘要播报按钮区 */
.summary-actions {
  margin-left: auto;
  align-self: center;
  flex-shrink: 0;
}

.example-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  flex-wrap: wrap;
}

.example-label {
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
  flex-shrink: 0;
}

.example-tag {
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

.example-tag:hover {
  background: rgba(14, 165, 233, 0.2);
}

.keyboard-hint {
  margin-top: 6px;
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
  font-family: ui-monospace, "Consolas", monospace;
}

/* QueryAgent 解析过程 */
.agent-parse {
  flex-shrink: 0;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid rgba(14, 165, 233, 0.25);
  border-left: 3px solid var(--gis-accent, #0ea5e9);
  border-radius: 3px;
  overflow: hidden;
}

.agent-parse-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(14, 165, 233, 0.08);
  border-bottom: 1px solid rgba(14, 165, 233, 0.15);
}

.ap-agent-badge {
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 700;
  color: #020617;
  background: var(--gis-accent, #0ea5e9);
  border-radius: 10px;
  font-family: ui-monospace, "Consolas", monospace;
  letter-spacing: 0.03em;
}

.ap-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--gis-text, #f8fafc);
}

.ap-method {
  margin-left: auto;
  padding: 1px 10px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  white-space: nowrap;
}
.ap-method.llm {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
  border: 1px solid rgba(74, 222, 128, 0.3);
}
.ap-method.keyword {
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.3);
}

.agent-parse-body {
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ap-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 11px;
}

.ap-label {
  flex-shrink: 0;
  min-width: 32px;
  color: var(--gis-text-muted, #64748b);
  font-family: ui-monospace, "Consolas", monospace;
}

.ap-value {
  color: var(--gis-text, #f8fafc);
  line-height: 1.5;
  word-break: break-all;
}

.ap-value.intent {
  color: var(--gis-accent, #0ea5e9);
  font-weight: 600;
}

.ap-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ap-chip {
  padding: 1px 8px;
  font-size: 10px;
  color: var(--gis-text, #f8fafc);
  background: rgba(34, 211, 238, 0.08);
  border: 1px solid rgba(34, 211, 238, 0.2);
  border-radius: 10px;
  white-space: nowrap;
  font-family: ui-monospace, "Consolas", monospace;
}

.ap-chip em {
  font-style: normal;
  color: var(--gis-text-muted, #94a3b8);
  margin-right: 4px;
}

/* 结果区 */
.result-area {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 480px; /* 结果区最小高度（与 Agent 中心报告区一致），保证表格/图表/地图有足够展示空间 */
  gap: 10px;
}

/* 摘要卡片 */
.summary-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 14px;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-left: 3px solid var(--gis-accent, #0ea5e9);
  border-radius: 3px;
  flex-shrink: 0;
}

.summary-icon {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  font-family: ui-monospace, "Consolas", monospace;
  color: #020617;
  background: var(--gis-accent, #0ea5e9);
  border-radius: 50%;
}

.summary-content {
  flex: 1;
  min-width: 0;
}

.summary-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--gis-text, #f8fafc);
}

.summary-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--gis-text-muted, #64748b);
}

/* Tab 切换 */
.result-tabs {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 3px;
  padding: 2px;
}

.tab-btn {
  flex: 1;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--gis-text-muted, #94a3b8);
  background: transparent;
  border: none;
  border-radius: 2px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}

.tab-btn:hover:not(:disabled) {
  color: var(--gis-text, #f8fafc);
  background: rgba(34, 211, 238, 0.08);
}

.tab-btn.active {
  color: #020617;
  background: var(--gis-accent, #0ea5e9);
  font-weight: 600;
}

.tab-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 解析方式徽标 */
.method-badge {
  align-self: center;
  margin-left: auto;
  margin-right: 8px;
  padding: 2px 10px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 10px;
  white-space: nowrap;
}
.method-badge.llm {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.12);
  border: 1px solid rgba(74, 222, 128, 0.3);
}
.method-badge.keyword {
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.3);
}

/* Tab 内容 */
.tab-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 3px;
  padding: 12px;
  overflow: hidden;
}

.tab-summary .summary-full {
  flex: 1;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.7;
  color: var(--gis-text, #f8fafc);
  white-space: pre-wrap;
}

.tab-fill {
  padding: 4px;
}

/* 表格：外层不再滚动，由表格自身接管，消除双重滚动条 */
.table-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.result-table {
  width: 100%;
  height: 100%;
}

/* 图表 */
.chart-container {
  flex: 1;
  min-height: 0;
  width: 100%;
}

/* 地图 */
.map-container {
  flex: 1;
  min-height: 0;
  width: 100%;
  border-radius: 3px;
  overflow: hidden;
}
.map-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--gis-text-muted, #94a3b8);
  background: rgba(2, 6, 23, 0.4);
  border: 1px dashed var(--gis-border, #334155);
  border-radius: 3px;
}
.map-container :deep(.ol-attribution) {
  background: rgba(2, 6, 23, 0.6);
  font-size: 10px;
}
.map-container :deep(.ol-control button) {
  background: rgba(2, 6, 23, 0.6);
}
.map-container :deep(.ol-control button:hover) {
  background: rgba(14, 165, 233, 0.8);
}

/* 表格 */
.result-table :deep(.el-table) {
  --el-table-bg-color: transparent !important;
  --el-table-tr-bg-color: transparent !important;
  --el-table-header-bg-color: #020617 !important;
  --el-table-row-hover-bg-color: rgba(34, 211, 238, 0.08) !important;
  color: var(--gis-text, #f8fafc) !important;
}

.result-table :deep(th.el-table__cell) {
  background: #020617 !important;
  color: var(--gis-accent, #0ea5e9) !important;
  font-size: 11px;
  font-family: ui-monospace, "Consolas", monospace;
  border-bottom: 1px solid var(--gis-border, #334155) !important;
}

.result-table :deep(td.el-table__cell) {
  background: rgba(15, 23, 42, 0.92) !important;
  color: var(--gis-text, #f8fafc) !important;
  border-bottom: 1px solid var(--gis-border, #334155) !important;
  font-size: 11px;
}

/* 空状态 */
.empty-state {
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

.empty-icon {
  font-size: 48px;
  opacity: 0.3;
  color: var(--gis-text-muted, #94a3b8);
}

.empty-text {
  font-size: 13px;
  color: var(--gis-text-muted, #94a3b8);
  max-width: 300px;
  text-align: center;
  line-height: 1.6;
}
</style>