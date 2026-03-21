// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useCallback } from "react";
import { toast } from "sonner";

import { fetchWithAuth } from "@/services/apiClient";

export interface ImportedPlugin {
  name: string;
  version: string | null;
}

export interface ImportPluginResult {
  status: string;
  plugin: ImportedPlugin;
  message: string;
  existing_version?: string | null;
}

export interface ConflictInfo {
  pluginName: string;
  existingVersion: string | null;
  newVersion: string | null;
  blob: Blob;
  fileName: string;
}

const MAX_FILE_SIZE = 100 * 1024 * 1024; // 100MB

/**
 * Read a File into a Blob, working around sandboxed browsers (e.g. Chromium snap)
 * that block direct reads of drag-and-dropped files.
 *
 * If the initial read fails with NotFoundError, opens a file picker so the
 * user can re-select the same file with explicit browser permission.
 */
async function readFileWithFallback(file: File): Promise<Blob> {
  try {
    const buffer = await file.arrayBuffer();
    return new Blob([buffer], { type: "application/octet-stream" });
  } catch (err) {
    const isSandboxBlock =
      err instanceof DOMException && err.name === "NotFoundError";
    if (!isSandboxBlock) {
      throw new Error(
        `Cannot read file: ${err instanceof Error ? err.message : "unknown error"}`
      );
    }
  }

  // Sandbox blocked the drag-and-drop file — open a file picker as fallback.
  // The picker grants explicit per-file access via the XDG portal.
  return new Promise<Blob>((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".dryadepkg";
    input.style.display = "none";
    input.addEventListener("change", async () => {
      const picked = input.files?.[0];
      document.body.removeChild(input);
      if (!picked) {
        reject(new Error("No file selected"));
        return;
      }
      try {
        const buffer = await picked.arrayBuffer();
        resolve(new Blob([buffer], { type: "application/octet-stream" }));
      } catch (readErr) {
        reject(
          new Error(
            `Cannot read file: ${readErr instanceof Error ? readErr.message : "unknown error"}`
          )
        );
      }
    });
    input.addEventListener("cancel", () => {
      document.body.removeChild(input);
      reject(new Error("File selection cancelled"));
    });
    document.body.appendChild(input);
    input.click();
  });
}

async function doUpload(
  blob: Blob,
  fileName: string,
  force: boolean
): Promise<ImportPluginResult> {
  const formData = new FormData();
  formData.append("file", blob, fileName);
  if (force) {
    formData.append("force", "true");
  }

  return fetchWithAuth<ImportPluginResult>("/plugins/import", {
    method: "POST",
    body: formData,
  });
}

/**
 * Hook for importing .dryadepkg marketplace packages via POST /api/plugins/import.
 *
 * Returns mutation controls plus conflict state for the confirmation modal.
 */
export function usePluginImport() {
  const queryClient = useQueryClient();
  const [conflict, setConflict] = useState<ConflictInfo | null>(null);

  const mutation = useMutation<
    ImportPluginResult,
    Error,
    { blob: Blob; fileName: string; force?: boolean }
  >({
    mutationFn: ({ blob, fileName, force }) =>
      doUpload(blob, fileName, force ?? false),
    onSuccess: (data, variables) => {
      if (data.status === "conflict") {
        setConflict({
          pluginName: data.plugin.name,
          existingVersion: data.existing_version ?? null,
          newVersion: data.plugin.version,
          blob: variables.blob,
          fileName: variables.fileName,
        });
        return;
      }
      toast.success(
        `Plugin "${data.plugin.name}" v${data.plugin.version ?? "?"} imported successfully. It will be available after reload.`
      );
      void queryClient.invalidateQueries({ queryKey: ["plugins", "installed"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to import plugin");
    },
  });

  const importFile = useCallback(
    async (file: File) => {
      if (!file.name.endsWith(".dryadepkg")) {
        toast.error("File must be a .dryadepkg package");
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        toast.error("Package exceeds 100MB limit");
        return;
      }
      try {
        const blob = await readFileWithFallback(file);
        mutation.mutate({ blob, fileName: file.name });
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Failed to read file"
        );
      }
    },
    [mutation]
  );

  const confirmOverwrite = useCallback(() => {
    if (!conflict) return;
    mutation.mutate({
      blob: conflict.blob,
      fileName: conflict.fileName,
      force: true,
    });
    setConflict(null);
  }, [conflict, mutation]);

  const cancelOverwrite = useCallback(() => {
    setConflict(null);
    mutation.reset();
  }, [mutation]);

  return {
    importFile,
    isPending: mutation.isPending,
    isSuccess: mutation.isSuccess && !conflict,
    isError: mutation.isError,
    error: mutation.error,
    data: mutation.data,
    reset: mutation.reset,
    // Conflict modal state
    conflict,
    confirmOverwrite,
    cancelOverwrite,
  };
}
