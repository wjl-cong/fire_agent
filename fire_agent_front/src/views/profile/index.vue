<script setup>
/**
 * 个人中心 — 查看/修改个人资料（邮箱）与修改密码
 *
 * 后端 API: PUT /api/v1/auth/me、PUT /api/v1/auth/me/password
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User as UserIcon, Lock, Promotion } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { API_V1 } from '@/utils/config'

const API_BASE = `${API_V1}/auth`
const auth = useAuthStore()
const router = useRouter()

const roleLabel = (r) => (r === 'admin' ? '管理员' : '普通用户')
const fmtTime = (t) => (t ? String(t).replace('T', ' ').slice(0, 19) : '—')

// ====== 个人资料 ======
const profileForm = reactive({
  email: auth.user?.email || '',
})
const savingProfile = ref(false)

const saveProfile = async () => {
  savingProfile.value = true
  try {
    const res = await fetch(`${API_BASE}/me`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ email: profileForm.email.trim() }),
    })
    const json = await res.json()
    if (res.ok && json.code === 200) {
      auth.updateUser({ email: json.data.email })
      ElMessage.success('个人资料已更新')
    } else {
      ElMessage.error(json.detail || '保存失败')
    }
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingProfile.value = false
  }
}

// ====== 修改密码 ======
const pwdForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const savingPwd = ref(false)

const changePassword = async () => {
  if (!pwdForm.old_password || !pwdForm.new_password) {
    ElMessage.warning('请填写完整')
    return
  }
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  savingPwd.value = true
  try {
    const res = await fetch(`${API_BASE}/me/password`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        old_password: pwdForm.old_password,
        new_password: pwdForm.new_password,
      }),
    })
    const json = await res.json()
    if (res.ok && json.code === 200) {
      ElMessage.success('密码已修改，请重新登录')
      // 修改密码后强制重新登录
      setTimeout(async () => {
        try { await ElMessageBox.close() } catch { /* ignore */ }
        auth.logout()
        router.replace('/login')
      }, 1200)
    } else {
      ElMessage.error(json.detail || '修改失败')
    }
  } catch {
    ElMessage.error('修改失败')
  } finally {
    savingPwd.value = false
  }
}
</script>

<template>
  <div class="profile-shell">
    <header class="profile-header">
      <h1 class="profile-title">个人中心</h1>
      <p class="profile-subtitle">管理个人资料与账号安全</p>
    </header>

    <div class="profile-grid">
      <!-- 个人资料 -->
      <section class="profile-card">
        <div class="pc-title">
          <el-icon><UserIcon /></el-icon>
          个人资料
        </div>

        <div class="info-rows">
          <div class="info-row">
            <span class="ir-label">用户名</span>
            <span class="ir-value">
              {{ auth.user?.username }}
              <span class="role-badge" :class="auth.user?.role === 'admin' ? 'role-admin' : 'role-user'">
                {{ roleLabel(auth.user?.role) }}
              </span>
            </span>
          </div>
          <div class="info-row">
            <span class="ir-label">注册时间</span>
            <span class="ir-value">{{ fmtTime(auth.user?.created_at) }}</span>
          </div>
        </div>

        <div class="form-item">
          <label>邮箱</label>
          <el-input v-model="profileForm.email" placeholder="用于找回密码与通知（可留空）" maxlength="120" clearable />
        </div>

        <div class="card-actions">
          <el-button type="primary" :loading="savingProfile" @click="saveProfile" :icon="Promotion">
            保存资料
          </el-button>
        </div>
      </section>

      <!-- 修改密码 -->
      <section class="profile-card">
        <div class="pc-title">
          <el-icon><Lock /></el-icon>
          修改密码
        </div>

        <div class="form-item">
          <label>旧密码</label>
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="当前密码" />
        </div>
        <div class="form-item">
          <label>新密码</label>
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少 6 位" />
        </div>
        <div class="form-item">
          <label>确认新密码</label>
          <el-input v-model="pwdForm.confirm_password" type="password" show-password placeholder="再次输入新密码" />
        </div>

        <div class="pwd-note">
          修改密码成功后将退出登录，需使用新密码重新登录。
        </div>

        <div class="card-actions">
          <el-button type="primary" :loading="savingPwd" @click="changePassword">
            确认修改
          </el-button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.profile-shell {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0a0f1e;
  color: #f8fafc;
  overflow-y: auto;
}
.profile-header {
  padding: 18px 24px;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
}
.profile-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}
.profile-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  color: #64748b;
}
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 16px;
  padding: 20px 24px;
  max-width: 960px;
}
.profile-card {
  background: #0f172a;
  border: 1px solid #1e293b;
  border-radius: 8px;
  padding: 18px 20px;
}
.pc-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #1e293b;
}
.info-rows {
  margin-bottom: 16px;
}
.info-row {
  display: flex;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed #1e293b;
}
.info-row:last-child {
  border-bottom: none;
}
.ir-label {
  width: 80px;
  font-size: 12px;
  color: #64748b;
  flex-shrink: 0;
}
.ir-value {
  font-size: 13px;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.role-badge {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 8px;
}
.role-admin {
  color: #facc15;
  background: rgba(250, 204, 21, 0.12);
  border: 1px solid rgba(250, 204, 21, 0.3);
}
.role-user {
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.3);
}
.form-item {
  margin-bottom: 14px;
}
.form-item label {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 6px;
}
.card-actions {
  margin-top: 16px;
}
.card-actions :deep(.el-button--primary) {
  background: #0ea5e9;
  border-color: #0ea5e9;
}
.pwd-note {
  margin-top: 4px;
  padding: 8px 12px;
  font-size: 11px;
  line-height: 1.7;
  color: #94a3b8;
  background: rgba(14, 165, 233, 0.05);
  border: 1px dashed rgba(14, 165, 233, 0.25);
  border-radius: 4px;
}
</style>
