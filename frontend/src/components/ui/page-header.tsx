'use client';
import { motion } from 'framer-motion';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  updatedAt?: number; // unix timestamp
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, updatedAt, actions }: PageHeaderProps) {
  return (
    <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between mb-6">
      <div>
        <h1 className="text-2xl font-bold text-white">{title}</h1>
        {subtitle && <p className="text-sm text-gray-400 mt-1">{subtitle}</p>}
        {updatedAt && <p className="text-xs text-gray-500 mt-0.5">更新于 {new Date(updatedAt * 1000).toLocaleTimeString('zh-CN')}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </motion.div>
  );
}
