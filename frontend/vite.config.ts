import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  // Public artifact ignores all local dotenv files and forces live mode off.
  ...(mode === 'static' ? {
    envDir: false,
    define: {
      'import.meta.env.VITE_STATIC_DEMO': JSON.stringify('true'),
      'import.meta.env.VITE_ENABLE_LIVE_SEARCH': JSON.stringify('false'),
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(''),
    },
  } : {}),
  build: { sourcemap: false },
  plugins: [react()],
  test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', clearMocks: true },
}))
