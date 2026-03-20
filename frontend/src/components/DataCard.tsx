import React from 'react';

interface DataCardProps {
    title: string;
    value: string | number;
    icon?: React.ElementType;
    className?: string;
    trend?: string;
    trendUp?: boolean;
}

export function DataCard({
    title,
    value,
    icon: Icon,
    className = '',
    trend,
    trendUp,
}: DataCardProps) {
    return (
        <div className={`bg-slate-800/40 border border-slate-700/60 rounded-sm p-6 transition-all duration-200 hover:border-slate-500 ${className}`}>
            <div className="flex items-start justify-between">
                <div>
                    <p className="text-slate-500 text-xs uppercase tracking-wider font-mono mb-2">{title}</p>
                    <p className="text-3xl font-bold font-mono text-slate-100">{value}</p>
                    {trend && (
                        <p className={`text-xs font-mono mt-1 ${trendUp ? 'text-green-400' : 'text-red-400'}`}>
                            {trendUp ? '▲' : '▼'} {trend}
                        </p>
                    )}
                </div>
                {Icon && (
                    <div className="text-blue-400">
                        <Icon size={28} weight="duotone" />
                    </div>
                )}
            </div>
        </div>
    );
}
