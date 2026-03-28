import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';

interface StatItem {
  label: string;
  value: string | number;
  change?: number; // percentage change
  icon?: LucideIcon;
  color?: string;
}

interface StatGridProps {
  stats: StatItem[];
  columns?: 2 | 3 | 4 | 5 | 6;
  className?: string;
}

export function StatGrid({ stats, columns = 4, className }: StatGridProps) {
  const colClass = {
    2: 'grid-cols-2',
    3: 'grid-cols-1 sm:grid-cols-3',
    4: 'grid-cols-2 lg:grid-cols-4',
    5: 'grid-cols-2 lg:grid-cols-5',
    6: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-6',
  }[columns];

  return (
    <div className={cn('grid gap-4', colClass, className)}>
      {stats.map((stat, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-gray-400">{stat.label}</span>
            {stat.icon && <stat.icon className={cn('w-4 h-4', stat.color || 'text-gray-500')} />}
          </div>
          <div className="text-xl font-bold text-white font-mono">{typeof stat.value === 'number' ? stat.value.toLocaleString() : stat.value}</div>
          {stat.change !== undefined && (
            <div className={cn('text-xs mt-1 font-mono', stat.change >= 0 ? 'text-emerald-400' : 'text-red-400')}>
              {stat.change >= 0 ? '↑' : '↓'} {Math.abs(stat.change).toFixed(1)}%
            </div>
          )}
        </motion.div>
      ))}
    </div>
  );
}
