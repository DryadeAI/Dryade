/**
 * Global teardown for deep E2E tests.
 *
 * Removes the storageState file created during global setup.
 */

import fs from "node:fs";
import path from "node:path";

const STORAGE_STATE_PATH = path.join(
  __dirname,
  ".auth",
  "deep-storage-state.json",
);

export default async function globalTeardown() {
  try {
    fs.unlinkSync(STORAGE_STATE_PATH);
  } catch {
    // File may not exist — ignore
  }
}
