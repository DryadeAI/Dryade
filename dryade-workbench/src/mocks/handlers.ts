// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { http, HttpResponse } from 'msw';

export const handlers = [
  // Health check endpoint for initial smoke test
  http.get('/api/health', () => {
    return HttpResponse.json({
      status: 'ok',
      timestamp: new Date().toISOString(),
    });
  }),
];
