// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
// Minimal wrappers around Intl for locale-aware formatting
export const formatDate = (date: Date, locale: string, options?: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat(locale, options).format(date);

export const formatCurrency = (amount: number, locale: string, currency = 'USD') =>
  new Intl.NumberFormat(locale, { style: 'currency', currency }).format(amount);

export const formatCompactNumber = (value: number, locale: string) =>
  new Intl.NumberFormat(locale, { notation: 'compact' }).format(value);
