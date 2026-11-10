import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 5174,
    open: false,
    strictPort: false,
  },
  build: {
    target: 'es2022',
  },
});
