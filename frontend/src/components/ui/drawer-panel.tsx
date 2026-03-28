'use client';
import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DrawerPanelProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  width?: 'md' | 'lg' | 'xl';
  children: React.ReactNode;
}

const widthMap = { md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl' };

export function DrawerPanel({ open, onClose, title, subtitle, width = 'lg', children }: DrawerPanelProps) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    if (open) document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40"
            onClick={onClose}
          />
          <motion.div
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn('fixed right-0 top-0 h-full w-full bg-[#0d1220] border-l border-white/[0.08] z-50 flex flex-col shadow-2xl', widthMap[width])}
          >
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.06]">
              <div>
                <h2 className="text-lg font-semibold text-white">{title}</h2>
                {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
              </div>
              <button onClick={onClose} className="p-2 rounded-lg hover:bg-white/[0.06] text-gray-400 hover:text-white transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6">{children}</div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
