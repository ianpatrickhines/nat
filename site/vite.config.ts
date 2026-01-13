import { defineConfig } from 'vite';

export default defineConfig({
  root: '.',
  build: {
    outDir: 'dist',
    emptyDirBeforeWrite: true,
  },
  server: {
    port: 3000,
    open: true,
  },
});
