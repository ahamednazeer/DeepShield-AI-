'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ClockCounterClockwise, MagnifyingGlass, Pulse } from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function TextHistoryPage() {
    const router = useRouter();
    const [items, setItems] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchHistory() {
            try {
                const data = await api.getTextHistory();
                setItems(data.analyses || []);
            } catch (error) {
                console.error('Failed to fetch text history:', error);
            } finally {
                setLoading(false);
            }
        }
        fetchHistory();
    }, []);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-cyan-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-cyan-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">
                    Loading Text History...
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                    <ClockCounterClockwise size={28} weight="duotone" className="text-cyan-400" />
                    Text History
                </h1>
                <p className="text-slate-500 mt-1 font-mono text-sm">{items.length} stored text analyses</p>
            </div>

            {items.length > 0 ? (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-900/50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Verdict</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Excerpt</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Review</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Created</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700/50">
                                {items.map((item) => (
                                    <tr
                                        key={item.id}
                                        onClick={() => router.push(`/dashboard/text-history/${item.id}`)}
                                        className="cursor-pointer hover:bg-slate-800/50 transition-colors"
                                    >
                                        <td className="px-4 py-4"><StatusBadge status={item.effective_verdict || item.verdict || 'UNKNOWN'} /></td>
                                        <td className="px-4 py-4 text-sm text-slate-300 max-w-[460px] truncate">
                                            {item.input_text}
                                        </td>
                                        <td className="px-4 py-4"><StatusBadge status={item.moderation?.review_status || 'clear'} /></td>
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
                    <p className="text-slate-500 font-mono text-sm">No text analyses recorded yet.</p>
                </div>
            )}
        </div>
    );
}
