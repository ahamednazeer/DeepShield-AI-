'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    ArrowLeft,
    Bell,
    Globe,
    Pulse,
    ShareNetwork,
    Warning,
} from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

function formatPercent(value?: number | null) {
    if (value == null) return 'N/A';
    return `${Math.round(value * 100)}%`;
}

function getConfidenceDisplay(verdict: string, score?: number | null) {
    if (verdict === 'UNKNOWN') {
        return {
            label: 'Provider Status',
            percent: null as number | null,
        };
    }
    const normalizedScore = typeof score === 'number' ? score : 0;
    if (verdict === 'AUTHENTIC') {
        return {
            label: 'Authentic Confidence',
            percent: Math.round((1 - normalizedScore) * 100),
        };
    }

    if (verdict === 'MANIPULATED') {
        return {
            label: 'Manipulated Confidence',
            percent: Math.round(normalizedScore * 100),
        };
    }

    return {
        label: 'Verification Risk',
        percent: Math.round(normalizedScore * 100),
    };
}

function providerScoreLabel(provider?: { status?: string; risk_score?: number | null }) {
    const status = provider?.status || 'unknown';
    if (status === 'pending') return 'Pending';
    if (status === 'disabled') return 'Not Configured';
    if (status === 'error') return 'Error';
    if (status === 'skipped') return 'Skipped';
    if (typeof provider?.risk_score === 'number') return formatPercent(provider.risk_score);
    return 'N/A';
}

function providerStatus(provider?: { status?: string }) {
    return provider?.status || 'unknown';
}

function isProviderResolved(provider?: { status?: string }) {
    return ['completed', 'disabled', 'skipped'].includes(providerStatus(provider));
}

function getLinkReadiness(item: any) {
    const vtResolved = isProviderResolved(item?.provider_summary?.virustotal);
    const urlscanResolved = isProviderResolved(item?.provider_summary?.urlscan);
    const isFinal = item?.status === 'completed' && vtResolved && urlscanResolved;
    const isPending = item?.status === 'processing' || !vtResolved || !urlscanResolved;
    return {
        isFinal,
        isPending,
    };
}

export default function LinkAnalysisDetailPage() {
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
                const data = await api.getLinkAnalysis(analysisId);
                setItem(data);
            } catch (err: any) {
                setError(err.message || 'Failed to load link analysis');
            } finally {
                setLoading(false);
            }
        }
        if (analysisId) fetchItem();
    }, [analysisId]);

    useEffect(() => {
        if (!analysisId || !item) return;
        const readiness = getLinkReadiness(item);
        if (!readiness.isPending) return;

        let attempts = 0;
        const timer = window.setInterval(async () => {
            attempts += 1;
            try {
                const data = await api.getLinkAnalysis(analysisId);
                setItem(data);
                const nextReadiness = getLinkReadiness(data);
                if (!nextReadiness.isPending || attempts >= 12) {
                    window.clearInterval(timer);
                }
            } catch (err) {
                console.error('Failed to refresh link analysis detail', err);
                if (attempts >= 12) {
                    window.clearInterval(timer);
                }
            }
        }, 4000);

        return () => window.clearInterval(timer);
    }, [analysisId, item?.status, item?.provider_summary?.virustotal?.status, item?.provider_summary?.urlscan?.status]);

    const handleShare = async () => {
        try {
            const result = await api.createShareLink('link', analysisId);
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
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-sky-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-sky-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Loading Link Analysis...</p>
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

    const vtSummary = item.provider_summary?.virustotal || {};
    const urlscanSummary = item.provider_summary?.urlscan || {};
    const readiness = getLinkReadiness(item);
    const effectiveVerdict = readiness.isFinal ? (item.effective_verdict || item.verdict || 'UNKNOWN') : 'UNKNOWN';
    const confidenceDisplay = getConfidenceDisplay(effectiveVerdict, item.risk_score);
    const canShare = Boolean(item.permissions?.can_share) && readiness.isFinal;

    return (
        <div className="space-y-8 max-w-6xl mx-auto">
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
                            <Globe size={28} weight="duotone" className="text-sky-400" />
                            Link Analysis #{item.id}
                        </h1>
                        <p className="text-slate-500 mt-1 font-mono text-sm">Stored URL threat scan and reputation evidence</p>
                    </div>
                </div>
                <div className="flex gap-3 flex-wrap">
                    <button
                        onClick={handleShare}
                        disabled={!canShare}
                        className="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <ShareNetwork size={16} />
                        {canShare ? 'Share Summary' : 'Sharing Disabled'}
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
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Effective Verdict</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                            <StatusBadge status={effectiveVerdict} />
                            {item.raw_verdict && <StatusBadge status={item.raw_verdict} />}
                            {item.status !== 'completed' && <StatusBadge status={item.status || 'processing'} />}
                            <StatusBadge status={item.moderation?.review_status || 'clear'} />
                            {item.moderation?.is_flagged && <StatusBadge status="flagged" />}
                            {item.moderation?.is_quarantined && <StatusBadge status="quarantined" />}
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">{confidenceDisplay.label}</p>
                        <p className="mt-2 text-4xl font-bold font-mono text-slate-100">
                            {confidenceDisplay.percent == null ? 'WAIT' : `${confidenceDisplay.percent}%`}
                        </p>
                    </div>
                </div>
                {!readiness.isFinal && (
                    <p className="mt-4 text-xs font-mono uppercase tracking-wider text-amber-300">
                        Waiting for VirusTotal and urlscan to finish before issuing a final verdict
                    </p>
                )}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Resolved URLs</h2>
                    <div className="space-y-4 text-sm font-mono text-slate-300">
                        <div>
                            <p className="text-slate-500 uppercase tracking-wider text-[11px] mb-1">Input URL</p>
                            <p className="break-all">{item.input_url}</p>
                        </div>
                        <div>
                            <p className="text-slate-500 uppercase tracking-wider text-[11px] mb-1">Normalized URL</p>
                            <p className="break-all">{item.normalized_url || '—'}</p>
                        </div>
                        <div>
                            <p className="text-slate-500 uppercase tracking-wider text-[11px] mb-1">Final URL</p>
                            <p className="break-all">{item.final_url || item.normalized_url || '—'}</p>
                        </div>
                    </div>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Page Metadata</h2>
                    <div className="space-y-2 text-sm text-slate-300">
                        <div className="flex items-center justify-between gap-4"><span>Domain</span><span className="font-mono">{item.page_metadata?.domain || item.domain || '—'}</span></div>
                        <div className="flex items-center justify-between gap-4"><span>Title</span><span className="font-mono text-right">{item.page_metadata?.title || '—'}</span></div>
                        <div className="flex items-center justify-between gap-4"><span>Status</span><span className="font-mono">{item.page_metadata?.status || '—'}</span></div>
                        <div className="flex items-center justify-between gap-4"><span>Server</span><span className="font-mono text-right">{item.page_metadata?.server || '—'}</span></div>
                        <div className="flex items-center justify-between gap-4"><span>IP</span><span className="font-mono">{item.page_metadata?.ip || '—'}</span></div>
                        <div className="flex items-center justify-between gap-4"><span>Created</span><span className="font-mono">{new Date(item.created_at).toLocaleString()}</span></div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Provider Summary</h2>
                    <div className="space-y-4">
                        <div className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                            <div className="flex items-center justify-between gap-4">
                                <p className="text-sm text-slate-200">VirusTotal</p>
                                <StatusBadge status={vtSummary?.status || 'unknown'} />
                            </div>
                            <div className="mt-3 text-xs font-mono text-slate-400 space-y-1">
                                <div>risk {providerScoreLabel(vtSummary)}</div>
                                <div>malicious {(vtSummary?.stats || {}).malicious || 0}</div>
                                <div>suspicious {(vtSummary?.stats || {}).suspicious || 0}</div>
                                {vtSummary?.reason && <div>{vtSummary.reason}</div>}
                            </div>
                        </div>
                        <div className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                            <div className="flex items-center justify-between gap-4">
                                <p className="text-sm text-slate-200">urlscan</p>
                                <StatusBadge status={urlscanSummary?.status || 'unknown'} />
                            </div>
                            <div className="mt-3 text-xs font-mono text-slate-400 space-y-1">
                                <div>risk {providerScoreLabel(urlscanSummary)}</div>
                                <div>score {urlscanSummary?.score ?? '—'}</div>
                                <div>downloads {urlscanSummary?.downloads ?? '—'}</div>
                                {urlscanSummary?.reason && <div>{urlscanSummary.reason}</div>}
                            </div>
                            {(urlscanSummary?.categories || []).length ? (
                                <div className="mt-3 flex gap-2 flex-wrap">
                                    {urlscanSummary.categories.map((category: string) => (
                                        <StatusBadge key={category} status={category.toUpperCase()} />
                                    ))}
                                </div>
                            ) : null}
                        </div>
                    </div>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Moderation</h2>
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

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Risk Signals</h2>
                    <div className="space-y-3">
                        {(item.signals || []).length ? (
                            item.signals.map((signal: any, index: number) => (
                                <div key={`${signal.source}-${index}`} className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                    <div className="flex items-center justify-between gap-3 flex-wrap">
                                        <p className="text-sm text-slate-200">{signal.label}</p>
                                        <div className="flex gap-2">
                                            <StatusBadge status={signal.severity || 'info'} />
                                            <StatusBadge status={signal.source || 'local'} />
                                        </div>
                                    </div>
                                    {signal.details && Object.keys(signal.details).length > 0 && (
                                        <pre className="mt-3 text-xs text-slate-500 font-mono whitespace-pre-wrap">{JSON.stringify(signal.details, null, 2)}</pre>
                                    )}
                                </div>
                            ))
                        ) : (
                            <p className="text-slate-500 font-mono text-sm">No signals stored.</p>
                        )}
                    </div>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Redirect Chain</h2>
                    <div className="space-y-3">
                        {(item.redirect_chain || []).length ? (
                            item.redirect_chain.map((entry: string, index: number) => (
                                <div key={`${entry}-${index}`} className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                    <p className="text-[11px] text-slate-500 font-mono uppercase tracking-wider">Step {index + 1}</p>
                                    <p className="mt-2 break-all text-sm font-mono text-slate-300">{entry}</p>
                                </div>
                            ))
                        ) : (
                            <p className="text-slate-500 font-mono text-sm">No redirect information recorded.</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
