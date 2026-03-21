// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
export const truncateNumber = (value: number, fractionDigits = 4): number => {
  if (!Number.isFinite(value)) return 0;
  if (fractionDigits <= 0) return Math.trunc(value);
  const factor = 10 ** fractionDigits;
  return Math.trunc(value * factor) / factor;
};

export const formatNumber = (value: number, maxFractionDigits = 4): string => {
  const truncated = truncateNumber(value, maxFractionDigits);
  return truncated.toFixed(maxFractionDigits).replace(/\.?0+$/, "");
};

export const formatMs = (value: number, maxFractionDigits = 4): string => {
  return `${formatNumber(value, maxFractionDigits)}ms`;
};

export const formatDuration = (ms?: number): string => {
  if (!ms) return "-";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60000);
  const seconds = Math.floor((ms % 60000) / 1000);
  return `${minutes}m ${seconds}s`;
};

