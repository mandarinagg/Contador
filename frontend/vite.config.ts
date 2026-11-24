import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Tauri sirve el build desde archivos locales y en desarrollo espera este puerto fijo.
  server: { port: 5173, strictPort: true, host: '127.0.0.1' },
  clearScreen: false,
  build: { target: 'es2022', sourcemap: true },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'] },
})
