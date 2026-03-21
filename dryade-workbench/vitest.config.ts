import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react-swc';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'happy-dom',
    setupFiles: ['./src/setupTests.ts', './src/__tests__/setup.ts'],
    globals: true,
    css: true,
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: [
      'node_modules/**',
      'e2e/**',
      // ChatPage/chat tests cause worker OOM/hang in happy-dom (known MSW+happy-dom issue).
      // Tests pass but worker won't exit cleanly. Run via Playwright E2E instead.
      'src/__tests__/components/ChatPage.test.tsx',
      'src/__tests__/chat.test.tsx',
    ],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'node_modules/',
        'src/setupTests.ts',
        'src/__tests__/**',
        'src/**/*.d.ts',
      ],
      thresholds: {
        lines: 15,
        statements: 15,
        functions: 15,
        branches: 10,
      },
    },
  },
});
