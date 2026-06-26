import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import electron from 'vite-plugin-electron';
import renderer from 'vite-plugin-electron-renderer';
import monacoEditorPlugin from 'vite-plugin-monaco-editor';
import path from 'path';

export default defineConfig({
  plugins: [
    react(),
    monacoEditorPlugin({
      languageWorkers: ['editorWorkerService'],
      customDistPath: (_root, _outDir, base) =>
        path.resolve(__dirname, 'dist/renderer', base || '', 'monacoeditorwork'),
    }),
    electron([
      {
        entry: 'src/main/index.ts',
        vite: {
          root: '.',
          build: {
            outDir: 'dist/main',
            rollupOptions: {
              external: ['electron'],
            },
          },
        },
      },
      {
        entry: 'src/main/preload.ts',
        vite: {
          root: '.',
          build: {
            outDir: 'dist/main',
          },
        },
      },
    ]),
    renderer(),
  ],
  root: 'src/renderer',
  base: './',
  optimizeDeps: {
    include: ['monaco-editor'],
  },
  build: {
    outDir: path.resolve(__dirname, 'dist/renderer'),
    emptyOutDir: false,
    rollupOptions: {
      output: {
        manualChunks: {
          monaco: ['monaco-editor'],
        },
      },
    },
  },
});
