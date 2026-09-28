/**
 * Vue 应用入口 — 注册全局插件并挂载根组件
 * - Pinia（状态管理，备用）
 * - Vue Router（单路由，/ 指向 map.vue）
 * - Element Plus（中文语言包）
 * 底部 patch：修复 Canvas getContext willReadFrequently，兼容 OpenLayers 导出
 */
import '@/style/common.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '@/style/gis-theme.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import App from './App.vue'
import router from './router'
import { applyTheme } from '@/stores/theme'

export const app = createApp(App)

// 主题：挂载前先应用已保存的主题类，避免浅色默认主题出现深色闪烁
applyTheme(localStorage.getItem('fire_agent_theme') === 'dark' ? 'dark' : 'light')

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')

// patch：Canvas getContext 2D 添加 willReadFrequently，提升 OL 导出性能