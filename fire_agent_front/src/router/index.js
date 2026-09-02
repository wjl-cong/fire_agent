/**
 * 多页面路由表
 *
 * 页面结构：
 *   /login           → 登录/注册
 *   /dashboard       → 作战大屏（现有 GIS 大屏）
 *   /smart-query     → 智能查询
 *   /knowledge-base  → 知识库 RAG 问答
 *   /agent-center    → Agent 协作中心
 *   /report-center   → 报告中心
 *   /profile         → 个人中心（资料/密码）
 *   /admin           → 系统管理（仅管理员）
 */
import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
    history: createWebHistory(
        import.meta.env.BASE_URL),
    routes: [{
            path: '/login',
            name: 'login',
            component: () =>
                import ('@/views/login/index.vue'),
            meta: { public: true }
        },
        {
            path: '/',
            redirect: '/dashboard'
        },
        {
            path: '/dashboard',
            name: 'dashboard',
            component: () =>
                import ('@/views/dashboard/index.vue')
        },
        {
            path: '/smart-query',
            name: 'smart-query',
            component: () =>
                import ('@/views/smart-query/index.vue')
        },
        {
            path: '/knowledge-base',
            name: 'knowledge-base',
            component: () =>
                import ('@/views/knowledge-base/index.vue')
        },
        {
            path: '/agent-center',
            name: 'agent-center',
            component: () =>
                import ('@/views/agent-center/index.vue')
        },
        {
            path: '/report-center',
            name: 'report-center',
            component: () =>
                import ('@/views/report-center/index.vue')
        },
        {
            path: '/profile',
            name: 'profile',
            component: () =>
                import ('@/views/profile/index.vue')
        },
        {
            path: '/admin',
            name: 'admin',
            component: () =>
                import ('@/views/admin/index.vue'),
            meta: { requiresAdmin: true }
        }
    ]
})

router.beforeEach((to, from, next) => {
    // 登录页无需鉴权
    if (to.meta.public) {
        next()
        return
    }
    try {
        const auth = useAuthStore()
        if (!auth.isLoggedIn) {
            next({ path: '/login', query: to.path === '/' ? {} : { redirect: to.fullPath } })
            return
        }
        // 系统管理页仅管理员可访问
        const userRole = auth.user && auth.user.role
        if (to.meta.requiresAdmin && userRole !== 'admin') {
            ElMessage.warning('需要管理员权限')
            next('/dashboard')
            return
        }
    } catch (e) {
        /* pinia 未初始化时放行 */
    }
    next()
})

export default router