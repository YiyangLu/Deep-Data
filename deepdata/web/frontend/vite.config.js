import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const wsTarget = env.VITE_WS_URL || 'ws://localhost:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/ws': {
          target: wsTarget,
          ws: true
        }
      }
    }
  }
})
