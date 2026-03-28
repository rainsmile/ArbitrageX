'use client';
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

interface RealtimeValueProps {
  value: number;
  format?: (val: number) => string;
  className?: string;
  highlightDuration?: number;
}

export function RealtimeValue({ value, format, className, highlightDuration = 1000 }: RealtimeValueProps) {
  const prevRef = useRef(value);
  const [highlight, setHighlight] = useState<'up' | 'down' | null>(null);

  useEffect(() => {
    if (value !== prevRef.current) {
      setHighlight(value > prevRef.current ? 'up' : 'down');
      prevRef.current = value;
      const timer = setTimeout(() => setHighlight(null), highlightDuration);
      return () => clearTimeout(timer);
    }
  }, [value, highlightDuration]);

  const formatted = format ? format(value) : value.toLocaleString();

  return (
    <span className={cn(
      'font-mono transition-colors duration-300',
      highlight === 'up' && 'text-emerald-400',
      highlight === 'down' && 'text-red-400',
      !highlight && 'text-gray-200',
      className,
    )}>
      {formatted}
    </span>
  );
}
