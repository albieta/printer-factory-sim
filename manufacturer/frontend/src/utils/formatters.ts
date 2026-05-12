const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

export const formatCurrency = (value: number) => currencyFormatter.format(Number(value) || 0);

export const formatNumber = (value: number, digits = 0) =>
  Number(value || 0).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export const formatTimestamp = (value?: string | null) => {
  if (!value) {
    return '-';
  }

  return new Date(value).toLocaleString();
};

export const formatEventType = (eventType: string) =>
  eventType
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export const describeEventDetails = (details?: Record<string, unknown>) => {
  if (!details) {
    return 'No additional details recorded.';
  }

  const reference = typeof details.reference_code === 'string' ? details.reference_code : null;
  const product = typeof details.product_name === 'string' ? details.product_name : null;
  const quantity = typeof details.quantity === 'number' ? details.quantity : null;
  const reason = typeof details.reason === 'string' ? details.reason : null;
  const totalCost = typeof details.total_cost === 'number' ? details.total_cost : null;

  const parts = [
    reference,
    product,
    quantity !== null ? `qty ${quantity}` : null,
    totalCost !== null ? formatCurrency(totalCost) : null,
    reason,
  ].filter(Boolean);

  return parts.length ? parts.join(' • ') : JSON.stringify(details);
};
