import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const repoRoot = fileURLToPath(new URL('..', import.meta.url))

  const env = loadEnv(mode, repoRoot, '')
  const apiToken = env.MOTH_API_TOKEN

  if (!apiToken) {
    throw new Error(
      'MOTH_API_TOKEN is missing from the repository .env file.',
    )
  }

  return {
    plugins: [react()],

    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,

          configure(proxy) {
            proxy.on('proxyReq', (proxyRequest) => {
              proxyRequest.setHeader(
                'Authorization',
                `Bearer ${apiToken}`,
              )
            })
          },
        },
      },
    },
  }
})