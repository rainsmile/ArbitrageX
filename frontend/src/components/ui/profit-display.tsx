import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface ProfitDisplayProps {
  value: number;
  format?: 'currency' | 'percent';
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  className?: string;
}

export function ProfitDisplay({ value, format = 'currency', size = 'md', showIcon = false, className }: ProfitDisplayProps) {
  const isPositive = value > 0;
  const isZero = Math.abs(value) < 0.001;
  const color = isZero ? 'text-gray-400' : isPositive ? 'text-emerald-400' : 'text-red-400';
  const Icon = isZero ? Minus : isPositive ? TrendingUp : TrendingDown;
  const sizeClass = size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-lg font-bold' : 'text-sm font-medium';

  const formatted = format === 'percent'
    ? `${isPositive ? '+' : ''}${value.toFixed(2)}%`
    : `${isPositive ? '+' : ''}$${Math.abs(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
    <span className={cn('inline-flex items-center gap-1 font-mono', color, sizeClass, className)}>
      {showIcon && <Icon className={cn(size === 'sm' ? 'w-3 h-3' : size === 'lg' ? 'w-5 h-5' : 'w-4 h-4')} />}
      {formatted}
    </span>
  );
}
