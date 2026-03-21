// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { useState, useCallback, useRef, useEffect } from "react";
import { sandboxApi } from "@/services/api";
import type { CodeExecuteResponse, CodeExecutionStatus } from "@/types/extended-api";

interface UseCodeExecutionReturn {
  execute: (code: string, language: "python" | "bash" | "sh") => Promise<void>;
  result: CodeExecuteResponse | null;
  status: CodeExecutionStatus;
  error: string | null;
  reset: () => void;
}

export function useCodeExecution(): UseCodeExecutionReturn {
  const [status, setStatus] = useState<CodeExecutionStatus>("idle");
  const [result, setResult] = useState<CodeExecuteResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const execute = useCallback(
    async (code: string, language: "python" | "bash" | "sh") => {
      setStatus("running");
      setResult(null);
      setError(null);

      try {
        const response = await sandboxApi.execute({
          code,
          language,
          timeout_seconds: 30,
        });

        if (!mountedRef.current) return;
        setResult(response);
        setStatus("complete");
      } catch (err) {
        if (!mountedRef.current) return;
        const message =
          err instanceof Error ? err.message : "Code execution failed";
        setError(message);
        setStatus("error");
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setStatus("idle");
    setResult(null);
    setError(null);
  }, []);

  return { execute, result, status, error, reset };
}
