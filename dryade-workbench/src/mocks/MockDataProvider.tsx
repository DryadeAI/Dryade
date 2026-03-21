// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Mock Data Provider - context for toggling mock mode
// To remove: delete this file, remove <MockDataProvider> from App.tsx

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { enableMocks, disableMocks } from './mockInterceptor';

const STORAGE_KEY = 'dryade-mock-mode';

interface MockDataContextValue {
  mockEnabled: boolean;
  toggleMock: () => void;
}

const MockDataContext = createContext<MockDataContextValue>({
  mockEnabled: false,
  toggleMock: () => {},
});

export const useMockData = () => useContext(MockDataContext);

export const MockDataProvider = ({ children }: { children: ReactNode }) => {
  const [mockEnabled] = useState(() => localStorage.getItem(STORAGE_KEY) === 'true');

  useEffect(() => {
    if (mockEnabled) {
      enableMocks();
    }
    return () => {
      if (mockEnabled) disableMocks();
    };
  }, [mockEnabled]);

  const toggleMock = () => {
    const next = !mockEnabled;
    localStorage.setItem(STORAGE_KEY, String(next));
    window.location.reload();
  };

  return (
    <MockDataContext.Provider value={{ mockEnabled, toggleMock }}>
      {children}
    </MockDataContext.Provider>
  );
};
