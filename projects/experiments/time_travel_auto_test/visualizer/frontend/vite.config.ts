import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// dev 模式：vite (5173) 把 /ws 与 /api 代理到后端 run_server.py (8800)
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/ws': {
        target: 'http://127.0.0.1:8800',
        ws: true,
      },
      '/api': {
        target: 'http://127.0.0.1:8800',
      },
    },
  },
  test: {
    environment: 'node',
    globals: true,
  },
});
