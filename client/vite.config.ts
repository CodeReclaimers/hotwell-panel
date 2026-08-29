import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// No node APIs in this file: @types/node is deliberately not a dependency (§1
// pins the dev-dependency list and nothing here needs one).
export default defineConfig({
  plugins: [svelte()],
  server: {
    // Dev runs two processes (§2): vite serves the client with HMR and proxies
    // the WebSocket to uvicorn on :8000, upgrade included.
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
  test: {
    include: ['tests/**/*.test.ts'],
    environment: 'node',
  },
});
