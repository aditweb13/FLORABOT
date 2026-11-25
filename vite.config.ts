import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'FLORABOT_');
  const backend = env.FLORABOT_API_TARGET || 'http://127.0.0.1:8001';
  return {
    plugins: [react()],
    server: {
      port: 5190,
      host: '0.0.0.0',
      proxy: {
        '/api': backend,
        '/files': backend
      }
    }
  };
});
