import { cn } from '@/lib/utils';
import { Loader2 } from 'lucide-react';

interface LoadingStateProps {
  text?: string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export function LoadingState({ text = '加载中...', className, size = 'md' }: LoadingStateProps) {
  const sizeClass = size === 'sm' ? 'w-4 h-4' : size === 'lg' ? 'w-8 h-8' : 'w-6 h-6';
  return (
    <div className={cn('flex flex-col items-center justify-center py-12 gap-3', className)}>
      <Loader2 className={cn(sizeClass, 'text-blue-400 animate-spin')} />
      <span className="text-sm text-gray-400">{text}</span>
    </div>
  );
}
