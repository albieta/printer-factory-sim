import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = Number(process.env.VITE_BACKEND_PORT ?? '8000')

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: `http://localhost:${backendPort}`,
        changeOrigin: true,
      }
    }
  }
})
