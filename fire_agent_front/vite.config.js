import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
    base: './',
    server: {
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            // 天地图瓦片代理：本地开发走同源 /tianditu，与生产 Nginx 行为一致
            // 关键：删除 Referer（实测无 Referer 的请求天地图放行，带不匹配的 Referer 反而 403）
            '/tianditu': {
                target: 'http://t0.tianditu.com',
                changeOrigin: true,
                rewrite: (p) => p.replace(/^\/tianditu/, ''),
                configure: (proxy) => {
                    proxy.on('proxyReq', (proxyReq) => {
                        proxyReq.removeHeader('referer')
                    })
                },
            },
        },
    },
    plugins: [
        vue(),
        AutoImport({
            resolvers: [ElementPlusResolver()],
        }),
        Components({
            resolvers: [ElementPlusResolver()],
        }),
    ],
    resolve: {
        alias: {
            '@': fileURLToPath(new URL('./src',
                import.meta.url))
        },
    },
})