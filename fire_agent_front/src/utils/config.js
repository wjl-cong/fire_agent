/**
 * 全局 API 地址统一配置
 *
 * 所有环境统一使用相对路径 /api，无需按域名/IP 分别修改：
 *   - 本地开发（.env.development）：VITE_API_BASE=/api → 由 vite.config.js 的 dev 代理转发到 localhost:8000
 *   - 生产构建（.env.production） ：VITE_API_BASE=/api → 由服务器 Nginx 反向代理到 127.0.0.1:8000
 *   - 例外（前后端分离部署到不同域名）才需要改 .env.production：
 *       VITE_API_BASE=https://后端域名/api
 *
 * 注意：Vite 在构建时注入环境变量，改完 .env 需重新 npm run dev / npm run build。
 */
export const API_BASE = (
    import.meta.env.VITE_API_BASE || '/api').replace(/\/+$/, '')
export const API_V1 = `${API_BASE}/v1`