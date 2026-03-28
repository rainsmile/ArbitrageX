import { cn } from '@/lib/utils';

const statusConfig: Record<string, { color: string; bg: string; label: string }> = {
  COMPLETED: { color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: '已完成' },
  FILLED: { color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: '已成交' },
  EXECUTING: { color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20', label: '执行中' },
  READY: { color: 'text-cyan-400', bg: 'bg-cyan-500/10 border-cyan-500/20', label: '就绪' },
  RISK_CHECKING: { color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20', label: '风控检查' },
  CREATED: { color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/20', label: '已创建' },
  FAILED: { color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20', label: '失败' },
  HEDGING: { color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/20', label: '对冲中' },
  REJECTED: { color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20', label: '已拒绝' },
  DETECTED: { color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20', label: '已发现' },
  EXPIRED: { color: 'text-gray-500', bg: 'bg-gray-600/10 border-gray-600/20', label: '已过期' },
  PENDING: { color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/20', label: '等待中' },
  SUBMITTED: { color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20', label: '已提交' },
  PARTIAL_FILLED: { color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20', label: '部分成交' },
  PAPER: { color: 'text-violet-400', bg: 'bg-violet-500/10 border-violet-500/20', label: '模拟' },
  LIVE: { color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20', label: '实盘' },
};

interface StatusBadgeProps {
  status: string;
  className?: string;
  pulse?: boolean;
}

export function StatusBadge({ status, className, pulse }: StatusBadgeProps) {
  const cfg = statusConfig[status] || { color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-500/20', label: status };
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border', cfg.bg, cfg.color, className)}>
      {pulse && <span className={cn('w-1.5 h-1.5 rounded-full animate-pulse', cfg.color.replace('text-', 'bg-'))} />}
      {cfg.label}
    </span>
  );
}
