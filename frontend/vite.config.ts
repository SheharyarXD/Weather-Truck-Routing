import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Django + WhiteNoise serve the production build from /static/. GitHub Pages serves it from
  // /<repository>/, which the Pages workflow passes in as VITE_BASE.
  base: process.env.VITE_BASE ?? (command === 'build' ? '/static/' : '/'),
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
}));
