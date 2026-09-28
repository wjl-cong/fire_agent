<script setup>
/**
 * 主布局 — 左侧导航栏 + 右侧内容区
 * 导航项使用 iconfont（阿里矢量图标库，已在 index.html 全局加载）
 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()

const handleLogout = () => {
  auth.logout()
  router.replace('/login')
}

const handleToggleTheme = () => {
  theme.toggle()
}

// iconfont 实际可用图标（已从阿里 CDN 核实）：
// ditu01, jingweidu, 023tuceng, duobianxing, relitu, radio-on, ...
const allNavItems = [
  { path: '/dashboard',    label: '作战大屏',   icon: 'icon-ditu01' },
  { path: '/smart-query',  label: '智能查询',   icon: 'icon-jingweidu' },
  { path: '/knowledge-base', label: '知识库',    icon: 'icon-023tuceng' },
  { path: '/agent-center', label: 'Agent中心',  icon: 'icon-duobianxing' },
  { path: '/report-center', label: '报告中心',   icon: 'icon-relitu' },
  { path: '/admin',        label: '系统管理',   icon: 'icon-radio-on', adminOnly: true },
]
// 系统管理仅管理员可见
const navItems = computed(() =>
  allNavItems.filter(item => !item.adminOnly || auth.user?.role === 'admin')
)
</script>

<template>
  <div class="app-shell">
    <!-- 左侧导航栏 -->
    <aside class="app-sidebar">
      <div class="sidebar-brand">
        <span class="brand-text" title="焰哨多Agent与可视化平台">焰</span>
      </div>
      <nav class="sidebar-nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
          :title="item.label"
        >
          <i class="iconfont" :class="item.icon"></i>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>

      <!-- 主题切换 / 用户信息 / 退出 -->
      <div class="sidebar-user">
        <button
          class="theme-btn"
          :title="theme.mode === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
          @click="handleToggleTheme"
        >
          {{ theme.mode === 'dark' ? '☀' : '☾' }}
        </button>
        <router-link to="/profile" class="user-avatar" title="个人中心">
          {{ auth.displayName ? auth.displayName.charAt(0).toUpperCase() : 'U' }}
        </router-link>
        <button class="logout-btn" title="退出登录" @click="handleLogout">
          ⏻
        </button>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  background: var(--gis-atmo-bg);
  color: var(--gis-text, #f8fafc);
  overflow: hidden;
}

/* 侧栏 */
.app-sidebar {
  flex-shrink: 0;
  width: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: linear-gradient(180deg, var(--gis-glass-solid) 0%, var(--gis-bg-deep) 100%);
  backdrop-filter: blur(var(--gis-glass-blur)) saturate(var(--gis-glass-saturate));
  border-right: 1px solid var(--gis-glass-border);
  box-shadow: 1px 0 0 var(--gis-glass-border);
  z-index: 30;
  overflow: hidden;
}

.sidebar-brand {
  width: 100%;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid var(--gis-border, #334155);
}

.brand-text {
  font-family: ui-monospace, 'Consolas', monospace;
  font-size: 18px;
  font-weight: 800;
  color: var(--gis-accent, #0ea5e9);
  letter-spacing: 0.04em;
  text-shadow: var(--gis-text-glow, 0 0 8px rgba(34, 211, 238, 0.4));
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 12px 0;
}

.nav-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 44px;
  text-decoration: none;
  color: var(--gis-text-muted, #94a3b8);
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
  cursor: pointer;
}

.nav-item:hover {
  color: var(--gis-text, #f8fafc);
  background: var(--gis-hover-tint);
}

.nav-item.active {
  color: var(--gis-accent, #0ea5e9);
  background: var(--gis-accent-soft);
  box-shadow: var(--gis-glow-strong);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: var(--gis-metal-accent);
  box-shadow: 0 0 6px var(--gis-accent-dim);
}

.nav-item .iconfont {
  font-size: 18px;
  line-height: 1;
}

.nav-label {
  display: none;
  font-size: 9px;
  line-height: 1;
  margin-top: 2px;
  letter-spacing: 0.02em;
}

/* 内容区 */
.app-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

/* 用户区块 */
.sidebar-user {
  flex-shrink: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 10px 0 14px;
  border-top: 1px solid var(--gis-border, #334155);
}
.user-avatar {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--gis-on-accent);
  background: var(--gis-metal-accent);
  border-radius: 50%;
  cursor: pointer;
  text-decoration: none;
  transition: box-shadow 0.15s, transform 0.15s;
}
.user-avatar:hover {
  box-shadow: 0 0 0 2px var(--gis-accent-dim), var(--gis-glow);
  transform: scale(1.08);
}
.theme-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  line-height: 1;
  color: var(--gis-text-muted, #94a3b8);
  background: transparent;
  border: 1px solid var(--gis-border, #334155);
  border-radius: 50%;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.theme-btn:hover {
  color: var(--gis-accent, #0ea5e9);
  border-color: var(--gis-accent-dim);
  box-shadow: var(--gis-glow);
}
.logout-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: var(--gis-text-muted, #94a3b8);
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.logout-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
}
</style>