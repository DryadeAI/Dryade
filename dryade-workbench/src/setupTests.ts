// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import '@testing-library/jest-dom';
import { beforeAll, afterEach, afterAll } from 'vitest';
import { server } from './mocks/server';

// Polyfill localStorage for jsdom
class LocalStorageMock implements Storage {
  private store: Record<string, string> = {};

  get length(): number {
    return Object.keys(this.store).length;
  }

  key(index: number): string | null {
    const keys = Object.keys(this.store);
    return keys[index] ?? null;
  }

  getItem(key: string): string | null {
    return this.store[key] || null;
  }

  setItem(key: string, value: string): void {
    this.store[key] = value;
  }

  removeItem(key: string): void {
    delete this.store[key];
  }

  clear(): void {
    this.store = {};
  }
}

global.localStorage = new LocalStorageMock();

// Polyfill scrollIntoView for jsdom (not implemented)
Element.prototype.scrollIntoView = function () {
  // No-op in test environment
};

// Polyfill ResizeObserver for jsdom (not implemented)
global.ResizeObserver = class ResizeObserver {
  observe() {
    // No-op in test environment
  }
  unobserve() {
    // No-op in test environment
  }
  disconnect() {
    // No-op in test environment
  }
};

// Start MSW server before all tests
beforeAll(() => {
  server.listen({ onUnhandledRequest: 'error' });
});

// Reset handlers after each test
afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});

// Clean up after all tests
afterAll(() => {
  server.close();
});
