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
          <input v-model="form.password" type="password" placeholder="请输入密码" @keyup.enter="onSubmit" />
        </label>

        <label v-if="mode === 'register'" class="field">
          <span>确认密码</span>
          <input v-model="form.confirm" type="password" placeholder="请再次输入密码" @keyup.enter="onSubmit" />
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
  background: #020617;
  overflow: hidden;
}
.login-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(600px 300px at 20% 20%, rgba(14, 165, 233, 0.15), transparent 60%),
    radial-gradient(600px 300px at 80% 80%, rgba(34, 211, 238, 0.12), transparent 60%),
    #020617;
}
.login-card {
  position: relative;
  width: 380px;
  padding: 36px 34px 28px;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(8px);
  border: 1px solid #1e293b;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.login-title {
  font-size: 16px;
  font-weight: 700;
  color: #f8fafc;
  text-align: center;
  line-height: 1.4;
}
.login-subtitle {
  margin-top: 6px;
  font-size: 12px;
  color: #0ea5e9;
  text-align: center;
  letter-spacing: 0.04em;
}
.mode-switch {
  display: flex;
  gap: 8px;
  margin: 24px 0 20px;
  padding: 4px;
  background: #0f172a;
  border-radius: 8px;
}
.mode-switch button {
  flex: 1;
  padding: 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: #94a3b8;
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-switch button.active {
  color: #020617;
  background: #0ea5e9;
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
  color: #94a3b8;
}
.field input {
  padding: 10px 12px;
  font-size: 13px;
  color: #f8fafc;
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 6px;
  outline: none;
  transition: border 0.15s;
}
.field input:focus {
  border-color: #0ea5e9;
}
.field input::placeholder {
  color: #475569;
}
.submit-btn {
  margin-top: 6px;
  padding: 11px 0;
  font-size: 14px;
  font-weight: 700;
  color: #020617;
  background: #0ea5e9;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) {
  background: #38bdf8;
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
  color: #0ea5e9;
  cursor: pointer;
  text-decoration: underline;
}
</style>