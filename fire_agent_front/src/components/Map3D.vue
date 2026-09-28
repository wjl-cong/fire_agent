<script setup>
/**
 * Map3D — sc-datav 风格 3D 省级地图（Three.js，参照 sc-datav-main/Demo2 实现）
 *
 * 视觉要素：
 * - 州市面片挤出（ExtrudeGeometry）：顶面 MeshStandardMaterial 按火险等级着色，叠云南地形法线贴图
 *   （AWS Terrain Tiles 高程离线生成，与全局 UV 逐像素对齐，呈现地形浮雕），
 *   侧面自定义扫光 shader（自底向顶渐变 + 周期性光带上扫）
 * - 省会（昆明）→ 各州市 贝塞尔飞线（TubeGeometry + 流光贴图滚动）
 * - 上升光柱粒子（AdditiveBlending 辉光圆柱）
 * - 底部旋转光环（quan1 贴图，AdditiveBlending）
 * - 州市名称标签（CSS2DRenderer）
 * - 火点总数柱状图（按州市聚合：柱高=火点数，青→琥珀→红渐变，柱顶数值标签，16 州市全覆盖）
 * - 悬停州市抬升（scale.z lerp 1.5）+ 点击州市向上冒泡 city-click
 * - 明暗主题联动（stores/theme）：背景/雾/扫光/描边/飞线/氛围元素双套配色
 *
 * 投影：Web Mercator（手写，避免引入 d3-geo）→ 归一化至最长边 TARGET 单位，中心在原点。
 */
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { RISK_COLORS } from '@/utils/riskLevel'
import { useThemeStore } from '@/stores/theme'

// sc-datav 原版贴图资产复用（飞线流光 / 底部光环）
import flyLineUrl from '../../sc-datav-main/src/assets/fly_line.png'
import ringUrl from '../../sc-datav-main/src/assets/quan1.png'
// 云南省地形法线贴图：由 AWS Terrain Tiles 公开高程瓦片（terrarium 编码，zoom 8）按本组件
// Mercator 投影公式反演 UV 对齐后中心差分生成，图片顶行 = v=1 = 北，与 applyBboxUV 全局包络严格对齐
import terrainNormalUrl from '@/assets/yunnan_terrain_normal.png'

const props = defineProps({
  /** 16 州市行政边界 GeoJSON（与 2D 地图共用 Yunnan_border.json） */
  cityPolygons: { type: Object, required: true },
  /** { 州市名: 1-5 } 火险等级映射（预测模式选日期后才有值，null 时用中性底色） */
  cityRiskData: { type: Object, default: null },
  /** 火点 FeatureCollection（历史/预测当前筛选结果） */
  firePoints: { type: Object, default: null },
})
const emit = defineEmits(['city-click'])

const themeStore = useThemeStore()
const hostRef = ref(null)

// ====== 常量 ======
const TARGET = 16          // 地图归一化后最长边（世界单位）
const DEPTH = 1.1          // 挤出厚度

// 双主题配色（随系统明暗切换：深色=深空科技风，浅色=清爽大屏风）
const THEME_COLORS = {
  dark: {
    bg: 0x04101f,          // 场景底色
    // 无火险数据顶面底色：顶面是场景唯一受光材质，灯光按物理亮度调低后颜色即最终显示色，
    // 深空背景上必须亮色才清晰（原深蓝 0x1c3346 在旧饱和光照下从未真实显示过，实显一直是亮白）
    neutral: 0xd8e6f2,
    sweepTop: '#27506b', sweepBottom: '#0d1b2c', scan: '#4cc9f0',
    edge: 0xd9f2ff, edgeOpacity: 0.9,   // 州市轮廓描边（省界增强）
    underlay: 0x13273e,    // 底座垫层（覆盖州市边界裂缝）
    fly: 0x8fc2ff, ring: 0x3fa9f5, beam: '#7dd3fc',
  },
  light: {
    bg: 0xe3ecf6,
    neutral: 0xffffff,
    sweepTop: '#ffffff', sweepBottom: '#f2f7fc', scan: '#2563eb',
    edge: 0x1e5a8a, edgeOpacity: 0.85,
    underlay: 0xffffff,
    fly: 0x1d4ed8, ring: 0x2563eb, beam: '#3b82f6',
  },
}
let themeMode = 'dark'     // 当前主题（init/watch 同步）
function themeC() { return THEME_COLORS[themeMode] || THEME_COLORS.dark }

// ====== Three 核心对象 ======
let renderer, labelRenderer, scene, camera, controls, rafId = 0
let mapGroup               // 旋转 -90° 的地图根组
let regionMeshes = []      // 州市挤出网格（含 userData.name / center / lngLat）
let clusterGroup = null    // 火点聚类柱组（随缩放重建，镜像 2D Cluster 行为）
let underlayMats = []      // 底座垫层材质（主题切换统一调色）
let rebuildTimer = null    // 聚类重建防抖
let introClusterDone = false // 入场动画结束后的首建标记
let edgesMats = []         // 州市轮廓描边材质（主题切换统一调色）
let flyMats = []           // 飞线材质（主题切换统一调色）
let flyTex, ringTex, normalTex
let bottomRing             // 底部旋转光环
let beams                  // 上升光柱组
let sweepMat               // 共享侧面扫光材质
let projFn = null          // 经纬度 → 世界坐标 (x, y)
let geoBBox = null         // 全省几何投影包络 { minX, maxX, minY, maxY }（法线贴图 UV 基准）
let clock = new THREE.Clock()
let resizeObserver = null
let introProgress = 0      // 入场动画进度 0→1
const CAM_START = new THREE.Vector3(0, 26, 1.2)
const CAM_END = new THREE.Vector3(0, 12.5, 13.5)
let hovered = null
let raycaster = new THREE.Raycaster()
let pointerNdc = new THREE.Vector2()
let downXY = null

// ====== Mercator 投影 + 归一化 ======
function buildProjection(geojson) {
  let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity
  const scan = (coords) => {
    if (typeof coords[0] === 'number') {
      if (coords[0] < minLng) minLng = coords[0]
      if (coords[0] > maxLng) maxLng = coords[0]
      if (coords[1] < minLat) minLat = coords[1]
      if (coords[1] > maxLat) maxLat = coords[1]
      return
    }
    coords.forEach(scan)
  }
  geojson.features.forEach(f => scan(f.geometry.coordinates))

  const R = 6378137
  const c0 = (minLng + maxLng) / 2
  const c1 = (minLat + maxLat) / 2
  const raw = ([lng, lat]) => [
    R * (lng - c0) * Math.PI / 180,
    R * Math.log(Math.tan(Math.PI / 4 + (lat - c1) * Math.PI / 360)),
  ]
  // 用原始墨卡托包络计算缩放比
  const corners = [
    raw([minLng, minLat]), raw([maxLng, minLat]),
    raw([minLng, maxLat]), raw([maxLng, maxLat]),
  ]
  const xs = corners.map(p => p[0]), ys = corners.map(p => p[1])
  const s = TARGET / Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))
  // 全省几何包络（投影后世界坐标）：顶面法线贴图全局 UV 的基准
  geoBBox = {
    minX: Math.min(...xs) * s, maxX: Math.max(...xs) * s,
    minY: Math.min(...ys) * s, maxY: Math.max(...ys) * s,
  }
  // y 不取负：北 = 局部 +Y；配合地图组 rotation.x = -PI/2（局部 +Y → 世界 -Z，远离相机），
  // 北指向屏幕上方、东指向屏幕右侧，与 2D 地图朝向一致
  return ([lng, lat]) => {
    const [x, y] = raw([lng, lat])
    return [x * s, y * s]
  }
}

// ====== 侧面扫光 shader（移植 sc-datav ShiftMaterial） ======
function makeSweepMaterial() {
  return new THREE.ShaderMaterial({
    transparent: true,
    uniforms: {
      time: { value: 0 },
      depth: { value: DEPTH },
      baseTopColor: { value: new THREE.Color('#27506b') },
      baseBottomColor: { value: new THREE.Color('#0d1b2c') },
      scanColor: { value: new THREE.Color('#4cc9f0') },
      opacity: { value: 1.0 },
    },
    vertexShader: `
      varying vec3 vPosition;
      void main() {
        vPosition = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      varying vec3 vPosition;
      uniform float time;
      uniform float depth;
      uniform vec3 baseTopColor;
      uniform vec3 baseBottomColor;
      uniform vec3 scanColor;
      uniform float opacity;
      void main() {
        float bandHeight = 0.45;
        float normalizedHeight = clamp(vPosition.z / depth, 0.0, 1.0);
        float progress = fract(time) * (1.0 + bandHeight) - bandHeight;
        float distance = (progress + bandHeight) - normalizedHeight;
        float belowHead = step(0.0, distance);
        float withinBand = clamp(1.0 - distance / bandHeight, 0.0, 1.0) * belowHead;
        float feather = smoothstep(0.0, 1.0, withinBand);
        float bandCore = pow(feather, 1.5);
        float bandEdge = smoothstep(0.0, 0.6, withinBand) * (1.0 - smoothstep(0.6, 1.0, withinBand));
        float scanStrength = (bandCore * 0.85 + bandEdge * 0.4);
        if (normalizedHeight < 0.001 || normalizedHeight > 0.999) {
          scanStrength = 0.0;
        }
        vec3 baseColor = mix(baseBottomColor, baseTopColor, normalizedHeight);
        vec3 scanned = mix(baseColor, scanColor, clamp(scanStrength, 0.0, 1.0));
        gl_FragColor = vec4(scanned, opacity);
      }`,
  })
}

// ====== 上升光柱 shader（移植 sc-datav SparklesImplMaterial） ======
function makeBeamMaterial(opacity) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uColor: { value: new THREE.Color('#7dd3fc') },
      uOpacity: { value: opacity },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      varying vec2 vUv;
      void main() {
        float strength = 1.0 - abs(vUv.x - 0.5) * 2.0;
        strength = pow(strength, 2.0);
        float verticalFade = sin(vUv.y * 3.14159);
        verticalFade = pow(verticalFade, 0.5);
        float brightness = strength * verticalFade;
        gl_FragColor = vec4(uColor * brightness * 2.0, brightness * uOpacity);
      }`,
  })
}

// ====== GeoJSON 几何归一化（Polygon / MultiPolygon → 环数组列表） ======
function featurePolys(feature) {
  const g = feature.geometry
  if (!g) return []
  if (g.type === 'Polygon') return [g.coordinates]
  if (g.type === 'MultiPolygon') return g.coordinates
  return []
}

function ringsToShape(rings, proj) {
  const toVec2 = ring => ring.map(c => {
    const [x, y] = proj(c)
    return new THREE.Vector2(x, y)
  })
  const shape = new THREE.Shape(toVec2(rings[0]))
  for (let i = 1; i < rings.length; i++) {
    shape.holes.push(new THREE.Path(toVec2(rings[i])))
  }
  return shape
}

// 顶面颜色：有火险等级用等级色，否则中性色（随主题变化）
function topColorFor(name, riskData) {
  const level = riskData && riskData[name]
  if (level >= 1 && level <= 5) return new THREE.Color(RISK_COLORS[level - 1])
  return new THREE.Color(themeC().neutral)
}

// 顶面全局 UV：以全省几何投影包络为基准归一化（侧面/底盖 UV 一并覆写，
// 但侧面扫光 shader 不采样 UV，无影响；顶面据此与地形法线贴图逐像素对齐）
function applyBboxUV(geo) {
  if (!geoBBox || !geo.attributes.uv) return
  const pos = geo.attributes.position
  const uv = geo.attributes.uv
  const dx = geoBBox.maxX - geoBBox.minX
  const dy = geoBBox.maxY - geoBBox.minY
  for (let i = 0; i < pos.count; i++) {
    uv.setXY(i, (pos.getX(i) - geoBBox.minX) / dx, (pos.getY(i) - geoBBox.minY) / dy)
  }
  uv.needsUpdate = true
}

// ====== 构建地图 ======
function buildMap() {
  // 重建时刷新主题态，确保垫层/描边取到当前主题配色
  themeMode = themeStore.isDark() ? 'dark' : 'light'
  // 清空旧场景内容
  if (mapGroup) {
    scene.remove(mapGroup)
    disposeGroup(mapGroup)
  }
  regionMeshes = []
  edgesMats = []
  flyMats = []
  underlayMats = []
  projFn = buildProjection(props.cityPolygons)

  mapGroup = new THREE.Group()
  mapGroup.rotation.x = -Math.PI / 2   // xy 平面铺到 XZ 地面，挤出方向朝上
  scene.add(mapGroup)

  const features = (props.cityPolygons.features || []).filter(f => f.geometry)

  features.forEach(feature => {
    const name = feature.properties?.name || ''
    const polys = featurePolys(feature)
    if (!polys.length) return
    const shapes = polys.map(rings => ringsToShape(rings, projFn))

    // 州市中心（外环顶点均值）：世界坐标 + 原始经纬度（供火点就近归簇）
    let cx = 0, cy = 0, n = 0
    let clng = 0, clat = 0
    polys[0][0].forEach(c => {
      const [x, y] = projFn(c)
      cx += x; cy += y; clng += c[0]; clat += c[1]; n++
    })
    cx /= n; cy /= n; clng /= n; clat /= n

    // 挤出网格：材质数组 [顶/底盖, 侧面]
    const geo = new THREE.ExtrudeGeometry(shapes, { depth: DEPTH, bevelEnabled: false })
    applyBboxUV(geo)
    const topMat = new THREE.MeshStandardMaterial({
      color: topColorFor(name, props.cityRiskData),
      // 顶面地形浮雕：云南高程法线贴图 + 哑光底色（近零金属度防背光发黑，高粗糙度保持哑光质感）
      metalness: 0.05,
      roughness: 0.92,
      normalMap: normalTex,
      normalScale: new THREE.Vector2(0.85, 0.85),
    })
    const mesh = new THREE.Mesh(geo, [topMat, sweepMat])
    mesh.userData = { name, center: new THREE.Vector3(cx, cy, 0), lngLat: [clng, clat] }
    mapGroup.add(mesh)
    regionMeshes.push(mesh)

    // 顶面描边（省界轮廓增强：高亮色 + 高不透明度，随主题切换调色）
    const topGeo = new THREE.ShapeGeometry(shapes)
    const edgeMat = new THREE.LineBasicMaterial({
      color: themeC().edge,
      transparent: true,
      opacity: themeC().edgeOpacity,
    })
    edgesMats.push(edgeMat)
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(topGeo), edgeMat)
    edges.position.z = DEPTH + 0.02
    mapGroup.add(edges)
    topGeo.dispose()

    // 底座基座：各多边形轮廓放大 8% 挤出成实心垫块（厚 0.3，位于地图正下方），
    // 彻底填死相邻州市边界不重合的裂缝，任何角度都不透背景色；
    // 相邻垫块会重叠，用逐块递增的 polygonOffset 错开深度避免共面闪烁
    shapes.forEach((shape, si) => {
      const pg = new THREE.ExtrudeGeometry(shape, { depth: 0.3, bevelEnabled: false })
      pg.computeBoundingBox()
      const bb = pg.boundingBox
      const bx = (bb.min.x + bb.max.x) / 2
      const by = (bb.min.y + bb.max.y) / 2
      pg.translate(-bx, -by, 0)
      pg.scale(1.08, 1.08, 1)
      pg.translate(bx, by, 0)
      const pmat = new THREE.MeshBasicMaterial({
        color: themeC().underlay,
        polygonOffset: true,
        polygonOffsetFactor: si * 2,
        polygonOffsetUnits: si * 2,
      })
      underlayMats.push(pmat)
      const plate = new THREE.Mesh(pg, pmat)
      plate.position.z = -0.34   // 垫块顶面 -0.04，与地图底面留阴影缝
      plate.renderOrder = -1
      mapGroup.add(plate)
    })

    // 州市名标签（CSS2D）
    const labelDiv = document.createElement('div')
    labelDiv.className = 'm3d-label'
    labelDiv.textContent = name
    const labelObj = new CSS2DObject(labelDiv)
    labelObj.position.set(cx, cy, DEPTH + 0.25)
    mapGroup.add(labelObj)
  })

  buildFlyLines(features)
  buildClusters()
}

// ====== 飞线：省会 → 各州市 ======
function buildFlyLines(features) {
  const centers = regionMeshes.map(m => m.userData)
  if (centers.length < 2) return
  const hub = centers.find(c => c.name && c.name.includes('昆明')) || centers[0]

  const group = new THREE.Group()
  group.renderOrder = 10
  group.position.z = DEPTH + 0.1
  centers.forEach(c => {
    if (c === hub) return
    const a = new THREE.Vector3(hub.center.x, hub.center.y, 0.15)
    const b = new THREE.Vector3(c.center.x, c.center.y, 0.15)
    const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5)
    mid.z = 4.2
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b)
    const flyMat = new THREE.MeshBasicMaterial({
      map: flyTex,
      transparent: true,
      color: themeC().fly,
      depthTest: false,
      blending: THREE.AdditiveBlending,
    })
    flyMats.push(flyMat)
    const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 32, 0.045, 6, false), flyMat)
    tube.renderOrder = 10
    group.add(tube)
  })
  mapGroup.add(group)
}

// ====== 火点总数柱状图（按州市聚合，随 props.firePoints 重建） ======
// 州市名归一：剥掉民族后缀/行政后缀后比对（西双版纳傣族自治州 ↔ 西双版纳州 ↔ 西双版纳）
const normCity = s => String(s || '')
  .replace(/傣族|彝族|哈尼族|白族|壮族|苗族|藏族|傈僳族|景颇族|回族|纳西族|自治州|地区|市|州/g, '')

function haversineKm(a, b) {
  const rad = Math.PI / 180
  const dLat = (b[1] - a[1]) * rad
  const dLng = (b[0] - a[0]) * rad
  const s = Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLng / 2) ** 2
  return 2 * 6371 * Math.asin(Math.sqrt(s))
}

// 火点归属州市：优先 properties.city 文本匹配，无 city 字段则就近州市中心归簇
function cityOfPoint(feature, centers) {
  const p = feature.properties || {}
  const raw = p.city || p.region || p.adname || ''
  if (raw) {
    const key = normCity(raw)
    const hit = centers.find(c => {
      const rn = normCity(c.name)
      return (rn && key && (rn === key || rn.includes(key) || key.includes(rn)))
    })
    if (hit) return hit.name
  }
  const c = feature.geometry && feature.geometry.coordinates
  if (c && typeof c[0] === 'number' && centers.length) {
    let best = null, bestD = Infinity
    centers.forEach(ctr => {
      const d = haversineKm(ctr.lngLat, [c[0], c[1]])
      if (d < bestD) { bestD = d; best = ctr }
    })
    if (best) return best.name
  }
  return null
}

// 单根柱（顶亮底暗渐变 + 沿口描边，基柱/聚类柱/单点柱共用）
function makeBar(x, y, count, max) {
  const h = count >= 2 ? 0.35 + (count / max) * 3.4 : (count === 1 ? 0.22 : 0.12)
  const ratio = Math.min(1, count / max)
  const cLow = new THREE.Color('#38bdf8')
  const cMid = new THREE.Color('#fbbf24')
  const cHigh = new THREE.Color('#ef4444')
  const color = ratio < 0.5
    ? cLow.clone().lerp(cMid, ratio / 0.5)
    : cMid.clone().lerp(cHigh, (ratio - 0.5) / 0.5)
  const r = count >= 2 ? 0.3 : 0.14

  const geo = new THREE.CylinderGeometry(r, r, 1, 20)
  geo.rotateX(Math.PI / 2)   // 柱轴对齐地图局部 +Z（挤出方向）
  // 顶亮底暗顶点色渐变：unlit 也自带立体感，任何视角都能读出「立柱」
  const cBot = color.clone().multiplyScalar(0.4)
  const cTop = color.clone().lerp(new THREE.Color('#ffffff'), 0.42)
  const posAttr = geo.attributes.position
  const colArr = new Float32Array(posAttr.count * 3)
  const vc = new THREE.Color()
  for (let i = 0; i < posAttr.count; i++) {
    const t = THREE.MathUtils.clamp(posAttr.getZ(i) + 0.5, 0, 1)
    vc.copy(cBot).lerp(cTop, t)
    colArr[i * 3] = vc.r
    colArr[i * 3 + 1] = vc.g
    colArr[i * 3 + 2] = vc.b
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colArr, 3))
  const bar = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true }))
  // 顶/底沿高亮圆环描边（阈值 30° 只保留棱边：两道圆环，不含侧面经线）
  bar.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(geo, 30),
    new THREE.LineBasicMaterial({ color: cTop, transparent: true, opacity: 0.95 }),
  ))
  bar.position.set(x, y, DEPTH + h / 2)
  bar.scale.z = h
  bar.renderOrder = 12
  clusterGroup.add(bar)

  // 数量标签：只有聚合簇（≥2）才标数字，单点/基柱保持画面干净
  if (count >= 2) {
    const labelDiv = document.createElement('div')
    labelDiv.className = 'm3d-bar-label'
    labelDiv.textContent = String(count)
    const labelObj = new CSS2DObject(labelDiv)
    labelObj.position.set(x, y, DEPTH + h + 0.28)
    clusterGroup.add(labelObj)
  }
}

// 聚类重建防抖（缩放/旋转/视口/数据变化时触发）
function scheduleClusters() {
  if (rebuildTimer) clearTimeout(rebuildTimer)
  rebuildTimer = setTimeout(() => {
    rebuildTimer = null
    buildClusters()
  }, 120)
}

// 火点屏幕空间聚类柱 —— 镜像 2D 地图 OL Cluster（distance=40px）的缩放联动：
// 拉远合并成大柱（≈州市总数）、拉近拆分成小柱/单点，数字随缩放变化
function buildClusters() {
  if (clusterGroup) {
    mapGroup.remove(clusterGroup)
    disposeGroup(clusterGroup)
    clusterGroup = null
  }
  if (!projFn || !regionMeshes.length || !camera) return
  clusterGroup = new THREE.Group()
  clusterGroup.renderOrder = 12

  const centers = regionMeshes.map(m => m.userData)

  // 1) 0 火点州市保留基柱，保证全省 16 州市全覆盖
  const cityCounts = {}
  centers.forEach(c => { cityCounts[c.name] = 0 })
  const feats = (props.firePoints && props.firePoints.features) || []
  feats.forEach(f => {
    const name = cityOfPoint(f, centers)
    if (name && cityCounts[name] != null) cityCounts[name]++
  })
  Object.entries(cityCounts).forEach(([name, count]) => {
    if (count === 0) {
      const center = centers.find(c => c.name === name)
      if (center) makeBar(center.center.x, center.center.y, 0, 1)
    }
  })

  // 2) 火点投影到屏幕像素后贪心聚类（阈值 40px，与 2D 一致）
  const host = hostRef.value
  const vw = (host && host.clientWidth) || 800
  const vh = (host && host.clientHeight) || 600
  camera.updateMatrixWorld()
  mapGroup.updateWorldMatrix(true, false)
  const CLUSTER_PX = 40
  const local = []
  const screen = []
  feats.forEach(f => {
    const c = f.geometry && f.geometry.coordinates
    if (!c || typeof c[0] !== 'number') return
    const [px, py] = projFn([c[0], c[1]])
    const wp = new THREE.Vector3(px, py, DEPTH).applyMatrix4(mapGroup.matrixWorld)
    const ndc = wp.clone().project(camera)
    if (ndc.z < -1 || ndc.z > 1) return
    local.push([px, py])
    screen.push({ x: (ndc.x + 1) / 2 * vw, y: (1 - ndc.y) / 2 * vh })
  })

  const clusters = []
  for (let i = 0; i < screen.length; i++) {
    const s = screen[i]
    let best = null
    let bestD = CLUSTER_PX * CLUSTER_PX
    for (let j = 0; j < clusters.length; j++) {
      const cl = clusters[j]
      const dx = cl.sx / cl.n - s.x
      const dy = cl.sy / cl.n - s.y
      const d = dx * dx + dy * dy
      if (d < bestD) { bestD = d; best = cl }
    }
    if (best) { best.sx += s.x; best.sy += s.y; best.n++; best.idx.push(i) }
    else clusters.push({ sx: s.x, sy: s.y, n: 1, idx: [i] })
  }

  let max = 1
  clusters.forEach(cl => { if (cl.n > max) max = cl.n })
  clusters.forEach(cl => {
    let ax = 0, ay = 0
    cl.idx.forEach(k => { ax += local[k][0]; ay += local[k][1] })
    makeBar(ax / cl.n, ay / cl.n, cl.n, max)
  })

  mapGroup.add(clusterGroup)
}


// ====== 底部旋转光环 + 上升光柱（世界坐标，不随地图组旋转） ======
function buildAmbience() {
  const ringGeo = new THREE.PlaneGeometry(19, 19)
  bottomRing = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({
    map: ringTex,
    transparent: true,
    color: themeC().ring,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  }))
  bottomRing.rotation.x = -Math.PI / 2
  bottomRing.position.y = -0.05
  scene.add(bottomRing)

  beams = new THREE.Group()
  const RANGE = 15
  const beamGeo = new THREE.CylinderGeometry(0.03, 0.03, 1, 6, 1, true)
  for (let k = 0; k < 18; k++) {
    const baseOpacity = 0.35 + Math.random() * 0.25
    const mat = makeBeamMaterial(baseOpacity)
    const beam = new THREE.Mesh(beamGeo, mat)
    beam.position.set(
      (Math.random() - 0.5) * RANGE,
      Math.random() * 8,
      (Math.random() - 0.5) * RANGE,
    )
    beam.scale.y = 2 + Math.random() * 3
    beam.userData = { speed: 1.2 + Math.random(), resetHeight: 10 + Math.random() * 8, range: RANGE, baseOpacity }
    beams.add(beam)
  }
  scene.add(beams)
}

// ====== 主题应用（明暗切换：背景/雾/扫光/描边/飞线/氛围元素统一调色） ======
function applySceneTheme() {
  if (!scene) return
  themeMode = themeStore.isDark() ? 'dark' : 'light'
  const c = themeC()
  const dark = themeMode === 'dark'

  // 场景底色与雾
  scene.background = new THREE.Color(c.bg)
  if (scene.fog) scene.fog.color.set(c.bg)
  else scene.fog = new THREE.Fog(c.bg, 20, 46)

  // 侧面扫光
  if (sweepMat) {
    sweepMat.uniforms.baseTopColor.value.set(c.sweepTop)
    sweepMat.uniforms.baseBottomColor.value.set(c.sweepBottom)
    sweepMat.uniforms.scanColor.value.set(c.scan)
  }

  // 州市轮廓描边（省界增强）
  edgesMats.forEach(m => { m.color.set(c.edge); m.opacity = c.edgeOpacity })

  // 底座垫层
  underlayMats.forEach(m => { m.color.set(c.underlay) })

  // 顶面中性底色（有火险数据的州市保持等级色）
  regionMeshes.forEach(m => {
    const top = Array.isArray(m.material) ? m.material[0] : m.material
    top.color.copy(topColorFor(m.userData.name, props.cityRiskData))
  })

  // 飞线：浅色下改普通混合（叠加混合在浅底上会发白失真）
  flyMats.forEach(m => {
    m.color.set(c.fly)
    m.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending
    m.opacity = dark ? 1 : 0.6
    m.needsUpdate = true
  })

  // 底部光环
  if (bottomRing) {
    bottomRing.material.color.set(c.ring)
    bottomRing.material.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending
    bottomRing.material.opacity = dark ? 1 : 0.4
    bottomRing.material.needsUpdate = true
  }

  // 上升光柱
  if (beams) {
    beams.children.forEach(b => {
      b.material.uniforms.uColor.value.set(c.beam)
      b.material.blending = dark ? THREE.AdditiveBlending : THREE.NormalBlending
      b.material.uniforms.uOpacity.value = dark ? b.userData.baseOpacity : b.userData.baseOpacity * 0.4
      b.material.needsUpdate = true
    })
  }
}

// ====== 交互：悬停抬升 / 点击选中 ======
function setPointer(e) {
  const rect = hostRef.value.getBoundingClientRect()
  pointerNdc.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointerNdc.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
}
function pickRegion() {
  raycaster.setFromCamera(pointerNdc, camera)
  const hits = raycaster.intersectObjects(regionMeshes, false)
  return hits.length ? hits[0].object : null
}
function onPointerMove(e) {
  if (!regionMeshes.length) return
  setPointer(e)
  const hit = pickRegion()
  if (hit !== hovered) {
    hovered = hit
    hostRef.value.style.cursor = hit ? 'pointer' : 'grab'
  }
}
function onPointerDown(e) { downXY = [e.clientX, e.clientY] }
function onPointerUp(e) {
  if (!downXY) return
  const moved = Math.hypot(e.clientX - downXY[0], e.clientY - downXY[1])
  downXY = null
  if (moved > 6) return
  setPointer(e)
  const hit = pickRegion()
  if (hit) emit('city-click', hit.userData.name)
}

// ====== 渲染循环 ======
function tick() {
  rafId = requestAnimationFrame(tick)
  const delta = Math.min(clock.getDelta(), 0.1)
  const elapsed = clock.elapsedTime

  // 入场：相机从高空俯视降轨至斜视（2.2s ease-out）
  if (introProgress < 1) {
    introProgress = Math.min(1, introProgress + delta / 2.2)
    const t = 1 - Math.pow(1 - introProgress, 3)
    camera.position.lerpVectors(CAM_START, CAM_END, t)
    if (introProgress >= 1 && !introClusterDone) {
      introClusterDone = true
      controls.enabled = true
      scheduleClusters()   // 入场结束按最终视角重建聚类
    }
  }

  // 侧面扫光 + 飞线流光
  sweepMat.uniforms.time.value = elapsed / 3
  flyTex.offset.x -= delta / 5
  // 底部光环旋转
  if (bottomRing) bottomRing.rotation.z += delta / 5
  // 光柱上升
  if (beams) {
    beams.children.forEach(beam => {
      beam.position.y += beam.userData.speed * delta
      if (beam.position.y > beam.userData.resetHeight) {
        beam.position.x = (Math.random() - 0.5) * beam.userData.range
        beam.position.z = (Math.random() - 0.5) * beam.userData.range
        beam.position.y = -1 - Math.random() * 2
        beam.scale.y = 2 + Math.random() * 3
      }
    })
  }
  // 悬停州市抬升
  regionMeshes.forEach(m => {
    const target = m === hovered ? 1.5 : 1
    m.scale.z += (target - m.scale.z) * 0.12
  })

  controls.update()
  renderer.render(scene, camera)
  labelRenderer.render(scene, camera)
}

// ====== 初始化 / 销毁 ======
function init() {
  const host = hostRef.value
  const w = host.clientWidth || 800
  const h = host.clientHeight || 600

  themeMode = themeStore.isDark() ? 'dark' : 'light'
  scene = new THREE.Scene()
  scene.background = new THREE.Color(themeC().bg)
  scene.fog = new THREE.Fog(themeC().bg, 20, 46)

  camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 200)
  camera.position.copy(CAM_START)

  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(w, h)
  host.appendChild(renderer.domElement)

  labelRenderer = new CSS2DRenderer()
  labelRenderer.setSize(w, h)
  labelRenderer.domElement.className = 'm3d-label-layer'
  host.appendChild(labelRenderer.domElement)

  // 灯光（位置/配色沿用 sc-datav，强度按 0.1 重调：只有顶面 topMat 受光照影响，
  // 原强度下白顶漫反射≈9 倍饱和裁剪，法线浮雕会被完全淹没；现平顶总亮度≈0.95，
  // 北坡变亮/南坡变暗的浮雕调制才能显现在哑光顶面上）
  scene.add(new THREE.AmbientLight(0xffffff, 0.25))
  const dir1 = new THREE.DirectionalLight(0xffffff, 0.8)
  dir1.position.set(0, 50, -50)
  scene.add(dir1)
  const dir2 = new THREE.DirectionalLight(0x88ccff, 0.25)
  dir2.position.set(-30, 40, 30)
  scene.add(dir2)

  // 贴图
  const loader = new THREE.TextureLoader()
  flyTex = loader.load(flyLineUrl, (t) => {
    t.wrapS = t.wrapT = THREE.RepeatWrapping
    t.repeat.set(0.5, 2)
  })
  ringTex = loader.load(ringUrl)
  ringTex.colorSpace = THREE.SRGBColorSpace
  // 地形法线贴图：保持线性色彩空间（法线数据不做 sRGB 解码），各向异性过滤提升斜视角清晰度
  normalTex = loader.load(terrainNormalUrl)
  normalTex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy())

  sweepMat = makeSweepMaterial()
  buildMap()
  buildAmbience()
  applySceneTheme()

  // 控制器（入场动画结束后启用）
  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = 6
  controls.maxDistance = 34
  controls.maxPolarAngle = 1.42
  controls.minPolarAngle = 0.52   // 禁止转到近天顶：俯视时柱体投影会退化成空白圆片
  controls.zoomSpeed = 0.6
  controls.target.set(0, 0.4, 0)
  controls.enabled = false
  controls.addEventListener('change', scheduleClusters)

  // 事件
  host.addEventListener('pointermove', onPointerMove)
  host.addEventListener('pointerdown', onPointerDown)
  host.addEventListener('pointerup', onPointerUp)

  resizeObserver = new ResizeObserver(() => {
    const nw = host.clientWidth, nh = host.clientHeight
    if (!nw || !nh) return
    camera.aspect = nw / nh
    camera.updateProjectionMatrix()
    renderer.setSize(nw, nh)
    labelRenderer.setSize(nw, nh)
    scheduleClusters()
  })
  resizeObserver.observe(host)

  clock.start()
  tick()
}

function disposeGroup(group) {
  group.traverse(obj => {
    if (obj.geometry) obj.geometry.dispose()
    if (obj.material) {
      const mats = Array.isArray(obj.material) ? obj.material : [obj.material]
      mats.forEach(m => {
        // 共享资源（sweepMat/贴图）不在此销毁
        if (m !== sweepMat) m.dispose()
      })
    }
    if (obj.isCSS2DObject && obj.element && obj.element.parentNode) {
      obj.element.parentNode.removeChild(obj.element)
    }
  })
}

function dispose() {
  cancelAnimationFrame(rafId)
  if (rebuildTimer) { clearTimeout(rebuildTimer); rebuildTimer = null }
  const host = hostRef.value
  if (host) {
    host.removeEventListener('pointermove', onPointerMove)
    host.removeEventListener('pointerdown', onPointerDown)
    host.removeEventListener('pointerup', onPointerUp)
  }
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null }
  if (controls) { controls.dispose(); controls = null }
  if (mapGroup) { scene.remove(mapGroup); disposeGroup(mapGroup); mapGroup = null }
  if (bottomRing) { scene.remove(bottomRing); bottomRing.geometry.dispose(); bottomRing.material.dispose() }
  if (beams) {
    beams.children.forEach(b => b.material.dispose())
    beams.geometry && beams.geometry.dispose()
    scene.remove(beams)
  }
  if (sweepMat) { sweepMat.dispose(); sweepMat = null }
  if (flyTex) flyTex.dispose()
  if (ringTex) ringTex.dispose()
  if (normalTex) normalTex.dispose()
  if (renderer) { renderer.dispose(); renderer.domElement && renderer.domElement.remove(); renderer = null }
  if (labelRenderer) { labelRenderer.domElement && labelRenderer.domElement.remove(); labelRenderer = null }
  regionMeshes = []
  edgesMats = []
  flyMats = []
}

// ====== 响应外部数据 ======
watch(() => props.cityRiskData, (rd) => {
  regionMeshes.forEach(m => {
    const top = Array.isArray(m.material) ? m.material[0] : m.material
    top.color.copy(topColorFor(m.userData.name, rd))
  })
}, { deep: true })

watch(() => props.firePoints, () => scheduleClusters())

// 明暗主题联动
watch(() => themeStore.mode, () => applySceneTheme())

/** 复位视角（dock「全省」按钮在 3D 模式下调用） */
function resetView() {
  introProgress = 0
  introClusterDone = false
  controls.enabled = false
  controls.target.set(0, 0.4, 0)
}

defineExpose({ resetView })

onMounted(init)
onBeforeUnmount(dispose)
</script>

<template>
  <div ref="hostRef" class="m3d-root">
    <div class="m3d-hint">拖拽旋转 · 滚轮缩放 · 点击州市检索</div>
  </div>
</template>

<style scoped>
.m3d-root {
  position: absolute;
  inset: 0;
  overflow: hidden;
  cursor: grab;
}

.m3d-root :deep(canvas) {
  display: block;
}

.m3d-hint {
  position: absolute;
  right: 12px;
  bottom: 10px;
  font-size: 10px;
  letter-spacing: 0.08em;
  color: rgba(148, 197, 235, 0.55);
  font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
  pointer-events: none;
  z-index: 5;
}

html:not(.dark) .m3d-hint {
  color: rgba(30, 90, 138, 0.6);
}
</style>

<!-- CSS2D 标签由 three 动态插入，无法被 scoped 编译，需全局样式 -->
<style>
.m3d-label-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.m3d-label {
  color: #e8f4ff;
  font-size: 11px;
  letter-spacing: 0.06em;
  white-space: nowrap;
  text-shadow: 0 0 6px rgba(56, 189, 248, 0.9), 0 1px 3px rgba(0, 0, 0, 0.9);
  transform: translateY(-6px);
}

/* 柱顶火点总数标签 */
.m3d-bar-label {
  color: #fcd34d;
  font-size: 10px;
  font-weight: 600;
  font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
  white-space: nowrap;
  text-shadow: 0 0 6px rgba(251, 191, 36, 0.75), 0 1px 2px rgba(0, 0, 0, 0.85);
  transform: translateY(-2px);
}

/* 浅色主题：深字 + 白色柔光，保证可读性 */
html:not(.dark) .m3d-label {
  color: #14456e;
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.92), 0 0 6px rgba(255, 255, 255, 0.75);
}

html:not(.dark) .m3d-bar-label {
  color: #b45309;
  text-shadow: 0 1px 2px rgba(255, 255, 255, 0.92);
}
</style>
