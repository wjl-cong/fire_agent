<script setup>
/**
 * ============================================================================
 * 焰哨 FlameSentry · 智慧火险预警监测平台 · 作战大屏
 *
 * 页面布局（三栏 flex 填充视口）：
 *   顶栏(56px) → 主体(左右侧栏+地图) → 底栏
 *
 * 核心数据流：
 *   fireDataJson / predictDailyJson / predictMonthJson → processedPredictData → displayFireData → map.vue
 *   地图点击聚合点 → clusterData → el-drawer（火点详情表格）
 *
 * 依赖：Vue3 | OpenLayers | ECharts | Element Plus | Turf.js | 天地图 | 高德天气API
 * ============================================================================
 */
import { ref, onMounted, onUnmounted, computed } from 'vue'
import Clock from '@/components/clock.vue'                          // 实时时钟
import MapModule from '@/components/map.vue'                       // OpenLayers 地图核心
import { downloadMap } from '@/utils/downLoad'                    // 地图导出 PNG
import { upDateCurrentTime, upDateCurrentDate, fethLocation } from '@/utils/timeWeather'
import { createDraw } from '@/utils/draw'                        // OL Draw 交互
import { calculateArea, calculateDistance } from '@/utils/computed' // Turf.js 量测
import { ElMessage } from 'element-plus'
import { fireIndexToLevel, riskScoreToLevel, getLevelInfoByScore, getLevelInfoByFireIndex, SUMMARY_MAP } from '@/utils/riskLevel'

// ========== API 服务 ==========
import { fetchHistoryFires, fetchPredictRisks } from '@/api/dashboard'

// ========== 图表组件（ECharts） ==========
import RightFirstChart  from '../chart/proportionFireRiskWarnings.vue'  // 预测火险占比（右上）
import RightSecondChart from '../chart/distributionFireRiskWarning.vue' // 预测火险分布（右下）
import LeftFirstChart   from '../chart/historicalFireHazardLevel.vue'   // 历史火险等级（左上）
import LeftSecondChart  from '../chart/historicalFireFrequency.vue'      // 历史火点频次（左下）

// ========== OpenLayers ==========
import VectorSource from 'ol/source/Vector'
import VectorLayer from 'ol/layer/Vector'
import { Heatmap as HeatmapLayer } from 'ol/layer'
import GeoJSON from 'ol/format/GeoJSON'

// ========== 数据文件（本地 JSON 作为 API 降级兜底） ==========
import fireDataJson     from '@/assets/Yunnan_fire.json'        // 历史火点（NASA FIRMS MODIS）
import borderDataJson   from '@/assets/Yunnan_border.json'       // 州市行政边界 GeoJSON
import predictMonthJson  from '@/assets/predict_2025_2026_month.json' // 逐月预测火险
import predictDailyJson  from '@/assets/predict_2025_2026_daily.json' // 逐日预测火险（含Day字段）

// ====== API 数据状态（ref 包装，computed 自动追踪） ======
const apiLoading = ref(false)
// DataAgent 数据管线状态：loading（同步中）/ api（后端数据）/ local（本地降级）
const dataSource = ref('loading')
const pipelineLabel = computed(() => ({
  loading: '同步数据中…',
  api: '后端数据',
  local: '本地降级',
}[dataSource.value] || dataSource.value))
const historyFireData = ref(fireDataJson)       // 初始值为本地 JSON
const predictDailyData = ref(predictDailyJson)
const predictMonthData = ref(predictMonthJson)

/** 从后端 API 加载大屏数据，失败时自动降级到本地 JSON */
async function loadDashboardData() {
  apiLoading.value = true
  dataSource.value = 'loading'
  try {
    const [historyResult, dailyResult, monthlyResult] = await Promise.all([
      fetchHistoryFires({ page_size: 5000 }).catch(() => null),
      fetchPredictRisks({ view_mode: 'daily' }).catch(() => null),
      fetchPredictRisks({ view_mode: 'monthly' }).catch(() => null),
    ])

    // 任一数据源成功即视为「后端数据」，全部失败才降级本地
    dataSource.value = (historyResult || dailyResult || monthlyResult) ? 'api' : 'local'

    // 如果 API 成功，将后端返回的 items 转换为本地一致的格式
    if (historyResult) {
      historyFireData.value = {
        type: 'FeatureCollection',
        features: (historyResult.items || []).map(item => ({
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [item.longitude, item.latitude],
          },
          properties: item,
        })),
      }
    }
    if (dailyResult) {
      predictDailyData.value = (dailyResult.items || []).map(item => ({
        City: item.city,
        Year: item.year,
        Month: item.month,
        Day: item.day,
        Base_Fire_Index: item.base_fire_index,
        Final_Fire_Index: item.final_fire_index,
        Fire_Level: item.fire_level,
        Pred_Fire_Count: item.pred_fire_count,
      }))
    }
    if (monthlyResult) {
      predictMonthData.value = (monthlyResult.items || []).map(item => ({
        City: item.city,
        Year: item.year,
        Month: item.month,
        Pred_Fire_Risk: item.pred_fire_risk ?? item.risk_score,
        Risk_Score: item.risk_score,
      }))
    }
  } catch {
    // 静默降级，保持本地 JSON
  } finally {
    apiLoading.value = false
  }
}

// ====== 州市中心经纬度映射（预测数据无精确坐标，用州市中心点代替） ======
const cityCenterMap = {
  "昆明市": [102.712251, 25.040609], "曲靖市": [103.797851, 25.501557],
  "玉溪市": [102.543907, 24.350461], "保山市": [99.167133, 25.111802],
  "昭通市": [103.717216, 27.336999], "丽江市": [100.233026, 26.872108],
  "普洱市": [100.973444, 22.777021], "临沧市": [100.08697, 23.886567],
  "楚雄彝族自治州": [101.546046, 25.035118],
  "红河哈尼族彝族自治州": [103.384182, 23.366775],
  "文山壮族苗族自治州": [104.24401, 23.36951],
  "西双版纳傣族自治州": [100.797936, 22.001726],
  "大理白族自治州": [100.225668, 25.589449],
  "德宏傣族景颇族自治州": [98.578363, 24.436694],
  "怒江傈僳族自治州": [98.854304, 25.850949],
  "迪庆藏族自治州": [99.706463, 27.826853]
}

// ====== 界面状态 ======
const currentTime   = ref('')
const currentDate   = ref('')
const weatherInfo   = ref(null)
const activeTool    = ref('')  // 当前展开的工具菜单（'layer' | 'draw' | 'measure' | ''）
const layers        = ref([])

// ====== 州市选项（从边界 GeoJSON 提取，用于下拉选择） ======
const cityOptions = computed(() => borderDataJson.features.map(f => f.properties.name))

// ====== 地图实例引用 ======
let drawSource = {}
let map = null
const mapRef   = ref(null)

// ====== Draw / Measure 交互 ======
let drawInteraction    = null
let measureInteraction = null
let measureSource = new VectorSource()
let measureLayer  = new VectorLayer({ source: measureSource, title: '测量图层' })

// ====== 火点详情抽屉 ======
const drawerVisible = ref(false)
const clusterData   = ref([])

// ====== 数据切换与筛选 ======
const currentDataType = ref('history') // 'history' | 'predict'
const predictViewMode = ref('daily') // 'daily' | 'monthly' — 预测火险的逐日/逐月视图
const searchDate      = ref('')

// 日期选择器可选年份：历史火点与预测火险数据范围不同
const HISTORY_FIRE_YEAR_MIN = 2021
const HISTORY_FIRE_YEAR_MAX = 2025
const PREDICT_YEAR_MIN = 2025
const PREDICT_YEAR_MAX = 2026

/** 历史火点：仅 2021–2025（与 Yunnan_fire.json 一致） */
const disabledHistorySearchDate = (date) => {
  const y = date.getFullYear()
  return y < HISTORY_FIRE_YEAR_MIN || y > HISTORY_FIRE_YEAR_MAX
}
/** 预测火险：仅 2025–2026 */
const disabledPredictSearchDate = (date) => {
  const y = date.getFullYear()
  return y < PREDICT_YEAR_MIN || y > PREDICT_YEAR_MAX
}
const searchCity      = ref('')

// ====== 火险预警详情展开状态 ======
const showFireWarningDetail = ref(false)

// ====== 火险预警 ======
// 预警等级：1=正常, 2=注意, 3=警告, 4=高度, 5=极度
// ★★★ 图表/预警数据与 predictViewMode 同步：逐日用逐日数据，逐月用逐月数据 ★★★
const fireWarning = computed(() => {
  if (currentDataType.value !== 'predict') return null

  const [year, month, day] = searchDate.value
    ? searchDate.value.split('-').map(Number)
    : [null, null, null]

  // 月份必须在 1-12 范围内（排除逐日模式选 13 日以上时 parts[1] 超出范围的问题）
  if (!year || !month || month < 1 || month > 12) return null

  // 生成动态摘要文本（使用 warningCount / highRiskCount）
  const generateSummaryText = (level, wCount, hCount) => {
    const texts = {
      1: '全省火险形势平稳，无明显风险区域，可正常开展各项生产活动。',
      2: `全省${wCount > 0 ? `${wCount}个州市` : '大部分地区'}需引起关注，建议加强火源管控和日常巡护。`,
      3: `全省火险等级升至警告水平，${wCount}个州市处于中高风险，需强化防控措施。`,
      4: `全省火险形势严峻，${wCount}个州市达中高风险，其中${hCount}个高度危险，需全面戒备。`,
      5: `全省已处于极度危险状态！${wCount}个州市全部告警，建议立即启动最高级别应急预案。`
    }
    return texts[level] || texts[1]
  }

  let records = []
  let isDaily = predictViewMode.value === 'daily'

  if (isDaily) {
    // —— 逐日数据：精确匹配 Year-Month-Day ——
    if (day === undefined || day === null) return null
    records = predictDailyData.value.filter(
      d => Number(d.Year) === year && Number(d.Month) === month && Number(d.Day) === day
    )
    if (records.length === 0) return null
  } else {
    // —— 逐月数据：精确匹配 Year-Month ——
    records = predictMonthData.value.filter(
      d => Number(d.Year) === year && Number(d.Month) === month
    )
    if (records.length === 0) return null
  }

  // ===== 整体评分计算 =====
  let avgScore, maxRecord, maxScore, overallLevel, regionList

  if (isDaily) {
    // 逐日：基于 Final_Fire_Index
    const indices = records.map(r => Number(r.Final_Fire_Index))
    avgScore = indices.reduce((s, v) => s + v, 0) / indices.length
    maxRecord = records.reduce((m, r) =>
      Number(r.Final_Fire_Index) > Number(m.Final_Fire_Index) ? r : m, records[0])
    maxScore = Number(maxRecord.Final_Fire_Index)
    overallLevel = fireIndexToLevel(avgScore)

    regionList = records.map(r => {
      const info = getLevelInfoByFireIndex(Number(r.Final_Fire_Index))
      return {
        city: r.City,
        riskScore: Number(r.Final_Fire_Index),
        riskLevel: info.level,
        label: info.label,
        color: info.color,
        desc: info.desc,
        measure: info.measure,
        predFireRisk: r.Pred_Fire_Count
      }
    }).sort((a, b) => Number(b.riskScore) - Number(a.riskScore))
  } else {
    // 逐月：基于 Risk_Score
    const scores = records.map(r => Number(r.Risk_Score))
    avgScore = scores.reduce((s, v) => s + v, 0) / scores.length
    maxRecord = records.reduce((m, r) =>
      Number(r.Risk_Score) > Number(m.Risk_Score) ? r : m, records[0])
    maxScore = Number(maxRecord.Risk_Score)
    overallLevel = Math.min(5, Math.max(1, Math.round((avgScore + maxScore * 0.5) / 0.2)))

    regionList = records.map(r => {
      const info = getLevelInfoByScore(r.Risk_Score)
      return {
        city: r.City,
        riskScore: Number(r.Risk_Score),
        riskLevel: info.level,
        label: info.label,
        color: info.color,
        desc: info.desc,
        measure: info.measure,
        predFireRisk: r.Pred_Fire_Risk
      }
    }).sort((a, b) => Number(b.riskScore) - Number(a.riskScore))
  }

  // ===== 整体摘要 =====
  const overallLevelInfo = isDaily
    ? getLevelInfoByFireIndex(avgScore)
    : getLevelInfoByScore(avgScore)
  const highRiskCount = regionList.filter(r => r.riskLevel >= 4).length
  const warningCount = regionList.filter(r => r.riskLevel >= 3).length

  return {
    year,
    month,
    day: isDaily ? day : null,
    viewMode: predictViewMode.value,
    overallLevel,
    overallLevelInfo,
    summary: { ...SUMMARY_MAP[overallLevel], summary: generateSummaryText(overallLevel, warningCount, highRiskCount) },
    regionList,
    avgScore: avgScore.toFixed(4),
    maxScore: maxScore.toFixed(4),
    topCity: maxRecord.City,
    highRiskCount,
    warningCount,
    totalRegions: records.length
  }
})

// ====== 预测数据处理（fireIndexToLevel 已从 riskLevel.js 导入） ======
// 逐日：predict_2025_2026_daily.json → fireIndexToLevel(Final_Fire_Index) 为等级，Pred_Fire_Count 四舍五入整数
// 逐月：predict_2025_2026_month.json → Risk_Score / Pred_Fire_Risk（原逻辑）
const processedPredictData = computed(() => {
  if (predictViewMode.value === 'daily') {
    if (!searchDate.value) {
      return { type: 'FeatureCollection', features: [] }
    }
    const parts = searchDate.value.split('-').map(Number)
    const year = parts[0]
    const month = parts[1]
    const day = parts[2]
    if (!year || year < 2025 || year > 2026 || !month || day === undefined) {
      return { type: 'FeatureCollection', features: [] }
    }
    const filtered = predictDailyData.value.filter(item =>
      Number(item.Year) === year &&
      Number(item.Month) === month &&
      Number(item.Day) === day
    )
    const features = filtered.map(item => {
      const fireCount = Math.round(Number(item.Pred_Fire_Count))
      const fireIndex = Number(item.Final_Fire_Index)
      const riskLevel = fireIndexToLevel(fireIndex)
      const coords = cityCenterMap[item.City] || [102, 25]
      const y = String(item.Year)
      const m = String(Number(item.Month)).padStart(2, '0')
      const d = String(Number(item.Day)).padStart(2, '0')
      const dateStr = `${y}-${m}-${d}`
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: coords },
        properties: {
          city: item.City,
          acq_date: dateStr,
          acq_time: '逐日预测',
          frp: fireCount,
          fire_count: fireCount,
          fire_index: fireIndex,
          risk_level: riskLevel,
          conf: riskLevel >= 4 ? 'high' : (riskLevel >= 2 ? 'nominal' : 'low')
        }
      }
    })
    return { type: 'FeatureCollection', features }
  }

  // —— 逐月 ——
  const dataSrc = predictMonthData.value
  let filtered = dataSrc
  if (searchDate.value) {
    const parts = searchDate.value.split('-').map(Number)
    const year = parts[0]
    if (year >= 2025 && year <= 2026) {
      const month = parts[1]
      filtered = dataSrc.filter(
        item => Number(item.Year) === year && Number(item.Month) === month
      )
    }
  }

  const features = filtered
    .filter(item => Number(item.Pred_Fire_Risk) > 0)
    .map(item => {
      const fireCount = Math.round(Number(item.Pred_Fire_Risk))
      const rs = Number(item.Risk_Score)
      let riskLevel = Math.ceil(rs / 0.2)
      if (rs === 0) riskLevel = 1
      riskLevel = Math.max(1, Math.min(5, riskLevel))
      const coords = cityCenterMap[item.City] || [102, 25]
      const dateStr = `${Number(item.Year)}-${String(Number(item.Month)).padStart(2, '0')}`
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: coords },
        properties: {
          city: item.City,
          acq_date: dateStr,
          acq_time: '逐月预测',
          frp: fireCount,
          fire_count: fireCount,
          risk_score: rs,
          risk_level: riskLevel,
          conf: riskLevel >= 4 ? 'high' : (riskLevel >= 2 ? 'nominal' : 'low')
        }
      }
    })
  return { type: 'FeatureCollection', features }
})

// ====== 各州市火险等级映射（用于州市边界底色渲染） ======
// 仅在预测模式 + 选了日期（且年份在 2025-2026）时生效
// 逐日模式：精确匹配 Year-Month-Day（当天等级）；逐月模式：精确匹配 Year-Month
const cityRiskData = computed(() => {
  if (currentDataType.value !== 'predict' || !searchDate.value) return null
  const parts = searchDate.value.split('-').map(Number)
  const year = parts[0]
  if (!year || year < 2025 || year > 2026) return null

  const riskMap = {}

  if (predictViewMode.value === 'daily') {
    const month = parts[1]
    const day = parts[2]
    if (month === undefined || day === undefined) return null
    predictDailyData.value.forEach(item => {
      if (
        Number(item.Year) !== year ||
        Number(item.Month) !== month ||
        Number(item.Day) !== day
      ) {
        return
      }
      riskMap[item.City] = fireIndexToLevel(Number(item.Final_Fire_Index))
    })
    return Object.keys(riskMap).length > 0 ? riskMap : null
  }

  predictMonthData.value.forEach(item => {
    if (Number(item.Year) !== year) return
    const month = parts[1]
    if (Number(item.Month) !== month) return

    const rs = Number(item.Risk_Score)
    let level = Math.ceil(rs / 0.2)
    if (rs === 0) level = 1
    level = Math.max(1, Math.min(5, level))
    riskMap[item.City] = level
  })
  return Object.keys(riskMap).length > 0 ? riskMap : null
})

const predictFireData = processedPredictData

// 为预测图表组件提供当前筛选后的数据
const predictDataForChart = computed(() => {
  if (currentDataType.value !== 'predict') return null
  if (!searchDate.value) return null
  const parts = searchDate.value.split('-').map(Number)
  const year = parts[0]
  if (!year || year < 2025 || year > 2026) return null
  const month = parts[1]

  if (predictViewMode.value === 'daily') {
    const day = parts[2]
    if (day === undefined) return null
    return predictDailyData.value.filter(
      d => Number(d.Year) === year && Number(d.Month) === month && Number(d.Day) === day
    )
  }
  return predictMonthData.value.filter(
    d => Number(d.Year) === year && Number(d.Month) === month
  )
})

// ====== 当前显示的火点数据（按日期筛选） ======
// 历史模式：按 acq_date 精确过滤 searchDate（searchDate 格式为 YYYY-MM-DD）
// 预测模式：processedPredictData 已精确按 searchDate 过滤，此处直接引用不做二次过滤
const displayFireData = computed(() => {
  if (currentDataType.value === 'history' && searchDate.value) {
    const features = historyFireData.value.features.filter(f => {
      if (!f.properties.acq_date) return false
      return f.properties.acq_date === searchDate.value
    })
    return { ...historyFireData.value, features }
  }
  return currentDataType.value === 'history' ? historyFireData.value : predictFireData.value
})

// ====== 切换历史/预测模式 ======
const toggleDataType = (type) => {
  currentDataType.value = type
  if (type === 'history') {
    // 历史筛选按日 YYYY-MM-DD；若留在逐月格式的值则清空
    const p = searchDate.value.split('-')
    if (p.length === 2) searchDate.value = ''
  } else if (type === 'predict' && searchDate.value) {
    const year = Number(searchDate.value.split('-')[0])
    if (!year || year < PREDICT_YEAR_MIN || year > PREDICT_YEAR_MAX) {
      searchDate.value = ''
    }
  }
  ElMessage.success({
    message: type === 'predict' ? '已切换至预测火点数据模式' : '已切换至历史火点数据模式',
    duration: 500
  })
}

// ====== 检索：定位州市 + 筛选日期 ======
const handleSearch = () => {
  if (searchCity.value) {
    const cityFeature = borderDataJson.features.find(f => f.properties.name.includes(searchCity.value))
    if (cityFeature) {
      const geometry = new GeoJSON().readFeature(cityFeature).getGeometry()
      const extent   = geometry.getExtent()
      if (mapRef.value) {
        mapRef.value.flyToExtent(extent)
        mapRef.value.highlightCity(cityFeature)
        ElMessage.success({ message: `已定位到 ${cityFeature.properties.name}`, duration: 1800 })
      }
    } else {
      ElMessage.warning({ message: '未找到该城市，请检查输入', duration: 2000 })
    }
  } else if (searchDate.value) {
    ElMessage.success({ message: `已筛选 ${searchDate.value} 的火点数据`, duration: 1800 })
  }
}

// ====== 天气 ======
const amapKey     = import.meta.env.VITE_AMAP_KEY || 'b09f93666c56d12e71ac488e70cdf2d3'
const showWeather = ref(false)
const toggleWeather = () => { showWeather.value = !showWeather.value }

// ====== 地图加载完成回调 ======
const handleMapLoaded = (mapInstance) => {
  map = mapInstance
  layers.value = map.getLayers().getArray()

  // 为每种几何类型创建独立画笔图层（点/线/面/圆）
  drawSource = {
    Point: new VectorSource(), LineString: new VectorSource(),
    Polygon: new VectorSource(), Circle: new VectorSource()
  }
  for (const [type, source] of Object.entries(drawSource)) {
    map.addLayer(new VectorLayer({ source, title: '画笔图层' }))
  }
  map.addLayer(measureLayer) // 测量图层
}

// ====== 聚合点击 → 打开抽屉 ======
const handleClusterClick = (data) => {
  clusterData.value = data
  drawerVisible.value = true
}

// ====== 定位到云南省中心 ======
const animateView = () => {
  if (!map) return
  const view = map.getView()
  view.cancelAnimations()
  view.animate({ center: [102.42, 25.02], zoom: 6, duration: 1000 })
}

// ====== 标绘工具 ======
const activeDrawTool = (type) => {
  if (!map) return
  if (measureInteraction) { map.removeInteraction(measureInteraction); measureInteraction = null }
  if (drawInteraction)    { map.removeInteraction(drawInteraction); drawInteraction = null }
  drawInteraction = createDraw({ type, source: drawSource[type] })
  map.addInteraction(drawInteraction)
}

// ====== 清空标绘与测量 ======
const clearDraw = () => {
  for (const key in drawSource) drawSource[key].clear()
  measureSource.clear()
  map.getOverlays().getArray().slice(0).forEach(overlay => map.removeOverlay(overlay))
}

// ====== 测量工具 ======
const activeMeasureTool = (type) => {
  if (!map) return
  if (drawInteraction)    { map.removeInteraction(drawInteraction);    drawInteraction = null }
  if (measureInteraction) { map.removeInteraction(measureInteraction); measureInteraction = null }
  measureInteraction = createDraw({ type, source: measureSource })
  map.addInteraction(measureInteraction)
  measureInteraction.on('drawend', (e) => {
    const geometry = e.feature.getGeometry()
    const coords   = geometry.getCoordinates()
    if (type === 'LineString') calculateDistance(coords)
    else if (type === 'Polygon') calculateArea(coords[0])
    map.removeInteraction(measureInteraction)
    measureInteraction = null
  })
}

// ====== 生命周期 ======
// ====== AI 火情识别左侧栏（视觉模型 qwen-vl 系列，含历史/MD渲染/语音播报） ======
import authFetch from '@/utils/authFetch'
import { API_V1 } from '@/utils/config'
import renderMarkdown from '@/utils/markdown'
import { speakState, speakText, cleanupSpeech } from '@/utils/speech'

const VISION_API = `${API_V1}/vision`
const visionOpen = ref(false)
const visionAnalyzing = ref(false)
const visionFile = ref(null)
const visionDetail = ref(null)   // 当前展示详情：{ id, filename, model, analysis, created_at, imageSrc }
const visionHistory = ref([])
const visionError = ref('')

// 拉取识别历史（带鉴权）
const loadVisionHistory = async () => {
  try {
    const res = await authFetch(`${VISION_API}/history`)
    const json = await res.json()
    if (json.code === 200) visionHistory.value = json.data || []
  } catch { /* 静默失败 */ }
}

// 通过鉴权接口加载历史图片（blob → objectURL）
const loadVisionImage = async (id) => {
  try {
    const res = await authFetch(`${VISION_API}/image/${id}`)
    if (!res.ok) return ''
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  } catch { return '' }
}

// 点击历史条目 → 加载详情 + 图片
const openVisionRecord = async (h) => {
  visionError.value = ''
  visionDetail.value = { ...h, imageSrc: '' }
  if (h.has_image) {
    visionDetail.value.imageSrc = await loadVisionImage(h.id)
  }
}

// 删除历史记录
const deleteVisionHistory = async (h) => {
  try {
    const res = await authFetch(`${VISION_API}/history/${h.id}`, { method: 'DELETE' })
    const json = await res.json()
    if (json.code === 200) {
      visionHistory.value = visionHistory.value.filter(x => x.id !== h.id)
      if (visionDetail.value && visionDetail.value.id === h.id) visionDetail.value = null
      ElMessage.success('已删除')
    } else {
      ElMessage.error(json.detail || '删除失败')
    }
  } catch { ElMessage.error('删除失败') }
}

// 选择图片（新识别）
const onVisionFile = (uploadFile) => {
  const raw = uploadFile.raw
  if (!raw) return
  if (raw.size > 10 * 1024 * 1024) { ElMessage.error('图片不能超过 10MB'); return }
  visionFile.value = raw
  visionError.value = ''
  // 先本地预览
  visionDetail.value = {
    id: null, filename: raw.name, model: '', created_at: '待识别',
    analysis: '> 已选择图片，点击「开始识别」进行火情分析', imageSrc: URL.createObjectURL(raw),
  }
}

// 执行识别
const analyzeVision = async () => {
  if (!visionFile.value) return
  visionAnalyzing.value = true
  visionError.value = ''
  try {
    const fd = new FormData()
    fd.append('file', visionFile.value)
    const res = await authFetch(`${VISION_API}/analyze`, { method: 'POST', body: fd })
    const json = await res.json()
    if (json.code === 200 && json.data.ok) {
      visionDetail.value = {
        id: json.data.id,
        filename: json.data.filename,
        model: json.data.model,
        analysis: json.data.analysis,
        created_at: '刚刚',
        imageSrc: visionDetail.value?.imageSrc || '',
      }
      visionFile.value = null
      loadVisionHistory()
    } else {
      visionError.value = json.data?.detail || '识别失败'
    }
  } catch {
    visionError.value = '识别请求失败，请检查后端服务'
  } finally {
    visionAnalyzing.value = false
  }
}

onMounted(() => {
  loadVisionHistory()
  upDateCurrentTime(currentTime)
  upDateCurrentDate(currentDate)

  // 异步加载天气
  fethLocation(amapKey, weatherInfo)

  // 从后端 API 加载大屏数据（失败自动降级到本地 JSON）
  loadDashboardData()

  // 每秒更新时间
  const timer = setInterval(() => {
    upDateCurrentTime(currentTime)
    upDateCurrentDate(currentDate)
  }, 1000)

  onUnmounted(() => {
    clearInterval(timer)
    cleanupSpeech() // 停止语音播报/录音
    if (map) {
      if (drawInteraction)    map.removeInteraction(drawInteraction)
      if (measureInteraction) map.removeInteraction(measureInteraction)
    }
  })
})

// ====== 工具菜单切换 ======
const toggleToolMenu = (tool) => {
  activeTool.value = activeTool.value === tool ? '' : tool
}

// ====== 图层显隐切换 ======
const toggleLayer = (layer) => {
  layer.setVisible(!layer.getVisible())
}

// ====== 图层查找/移除工具 ======
const removeLayerByTitle = (title) => {
  if (!map) return
  map.getLayers().getArray().forEach(layer => {
    if (layer.get('title') === title) map.removeLayer(layer)
  })
}
const getLayerByTitle = (title) => {
  if (!map) return null
  return map.getLayers().getArray().find(layer => layer.get('title') === title)
}

// ====== 热力图 ======
const showHeatmap      = ref(false)
let heatMapLayerInst  = ref(null)

const performHeatmapAnalysis = () => {
  if (!map) return
  const pointLayer  = getLayerByTitle('火点分布')
  const predictLayer = getLayerByTitle('预测火险图层')

  if (showHeatmap.value) {
    // 关闭：移除热力图，恢复点位图层
    removeLayerByTitle('热力图')
    if (currentDataType.value === 'history' && pointLayer)  pointLayer.setVisible(true)
    if (currentDataType.value === 'predict' && predictLayer) predictLayer.setVisible(true)
  } else {
    // 开启：创建热力图层，隐藏点位图层
    const heatSource = new VectorSource({
      features: new GeoJSON().readFeatures(displayFireData.value)
    })
    heatMapLayerInst.value = new HeatmapLayer({
      source: heatSource,
      blur:   currentDataType.value === 'predict' ? 25 : 15,
      radius: currentDataType.value === 'predict' ? 12 : 8,
      // 渐变色：透明 → 青色 → 橙色 → 红色
      gradient: ['rgba(0,0,0,0)', '#0e7490', '#0891b2', '#f97316', '#dc2626'],
      weight: (feature) => {
        if (currentDataType.value === 'predict') {
          // 逐日/逐月均带 risk_level；逐日 risk_score 为指数量级，不宜直接作权重
          const rl = feature.get('risk_level')
          if (rl != null) return 0.12 + (Math.min(5, Math.max(1, Number(rl))) / 5) * 0.75
          const rs = feature.get('risk_score')
          return rs != null ? Math.min(Number(rs) * 0.8, 0.95) : 0.15
        }
        const frp = feature.get('frp')
        return frp ? Math.min(frp / 150, 0.8) : 0.1
      },
      zIndex: 1
    })
    heatMapLayerInst.value.set('title', '热力图')
    map.addLayer(heatMapLayerInst.value)
    if (pointLayer)   pointLayer.setVisible(false)
    if (predictLayer) predictLayer.setVisible(false)
  }

  showHeatmap.value = !showHeatmap.value
  map.render()
}
</script>

<template>
  <div class="gis-shell">
    <div class="gis-grid-layer" aria-hidden="true" />

    <!-- ======================= 顶栏 ======================= -->
    <header class="gis-topbar">
      <div class="gis-brand-block">
        <div class="gis-logo-badge" title="GIS">GIS</div>
        <div class="gis-title-block">
          <h1 class="gis-main-title">焰哨多Agent与可视化平台</h1>
          <p class="gis-sub-title">FlameSentry · Spatial Fire Risk Intelligence · Yunnan</p>
        </div>
      </div>

      <div class="gis-topbar-center">
        <!-- 数据模式切换 -->
        <div class="gis-seg" role="group" aria-label="数据模式">
          <button type="button" class="gis-seg-btn" :class="{ active: currentDataType === 'history' }" @click="toggleDataType('history')">历史火点</button>
          <button type="button" class="gis-seg-btn" :class="{ active: currentDataType === 'predict' }" @click="toggleDataType('predict')">预测火险</button>
        </div>
        <!-- 逐日/逐月切换（仅预测模式显示） -->
        <div v-if="currentDataType === 'predict'" class="gis-seg" role="group" aria-label="时间粒度">
          <button type="button" class="gis-seg-btn" :class="{ active: predictViewMode === 'daily' }" @click="predictViewMode = 'daily'">逐日</button>
          <button type="button" class="gis-seg-btn" :class="{ active: predictViewMode === 'monthly' }" @click="predictViewMode = 'monthly'">逐月</button>
        </div>
        <!-- 日期/州市筛选 -->
        <div class="gis-filters">
          <!-- 历史 / 预测分两个 picker，避免 Element Plus 复用实例时仍沿用预测的年份禁用逻辑 -->
          <el-date-picker
            v-if="currentDataType === 'history'"
            key="picker-history-fire"
            v-model="searchDate"
            type="date"
            placeholder="选择历史日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            :disabled-date="disabledHistorySearchDate"
            size="small"
            class="gis-el-compact gis-date"
          />
          <el-date-picker
            v-else
            key="picker-predict-risk"
            v-model="searchDate"
            :type="predictViewMode === 'daily' ? 'date' : 'month'"
            :placeholder="predictViewMode === 'daily' ? '选择日期' : '选择月份'"
            :format="predictViewMode === 'daily' ? 'YYYY-MM-DD' : 'YYYY-MM'"
            :value-format="predictViewMode === 'daily' ? 'YYYY-MM-DD' : 'YYYY-MM'"
            :disabled-date="disabledPredictSearchDate"
            size="small"
            class="gis-el-compact gis-date"
          />
          <el-select v-model="searchCity" placeholder="行政区" size="small" class="gis-el-compact gis-city" filterable clearable>
            <el-option v-for="city in cityOptions" :key="city" :label="city" :value="city" />
          </el-select>
          <el-button type="primary" size="small" @click="handleSearch">检索</el-button>
        </div>
        <!-- ====== 火险预警信息（摘要 + 各州市详情）====== -->
        <div v-if="currentDataType === 'predict' && fireWarning" class="fire-warning-wrap">
          <!-- 顶栏：整体摘要（可点击展开详情） -->
          <div
            class="fire-warning-summary"
            :style="{ borderColor: fireWarning.summary.color }"
            @click="showFireWarningDetail = !showFireWarningDetail"
          >
            <span class="fw-icon" :style="{ color: fireWarning.summary.color }">{{ fireWarning.summary.icon }}</span>
            <span class="fw-label" :style="{ color: fireWarning.summary.color }">
              {{ fireWarning.year }}-{{ String(fireWarning.month).padStart(2, '0') }}{{ fireWarning.day ? ('-' + String(fireWarning.day).padStart(2, '0')) : '' }} {{ fireWarning.summary.label }}
            </span>
            <span class="fw-text">{{ fireWarning.summary.summary }}</span>
            <span class="fw-meta">
              高风险<span class="fw-hl">{{ fireWarning.highRiskCount }}</span>个 ·
              中风险<span class="fw-hl">{{ fireWarning.warningCount - fireWarning.highRiskCount }}</span>个 ·
              <span class="fw-open">{{ showFireWarningDetail ? '收起▲' : '展开详情▼' }}</span>
            </span>
          </div>

          <!-- 展开详情：各州市预警表格 -->
          <div v-if="showFireWarningDetail" class="fire-warning-detail">
            <div class="fw-detail-grid">
              <div
                v-for="region in fireWarning.regionList"
                :key="region.city"
                class="fw-region-card"
                :style="{ borderLeftColor: region.color }"
              >
                <div class="fw-region-header">
                  <span class="fw-city">{{ region.city }}</span>
                  <span class="fw-level-tag" :style="{ background: region.color }">{{ region.label }}</span>
                </div>
                <div class="fw-region-desc">{{ region.desc }}</div>
                <div class="fw-region-measure">
                  <span class="fw-measure-icon">&#x2714;</span>
                  {{ region.measure }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="gis-topbar-right">
        <!-- 状态列：DataAgent 管线 + 天气 垂直堆叠（避免挤压左侧按钮） -->
        <div class="topbar-status-col">
          <!-- DataAgent 数据管线状态 -->
          <div
            class="agent-pipeline"
            :class="dataSource"
            :title="apiLoading ? 'DataAgent 正在同步后端数据…' : (dataSource === 'api' ? 'DataAgent 从后端 API 拉取数据' : '后端不可用，DataAgent 已降级本地数据')"
          >
            <span class="ap-dot"></span>
            <span class="ap-text">DataAgent · {{ pipelineLabel }}</span>
          </div>
          <!-- 高德天气 -->
          <div class="header-weather">
            <div class="weather-button-mini" @click.stop="toggleWeather">
              <i class="iconfont icon-duoyun"></i>
              <span v-if="weatherInfo && weatherInfo.city">{{ weatherInfo.city }} {{ weatherInfo.temperature }}℃</span>
              <span v-else>定位天气…</span>
            </div>
            <div class="weather-popup" v-if="showWeather && weatherInfo && weatherInfo.city" @click.stop>
              <div class="weather-details">
                <div class="city"><div>{{ weatherInfo.city }}</div><span>{{ weatherInfo.weather }}</span></div>
                <div class="info">
                  <span><i class="iconfont icon-wendu"></i>{{ weatherInfo.temperature }}℃</span>
                  <span><i class="iconfont icon-fengxiang"></i>{{ weatherInfo.winddirection }}</span>
                  <span><i class="iconfont icon-shidu"></i>{{ weatherInfo.humidity }}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="header-time"><Clock /></div>
      </div>
    </header>

    <!-- ======================= 主体三栏 ======================= -->
    <div class="gis-body">
      <!-- AI 火情识别侧栏（视觉模型，可折叠） -->
      <aside class="vision-rail" :class="{ open: visionOpen }">
        <!-- 折叠条 -->
        <div class="vr-collapse" :title="visionOpen ? '收起火情识别' : '展开 AI 火情识别（视觉模型）'" @click="visionOpen = !visionOpen">
          <span class="vr-coll-icon" :class="{ blink: visionAnalyzing }">◉</span>
          <span class="vr-coll-text">火情识别</span>
          <span class="vr-coll-arrow">{{ visionOpen ? '«' : '»' }}</span>
        </div>

        <!-- 展开面板 -->
        <div v-show="visionOpen" class="vr-panel">
          <header class="vr-head">
            <span class="vr-badge">VisionAgent</span>
            <span class="vr-title">AI 火情识别</span>
            <span class="vr-model-tag">{{ visionDetail?.model || 'qwen-vl' }}</span>
          </header>

          <!-- 上传识别 -->
          <div class="vr-upload">
            <el-upload
              drag
              :auto-upload="false"
              :show-file-list="false"
              accept="image/*"
              :on-change="onVisionFile"
              class="vr-upload-box"
            >
              <div class="vu-mini">
                <div class="vu-icon">🖼</div>
                <div class="vu-text">点击 / 拖拽上传火场照片</div>
                <div class="vu-tip">jpg / png / webp · ≤10MB</div>
              </div>
            </el-upload>
            <el-button
              type="primary" size="small" style="width: 100%; margin-top: 8px"
              :loading="visionAnalyzing" :disabled="!visionFile"
              @click="analyzeVision"
            >{{ visionAnalyzing ? '视觉模型识别中…' : '开始识别' }}</el-button>
            <div v-if="visionError" class="vr-error">{{ visionError }}</div>
          </div>

          <!-- 当前详情（新识别 / 历史） -->
          <div v-if="visionDetail" class="vr-detail">
            <div class="vrd-head">
              <span class="vrd-file" :title="visionDetail.filename">{{ visionDetail.filename || '识别结果' }}</span>
              <span class="vrd-time">{{ visionDetail.created_at }}</span>
            </div>
            <img v-if="visionDetail.imageSrc" :src="visionDetail.imageSrc" class="vrd-img" alt="识别图片" />
            <div class="vrd-actions">
              <el-button
                size="small"
                :type="speakState.speaking || speakState.loading ? 'danger' : 'default'"
                plain
                @click="speakText(visionDetail.analysis)"
              >{{ speakState.speaking || speakState.loading ? '■ 停止播报' : '🔊 语音播报' }}</el-button>
            </div>
            <div class="vrd-analysis markdown-body" v-html="renderMarkdown(visionDetail.analysis)" />
          </div>

          <!-- 识别历史 -->
          <div class="vr-history">
            <div class="vrh-title">识别历史（{{ visionHistory.length }}）</div>
            <div class="vrh-list">
              <div v-if="!visionHistory.length" class="vrh-empty">暂无识别记录，上传图片开始识别</div>
              <div
                v-for="h in visionHistory" :key="h.id"
                class="vrh-item"
                :class="{ active: visionDetail && visionDetail.id === h.id }"
                @click="openVisionRecord(h)"
              >
                <div class="vrh-info">
                  <div class="vrh-file">{{ h.filename || '未命名图片' }}</div>
                  <div class="vrh-time">{{ h.created_at }} · {{ h.model }}</div>
                </div>
                <el-button class="vrh-del" size="small" text type="danger" @click.stop="deleteVisionHistory(h)">删</el-button>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- 左栏：历史图表 -->
      <aside class="gis-rail gis-rail-left">
        <section class="gis-panel">
          <header class="gis-panel-head">
            <span class="gis-panel-kicker">HIST</span>
            <h2 class="gis-panel-title">历史火点危害等级</h2>
          </header>
          <div class="gis-panel-body"><LeftFirstChart :fireData="historyFireData" /></div>
        </section>
        <section class="gis-panel">
          <header class="gis-panel-head">
            <span class="gis-panel-kicker">FREQ</span>
            <h2 class="gis-panel-title">历史火点发生频次</h2>
          </header>
          <div class="gis-panel-body"><LeftSecondChart :fireData="historyFireData" /></div>
        </section>
      </aside>

      <!-- 中栏：地图 + 工具栏 -->
      <div class="gis-map-stage">
        <div class="gis-map-frame">
          <span class="gis-corner tl" /><span class="gis-corner tr" />
          <span class="gis-corner bl" /><span class="gis-corner br" />
          <div class="gis-map-inner">
            <MapModule
              ref="mapRef"
              :fireData="currentDataType === 'history' ? displayFireData : { type: 'FeatureCollection', features: [] }"
              :predictData="currentDataType === 'predict' ? displayFireData : { type: 'FeatureCollection', features: [] }"
              :currentDataType="currentDataType"
              :cityRiskData="cityRiskData"
              @map-loaded="handleMapLoaded"
              @cluster-click="handleClusterClick"
            />
          </div>
        </div>
        <!-- 底栏工具 -->
        <div class="gis-dock">
          <div class="gis-dock-item" @click="toggleToolMenu('layer')">
            <i class="iconfont icon-023tuceng"></i><span>图层</span>
            <div v-if="activeTool === 'layer'" class="gis-dock-menu" @click.stop>
              <div v-for="layer in layers" :key="layer.get('title')" @click.stop="toggleLayer(layer)" :class="{ on: layer.getVisible() }">{{ layer.get('title') }}</div>
            </div>
          </div>
          <div class="gis-dock-item" @click="toggleToolMenu('draw')">
            <i class="iconfont icon-xihuabi"></i><span>标绘</span>
            <div v-if="activeTool === 'draw'" class="gis-dock-menu" @click.stop>
              <div @click.stop="activeDrawTool('Point')">点</div>
              <div @click.stop="activeDrawTool('LineString')">线</div>
              <div @click.stop="activeDrawTool('Polygon')">面</div>
              <div @click.stop="clearDraw">清空</div>
            </div>
          </div>
          <div class="gis-dock-item" @click="toggleToolMenu('measure')">
            <i class="iconfont icon-celiangleixing"></i><span>量测</span>
            <div v-if="activeTool === 'measure'" class="gis-dock-menu" @click.stop>
              <div @click.stop="activeMeasureTool('LineString')">距离</div>
              <div @click.stop="activeMeasureTool('Polygon')">面积</div>
            </div>
          </div>
          <div class="gis-dock-item" @click="performHeatmapAnalysis">
            <i class="iconfont icon-relitu" :class="{ 'is-on': showHeatmap }"></i>
            <span>{{ showHeatmap ? '关热力' : '热力' }}</span>
          </div>
          <div class="gis-dock-item" @click="downloadMap(map)">
            <i class="iconfont icon-ico_dituxiazai"></i><span>导出</span>
          </div>
          <div class="gis-dock-item" title="定位到云南省范围" @click="animateView">
            <i class="iconfont icon-ditu01 gis-dock-icon-fit"></i><span>全省</span>
          </div>
        </div>
      </div>

      <!-- 右栏：预测图表 -->
      <aside class="gis-rail gis-rail-right">
        <section class="gis-panel">
          <header class="gis-panel-head">
            <span class="gis-panel-kicker">PRED</span>
            <h2 class="gis-panel-title">预测火险等级占比</h2>
          </header>
          <div class="gis-panel-body"><RightFirstChart :searchDate="searchDate" :viewMode="predictViewMode" :predictData="predictDataForChart" /></div>
        </section>
        <section class="gis-panel">
          <header class="gis-panel-head">
            <span class="gis-panel-kicker">DIST</span>
            <h2 class="gis-panel-title">预测火险等级频次分布</h2>
          </header>
          <div class="gis-panel-body"><RightSecondChart :searchDate="searchDate" :viewMode="predictViewMode" :predictData="predictDataForChart" /></div>
        </section>
      </aside>
    </div>

    <!-- ======================= 火点详情抽屉 ======================= -->
    <el-drawer v-model="drawerVisible" :title="currentDataType === 'history' ? '区域火点详细信息' : '预测区域火险详细信息'" direction="rtl" size="430px" :modal="false" :lock-scroll="false" class="fire-drawer">
      <el-table :data="clusterData" style="width: 100%" height="calc(100vh - 100px)">
        <!-- 历史数据列 -->
        <template v-if="currentDataType === 'history'">
          <el-table-column prop="acq_date" label="日期" min-width="100" />
          <el-table-column prop="acq_time" label="时间" min-width="70" />
          <el-table-column prop="frp" label="FRP" min-width="70" />
          <el-table-column prop="conf" label="置信度" min-width="80">
            <template #default="scope">
              <el-tag :type="scope.row.conf === 'high' ? 'danger' : 'success'" size="small">
                {{ scope.row.conf === 'high' ? '高' : (scope.row.conf === 'nominal' ? '中' : '低') }}
              </el-tag>
            </template>
          </el-table-column>
        </template>
        <!-- 预测数据列 -->
        <template v-else>
          <el-table-column prop="city" label="城市" min-width="100" show-overflow-tooltip />
          <el-table-column prop="acq_date" :label="predictViewMode === 'daily' ? '日期' : '月份'" min-width="90" />
          <el-table-column prop="fire_count" :label="predictViewMode === 'daily' ? '预测火点数(整数)' : '预测火点数量'" min-width="120" align="center" />
          <el-table-column label="火险等级" min-width="80" align="center">
            <template #default="scope">
              <el-tooltip
                effect="dark"
                :content="predictViewMode === 'daily'
                  ? ('火险指数: ' + (scope.row.fire_index != null ? Number(scope.row.fire_index).toFixed(1) : ''))
                  : ('火险评分: ' + (scope.row.risk_score ? scope.row.risk_score.toFixed(4) : '0.0000'))"
                placement="left"
              >
                <el-tag :type="scope.row.risk_level >= 4 ? 'danger' : (scope.row.risk_level >= 3 ? 'warning' : 'primary')" size="small">{{ scope.row.risk_level || 1 }}级</el-tag>
              </el-tooltip>
            </template>
          </el-table-column>
        </template>
      </el-table>
    </el-drawer>

    <!-- ======================= 底栏 ======================= -->
    <footer class="gis-footer">
      <span class="gis-footer-coord">EPSG:4326 · WGS84 · wjl · 19136220923@163.com</span>
      <span class="gis-footer-copy">© 2026 焰哨多Agent与可视化平台</span>
      <a class="gis-footer-link" href="https://gitee.com/wjl2004/fire_agent_front" target="_blank">Gitee</a>
    </footer>
  </div>
</template>

<style lang="scss" scoped>
/* 整体容器 */
.gis-shell {
  user-select: none;
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 100%;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  background: var(--gis-bg-deep);
  color: var(--gis-text);
  overflow: hidden;
}

/* 网格背景装饰 */
.gis-grid-layer {
  pointer-events: none;
  position: absolute;
  inset: 0;
  z-index: 0;
  background-image:
    linear-gradient(var(--gis-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--gis-grid) 1px, transparent 1px);
  background-size: 48px 48px;
  opacity: 0.55;
}

/* 顶栏（overflow 可见，便于预警详情以浮层展开而不撑高整栏、挤压下方图表） */
.gis-topbar {
  position: relative;
  z-index: 20;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 56px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--gis-border);
  background: linear-gradient(180deg, #0f172a 0%, #020617 100%);
  box-shadow: 0 1px 0 rgba(34, 211, 238, 0.12);
  overflow: visible;
}

.gis-brand-block {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.gis-logo-badge {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: ui-monospace, "Cascadia Code", "Consolas", monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #020617;
  background: linear-gradient(145deg, #22d3ee, #0891b2);
  border: 1px solid rgba(34, 211, 238, 0.6);
  border-radius: 4px;
}

.gis-title-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.gis-main-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--gis-text);
}

.gis-sub-title {
  margin: 0;
  font-size: 11px;
  font-family: ui-monospace, "Consolas", monospace;
  color: var(--gis-text-muted);
  letter-spacing: 0.02em;
}

.gis-topbar-center {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 14px 20px;
  min-width: 0;
  overflow: visible;
}

.gis-seg {
  display: inline-flex;
  padding: 2px;
  border-radius: 4px;
  border: 1px solid var(--gis-border);
  background: var(--gis-bg-panel);
}

.gis-seg-btn {
  border: none;
  cursor: pointer;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--gis-text-muted);
  background: transparent;
  border-radius: 2px;
  transition: color 0.15s, background 0.15s;
}

.gis-seg-btn:hover {
  color: var(--gis-text);
}

.gis-seg-btn.active {
  color: #020617;
  background: var(--gis-accent);
}

.gis-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 火险预警提示 */
.gis-warning-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid;
  border-radius: 4px;
  font-size: 11px;
  font-family: ui-monospace, "Consolas", monospace;
  white-space: nowrap;
  animation: warningPulse 2s ease-in-out infinite;

  .warning-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
    animation: dotPulse 1.5s ease-in-out infinite;
  }

  .warning-label {
    font-weight: 700;
    letter-spacing: 0.06em;
    flex-shrink: 0;
  }

  .warning-desc {
    color: var(--gis-text-muted);
    font-size: 10px;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}

@keyframes warningPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.2); }
  50% { box-shadow: 0 0 0 4px rgba(220, 38, 38, 0); }
}

@keyframes dotPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.8); }
}

/* ===== 火险预警面板：摘要占顶栏一行，详情绝对定位浮层，避免撑高顶栏导致侧栏四图错位 ===== */
.fire-warning-wrap {
  position: relative;
  z-index: 120;
  display: flex;
  flex-direction: column;
  gap: 0;
  max-width: 620px;
  flex-shrink: 1;
  min-width: 0;
  animation: fwFadeIn 0.25s ease-out;
}

@keyframes fwFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 摘要行 */
.fire-warning-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid;
  border-radius: 4px;
  font-size: 11px;
  font-family: ui-monospace, "Consolas", monospace;
  cursor: pointer;
  transition: background 0.15s;
  animation: warningPulse 3s ease-in-out infinite;
}

.fire-warning-summary:hover {
  background: rgba(20, 30, 50, 0.95);
}

@keyframes warningPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.15); }
  50% { box-shadow: 0 0 0 3px rgba(220, 38, 38, 0); }
}

.fw-icon { font-size: 14px; flex-shrink: 0; }
.fw-label {
  font-weight: 700;
  letter-spacing: 0.06em;
  flex-shrink: 0;
  white-space: nowrap;
}
.fw-text {
  color: var(--gis-text-muted);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}
.fw-meta {
  color: var(--gis-text-muted);
  flex-shrink: 0;
  white-space: nowrap;
  .fw-hl { color: var(--gis-accent); font-weight: 700; }
  .fw-open { color: var(--gis-accent); margin-left: 4px; }
}

/* 详情区：浮在地图上方，不参与文档流高度 */
.fire-warning-detail {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: min(680px, calc(100vw - 24px));
  max-height: min(340px, 42vh);
  background: rgba(15, 23, 42, 0.98);
  border: 1px solid var(--gis-border);
  border-radius: 4px;
  padding: 10px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--gis-border) transparent;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.65);
  animation: fwDetailIn 0.18s ease-out;
}

@keyframes fwDetailIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.fw-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 6px;
}

.fw-region-card {
  padding: 7px 10px;
  background: var(--gis-bg-panel-2, #0f172a);
  border: 1px solid var(--gis-border);
  border-left: 3px solid;
  border-radius: 3px;
  transition: background 0.15s;
}

.fw-region-card:hover {
  background: rgba(30, 41, 59, 0.8);
}

.fw-region-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
  gap: 6px;
}

.fw-city {
  font-size: 12px;
  font-weight: 600;
  color: var(--gis-text);
}

.fw-level-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  color: #020617;
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
}

.fw-region-desc {
  font-size: 10px;
  color: var(--gis-text-muted);
  margin-bottom: 4px;
  line-height: 1.4;
}

.fw-region-measure {
  font-size: 10px;
  color: var(--gis-text-muted);
  line-height: 1.4;
  display: flex;
  align-items: flex-start;
  gap: 4px;

  .fw-measure-icon {
    color: #22d3ee;
    flex-shrink: 0;
    margin-top: 1px;
    font-size: 10px;
  }
}

.gis-el-compact {
  :deep(.el-input__wrapper) {
    background: var(--gis-bg-panel) !important;
    box-shadow: 0 0 0 1px var(--gis-border) inset !important;
  }
  :deep(.el-input__inner) {
    color: var(--gis-text) !important;
    font-size: 12px;
  }
}

.gis-date { min-width: 118px; }
.gis-city { width: 140px; }

.gis-topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

/* 状态列：DataAgent 管线 + 天气 垂直堆叠 */
.topbar-status-col {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

/* DataAgent 数据管线状态 */
.agent-pipeline {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 10px;
  font-size: 11px;
  color: var(--gis-text, #e2e8f0);
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 4px;
  font-family: ui-monospace, "Consolas", monospace;
  white-space: nowrap;
}

/* ====== AI 火情识别左侧栏 ====== */
.vision-rail {
  width: 34px;
  flex-shrink: 0;
  display: flex;
  margin-right: 6px;
  z-index: 20;
  transition: width 0.25s ease;
  min-height: 0;
}
.vision-rail.open {
  width: min(310px, 26vw);
}
/* 折叠条 */
.vr-collapse {
  width: 34px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  cursor: pointer;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid rgba(251, 191, 36, 0.35);
  border-radius: 3px;
  color: #fbbf24;
  transition: all 0.2s;
  user-select: none;
}
.vr-collapse:hover {
  background: rgba(251, 191, 36, 0.1);
}
.vr-coll-icon {
  font-size: 15px;
}
.vr-coll-icon.blink {
  animation: vb-blink 1s ease-in-out infinite;
}
@keyframes vb-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.vr-coll-text {
  writing-mode: vertical-rl;
  letter-spacing: 0.3em;
  font-size: 12px;
  font-weight: 600;
}
.vr-coll-arrow {
  font-size: 11px;
  color: #64748b;
}
/* 展开面板 */
.vr-panel {
  flex: 1;
  min-width: 0;
  margin-left: 6px;
  display: flex;
  flex-direction: column;
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 2px;
  overflow: hidden;
}
.vr-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--gis-border, #334155);
  flex-shrink: 0;
}
.vr-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 3px;
  background: rgba(251, 191, 36, 0.15);
  color: #fbbf24;
  letter-spacing: 0.05em;
}
.vr-title {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}
.vr-model-tag {
  margin-left: auto;
  font-size: 10px;
  font-family: ui-monospace, "Consolas", monospace;
  color: #64748b;
}
/* 上传区 */
.vr-upload {
  padding: 8px 10px;
  border-bottom: 1px solid var(--gis-border, #334155);
  flex-shrink: 0;
}
.vr-upload-box :deep(.el-upload-dragger) {
  padding: 10px 6px;
  background: rgba(14, 165, 233, 0.04);
  border-color: rgba(56, 189, 248, 0.25);
}
.vu-mini {
  text-align: center;
}
.vu-icon {
  font-size: 22px;
}
.vu-text {
  margin-top: 4px;
  font-size: 11px;
  color: #cbd5e1;
}
.vu-tip {
  margin-top: 3px;
  font-size: 10px;
  color: #64748b;
}
.vr-error {
  margin-top: 6px;
  font-size: 11px;
  color: #f87171;
  line-height: 1.5;
}
/* 详情区 */
.vr-detail {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 10px;
  border-bottom: 1px solid var(--gis-border, #334155);
}
.vrd-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}
.vrd-file {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vrd-time {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 10px;
  color: #64748b;
  font-family: ui-monospace, "Consolas", monospace;
}
.vrd-img {
  width: 100%;
  max-height: 170px;
  object-fit: contain;
  border-radius: 4px;
  border: 1px solid #334155;
  margin-bottom: 8px;
}
.vrd-actions {
  margin-bottom: 8px;
}
.vrd-analysis {
  font-size: 12px;
  line-height: 1.8;
  color: #cbd5e1;
  word-break: break-word;
}
/* 详情区 Markdown 简版样式 */
.vrd-analysis :deep(h1),
.vrd-analysis :deep(h2),
.vrd-analysis :deep(h3),
.vrd-analysis :deep(h4) {
  margin: 10px 0 6px;
  font-size: 13px;
  font-weight: 700;
  color: #7dd3fc;
}
.vrd-analysis :deep(p) { margin: 6px 0; }
.vrd-analysis :deep(ul), .vrd-analysis :deep(ol) { padding-left: 18px; margin: 6px 0; }
.vrd-analysis :deep(li) { margin: 3px 0; }
.vrd-analysis :deep(strong) { color: #fbbf24; }
.vrd-analysis :deep(blockquote) {
  margin: 8px 0;
  padding: 4px 10px;
  border-left: 3px solid #38bdf8;
  background: rgba(56, 189, 248, 0.06);
  color: #94a3b8;
}
.vrd-analysis :deep(table) { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 11px; }
.vrd-analysis :deep(th), .vrd-analysis :deep(td) {
  border: 1px solid #334155;
  padding: 4px 8px;
  text-align: left;
}
.vrd-analysis :deep(th) { background: rgba(56, 189, 248, 0.08); color: #7dd3fc; }
.vrd-analysis :deep(code) {
  background: #1e293b;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 11px;
  color: #7dd3fc;
}
/* 历史区 */
.vr-history {
  flex-shrink: 0;
  max-height: 32%;
  display: flex;
  flex-direction: column;
  min-height: 90px;
}
.vrh-title {
  padding: 7px 10px 5px;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  border-bottom: 1px solid var(--gis-border, #334155);
}
.vrh-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 6px;
}
.vrh-empty {
  padding: 14px 8px;
  text-align: center;
  font-size: 11px;
  color: #475569;
}
.vrh-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.vrh-item:hover { background: rgba(56, 189, 248, 0.08); }
.vrh-item.active { background: rgba(56, 189, 248, 0.14); }
.vrh-info {
  flex: 1;
  min-width: 0;
}
.vrh-file {
  font-size: 11px;
  color: #e2e8f0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vrh-time {
  font-size: 10px;
  color: #64748b;
  font-family: ui-monospace, "Consolas", monospace;
}
.vrh-del {
  flex-shrink: 0;
  opacity: 0.7;
}

.agent-pipeline .ap-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #64748b;
  flex-shrink: 0;
}

.agent-pipeline.api .ap-dot {
  background: #4ade80;
  box-shadow: 0 0 6px rgba(74, 222, 128, 0.7);
}

.agent-pipeline.local .ap-dot {
  background: #facc15;
  box-shadow: 0 0 6px rgba(250, 204, 21, 0.7);
}

.agent-pipeline.loading .ap-dot {
  background: #38bdf8;
  animation: ap-pulse 1s ease-in-out infinite;
}

@keyframes ap-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.agent-pipeline.api .ap-text {
  color: #4ade80;
}

.agent-pipeline.local .ap-text {
  color: #facc15;
}

.header-weather {
  position: relative;
  z-index: 30;

  .weather-button-mini {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    font-size: 12px;
    color: var(--gis-text);
    cursor: pointer;
    background: var(--gis-bg-panel);
    border: 1px solid var(--gis-border);
    border-radius: 4px;
    font-family: ui-monospace, "Consolas", monospace;
  }

  .weather-button-mini:hover {
    border-color: var(--gis-accent-dim);
  }

  .iconfont {
    font-size: 15px;
    color: var(--gis-accent);
  }

  .weather-popup {
    position: absolute;
    top: 100%;
    right: 0;
    margin-top: 6px;
    min-width: 220px;
    padding: 12px 14px;
    background: var(--gis-bg-panel);
    border: 1px solid var(--gis-border);
    border-radius: 4px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
    z-index: 40;

    .city {
      display: flex;
      justify-content: space-between;
      margin-bottom: 8px;
      font-weight: 600;
      font-size: 14px;
    }

    .info {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: var(--gis-text-muted);

      .iconfont {
        color: var(--gis-accent);
        margin-right: 4px;
      }
    }
  }
}

.header-time {
  display: flex;
  align-items: center;
}

/* 主体三栏 */
.gis-body {
  position: relative;
  z-index: 10;
  display: flex;
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  width: 100%;
  padding: 8px 10px;
  gap: 0;
  overflow: hidden;
}

.gis-rail {
  width: min(300px, 24vw);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 15;
  min-height: 0;
}

.gis-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--gis-bg-panel);
  border: 1px solid var(--gis-border);
  border-radius: 2px;
  box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.06);
}

.gis-panel-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 10px 6px;
  border-bottom: 1px solid var(--gis-border);
  background: linear-gradient(90deg, rgba(8, 145, 178, 0.12), transparent);
}

.gis-panel-kicker {
  font-family: ui-monospace, "Consolas", monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--gis-accent);
}

.gis-panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text);
}

.gis-panel-body {
  flex: 1;
  min-height: 0;
  padding: 4px 6px 8px;
  display: flex;
  flex-direction: column;
}

.gis-panel-body > * {
  flex: 1;
  min-height: 0;
  width: 100%;
}

/* 地图 */
.gis-map-stage {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  z-index: 5;
  padding: 0 6px;
  display: flex;
  flex-direction: column;
}

.gis-map-frame {
  position: relative;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--gis-border-strong);
  border-radius: 2px;
  background: #000;
  box-shadow:
    0 0 0 1px rgba(34, 211, 238, 0.15),
    0 12px 40px rgba(0, 0, 0, 0.55);
}

.gis-map-inner {
  position: absolute;
  inset: 0;
  overflow: hidden;
}

/* 四角装饰 */
.gis-corner {
  position: absolute;
  width: 14px;
  height: 14px;
  border-color: var(--gis-accent);
  border-style: solid;
  pointer-events: none;
  z-index: 2;
}

.gis-corner.tl { top: -1px; left: -1px; border-width: 2px 0 0 2px; }
.gis-corner.tr { top: -1px; right: -1px; border-width: 2px 2px 0 0; }
.gis-corner.bl { bottom: -1px; left: -1px; border-width: 0 0 2px 2px; }
.gis-corner.br { bottom: -1px; right: -1px; border-width: 0 2px 2px 0; }

/* 底栏工具 */
.gis-dock {
  display: flex;
  flex-wrap: nowrap;
  flex-shrink: 0;
  justify-content: center;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  padding: 5px 6px;
  background: var(--gis-bg-panel);
  border: 1px solid var(--gis-border);
  border-radius: 2px;
}

.gis-dock-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 48px;
  flex: 0 1 auto;
  padding: 4px 6px 3px;
  cursor: pointer;
  color: var(--gis-text-muted);
  border-radius: 2px;
  transition: color 0.15s, background 0.15s;
}

.gis-dock-item:hover {
  color: var(--gis-text);
  background: rgba(34, 211, 238, 0.08);
}

.gis-dock-item .iconfont {
  font-size: 18px;
  margin-bottom: 2px;
  color: var(--gis-text);
}

.gis-dock-item .is-on {
  color: var(--gis-accent);
}

.gis-dock-item span {
  font-size: 11px;
  font-weight: 600;
  font-family: ui-monospace, "Consolas", monospace;
  letter-spacing: 0.02em;
}

/* icon-ditu01 线条偏细，补 text-shadow 描边以对齐视觉粗细 */
.gis-dock-item .gis-dock-icon-fit {
  font-size: 19px;
  text-shadow:
    0.45px 0 0 currentColor,
    -0.45px 0 0 currentColor,
    0 0.35px 0 currentColor,
    0 -0.35px 0 currentColor;
}

.gis-dock-menu {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 6px;
  padding: 8px 10px;
  min-width: 120px;
  background: var(--gis-bg-panel-2);
  border: 1px solid var(--gis-border);
  border-radius: 2px;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.5);
  z-index: 50;
}

.gis-dock-menu div {
  padding: 4px 0;
  font-size: 11px;
  color: var(--gis-text);
  white-space: nowrap;
  cursor: pointer;
}

.gis-dock-menu div:hover {
  color: var(--gis-accent);
}

.gis-dock-menu div.on {
  color: var(--gis-accent);
  font-weight: 600;
}

/* 底栏 */
.gis-footer {
  user-select: text;
  position: relative;
  flex-shrink: 0;
  z-index: 25;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 5px 12px;
  font-size: 11px;
  font-family: ui-monospace, "Consolas", monospace;
  color: var(--gis-text-muted);
  background: rgba(2, 6, 23, 0.92);
  border-top: 1px solid var(--gis-border);
}

.gis-footer-coord { color: var(--gis-accent); }
.gis-footer-link { color: var(--gis-text-muted); text-decoration: none; }
.gis-footer-link:hover { color: var(--gis-accent); }

/* 抽屉 */
:deep(.fire-drawer) {
  --el-drawer-bg-color: var(--gis-bg-panel) !important;
  background-color: var(--gis-bg-panel) !important;
  color: var(--gis-text) !important;
  border-left: 1px solid var(--gis-border) !important;

  .el-drawer__header {
    margin-bottom: 0;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--gis-border);
    color: var(--gis-text);
    font-weight: 600;
  }

  .el-table {
    --el-table-bg-color: var(--gis-bg-panel) !important;
    --el-table-tr-bg-color: var(--gis-bg-panel) !important;
    --el-table-header-bg-color: #020617 !important;
    --el-table-row-hover-bg-color: rgba(34, 211, 238, 0.1) !important;
    color: var(--gis-text) !important;
  }

  th.el-table__cell {
    background: #020617 !important;
    color: var(--gis-accent) !important;
    font-family: ui-monospace, "Consolas", monospace;
    font-size: 12px;
    border-bottom: 1px solid var(--gis-border) !important;
  }

  td.el-table__cell {
    background-color: rgba(15, 23, 42, 0.92) !important;
    color: var(--gis-text) !important;
    border-bottom: 1px solid var(--gis-border) !important;
    font-size: 12px;
  }

  .el-table__body tr:hover > td.el-table__cell {
    background-color: rgba(34, 211, 238, 0.08) !important;
    color: var(--gis-text) !important;
  }

  .el-table__inner-wrapper::before {
    height: 0 !important;
  }
}
</style>