import React from 'react';

interface StatusBadgeProps {
    status: string;
    className?: string;
}

const statusStyles: Record<string, string> = {
    AUTHENTIC: 'text-green-400 bg-green-950/50 border-green-800',
    MANIPULATED: 'text-red-400 bg-red-950/50 border-red-800',
    SUSPICIOUS: 'text-yellow-400 bg-yellow-950/50 border-yellow-800',
    REAL: 'text-green-400 bg-green-950/50 border-green-800',
    LIKELY_REAL: 'text-emerald-400 bg-emerald-950/50 border-emerald-800',
    SAFE: 'text-green-400 bg-green-950/50 border-green-800',
    LEGITIMATE: 'text-green-400 bg-green-950/50 border-green-800',
    FAKE: 'text-red-400 bg-red-950/50 border-red-800',
    LIKELY_FAKE: 'text-orange-400 bg-orange-950/50 border-orange-800',
    MISLEADING: 'text-amber-400 bg-amber-950/50 border-amber-800',
    UNSAFE: 'text-red-400 bg-red-950/50 border-red-800',
    MALICIOUS: 'text-red-400 bg-red-950/50 border-red-800',
    PHISHING: 'text-red-400 bg-red-950/50 border-red-800',
    SPAM: 'text-amber-400 bg-amber-950/50 border-amber-800',
    RISKY: 'text-yellow-400 bg-yellow-950/50 border-yellow-800',
    UNCERTAIN: 'text-yellow-400 bg-yellow-950/50 border-yellow-800',
    admin: 'text-red-300 bg-red-950/40 border-red-800',
    analyst: 'text-blue-300 bg-blue-950/40 border-blue-800',
    active: 'text-green-400 bg-green-950/50 border-green-800',
    suspended: 'text-red-400 bg-red-950/50 border-red-800',
    pending_review: 'text-orange-400 bg-orange-950/50 border-orange-800',
    reviewed: 'text-green-400 bg-green-950/50 border-green-800',
    clear: 'text-slate-400 bg-slate-950/50 border-slate-800',
    UNKNOWN: 'text-slate-400 bg-slate-950/50 border-slate-800',
    completed: 'text-green-400 bg-green-950/50 border-green-800',
    processing: 'text-blue-400 bg-blue-950/50 border-blue-800',
    pending: 'text-slate-400 bg-slate-950/50 border-slate-800',
    failed: 'text-red-400 bg-red-950/50 border-red-800',
    disabled: 'text-slate-400 bg-slate-950/50 border-slate-800',
    skipped: 'text-slate-400 bg-slate-950/50 border-slate-800',
    unknown: 'text-slate-400 bg-slate-950/50 border-slate-800',
    image: 'text-purple-400 bg-purple-950/50 border-purple-800',
    video: 'text-cyan-400 bg-cyan-950/50 border-cyan-800',
    text: 'text-cyan-400 bg-cyan-950/50 border-cyan-800',
    link: 'text-sky-400 bg-sky-950/50 border-sky-800',
    info: 'text-blue-400 bg-blue-950/50 border-blue-800',
    warning: 'text-yellow-400 bg-yellow-950/50 border-yellow-800',
    critical: 'text-red-400 bg-red-950/50 border-red-800',
    high: 'text-red-400 bg-red-950/50 border-red-800',
    medium: 'text-yellow-400 bg-yellow-950/50 border-yellow-800',
    low: 'text-green-400 bg-green-950/50 border-green-800',
    recommended: 'text-emerald-300 bg-emerald-950/40 border-emerald-800',
    experimental: 'text-fuchsia-300 bg-fuchsia-950/40 border-fuchsia-800',
    unavailable: 'text-slate-400 bg-slate-950/50 border-slate-800',
    flagged: 'text-orange-400 bg-orange-950/50 border-orange-800',
    quarantined: 'text-red-400 bg-red-950/50 border-red-800',
};

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
    const style = statusStyles[status] || 'text-slate-400 bg-slate-950/50 border-slate-800';

    return (
        <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider border ${style} ${className}`}
        >
            {status.replace('_', ' ')}
        </span>
    );
}
