<script setup>
/**
 * OpenLayers 地图核心组件
 * 职责：底图渲染（火点聚合 / 州市边界 / 搜索高亮 / 鼠标坐标）
 * 接收 props → fireData / predictData / currentDataType / cityRiskData
 * 暴露方法 → flyToExtent / highlightCity（供 App.vue 调用）
 */
import { ref, onMounted, computed, markRaw, watch } from 'vue'
import 'ol/ol.css'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import VectorLayer from 'ol/layer/Vector'
import XYZ from 'ol/source/XYZ'
import VectorSource from 'ol/source/Vector'
import Cluster from 'ol/source/Cluster'
import GeoJSON from 'ol/format/GeoJSON'
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from 'ol/style'
import { defaults as defaultInteractions, Select } from 'ol/interaction'
import { click } from 'ol/events/condition'
import yunnanBorder from '@/assets/Yunnan_border.json'
import { frpToRiskLevel, CONF_FALLBACK_LEVEL, getRiskColor, RISK_COLORS, RISK_FILL_ALPHA, RISK_COLORS_FILL } from '@/utils/riskLevel'

// ====== Props（接收父组件数据） ======
const props = defineProps({
  fireData: {
    type: Object,
    default: () => ({ type: 'FeatureCollection', features: [] })
  },
  predictData: {
    type: Object,
    default: () => ({ type: 'FeatureCollection', features: [] })
  },
  currentDataType: {
    type: String,
    default: 'history'
  },
  cityRiskData: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['map-loaded', 'cluster-click'])

// ====== 单火点样式（等级颜色从 riskLevel.js 统一读取） ======
const getStyle = (feature) => {
  let level = feature.get('risk_level')
  if (!level && props.currentDataType === 'history') {
    const frp = feature.get('frp')
    if (frp != null && frp !== '') {
      level = frpToRiskLevel(frp)
    } else {
      const conf = feature.get('conf')
      if (conf) level = CONF_FALLBACK_LEVEL[conf] || 1
    }
  }
  const color = level ? getRiskColor(level) : '#999999'

  return new Style({
    image: new CircleStyle({
      radius: 6,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: '#fff', width: 1 })
    })
  })
}

// ====== 聚合样式 ======
const getClusterStyle = (feature) => {
  const features = feature.get('features')
  const size = features.length
  let displayCount = 0, maxRiskLevel = 1

  features.forEach(f => {
    if (props.currentDataType === 'predict') {
      displayCount += f.get('fire_count') || 0
      maxRiskLevel = Math.max(maxRiskLevel, f.get('risk_level') || 1)
    } else {
      displayCount += 1
      const frp = f.get('frp')
      if (frp != null && frp !== '') {
        maxRiskLevel = Math.max(maxRiskLevel, frpToRiskLevel(frp))
      } else {
        const conf = f.get('conf')
        if (conf) maxRiskLevel = Math.max(maxRiskLevel, CONF_FALLBACK_LEVEL[conf] || 1)
      }
    }
  })

  const isCluster = (props.currentDataType === 'predict' && displayCount > 0) ||
    (props.currentDataType === 'history' && size > 1)
  if (!isCluster) return getStyle(features[0])

  const color = getRiskColor(maxRiskLevel)

  const radius = Math.min(12 + displayCount / 20, 22)

  return new Style({
    image: new CircleStyle({
      radius,
      fill: new Fill({ color }),
      stroke: new Stroke({ color: '#fff', width: 2 })
    }),
    text: new Text({
      text: displayCount.toString(),
      fill: new Fill({ color: '#fff' }),
      font: 'bold 12px Arial',
      stroke: new Stroke({ color: '#333', width: 2 })
    })
  })
}

// ====== 州市边界样式（预测模式下按风险等级5色渐变填充底色） ======
const getBoundaryStyle = (feature) => {
  const cityName = feature.get('name')
  const riskLevel = props.cityRiskData ? props.cityRiskData[cityName] : null

  const baseStyle = new Style({
    stroke: new Stroke({ color: 'rgba(34,211,238,0.85)', width: 1.5 })
  })

  if (riskLevel) {
    const l = Math.max(1, Math.min(5, Math.round(riskLevel)))
    baseStyle.setFill(new Fill({ color: RISK_COLORS_FILL[l - 1] }))
  }

  return baseStyle
}

// ====== 鼠标坐标 ======
let coordinate = ref([])
const formatCoordinate = computed(() => {
  if (coordinate.value.length === 2) {
    const [lon, lat] = coordinate.value
    return `lon:${lon.toFixed(3)},lat:${lat.toFixed(3)}`
  }
  return ''
})

// ====== 图层声明 ======
// 天地图底图（矢量/影像/注记三层叠加）— token 从 .env 读取
const tiandituKey = import.meta.env.VITE_TIANDITU_KEY || '24997a7210dbb9dc59c64076193a2e10'
const tiandituUrl = (t) => `http://t0.tianditu.com/DataServer?T=${t}_w&x={x}&y={y}&l={z}&tk=${tiandituKey}`

const tiandituVecLayer = new TileLayer({
  title: '天地图矢量图层',
  source: new XYZ({
    url: tiandituUrl('vec'),
    wrapX: false,
    crossOrigin: 'anonymous'
  })
})

const tiandituImgLayer = new TileLayer({
  title: '天地图影像图层',
  source: new XYZ({
    url: tiandituUrl('img'),
    wrapX: false,
    crossOrigin: 'anonymous'
  })
})

const tiandutiCvaLayer = new TileLayer({
  title: '天地图注记图层',
  source: new XYZ({
    url: tiandituUrl('cva'),
    wrapX: false,
    crossOrigin: 'anonymous'
  })
})

// 历史火点图层
const vectorSource = new VectorSource({
  features: new GeoJSON().readFeatures(props.fireData)
})
const clusterSource = new Cluster({
  wrapX: false,
  distance: 40,
  source: vectorSource
})
const disasterPointLayer = new VectorLayer({
  title: '火点分布',
  source: clusterSource,
  style: getClusterStyle,
  zIndex: 10
})

// 预测火险图层
const predictVectorSource = new VectorSource()
const predictClusterSource = new Cluster({
  wrapX: false,
  distance: 40,
  source: predictVectorSource
})
const predictLayer = new VectorLayer({
  title: '预测火险图层',
  source: predictClusterSource,
  style: getClusterStyle,
  visible: false,
  zIndex: 11
})

// 州市边界图层
const yunnanBoundaryLayer = new VectorLayer({
  title: '云南省边界',
  source: new VectorSource({
    features: new GeoJSON().readFeatures(yunnanBorder)
  }),
  style: getBoundaryStyle
})

// 搜索高亮图层
const highlightSource = new VectorSource()
const highlightLayer = new VectorLayer({
  title: '搜索高亮',
  source: highlightSource,
  style: new Style({
    stroke: new Stroke({ color: '#22d3ee', width: 3 }),
    fill: new Fill({ color: 'rgba(34,211,238,0.12)' })
  }),
  zIndex: 100
})

let map = null

// ====== 监听数据变化 ======
watch(() => props.fireData, (newData) => {
  if (vectorSource) {
    vectorSource.clear()
    if (newData?.features?.length > 0) {
      vectorSource.addFeatures(new GeoJSON().readFeatures(newData))
    }
  }
}, { deep: true })

watch(() => props.predictData, (newData) => {
  if (predictVectorSource) {
    predictVectorSource.clear()
    if (newData?.features?.length > 0) {
      predictVectorSource.addFeatures(new GeoJSON().readFeatures(newData))
    }
  }
}, { deep: true })

watch(() => props.cityRiskData, () => {
  yunnanBoundaryLayer?.changed()
}, { deep: true })

watch(() => props.currentDataType, (newType) => {
  disasterPointLayer.setVisible(newType === 'history')
  predictLayer.setVisible(newType === 'predict')
}, { immediate: true })

// ====== 暴露方法 ======
const highlightCity = (cityFeature) => {
  highlightSource.clear()
  if (cityFeature) highlightSource.addFeature(new GeoJSON().readFeature(cityFeature))
}
const flyToExtent = (extent) => {
  if (!map || !extent) return
  map.getView().fit(extent, { padding: [50, 50, 50, 50], duration: 1000, maxZoom: 10 })
}
defineExpose({ flyToExtent, highlightCity })

// ====== 挂载 ======
onMounted(() => {
  map = new Map({
    target: 'map',
    layers: [
      tiandituVecLayer,
      tiandituImgLayer,
      tiandutiCvaLayer,
      disasterPointLayer,
      predictLayer,
      yunnanBoundaryLayer,
      highlightLayer
    ],
    view: new View({
      center: [102.42, 25.02],
      zoom: 6,
      projection: 'EPSG:4326'
    }),
    interactions: defaultInteractions({ doubleClickZoom: false })
  })

  // 鼠标移动 → 更新坐标
  map.on('pointermove', (e) => {
    coordinate.value = e.coordinate
  })

  // 点击聚合点 → 提取属性发送给父组件（打开抽屉）
  const selectClick = new Select({
    condition: click,
    layers: [disasterPointLayer, predictLayer],
    style: null
  })
  map.addInteraction(selectClick)

  selectClick.on('select', (e) => {
    if (e.selected.length > 0) {
      const features = e.selected[0].get('features')
      if (features?.length > 0) {
        const cleanProps = features.map(f => {
          const props = {}
          const propsObj = f.getProperties()
          for (const key in propsObj) {
            if (key !== 'geometry' && typeof propsObj[key] !== 'object') {
              props[key] = propsObj[key]
            } else if (key !== 'geometry' && propsObj[key] !== null) {
              props[key] = JSON.parse(JSON.stringify(propsObj[key]))
            }
          }
          const geom = f.getGeometry().getCoordinates()
          props.longitude = geom[0].toFixed(3)
          props.latitude = geom[1].toFixed(3)
          return props
        })
        emit('cluster-click', cleanProps)
      }
      selectClick.getFeatures().clear()
    }
  })

  emit('map-loaded', markRaw(map))
})
</script>

<template>
  <div class="map-module-container">
    <div id="map"></div>
    <div id="mousePosition" class="gis-mousepos" :class="{ 'gis-mousepos-idle': coordinate.length === 0 }">
      <span v-if="coordinate.length > 0">
        <span class="gis-mousepos-tag">WGS84</span>
        <span class="gis-mousepos-val">{{ formatCoordinate }}</span>
      </span>
      <span v-else class="gis-mousepos-hint">移动鼠标读取坐标</span>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.map-module-container {
  width: 100%;
  height: 100%;
  position: relative;

  #map {
    width: 100%;
    height: 100%;
  }
}

#mousePosition {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: min(320px, 92vw);
  padding: 6px 10px;
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  color: var(--gis-text, #f8fafc);
  background: rgba(15, 23, 42, 0.92);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 2px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35);
}

.gis-mousepos-tag {
  flex-shrink: 0;
  padding: 2px 6px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #020617;
  background: var(--gis-accent, #22d3ee);
  border-radius: 2px;
}

.gis-mousepos-val {
  letter-spacing: 0.04em;
  color: var(--gis-accent, #22d3ee);
}

.gis-mousepos-idle .gis-mousepos-hint {
  color: var(--gis-text-muted, #94a3b8);
}
</style>
