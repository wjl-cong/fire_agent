<script setup>
/**
 * 登录 / 注册页
 * 未登录访问任意页面会被路由守卫重定向到这里
 */
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref('login') // login / register
const loading = ref(false)
const form = ref({
  username: '',
  password: '',
  confirm: '',
  email: '',
})

// 密码显示/隐藏（眼睛按钮）
const showPwd = ref(false)
const showConfirm = ref(false)

const onSubmit = async () => {
  const u = form.value.username.trim()
  const p = form.value.password
  if (!u || !p) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (u.length < 2) {
    ElMessage.warning('用户名至少 2 个字符')
    return
  }
  if (p.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  if (mode.value === 'register' && p !== form.value.confirm) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(u, p)
      ElMessage.success('登录成功')
    } else {
      await auth.register(u, p, form.value.email.trim())
      ElMessage.success('注册成功，已自动登录')
    }
    const redirect = route.query.redirect || '/dashboard'
    router.replace(redirect)
  } catch (e) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    loading.value = false
  }
}

const switchMode = (m) => {
  mode.value = m
  form.value.confirm = ''
}
</script>

<template>
  <div class="login-shell">
    <div class="login-bg" />
    <div class="login-card">
      <div class="login-title">焰哨多Agent与可视化平台</div>
      <div class="login-subtitle">FlameSentry · 森林火险预警智能决策系统</div>

      <!-- 模式切换 -->
      <div class="mode-switch">
        <button :class="{ active: mode === 'login' }" @click="switchMode('login')">登 录</button>
        <button :class="{ active: mode === 'register' }" @click="switchMode('register')">注 册</button>
      </div>

      <!-- 表单 -->
      <div class="form-area">
        <label class="field">
          <span>用户名</span>
          <input v-model="form.username" type="text" placeholder="请输入用户名" @keyup.enter="onSubmit" />
        </label>

        <template v-if="mode === 'register'">
          <label class="field">
            <span>邮箱（可选）</span>
            <input v-model="form.email" type="email" placeholder="用于找回账号" />
          </label>
        </template>

        <label class="field">
          <span>密码</span>
          <div class="pwd-wrap">
            <input v-model="form.password" :type="showPwd ? 'text' : 'password'" placeholder="请输入密码" @keyup.enter="onSubmit" />
            <button type="button" class="eye-btn" :title="showPwd ? '隐藏密码' : '显示密码'" @click="showPwd = !showPwd">
              <svg v-if="showPwd" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>
        </label>

        <label v-if="mode === 'register'" class="field">
          <span>确认密码</span>
          <div class="pwd-wrap">
            <input v-model="form.confirm" :type="showConfirm ? 'text' : 'password'" placeholder="请再次输入密码" @keyup.enter="onSubmit" />
            <button type="button" class="eye-btn" :title="showConfirm ? '隐藏密码' : '显示密码'" @click="showConfirm = !showConfirm">
              <svg v-if="showConfirm" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
              <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </button>
          </div>
        </label>

        <button class="submit-btn" :disabled="loading" @click="onSubmit">
          {{ loading ? '处理中...' : (mode === 'login' ? '登 录' : '注 册') }}
        </button>
      </div>

      <div class="login-foot">
        <p v-if="mode === 'login'">还没有账号？<a @click="switchMode('register')">立即注册</a></p>
        <p v-else>已有账号？<a @click="switchMode('login')">返回登录</a></p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-shell {
  position: relative;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gis-bg-deep);
  overflow: hidden;
}
.login-bg {
  position: absolute;
  inset: 0;
  background: var(--gis-atmo-bg);
}
.login-card {
  position: relative;
  width: 380px;
  padding: 36px 34px 28px;
  background: var(--gis-glass);
  backdrop-filter: blur(18px) saturate(150%);
  border: 1px solid var(--gis-glass-border);
  border-radius: var(--gis-radius-lg, 12px);
  box-shadow: var(--gis-glow), 0 20px 60px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}
.login-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 64px;
  background: var(--gis-metal-sheen);
  pointer-events: none;
}
.login-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--gis-text);
  text-align: center;
  line-height: 1.4;
}
.login-subtitle {
  margin-top: 6px;
  font-size: 12px;
  color: var(--gis-accent, #0ea5e9);
  text-align: center;
  letter-spacing: 0.04em;
  text-shadow: var(--gis-text-glow);
}
.mode-switch {
  display: flex;
  gap: 8px;
  margin: 24px 0 20px;
  padding: 4px;
  background: var(--gis-bg-deep);
  border-radius: 8px;
}
.mode-switch button {
  flex: 1;
  padding: 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--gis-text-muted);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-switch button.active {
  color: var(--gis-on-accent);
  background: var(--gis-metal-accent);
}
.form-area {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field span {
  font-size: 12px;
  color: var(--gis-text-muted);
}
.field input {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  color: var(--gis-text);
  background: var(--el-fill-color-blank, rgba(10, 17, 32, 0.6));
  border: 1px solid var(--gis-glass-border);
  border-radius: var(--gis-radius-sm, 6px);
  outline: none;
  transition: border 0.15s, box-shadow 0.15s;
}
.pwd-wrap {
  position: relative;
  display: flex;
}
.pwd-wrap input {
  padding-right: 38px;
}
.eye-btn {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: #64748b;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: color 0.15s;
}
.eye-btn:hover {
  color: var(--gis-accent, #38bdf8);
}
.field input:focus {
  border-color: var(--gis-accent, #0ea5e9);
  box-shadow: var(--gis-glow);
}
.field input::placeholder {
  color: var(--gis-text-muted);
}
.submit-btn {
  margin-top: 6px;
  padding: 11px 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--gis-on-accent);
  background: var(--gis-metal-accent);
  border: none;
  border-radius: var(--gis-radius-sm, 6px);
  cursor: pointer;
  transition: filter 0.15s, box-shadow 0.15s;
}
.submit-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  box-shadow: var(--gis-glow-strong);
}
.submit-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.login-foot {
  margin-top: 16px;
  text-align: center;
  font-size: 12px;
  color: #64748b;
}
.login-foot a {
  color: var(--gis-accent, #0ea5e9);
  cursor: pointer;
  text-decoration: underline;
}
</style>