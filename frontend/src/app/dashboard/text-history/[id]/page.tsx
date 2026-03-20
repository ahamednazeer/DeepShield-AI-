'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    ArrowLeft,
    Bell,
    Globe,
    NewspaperClipping,
    Pulse,
    ShareNetwork,
    Warning,
} from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function TextHistoryDetailPage() {
    const router = useRouter();
    const params = useParams();
    const analysisId = Number(params.id);

    const [item, setItem] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [shareMessage, setShareMessage] = useState('');

    useEffect(() => {
        async function fetchItem() {
            try {
                const data = await api.getTextAnalysis(analysisId);
                setItem(data);
            } catch (err: any) {
                setError(err.message || 'Failed to load text analysis');
            } finally {
                setLoading(false);
            }
        }
        if (analysisId) fetchItem();
    }, [analysisId]);

    const handleShare = async () => {
        try {
            const result = await api.createShareLink('text', analysisId);
            const shareUrl = `${window.location.origin}${result.share_url}`;
            await navigator.clipboard.writeText(shareUrl);
            setShareMessage(`Share link copied. Expires ${new Date(result.expires_at).toLocaleString()}`);
        } catch (err: any) {
            setShareMessage(err.message || 'Unable to create share link');
        }
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-cyan-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-cyan-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Loading Text Analysis...</p>
            </div>
        );
    }

    if (error || !item) {
        return (
            <div className="bg-red-950/50 border border-red-800 rounded-sm p-6 text-center">
                <p className="text-red-400 font-mono">{error || 'Analysis not found'}</p>
                <button onClick={() => router.back()} className="mt-4 btn-secondary">Go Back</button>
            </div>
        );
    }

    return (
        <div className="space-y-8 max-w-5xl mx-auto">
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => router.back()}
                        className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
                    >
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                            <NewspaperClipping size={28} weight="duotone" className="text-cyan-400" />
                            Text Analysis #{item.id}
                        </h1>
                        <p className="text-slate-500 mt-1 font-mono text-sm">Stored fake-news verification result</p>
                    </div>
                </div>
                <div className="flex gap-3 flex-wrap">
                    <button
                        onClick={handleShare}
                        disabled={!item.permissions?.can_share}
                        className="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <ShareNetwork size={16} />
                        {item.permissions?.can_share ? 'Share Summary' : 'Sharing Disabled'}
                    </button>
                    <button onClick={() => router.push('/dashboard/notifications')} className="btn-secondary flex items-center gap-2">
                        <Bell size={16} />
                        Alerts
                    </button>
                </div>
            </div>

            {item.permissions?.blocked_reason && (
                <div className="bg-amber-950/30 border border-amber-800/50 rounded-sm p-4 flex items-start gap-3">
                    <Warning size={18} className="text-amber-300 mt-0.5" />
                    <p className="text-amber-200 text-sm font-mono">{item.permissions.blocked_reason}</p>
                </div>
            )}

            {shareMessage && (
                <div className="bg-cyan-950/30 border border-cyan-800/50 rounded-sm p-4 text-cyan-200 text-sm font-mono">
                    {shareMessage}
                </div>
            )}

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Effective Verdict</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                            <StatusBadge status={item.effective_verdict || item.verdict || 'UNKNOWN'} />
                            <StatusBadge status={item.moderation?.review_status || 'clear'} />
                            {item.moderation?.is_flagged && <StatusBadge status="flagged" />}
                            {item.moderation?.is_quarantined && <StatusBadge status="quarantined" />}
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Risk Score</p>
                        <p className="mt-2 text-4xl font-bold font-mono text-slate-100">
                            {item.final_score != null ? `${Math.round(item.final_score * 100)}%` : 'N/A'}
                        </p>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Submitted Text</h3>
                    <p className="text-slate-200 whitespace-pre-wrap leading-7">{item.input_text}</p>
                </div>
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6 space-y-4">
                    <div>
                        <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Source URL</p>
                        <p className="mt-2 text-sm text-slate-300 break-all font-mono">
                            {item.source_url ? (
                                <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:text-cyan-200">
                                    <Globe size={12} className="inline mr-2" />
                                    {item.source_url}
                                </a>
                            ) : 'No source URL provided'}
                        </p>
                    </div>
                    <div>
                        <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Scores</p>
                        <div className="mt-2 space-y-2 text-sm font-mono text-slate-300">
                            <div className="flex justify-between"><span>NLP</span><span>{item.nlp_score != null ? `${Math.round(item.nlp_score * 100)}%` : 'N/A'}</span></div>
                            <div className="flex justify-between"><span>Fact Match</span><span>{item.fact_score != null ? `${Math.round(item.fact_score * 100)}%` : 'N/A'}</span></div>
                            <div className="flex justify-between"><span>Credibility</span><span>{item.credibility_score != null ? `${Math.round(item.credibility_score * 100)}%` : 'N/A'}</span></div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Evidence</h3>
                    <div className="space-y-3">
                        {(item.evidence || []).length ? (
                            item.evidence.map((ev: any, index: number) => (
                                <div key={index} className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                    <div className="flex items-center justify-between gap-2">
                                        <p className="text-sm font-medium text-slate-200">{ev.title || ev.source || 'Evidence'}</p>
                                        {ev.source && <StatusBadge status={ev.source.toLowerCase()} />}
                                    </div>
                                    {ev.extract && <p className="mt-2 text-sm text-slate-400">{ev.extract}</p>}
                                    {ev.url && (
                                        <a href={ev.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-xs font-mono text-cyan-300 hover:text-cyan-200">
                                            Open source
                                        </a>
                                    )}
                                </div>
                            ))
                        ) : (
                            <p className="text-slate-500 font-mono text-sm">No evidence items were stored.</p>
                        )}
                    </div>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Moderation & Notes</h3>
                    <div className="space-y-3 text-sm text-slate-300">
                        <div className="flex items-center justify-between"><span>Flagged</span><span>{item.moderation?.is_flagged ? 'Yes' : 'No'}</span></div>
                        <div className="flex items-center justify-between"><span>Quarantined</span><span>{item.moderation?.is_quarantined ? 'Yes' : 'No'}</span></div>
                        <div className="flex items-center justify-between"><span>Manual Verdict</span><span>{item.moderation?.manual_verdict || 'None'}</span></div>
                        <div className="flex items-center justify-between"><span>Auto Actions</span><span>{(item.moderation?.auto_actions || []).join(', ') || 'None'}</span></div>
                        {item.moderation?.review_notes && (
                            <div className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Review Notes</p>
                                <p className="mt-2 text-sm text-slate-300">{item.moderation.review_notes}</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
