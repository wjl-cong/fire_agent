<script setup>
/**
 * 时钟组件 — 实时显示系统日期与时间
 * - 日期行：YYYY-MM-DD 周X
 * - 时钟行：HH:mm:ss（每秒更新）
 * - 星期指示器：周一~周日横向排列，当前星期高亮
 */
import { ref, onMounted, onUnmounted } from 'vue'
import moment from 'moment'

// 星期数据（周一~周日），isActive 标记当前星期高亮
const times = ref([
  { name: '一', isActive: false }, { name: '二', isActive: false },
  { name: '三', isActive: false }, { name: '四', isActive: false },
  { name: '五', isActive: false }, { name: '六', isActive: false },
  { name: '日', isActive: false }
])

const currentTime = ref('')
const currentDateStr = ref('')

const updateClock = () => {
  const now = moment()
  currentTime.value = now.format('HH:mm:ss')
  const wk = ['日', '一', '二', '三', '四', '五', '六']
  currentDateStr.value = `${now.format('YYYY-MM-DD')} 周${wk[now.day()]}`
  const d = now.day()
  const idx = d === 0 ? 6 : d - 1
  times.value.forEach((item, i) => { item.isActive = i === idx })
}

onMounted(() => {
  updateClock()
  const interval = setInterval(updateClock, 1000)
  onUnmounted(() => clearInterval(interval))
})
</script>

<template>
  <div class="gis-clock" aria-live="polite">
    <div class="gis-clock-date">{{ currentDateStr }}</div>
    <div class="gis-clock-row">
      <div class="gis-clock-time">{{ currentTime }}</div>
      <div class="gis-clock-dow">
        <span v-for="(day, index) in times" :key="index" :class="{ on: day.isActive }">{{ day.name }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gis-clock {
  min-width: 200px;
  padding: 6px 10px;
  font-family: ui-monospace, 'Cascadia Code', 'Consolas', monospace;
  color: var(--gis-text, #f8fafc);
  background: var(--gis-bg-panel, #0f172a);
  border: 1px solid var(--gis-border, #334155);
  border-radius: 2px;
}

.gis-clock-date {
  font-size: 10px;
  letter-spacing: 0.06em;
  color: var(--gis-text-muted, #94a3b8);
  margin-bottom: 4px;
}

.gis-clock-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.gis-clock-time {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--gis-accent, #22d3ee);
}

.gis-clock-dow {
  display: flex;
  gap: 4px;
  font-size: 10px;
  color: var(--gis-text-muted, #64748b);
}

.gis-clock-dow span.on {
  color: var(--gis-text, #f8fafc);
  font-weight: 700;
}
</style>
