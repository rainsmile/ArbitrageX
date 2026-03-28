import { describe, it, expect } from 'vitest';
import { formatCurrency, formatPercent } from '@/lib/utils';

describe('Utility Functions', () => {
  it('formats currency correctly', () => {
    expect(formatCurrency(1234.56)).toContain('1,234');
  });

  it('formats percent correctly', () => {
    const result = formatPercent(12.34);
    expect(result).toContain('12.34');
  });
});
