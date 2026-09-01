<script setup>
/**
 * 预测火险等级频次柱状图（右下）
 * ★★★ 图表数据与 predictViewMode 同步：逐日用逐日数据，逐月用逐月数据 ★★★
 * 五色柱状图（与地图 riskLevelColors 一致），全屏含分页表格
 */
import { FullScreen, ScaleToOriginal } from '@element-plus/icons-vue'
import { onMounted, ref, nextTick, onUnmounted, computed, watch } from 'vue'
import * as echarts from 'echarts'
import predictMonthJson from '@/assets/predict_2025_2026_month.json'
import predictDailyJson from '@/assets/predict_2025_2026_daily.json'
import { gisChartPalette, riskLevelColors } from '@/utils/echartsGisTheme'
import { fireIndexToLevel, riskScoreToLevel } from '@/utils/riskLevel'

// 接收 searchDate、viewMode 和 predictData
const props = defineProps({
  searchDate: {
    type: String,
    default: ''
  },
  viewMode: {
    type: String,
    default: 'daily'
  },
  predictData: {
    type: Array,
    default: null
  }
})

// 小图 / 全屏图容器
const chartRef = ref(null)
const maxChartRef = ref(null)
let chartInstance = null
let maxChartInstance = null

// 全屏状态
const isMaximized = ref(false)

// ★★★ 根据 viewMode 切换数据源：逐日用逐日数据，逐月用逐月数据 ★★★
// 优先使用父组件传入的 predictData（API 数据），否则用本地 JSON
const tableData = computed(() => {
  const isDaily = props.viewMode === 'daily'

  // 如果父组件传入了 predictData，直接使用（已过滤好）
  if (props.predictData && props.predictData.length > 0) {
    return props.predictData.map(item => {
      const level = isDaily
        ? fireIndexToLevel(item.final_fire_index || item.Final_Fire_Index)
        : riskScoreToLevel(item.risk_score || item.Risk_Score)
      const displayDate = isDaily
        ? `${item.year || item.Year}-${String(Number(item.month || item.Month)).padStart(2, '0')}-${String(Number(item.day || item.Day)).padStart(2, '0')}`
        : `${item.year || item.Year}-${String(Number(item.month || item.Month)).padStart(2, '0')}`
      return {
        ...item,
        riskLevel: level,
        displayDate,
        _fireIndex: isDaily ? (item.final_fire_index || item.Final_Fire_Index) : (item.risk_score || item.Risk_Score),
        _predFireRisk: isDaily ? (item.pred_fire_count || item.Pred_Fire_Count) : (item.pred_fire_risk || item.Pred_Fire_Risk)
      }
    })
  }

  if (isDaily) {
    if (!props.searchDate) {
      return predictDailyJson.map(item => {
        const level = fireIndexToLevel(item.Final_Fire_Index)
        const y = String(item.Year)
        const m = String(Number(item.Month)).padStart(2, '0')
        const d = String(Number(item.Day)).padStart(2, '0')
        return {
          ...item,
          riskLevel: level,
          displayDate: `${y}-${m}-${d}`,
          _fireIndex: item.Final_Fire_Index,
          _predFireRisk: item.Pred_Fire_Count
        }
      })
    }
    const parts = props.searchDate.split('-').map(Number)
    const year = parts[0], month = parts[1], day = parts[2]
    return predictDailyJson
      .filter(item => Number(item.Year) === year && Number(item.Month) === month && Number(item.Day) === day)
      .map(item => {
        const level = fireIndexToLevel(item.Final_Fire_Index)
        const y = String(item.Year)
        const m = String(Number(item.Month)).padStart(2, '0')
        const d = String(Number(item.Day)).padStart(2, '0')
        return {
          ...item,
          riskLevel: level,
          displayDate: `${y}-${m}-${d}`,
          _fireIndex: item.Final_Fire_Index,
          _predFireRisk: item.Pred_Fire_Count
        }
      })
  } else {
    if (!props.searchDate) {
      return predictMonthJson.map(item => ({
        ...item,
        riskLevel: riskScoreToLevel(item.Risk_Score),
        displayDate: `${item.Year}-${String(item.Month).padStart(2, '0')}`,
        _fireIndex: item.Risk_Score,
        _predFireRisk: item.Pred_Fire_Risk
      }))
    }
    const parts = props.searchDate.split('-').map(Number)
    const year = parts[0], month = parts[1]
    return predictMonthJson
      .filter(item => Number(item.Year) === year && Number(item.Month) === month)
      .map(item => ({
        ...item,
        riskLevel: riskScoreToLevel(item.Risk_Score),
        displayDate: `${item.Year}-${String(item.Month).padStart(2, '0')}`,
        _fireIndex: item.Risk_Score,
        _predFireRisk: item.Pred_Fire_Risk
      }))
  }
})

// 按记录条数统计（非 Pred_Fire_Risk 求和），保证柱高与直觉一致
const levelDistribution = computed(() => {
  const counts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }
  tableData.value.forEach(item => counts[item.riskLevel]++)
  return {
    xData: ['1级', '2级', '3级', '4级', '5级'],
    yData: [counts[1], counts[2], counts[3], counts[4], counts[5]]
  }
})

// 分页
const currentPage = ref(1)
const pageSize = ref(20)
const isLoading = ref(false)

const paginatedData = computed(() => {
  return tableData.value.slice(
    (currentPage.value - 1) * pageSize.value,
    currentPage.value * pageSize.value
  )
})

const handleCurrentChange = (val) => {
  isLoading.value = true
  currentPage.value = val
  setTimeout(() => { isLoading.value = false }, 300)
}

const handleSizeChange = (val) => {
  pageSize.value = val
  currentPage.value = 1
}

// 柱状图配置（拷贝 data，避免 ECharts 就地改写导致与全屏实例不同步）
const getOption = () => ({
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'axis',
    backgroundColor: gisChartPalette.bgTooltip,
    borderColor: gisChartPalette.axis,
    borderWidth: 1,
    textStyle: { color: gisChartPalette.textStrong, fontSize: 12 },
    axisPointer: { type: 'shadow' }
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '10%',
    top: '15%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    data: [...levelDistribution.value.xData],
    axisLabel: { color: gisChartPalette.text, fontSize: 11 },
    axisLine: { lineStyle: { color: gisChartPalette.axis } }
  },
  yAxis: {
    type: 'value',
    name: '记录条数',
    nameTextStyle: { color: gisChartPalette.text },
    axisLabel: { color: gisChartPalette.text },
    splitLine: { lineStyle: { type: 'dashed', color: gisChartPalette.split } }
  },
  series: [{
    name: '该等级记录数',
    type: 'bar',
    data: [...levelDistribution.value.yData],
    itemStyle: {
      color: (params) => riskLevelColors[params.dataIndex],
      borderRadius: [0, 0, 0, 0]
    },
    label: {
      show: true,
      position: 'top',
      color: gisChartPalette.textStrong
    }
  }]
})

const scheduleMaxChartLayout = () => {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (!maxChartInstance || !maxChartRef.value) return
      maxChartInstance.resize()
      maxChartInstance.setOption(getOption(), { notMerge: true })
    })
  })
}

const initChart = () => {
  if (chartRef.value) {
    if (chartInstance) chartInstance.dispose()
    chartInstance = echarts.init(chartRef.value)
    chartInstance.setOption(getOption(), { notMerge: true })
  }
}

const initMaxChart = () => {
  if (maxChartRef.value) {
    if (maxChartInstance) maxChartInstance.dispose()
    maxChartInstance = echarts.init(maxChartRef.value)
    maxChartInstance.setOption(getOption(), { notMerge: true })
    scheduleMaxChartLayout()
  }
}

const applyChartDataToInstances = () => {
  chartInstance?.setOption(getOption(), { notMerge: true })
  if (isMaximized.value && maxChartInstance) {
    maxChartInstance.setOption(getOption(), { notMerge: true })
    scheduleMaxChartLayout()
  }
}

const toggleMaximize = async () => {
  isMaximized.value = !isMaximized.value
  await nextTick()
  if (isMaximized.value) {
    initMaxChart()
  } else {
    chartInstance && chartInstance.resize()
  }
}

const handleResize = () => {
  chartInstance && chartInstance.resize()
  maxChartInstance && maxChartInstance.resize()
}

watch(
  () => [props.searchDate, props.viewMode],
  () => {
    nextTick(() => applyChartDataToInstances())
  }
)

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) chartInstance.dispose()
  if (maxChartInstance) maxChartInstance.dispose()
})
</script>

<template>
  <div class="chart-wrapper">
    <!-- 正常模式 -->
    <div class="normal-view">
      <div class="expand-btn" @click="toggleMaximize">
        <el-icon size="20">
          <FullScreen />
        </el-icon>
      </div>
      <div class="chart-area" ref="chartRef"></div>
    </div>

    <!-- 全屏模式 -->
    <Teleport to="body">
      <div v-if="isMaximized" class="maximized-view">
        <div class="header-bar">
          <span class="max-title">预测火险等级频次分布详情</span>
          <el-button type="primary" circle @click="toggleMaximize">
            <el-icon size="20">
              <ScaleToOriginal />
            </el-icon>
          </el-button>
        </div>

        <div class="content-container">
          <!-- 左侧大图 -->
          <div class="chart-area-max" ref="maxChartRef"></div>

          <!-- 右侧表格 -->
          <div class="table-area">
            <div class="table-content-wrapper">
              <el-table
                v-if="isMaximized"
                v-loading="isLoading"
                :data="paginatedData"
                stripe
                border
                style="width: 100%; height: 100%; position: absolute; top: 0; left: 0;"
                :header-cell-style="{ background: '#f8fafc', color: '#606266', fontWeight: 'bold' }"
              >
                <el-table-column prop="City" label="城市" min-width="120" />
                <el-table-column prop="displayDate" :label="viewMode === 'daily' ? '日期' : '月份'" min-width="100" sortable />
                <el-table-column :prop="viewMode === 'daily' ? '_fireIndex' : '_fireIndex'" :label="viewMode === 'daily' ? '火险指数' : '火险评分'" min-width="100">
                  <template #default="scope">
                    {{ viewMode === 'daily'
                      ? (scope.row._fireIndex != null ? Number(scope.row._fireIndex).toFixed(1) : '0.0')
                      : (scope.row._fireIndex != null ? Number(scope.row._fireIndex).toFixed(4) : '0.0000')
                    }}
                  </template>
                </el-table-column>
                <el-table-column prop="_predFireRisk" :label="viewMode === 'daily' ? '预测火点数' : '预测火点数'" min-width="100">
                  <template #default="scope">
                    {{ scope.row._predFireRisk != null ? Math.round(Number(scope.row._predFireRisk)) : 0 }}
                  </template>
                </el-table-column>
                <el-table-column prop="riskLevel" label="火险等级" min-width="100">
                  <template #default="scope">
                    <el-tag
                      :type="scope.row.riskLevel >= 4 ? 'danger' : (scope.row.riskLevel >= 3 ? 'warning' : 'primary')"
                    >
                      {{ scope.row.riskLevel }}级
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="pagination-container">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[20, 50, 100, 200, 500]"
                :total="tableData.length"
                popper-style="z-index: 99999"
                layout="total, sizes, prev, pager, next, jumper"
                background
                @size-change="handleSizeChange"
                @current-change="handleCurrentChange"
              />
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style lang="scss" scoped>
.chart-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
}

.normal-view {
  width: 100%;
  height: 100%;
  position: relative;

  .expand-btn {
    position: absolute;
    top: 0;
    right: 0;
    cursor: pointer;
    color: #94a3b8;
    z-index: 10;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 4px;
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;

    &:hover {
      background: #1e293b;
    }
  }

  .chart-area {
    width: 100%;
    height: 100%;
  }
}

.maximized-view {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 2000;
  background: #020617;
  padding: 20px;
  display: flex;
  flex-direction: column;

  .header-bar {
    padding-right: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    flex-shrink: 0;

    .max-title {
      font-size: 22px;
      color: #f8fafc;
      font-weight: 600;
      letter-spacing: 0.04em;
    }
  }

  .content-container {
    flex: 1;
    display: flex;
    overflow: hidden;
    gap: 20px;

    .chart-area-max {
      width: 40%;
      height: 100%;
      background: #0f172a;
      border-radius: 2px;
      border: 1px solid #334155;
    }

    .table-area {
      flex: 1;
      height: 100%;
      background: #fff;
      border-radius: 6px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);

      .table-content-wrapper {
        flex: 1;
        width: 100%;
        position: relative;
        overflow: hidden;
      }

      :deep(.el-table) {
        border-radius: 6px;
        overflow: hidden;
        border: 1px solid #ebeef5;
        --el-table-border-color: #ebeef5;
        background-color: #fff;
      }

      :deep(.el-table .el-table__header-wrapper th) {
        background: #f5f5f5;
        font-weight: 500;
        border-bottom: 1px solid #ebeef5;
        color: #333;
      }

      :deep(.el-table--striped .el-table__body tr.el-table__row--striped td) {
        background: #fafafa !important;
      }

      :deep(.el-table .el-table__body tr:hover > td) {
        background: #f0f0f0 !important;
      }

      :deep(.el-table .cell) {
        padding: 12px 16px;
        font-size: 13px;
        color: #333;
      }

      .pagination-container {
        height: 70px;
        flex-shrink: 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-top: 5px;
        padding-bottom: 25px;
        padding-right: 20px;
      }
    }
  }
}
</style>
