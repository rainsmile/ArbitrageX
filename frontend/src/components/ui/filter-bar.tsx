'use client';
import { cn } from '@/lib/utils';
import { Search, Filter, X } from 'lucide-react';

interface FilterOption {
  label: string;
  value: string;
}

interface FilterBarProps {
  searchValue?: string;
  onSearchChange?: (val: string) => void;
  searchPlaceholder?: string;
  filters?: {
    key: string;
    label: string;
    options: FilterOption[];
    value: string;
    onChange: (val: string) => void;
  }[];
  actions?: React.ReactNode;
  className?: string;
}

export function FilterBar({ searchValue, onSearchChange, searchPlaceholder = '搜索...', filters, actions, className }: FilterBarProps) {
  return (
    <div className={cn('flex flex-wrap items-center gap-3 mb-4', className)}>
      {onSearchChange && (
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            value={searchValue || ''}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full pl-9 pr-8 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20"
          />
          {searchValue && (
            <button onClick={() => onSearchChange('')} className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-white/[0.06] rounded">
              <X className="w-3.5 h-3.5 text-gray-500" />
            </button>
          )}
        </div>
      )}
      {filters?.map((f) => (
        <select
          key={f.key}
          value={f.value}
          onChange={(e) => f.onChange(e.target.value)}
          className="px-3 py-2 bg-white/[0.04] border border-white/[0.08] rounded-lg text-sm text-gray-300 focus:outline-none focus:border-blue-500/50 appearance-none cursor-pointer"
        >
          <option value="">{f.label}</option>
          {f.options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ))}
      {actions && <div className="flex items-center gap-2 ml-auto">{actions}</div>}
    </div>
  );
}
