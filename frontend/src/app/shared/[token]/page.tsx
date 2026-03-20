'use client';

import React, { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Pulse, ShareNetwork, ShieldCheck } from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function SharedContentPage() {
    const params = useParams();
    const token = params.token as string;
    const [payload, setPayload] = useState<any>(null);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchPayload() {
            try {
                const data = await api.getPublicShare(token);
                setPayload(data);
            } catch (err: any) {
                setError(err.message || 'Unable to load shared content');
            } finally {
                setLoading(false);
            }
        }
        fetchPayload();
    }, [token]);

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center">
                <div className="text-center space-y-4">
                    <div className="relative">
                        <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin mx-auto" />
                        <Pulse size={24} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                    </div>
                    <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Loading Shared Summary...</p>
                </div>
            </div>
        );
    }

    if (error || !payload) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center px-6">
                <div className="max-w-xl rounded-sm border border-red-800 bg-red-950/20 p-8 text-center">
                    <p className="text-red-300 font-mono">{error || 'This shared item is unavailable.'}</p>
                </div>
            </div>
        );
    }

    const content = payload.content;

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 px-6 py-10">
            <div className="mx-auto max-w-4xl space-y-8">
                <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-8">
                    <div className="flex items-center gap-4">
                        <ShieldCheck size={40} className="text-blue-400" />
                        <div>
                            <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Shared DeepShield Summary</p>
                            <h1 className="mt-2 text-3xl font-chivo font-bold uppercase tracking-wider">{content.title}</h1>
                        </div>
                    </div>
                    <div className="mt-6 flex flex-wrap gap-3">
                        <StatusBadge status={content.type} />
                        <StatusBadge status={content.verdict || 'UNKNOWN'} />
                        <StatusBadge status={content.moderation?.review_status || 'clear'} />
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-6">
                        <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Score</p>
                        <p className="mt-3 text-4xl font-bold font-mono text-slate-100">
                            {content.score != null ? `${Math.round(content.score * 100)}%` : 'N/A'}
                        </p>
                    </div>
                    <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-6">
                        <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Created</p>
                        <p className="mt-3 text-sm font-mono text-slate-300">{new Date(content.created_at).toLocaleString()}</p>
                    </div>
                    <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-6">
                        <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Share Expires</p>
                        <p className="mt-3 text-sm font-mono text-slate-300">{new Date(payload.expires_at).toLocaleString()}</p>
                    </div>
                </div>

                {content.excerpt && (
                    <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-8">
                        <div className="flex items-center gap-3">
                            <ShareNetwork size={20} className="text-cyan-400" />
                            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400">Shared Excerpt</h2>
                        </div>
                        <p className="mt-4 leading-7 text-slate-200 whitespace-pre-wrap">{content.excerpt}</p>
                    </div>
                )}
            </div>
        </div>
    );
}
