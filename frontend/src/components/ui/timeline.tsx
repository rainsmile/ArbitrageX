import { cn } from '@/lib/utils';
import { Check, X, Clock, Loader2 } from 'lucide-react';

interface TimelineItem {
  label: string;
  description?: string;
  timestamp?: string;
  status: 'completed' | 'active' | 'pending' | 'failed';
  details?: Record<string, any>;
}

interface TimelineProps {
  items: TimelineItem[];
  className?: string;
}

const statusIcon = {
  completed: <Check className="w-3.5 h-3.5 text-emerald-400" />,
  active: <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />,
  pending: <Clock className="w-3.5 h-3.5 text-gray-500" />,
  failed: <X className="w-3.5 h-3.5 text-red-400" />,
};

const statusDot = {
  completed: 'border-emerald-500/50 bg-emerald-500/20',
  active: 'border-blue-500/50 bg-blue-500/20',
  pending: 'border-gray-600 bg-gray-700/50',
  failed: 'border-red-500/50 bg-red-500/20',
};

const statusLine = {
  completed: 'bg-emerald-500/30',
  active: 'bg-blue-500/30',
  pending: 'bg-gray-700',
  failed: 'bg-red-500/30',
};

export function Timeline({ items, className }: TimelineProps) {
  return (
    <div className={cn('space-y-0', className)}>
      {items.map((item, i) => (
        <div key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className={cn('w-7 h-7 rounded-full border-2 flex items-center justify-center', statusDot[item.status])}>
              {statusIcon[item.status]}
            </div>
            {i < items.length - 1 && <div className={cn('w-0.5 flex-1 min-h-[24px]', statusLine[items[i + 1]?.status || 'pending'])} />}
          </div>
          <div className="pb-6 flex-1 min-w-0">
            <div className="flex items-baseline justify-between gap-2">
              <span className={cn('text-sm font-medium', item.status === 'pending' ? 'text-gray-500' : item.status === 'failed' ? 'text-red-400' : 'text-gray-200')}>
                {item.label}
              </span>
              {item.timestamp && <span className="text-xs text-gray-500 font-mono shrink-0">{item.timestamp}</span>}
            </div>
            {item.description && <p className="text-xs text-gray-400 mt-0.5">{item.description}</p>}
            {item.details && Object.keys(item.details).length > 0 && (
              <div className="mt-2 text-xs text-gray-500 bg-white/[0.02] rounded-lg p-2 font-mono space-y-0.5">
                {Object.entries(item.details).map(([k, v]) => (
                  <div key={k}><span className="text-gray-400">{k}:</span> <span className="text-gray-300">{String(v)}</span></div>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
