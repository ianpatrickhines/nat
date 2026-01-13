import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';
import { resolve } from 'path';
import { copyFileSync, mkdirSync, existsSync, readdirSync } from 'fs';

// Copy public files to dist after build
function copyPublicFiles() {
  return {
    name: 'copy-public-files',
    closeBundle() {
      const publicDir = resolve(__dirname, 'public');
      const distDir = resolve(__dirname, 'dist');

      // Copy manifest.json
      copyFileSync(
        resolve(publicDir, 'manifest.json'),
        resolve(distDir, 'manifest.json')
      );

      // Copy icons if they exist
      const iconsDir = resolve(publicDir, 'icons');
      const distIconsDir = resolve(distDir, 'icons');
      if (existsSync(iconsDir)) {
        if (!existsSync(distIconsDir)) {
          mkdirSync(distIconsDir, { recursive: true });
        }
        const iconFiles = readdirSync(iconsDir);
        for (const file of iconFiles) {
          copyFileSync(
            resolve(iconsDir, file),
            resolve(distIconsDir, file)
          );
        }
      }

      // Copy content.css
      const contentCss = resolve(__dirname, 'src/content/content.css');
      if (existsSync(contentCss)) {
        copyFileSync(contentCss, resolve(distDir, 'content.css'));
      }
    },
  };
}

export default defineConfig({
  plugins: [preact(), copyPublicFiles()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        content: resolve(__dirname, 'src/content/index.tsx'),
        background: resolve(__dirname, 'src/background/index.ts'),
      },
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: '[name].js',
        assetFileNames: '[name].[ext]',
      },
    },
    sourcemap: process.env.NODE_ENV === 'development',
  },
  resolve: {
    alias: {
      react: 'preact/compat',
      'react-dom': 'preact/compat',
    },
  },
});
