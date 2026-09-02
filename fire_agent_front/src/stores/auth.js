/**
 * 认证状态管理（Pinia）
 * - token 与用户信息写入 localStorage 持久化
 * - 提供 login / register / logout
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { API_V1 } from '@/utils/config'

const API_BASE = `${API_V1}/auth`
const TOKEN_KEY = 'fire_agent_token'
const USER_KEY = 'fire_agent_user'

export const useAuthStore = defineStore('auth', () => {
    const token = ref(localStorage.getItem(TOKEN_KEY) || '')
    const user = ref(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

    const isLoggedIn = computed(() => !!token.value)
    const displayName = computed(() => user.value ?.username || '')

    function _persist() {
        if (token.value) localStorage.setItem(TOKEN_KEY, token.value)
        else localStorage.removeItem(TOKEN_KEY)
        if (user.value) localStorage.setItem(USER_KEY, JSON.stringify(user.value))
        else localStorage.removeItem(USER_KEY)
    }

    async function _request(path, body) {
        const res = await fetch(`${API_BASE}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
        const json = await res.json()
        if (!res.ok || json.code !== 200) {
            throw new Error(json ?.detail || json ?.message || '请求失败')
        }
        return json.data
    }

    async function login(username, password) {
        const data = await _request('/login', { username, password })
        token.value = data.access_token
        user.value = data.user
        _persist()
    }

    async function register(username, password, email = '') {
        const data = await _request('/register', { username, password, email })
        token.value = data.access_token
        user.value = data.user
        _persist()
    }

    /** 本地更新用户信息（个人中心保存后调用） */
    function updateUser(partial) {
        if (user.value) {
            user.value = { ...user.value, ...partial }
            _persist()
        }
    }

    function logout() {
        token.value = ''
        user.value = null
        _persist()
    }

    return { token, user, isLoggedIn, displayName, login, register, logout, updateUser }
})