import { cn } from '@/lib/utils';
import { AlertTriangle, Info, AlertOctagon } from 'lucide-react';

const severityMap = {
  CRITICAL: { color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20', icon: AlertOctagon, label: '严重' },
  WARNING: { color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20', icon: AlertTriangle, label: '警告' },
  INFO: { color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20', icon: Info, label: '信息' },
};

interface SeverityBadgeProps {
  severity: 'CRITICAL' | 'WARNING' | 'INFO' | string;
  showIcon?: boolean;
  className?: string;
}

export function SeverityBadge({ severity, showIcon = true, className }: SeverityBadgeProps) {
  const cfg = severityMap[severity as keyof typeof severityMap] || severityMap.INFO;
  const Icon = cfg.icon;
  return (
    <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border', cfg.bg, cfg.color, className)}>
      {showIcon && <Icon className="w-3 h-3" />}
      {cfg.label}
    </span>
  );
}
