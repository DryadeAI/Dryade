// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Additional test setup: browser API mocks not available in happy-dom
import { vi } from 'vitest';
import '@testing-library/jest-dom';
// Initialize i18n so useTranslation returns English values in tests
import '@/i18n';

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock crypto.subtle for Ed25519 verification tests
if (!window.crypto?.subtle) {
  Object.defineProperty(window, 'crypto', {
    value: {
      subtle: {},
      getRandomValues: vi.fn((arr: Uint8Array) => {
        for (let i = 0; i < arr.length; i++) arr[i] = Math.floor(Math.random() * 256);
        return arr;
      }),
    },
  });
}

// Mock IntersectionObserver
class MockIntersectionObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}
Object.defineProperty(window, 'IntersectionObserver', {
  value: MockIntersectionObserver,
});
