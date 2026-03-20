'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
    ClockCounterClockwise,
    Funnel,
    MagnifyingGlass,
    Pulse,
} from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function HistoryPage() {
    const router = useRouter();
    const [items, setItems] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');

    useEffect(() => {
        async function fetchHistory() {
            try {
                const data = await api.getUnifiedHistory();
                setItems(data.items || []);
            } catch (error) {
                console.error('Failed to fetch unified history:', error);
            } finally {
                setLoading(false);
            }
        }
        fetchHistory();
    }, []);

    const filteredItems = items.filter((item) => {
        if (filter === 'all') return true;
        if (filter === 'media') return item.content_type === 'media';
        if (filter === 'text') return item.content_type === 'text';
        if (filter === 'link') return item.content_type === 'link';
        if (filter === 'flagged') return item.moderation?.is_flagged;
        if (filter === 'review') return item.moderation?.review_status === 'pending_review';
        return true;
    });

    const openItem = (item: any) => {
        if (item.content_type === 'text') {
            router.push(`/dashboard/text-history/${item.content_id}`);
            return;
        }
        if (item.content_type === 'link') {
            router.push(`/dashboard/link-analysis/${item.content_id}`);
            return;
        }
        router.push(`/dashboard/analysis/${item.content_id}`);
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">
                    Loading Unified History...
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                        <ClockCounterClockwise size={28} weight="duotone" className="text-blue-400" />
                        Unified History
                    </h1>
                    <p className="text-slate-500 mt-1 font-mono text-sm">{items.length} total records</p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <Funnel size={16} className="text-slate-500" />
                    {['all', 'media', 'text', 'link', 'flagged', 'review'].map((value) => (
                        <button
                            key={value}
                            onClick={() => setFilter(value)}
                            className={`px-3 py-1.5 text-xs font-mono uppercase tracking-wider rounded-sm transition-all ${filter === value ? 'bg-blue-600 text-white' : 'bg-slate-800/50 text-slate-400 hover:text-slate-200 hover:bg-slate-700'}`}
                        >
                            {value}
                        </button>
                    ))}
                </div>
            </div>

            {filteredItems.length > 0 ? (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-900/50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Kind</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Title</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Verdict</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Review</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Permissions</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Date</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700/50">
                                {filteredItems.map((item) => (
                                    <tr
                                        key={item.id}
                                        onClick={() => openItem(item)}
                                        className="hover:bg-slate-800/50 transition-colors cursor-pointer"
                                    >
                                        <td className="px-4 py-4"><StatusBadge status={item.kind || item.content_type} /></td>
                                        <td className="px-4 py-4 text-sm text-slate-300 font-mono max-w-[320px] truncate">{item.title}</td>
                                        <td className="px-4 py-4"><StatusBadge status={item.effective_verdict || item.verdict || 'UNKNOWN'} /></td>
                                        <td className="px-4 py-4">
                                            <div className="flex gap-2 flex-wrap">
                                                <StatusBadge status={item.moderation?.review_status || 'clear'} />
                                                {item.moderation?.is_flagged && <StatusBadge status="flagged" />}
                                                {item.moderation?.is_quarantined && <StatusBadge status="quarantined" />}
                                            </div>
                                        </td>
                                        <td className="px-4 py-4 text-xs font-mono text-slate-400">
                                            {item.permissions?.can_download ? 'download on' : 'download off'}
                                            <br />
                                            {item.permissions?.can_share ? 'share on' : 'share off'}
                                        </td>
                                        <td className="px-4 py-4 text-xs font-mono text-slate-500">{new Date(item.created_at).toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            ) : (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm text-center py-16">
                    <MagnifyingGlass size={48} weight="duotone" className="text-slate-700 mx-auto mb-4" />
                    <p className="text-slate-500 font-mono text-sm">No records found for the selected filter.</p>
                </div>
            )}
        </div>
    );
}
