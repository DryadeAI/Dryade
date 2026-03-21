// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

// Setup MSW server with handlers
export const server = setupServer(...handlers);
