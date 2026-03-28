import { cn } from '@/lib/utils';
import { Wifi, WifiOff } from 'lucide-react';

interface ConnectionIndicatorProps {
  connected: boolean;
  label?: string;
  showIcon?: boolean;
  size?: 'sm' | 'md';
}

export function ConnectionIndicator({ connected, label, showIcon = true, size = 'sm' }: ConnectionIndicatorProps) {
  return (
    <div className={cn('inline-flex items-center gap-1.5', size === 'sm' ? 'text-xs' : 'text-sm')}>
      {showIcon ? (
        connected ? <Wifi className={cn(size === 'sm' ? 'w-3 h-3' : 'w-4 h-4', 'text-emerald-400')} /> : <WifiOff className={cn(size === 'sm' ? 'w-3 h-3' : 'w-4 h-4', 'text-red-400')} />
      ) : (
        <span className={cn('w-2 h-2 rounded-full', connected ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : 'bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.5)]')} />
      )}
      {label && <span className={connected ? 'text-gray-300' : 'text-gray-500'}>{label}</span>}
    </div>
  );
}
