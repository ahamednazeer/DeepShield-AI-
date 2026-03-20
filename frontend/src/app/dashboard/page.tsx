'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
    Bell,
    ChartPie,
    ClockCounterClockwise,
    Gauge,
    Pulse,
    ShieldCheck,
    ShieldWarning,
    Warning,
} from '@phosphor-icons/react';

import { DataCard } from '@/components/DataCard';
import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

interface DashboardStats {
    total_content: number;
    total_media_analyses: number;
    total_text_analyses: number;
    total_link_analyses: number;
    deepfake_count: number;
    authentic_count: number;
    suspicious_count: number;
    flagged_content: number;
    pending_review: number;
    unread_notifications: number;
    avg_confidence: number;
    content_type_distribution: Record<string, number>;
    verdict_distribution: Record<string, number>;
    recent_items: any[];
}

export default function DashboardPage() {
    const router = useRouter();
    const [stats, setStats] = useState<DashboardStats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchData() {
            try {
                const data = await api.getDashboardStats();
                setStats(data);
            } catch (error) {
                console.error('Failed to fetch dashboard stats:', error);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, []);

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">
                    Loading Dashboard...
                </p>
            </div>
        );
    }

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

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                    <Gauge size={28} weight="duotone" className="text-blue-400" />
                    Trust Dashboard
                </h1>
                <p className="text-slate-500 mt-1 font-mono text-sm">Unified monitoring across media, text, moderation, and alerts</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                <DataCard title="Total Content" value={stats?.total_content || 0} icon={ShieldCheck} />
                <DataCard title="Media Analyses" value={stats?.total_media_analyses || 0} icon={ChartPie} />
                <DataCard title="Text Analyses" value={stats?.total_text_analyses || 0} icon={ClockCounterClockwise} />
                <DataCard title="Link Scans" value={stats?.total_link_analyses || 0} icon={ClockCounterClockwise} />
                <DataCard title="High-Risk Items" value={stats?.deepfake_count || 0} icon={ShieldWarning} className="border-red-800/50" />
                <DataCard title="Flagged Content" value={stats?.flagged_content || 0} icon={Warning} className="border-amber-800/50" />
                <DataCard title="Review Queue" value={stats?.pending_review || 0} icon={Warning} className="border-orange-800/50" />
                <DataCard title="Unread Alerts" value={stats?.unread_notifications || 0} icon={Bell} className="border-blue-800/50" />
                <DataCard title="Authentic / Real" value={stats?.authentic_count || 0} icon={ShieldCheck} className="border-green-800/50" />
                <DataCard title="Avg Confidence" value={`${stats?.avg_confidence || 0}%`} icon={Gauge} />
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5">Content Type Distribution</h3>
                    <div className="space-y-3">
                        {Object.entries(stats?.content_type_distribution || {}).map(([type, count]) => (
                            <div key={type} className="flex items-center justify-between rounded-sm border border-slate-800 bg-slate-900/50 px-4 py-3">
                                <span className="text-slate-300 font-mono uppercase tracking-wider text-sm">{type}</span>
                                <span className="text-slate-100 font-bold font-mono">{count}</span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5">Verdict Distribution</h3>
                    <div className="flex flex-wrap gap-3">
                        {Object.entries(stats?.verdict_distribution || {}).map(([verdict, count]) => (
                            <div key={verdict} className="rounded-sm border border-slate-800 bg-slate-900/50 px-4 py-3">
                                <StatusBadge status={verdict} />
                                <p className="mt-2 text-lg font-bold font-mono text-slate-100">{count}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                <div className="flex items-center justify-between mb-5">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest">Recent Content</h3>
                    <button onClick={() => router.push('/dashboard/history')} className="btn-secondary">
                        Open History
                    </button>
                </div>
                {stats?.recent_items?.length ? (
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead className="bg-slate-900/50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Type</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Title</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Verdict</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Review</th>
                                    <th className="px-4 py-3 text-left text-xs font-mono text-slate-500 uppercase tracking-wider">Date</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-700/50">
                                {stats.recent_items.map((item) => (
                                    <tr
                                        key={item.id}
                                        onClick={() => openItem(item)}
                                        className="cursor-pointer hover:bg-slate-800/50 transition-colors"
                                    >
                                        <td className="px-4 py-4"><StatusBadge status={item.kind || item.content_type} /></td>
                                        <td className="px-4 py-4 text-sm text-slate-300 font-mono">{item.title}</td>
                                        <td className="px-4 py-4"><StatusBadge status={item.effective_verdict || item.verdict || 'UNKNOWN'} /></td>
                                        <td className="px-4 py-4"><StatusBadge status={item.moderation?.review_status || 'clear'} /></td>
                                        <td className="px-4 py-4 text-xs text-slate-500 font-mono">{new Date(item.created_at).toLocaleString()}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                ) : (
                    <p className="text-slate-500 font-mono text-sm">No content analyzed yet.</p>
                )}
            </div>
        </div>
    );
}
