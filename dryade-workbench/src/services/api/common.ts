// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Common API types and utilities shared across domain modules

import { fetchWithAuth } from '../apiClient';
import type { AgentStreamChunk } from '@/types/streaming';

// Error types for API responses
export interface ApiError {
  detail: string;
  status: number;
}

// Helper to extract error message from various error formats
export const getErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    return (error as ApiError).detail;
  }
  return 'An unknown error occurred';
};

// SSE stream chunk types for streaming chat (GAP-020)
interface StreamChunkContent {
  type: 'content';
  content: string;
  ttft?: number;      // Time to first token in milliseconds
  interval?: number;  // Interval since last chunk in milliseconds
}

interface StreamChunkToolCall {
  type: 'tool_call';
  tool_call: {
    tool: string;
    args?: Record<string, unknown>;
    result?: string;
    status?: string;
  };
}

interface StreamChunkError {
  type: 'error';
  message: string;
}

interface StreamChunkComplete {
  type: 'complete';
  total_time?: number;  // Total streaming time in milliseconds
}

export type StreamChunk = StreamChunkContent | StreamChunkToolCall | StreamChunkError | StreamChunkComplete | AgentStreamChunk;

// Enterprise license error for trainer APIs (GAP-088)
export class EnterpriseLicenseRequiredError extends Error {
  constructor(feature: string) {
    super(`Enterprise license required for ${feature}`);
    this.name = 'EnterpriseLicenseRequiredError';
  }
}

// Helper for enterprise endpoints - handles 403 as license requirement
export const fetchEnterprise = async <T>(
  endpoint: string,
  config?: RequestInit & { requiresAuth?: boolean }
): Promise<T> => {
  try {
    return await fetchWithAuth<T>(endpoint, config);
  } catch (error) {
    if (error instanceof Error && error.message.includes('403')) {
      throw new EnterpriseLicenseRequiredError(endpoint);
    }
    throw error;
  }
};
