<script setup>
/**
 * 历史火险等级饼图（左上）
 * 数据：parseGeoData() → confidenceCounts { high / low }
 * 全屏：点击右上角按钮，Teleport 弹窗，图表+表格左右分栏
 */
import { FullScreen, ScaleToOriginal } from '@element-plus/icons-vue'
import { onMounted, ref, nextTick, onUnmounted, computed, watch } from 'vue'
import * as echarts from 'echarts'
import { parseGeoData } from '@/utils/parseGeoData'
import { chartTokens } from '@/utils/themeTokens'
import { useThemeStore } from '@/stores/theme'

// 接收 fireData prop（由父组件传入 API 数据或本地数据）
const props = defineProps({
  fireData: {
    type: Object,
    default: null
  }
})

// 主题 Token：传入 mode 仅为建立响应式依赖，主题切换时重新读取 CSS 变量
const theme = useThemeStore()
const tokens = computed(() => chartTokens(theme.mode))

// 当 fireData 变化时重新解析
const rawGeo = ref(props.fireData ? parseGeoData(props.fireData) : parseGeoData())
watch(() => props.fireData, (val) => {
  rawGeo.value = val ? parseGeoData(val) : parseGeoData()
})

const geoData = computed(() => rawGeo.value)

// 小图容器
const chartRef = ref(null)
// 全屏图容器
const maxChartRef = ref(null)
let chartInstance = null
let maxChartInstance = null

// 表格数据（用 computed 确保响应式更新）
const tableData = computed(() => geoData.value.rawFeatures || [])

// 全屏状态
const isMaximized = ref(false)

// 分页
const currentPage = ref(1)
const pageSize = ref(20)
const isLoading = ref(false)

// 计算当前页数据
const paginatedData = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return tableData.value.slice(start, start + pageSize.value)
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

// ECharts 配置：环形饼图，高/低置信度两段（computed：数据/主题变化时自动更新）
const option = computed(() => {
  const t = tokens.value
  const counts = geoData.value.confidenceCounts || { high: 0, low: 0 }
  return {
  backgroundColor: 'transparent',
  tooltip: {
    trigger: 'item',
    backgroundColor: t.panel,
    borderColor: t.border,
    borderWidth: 1,
    textStyle: { color: t.text, fontSize: 12 },
    formatter: '{b}: {c} ({d}%)'
  },
  legend: {
    bottom: '5%',
    left: 'center',
    textStyle: { color: t.muted, fontSize: 11 }
  },
  series: [{
    name: '火险置信度分布',
    type: 'pie',
    radius: ['40%', '70%'],
    avoidLabelOverlap: false,
    itemStyle: {
      borderRadius: 0,
      borderColor: t.border,
      borderWidth: 1
    },
    label: {
      show: false,
      position: 'center'
    },
    emphasis: {
      label: {
        show: true,
        fontSize: 14,
        fontWeight: 600,
        color: t.text
      }
    },
    labelLine: {
      show: false
    },
    data: [
      { value: counts.high ?? 0, name: '高置信度', itemStyle: { color: '#dc2626' } },
      { value: counts.low ?? 0, name: '低置信度', itemStyle: { color: '#eab308' } }
    ]
  }]
  }
})

// 初始化小图
const initChart = () => {
  if (chartRef.value) {
    if (chartInstance) chartInstance.dispose()
    chartInstance = echarts.init(chartRef.value)
    chartInstance.setOption(option.value)
  }
}

// 初始化全屏图（显示外部标签）
const initMaxChart = () => {
  if (maxChartRef.value) {
    const t = tokens.value
    if (maxChartInstance) maxChartInstance.dispose()
    maxChartInstance = echarts.init(maxChartRef.value)
    const maxOption = JSON.parse(JSON.stringify(option.value))
    if (maxOption.series && maxOption.series[0]) {
      maxOption.series[0].label = {
        show: true,
        position: 'outside',
        color: t.text,
        formatter: '{b}: {c} ({d}%)',
        fontSize: 13
      }
      maxOption.series[0].labelLine = {
        show: true,
        lineStyle: { color: t.border }
      }
    }
    maxOption.legend = {
      bottom: '5%',
      left: 'center',
      textStyle: { color: t.muted, fontSize: 13 }
    }
    maxChartInstance.setOption(maxOption)
  }
}

// 切换全屏
const toggleMaximize = async () => {
  isMaximized.value = !isMaximized.value
  await nextTick()
  if (isMaximized.value) {
    initMaxChart()
  } else {
    chartInstance && chartInstance.resize()
  }
}

// 响应窗口大小变化
const handleResize = () => {
  chartInstance && chartInstance.resize()
  maxChartInstance && maxChartInstance.resize()
}

onMounted(() => {
  initChart()
  window.addEventListener('resize', handleResize)
})

// fireData 变化时刷新图表
watch(() => props.fireData, () => {
  nextTick(() => {
    initChart()
    if (isMaximized.value) {
      nextTick(() => initMaxChart())
    }
  })
})

// 主题切换时重建图表
watch(() => theme.mode, () => {
  nextTick(() => {
    initChart()
    if (isMaximized.value) {
      nextTick(() => initMaxChart())
    }
  })
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
          <span class="max-title">火险置信度分布详情</span>
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
                :header-cell-style="{ background: 'var(--gis-table-header)', color: 'var(--gis-text-muted)', fontWeight: 'bold' }"
              >
                <el-table-column prop="acq_date" label="日期" min-width="120" sortable />
                <el-table-column prop="conf" label="置信度" min-width="100">
                  <template #default="scope">
                    <el-tag
                      :type="scope.row.conf === 'high' ? 'danger' : 'success'"
                      effect="light"
                    >
                      {{ scope.row.conf === 'high' ? 'High' : 'Low' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="latitude" label="纬度" min-width="100" />
                <el-table-column prop="longitude" label="经度" min-width="100" />
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
    color: var(--gis-text-muted, #94a3b8);
    z-index: 10;
    background: var(--gis-glass-solid);
    border: 1px solid var(--gis-border);
    border-radius: var(--gis-radius-xs, 4px);
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;

    &:hover {
      background: var(--gis-accent-soft);
      box-shadow: var(--gis-glow);
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
  background: var(--gis-atmo-bg);
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
      color: var(--gis-text, #f8fafc);
      font-weight: 600;
      letter-spacing: 0.04em;
      text-shadow: var(--gis-text-glow);
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
      background: var(--gis-bg-panel);
      border-radius: 2px;
      border: 1px solid var(--gis-border);
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
