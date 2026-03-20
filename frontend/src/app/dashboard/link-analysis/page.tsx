'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
    ArrowRight,
    Globe,
    Lightning,
    Pulse,
    ShieldCheck,
    ShieldWarning,
    Warning,
} from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { getCommonVerdict } from '@/lib/verdicts';

const VERDICT_CONFIG: Record<string, { icon: React.ElementType; border: string; bg: string; color: string }> = {
    AUTHENTIC: { icon: ShieldCheck, border: 'border-green-700/60', bg: 'bg-green-950/30', color: 'text-green-300' },
    SUSPICIOUS: { icon: Warning, border: 'border-yellow-700/60', bg: 'bg-yellow-950/30', color: 'text-yellow-300' },
    MANIPULATED: { icon: ShieldWarning, border: 'border-red-700/60', bg: 'bg-red-950/30', color: 'text-red-300' },
    UNKNOWN: { icon: Globe, border: 'border-slate-700/60', bg: 'bg-slate-900/40', color: 'text-slate-300' },
};

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

function providerStatus(provider?: { status?: string }) {
    return provider?.status || 'unknown';
}

function isProviderResolved(provider?: { status?: string }) {
    return ['completed', 'disabled', 'skipped'].includes(providerStatus(provider));
}

function getLinkReadiness(result: any) {
    const vtResolved = isProviderResolved(result?.provider_summary?.virustotal);
    const urlscanResolved = isProviderResolved(result?.provider_summary?.urlscan);
    const isFinal = result?.status === 'completed' && vtResolved && urlscanResolved;
    const isPending = result?.status === 'processing' || !vtResolved || !urlscanResolved;
    return {
        isFinal,
        isPending,
    };
}

function providerScoreLabel(provider?: { status?: string; risk_score?: number | null }) {
    const status = providerStatus(provider);
    if (status === 'pending') return 'Pending';
    if (status === 'disabled') return 'Not Configured';
    if (status === 'error') return 'Error';
    if (status === 'skipped') return 'Skipped';
    if (typeof provider?.risk_score === 'number') return formatPercent(provider.risk_score);
    return 'N/A';
}

export default function LinkAnalysisPage() {
    const router = useRouter();
    const [url, setUrl] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [result, setResult] = useState<any>(null);
    const [history, setHistory] = useState<any[]>([]);

    async function loadHistory() {
        try {
            const data = await api.getLinkHistory();
            setHistory((data.analyses || []).slice(0, 6));
        } catch (err) {
            console.error('Failed to fetch link history', err);
        }
    }

    useEffect(() => {
        loadHistory();
    }, []);

    useEffect(() => {
        if (!result?.id) return;
        const readiness = getLinkReadiness(result);
        if (!readiness.isPending) return;

        let attempts = 0;
        const timer = window.setInterval(async () => {
            attempts += 1;
            try {
                const refreshed = await api.getLinkAnalysis(result.id);
                setResult(refreshed);
                const nextReadiness = getLinkReadiness(refreshed);
                if (!nextReadiness.isPending || attempts >= 12) {
                    window.clearInterval(timer);
                    loadHistory();
                }
            } catch (err) {
                console.error('Failed to refresh link analysis', err);
                if (attempts >= 12) {
                    window.clearInterval(timer);
                }
            }
        }, 4000);

        return () => window.clearInterval(timer);
    }, [result?.id, result?.status, result?.provider_summary?.virustotal?.status, result?.provider_summary?.urlscan?.status]);

    const handleAnalyze = async () => {
        if (!url.trim()) return;
        setLoading(true);
        setError('');
        try {
            const data = await api.analyzeLink(url.trim());
            setResult(data);
            await loadHistory();
        } catch (err: any) {
            setError(err.message || 'Link analysis failed');
        } finally {
            setLoading(false);
        }
    };

    const openDetail = (analysisId: number) => {
        router.push(`/dashboard/link-analysis/${analysisId}`);
    };

    const readiness = getLinkReadiness(result);
    const verdict = readiness.isFinal ? (getCommonVerdict(result?.effective_verdict || result?.verdict) || 'UNKNOWN') : 'UNKNOWN';
    const verdictConfig = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNKNOWN;
    const VerdictIcon = verdictConfig.icon;
    const vtSummary = result?.provider_summary?.virustotal || {};
    const urlscanSummary = result?.provider_summary?.urlscan || {};
    const confidenceDisplay = getConfidenceDisplay(verdict, result?.risk_score);

    return (
        <div className="space-y-8 max-w-6xl mx-auto">
            <div>
                <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                    <Globe size={28} weight="duotone" className="text-sky-400" />
                    Link Detection
                </h1>
                <p className="text-slate-500 mt-1 font-mono text-sm">
                    URL scanning with VirusTotal reputation and urlscan browser telemetry
                </p>
            </div>

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6 space-y-4">
                <label className="block text-xs font-mono text-slate-400 uppercase tracking-widest">
                    URL To Inspect
                </label>
                <div className="flex flex-col lg:flex-row gap-3">
                    <input
                        id="link-input"
                        type="url"
                        value={url}
                        onChange={(e) => setUrl(e.target.value)}
                        placeholder="https://example.com/verify-account"
                        className="flex-1 bg-slate-900/60 border border-slate-700/50 rounded-sm px-4 py-3 text-slate-200 font-mono text-sm placeholder:text-slate-600 focus:outline-none focus:border-sky-600/60 focus:ring-1 focus:ring-sky-600/20 transition-colors"
                    />
                    <button
                        id="scan-link-btn"
                        onClick={handleAnalyze}
                        disabled={loading || !url.trim()}
                        className="bg-gradient-to-r from-sky-700 to-cyan-700 hover:from-sky-600 hover:to-cyan-600 disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-500 text-white font-bold text-sm uppercase tracking-wider px-8 py-3 rounded-sm transition-all flex items-center justify-center gap-2"
                    >
                        {loading ? (
                            <>
                                <Pulse size={18} className="animate-pulse" />
                                Scanning...
                            </>
                        ) : (
                            <>
                                <Lightning size={18} weight="fill" />
                                Scan Link
                            </>
                        )}
                    </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
                    <div className="rounded-sm border border-slate-800 bg-slate-900/50 p-3 text-slate-400">
                        VirusTotal adds multi-engine URL reputation if <span className="text-slate-200">VIRUSTOTAL_API_KEY</span> is configured.
                    </div>
                    <div className="rounded-sm border border-slate-800 bg-slate-900/50 p-3 text-slate-400">
                        urlscan adds page verdicts, categories, and final redirect/page metadata if <span className="text-slate-200">URLSCAN_API_KEY</span> is configured.
                    </div>
                </div>
            </div>

            {error && (
                <div className="bg-red-950/30 border border-red-800/50 rounded-sm p-4 flex items-center gap-3">
                    <Warning size={18} className="text-red-300" />
                    <p className="text-red-200 text-sm font-mono">{error}</p>
                </div>
            )}

            {loading && (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-12 flex flex-col items-center gap-4">
                    <div className="relative">
                        <div className="w-16 h-16 rounded-full border-2 border-slate-700 border-t-sky-500 animate-spin" />
                        <Pulse size={30} className="absolute inset-0 m-auto text-sky-400 animate-pulse" />
                    </div>
                    <p className="text-slate-500 font-mono text-xs uppercase tracking-widest">
                        Querying VirusTotal and urlscan...
                    </p>
                </div>
            )}

            {result && (
                <div className="space-y-6">
                    <div className={`rounded-sm border p-6 ${verdictConfig.border} ${verdictConfig.bg}`}>
                        <div className="flex items-start justify-between gap-6 flex-wrap">
                            <div className="flex items-start gap-4">
                                <VerdictIcon size={32} className={verdictConfig.color} />
                                <div>
                                    <p className="text-xs font-mono uppercase tracking-widest text-slate-500">Effective Verdict</p>
                                    <div className="mt-3 flex gap-2 flex-wrap">
                                        <StatusBadge status={verdict} />
                                        {result.raw_verdict && <StatusBadge status={result.raw_verdict} />}
                                        <StatusBadge status={result.moderation?.review_status || 'clear'} />
                                        {result.moderation?.is_flagged && <StatusBadge status="flagged" />}
                                        {result.moderation?.is_quarantined && <StatusBadge status="quarantined" />}
                                    </div>
                                    <p className="mt-4 text-sm text-slate-300 break-all">{result.final_url || result.normalized_url || result.input_url}</p>
                                    {!readiness.isFinal && (
                                        <p className="mt-3 text-xs font-mono uppercase tracking-wider text-amber-300">
                                            Waiting for VirusTotal and urlscan to finish before issuing a final verdict
                                        </p>
                                    )}
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-xs font-mono uppercase tracking-widest text-slate-500">{confidenceDisplay.label}</p>
                                <p className="mt-2 text-4xl font-bold font-mono text-slate-100">
                                    {confidenceDisplay.percent == null ? 'WAIT' : `${confidenceDisplay.percent}%`}
                                </p>
                                <button onClick={() => openDetail(result.id)} className="mt-4 btn-secondary inline-flex items-center gap-2">
                                    Open Detail
                                    <ArrowRight size={16} />
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-5">
                            <p className="text-xs font-mono uppercase tracking-widest text-slate-500">VirusTotal</p>
                            <div className="mt-3 flex items-center justify-between">
                                <StatusBadge status={providerStatus(vtSummary)} />
                                <span className="font-mono text-slate-200">{providerScoreLabel(vtSummary)}</span>
                            </div>
                            {vtSummary?.stats && (
                                <div className="mt-3 text-xs font-mono text-slate-400 space-y-1">
                                    <div>malicious {vtSummary.stats.malicious || 0}</div>
                                    <div>suspicious {vtSummary.stats.suspicious || 0}</div>
                                    <div>harmless {vtSummary.stats.harmless || 0}</div>
                                </div>
                            )}
                            {vtSummary?.reason && <p className="mt-3 text-xs text-slate-500">{vtSummary.reason}</p>}
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-5">
                            <p className="text-xs font-mono uppercase tracking-widest text-slate-500">urlscan</p>
                            <div className="mt-3 flex items-center justify-between">
                                <StatusBadge status={providerStatus(urlscanSummary)} />
                                <span className="font-mono text-slate-200">{providerScoreLabel(urlscanSummary)}</span>
                            </div>
                            {urlscanSummary?.categories?.length ? (
                                <div className="mt-3 flex gap-2 flex-wrap">
                                    {urlscanSummary.categories.map((category: string) => (
                                        <StatusBadge key={category} status={category.toUpperCase()} />
                                    ))}
                                </div>
                            ) : null}
                            {urlscanSummary?.reason && <p className="mt-3 text-xs text-slate-500">{urlscanSummary.reason}</p>}
                        </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Resolved URLs</h2>
                            <div className="space-y-3 text-sm font-mono text-slate-300">
                                <div>
                                    <p className="text-slate-500 uppercase tracking-wider text-[11px] mb-1">Submitted</p>
                                    <p className="break-all">{result.input_url}</p>
                                </div>
                                <div>
                                    <p className="text-slate-500 uppercase tracking-wider text-[11px] mb-1">Normalized</p>
                                    <p className="break-all">{result.normalized_url || '—'}</p>
                                </div>
                                <div>
                                    <p className="text-slate-500 uppercase tracking-wider text-[11px] mb-1">Final</p>
                                    <p className="break-all">{result.final_url || result.normalized_url || '—'}</p>
                                </div>
                            </div>
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Page Metadata</h2>
                            <div className="space-y-2 text-sm text-slate-300">
                                <div className="flex items-center justify-between gap-4"><span>Domain</span><span className="font-mono">{result.page_metadata?.domain || result.domain || '—'}</span></div>
                                <div className="flex items-center justify-between gap-4"><span>Title</span><span className="font-mono text-right">{result.page_metadata?.title || '—'}</span></div>
                                <div className="flex items-center justify-between gap-4"><span>Status</span><span className="font-mono">{result.page_metadata?.status || '—'}</span></div>
                                <div className="flex items-center justify-between gap-4"><span>Server</span><span className="font-mono text-right">{result.page_metadata?.server || '—'}</span></div>
                                <div className="flex items-center justify-between gap-4"><span>IP</span><span className="font-mono">{result.page_metadata?.ip || '—'}</span></div>
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Risk Signals</h2>
                            <div className="space-y-3">
                                {(result.signals || []).length ? (
                                    result.signals.map((signal: any, index: number) => (
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
                                    <p className="text-slate-500 font-mono text-sm">No signals recorded.</p>
                                )}
                            </div>
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                            <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400 mb-4">Redirect Chain</h2>
                            <div className="space-y-3">
                                {(result.redirect_chain || []).length ? (
                                    result.redirect_chain.map((item: string, index: number) => (
                                        <div key={`${item}-${index}`} className="rounded-sm border border-slate-800 bg-slate-900/50 p-3">
                                            <p className="text-[11px] text-slate-500 font-mono uppercase tracking-wider">Step {index + 1}</p>
                                            <p className="mt-2 break-all text-sm font-mono text-slate-300">{item}</p>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-slate-500 font-mono text-sm">No redirect chain captured.</p>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
                    <div>
                        <h2 className="text-sm font-mono uppercase tracking-widest text-slate-400">Recent Link Scans</h2>
                        <p className="mt-1 text-xs font-mono text-slate-500">{history.length} recent records</p>
                    </div>
                </div>
                {history.length ? (
                    <div className="space-y-3">
                        {history.map((item) => (
                            <button
                                key={item.id}
                                onClick={() => openDetail(item.id)}
                                className="w-full text-left rounded-sm border border-slate-800 bg-slate-900/50 p-4 hover:bg-slate-900 transition-colors"
                            >
                                <div className="flex items-start justify-between gap-4 flex-wrap">
                                    <div>
                                        <div className="flex gap-2 flex-wrap">
                                            <StatusBadge status="link" />
                                            <StatusBadge status={item.effective_verdict || item.verdict || 'UNKNOWN'} />
                                            {item.status !== 'completed' && <StatusBadge status={item.status || 'processing'} />}
                                        </div>
                                        <p className="mt-3 text-sm font-mono text-slate-200 break-all">{item.final_url || item.normalized_url || item.input_url}</p>
                                    </div>
                                    <div className="text-right text-xs font-mono text-slate-500">
                                        <div>{item.status === 'completed' ? formatPercent(item.risk_score) : 'WAIT'}</div>
                                        <div className="mt-1">{new Date(item.created_at).toLocaleString()}</div>
                                    </div>
                                </div>
                            </button>
                        ))}
                    </div>
                ) : (
                    <p className="text-slate-500 font-mono text-sm">No link scans yet.</p>
                )}
            </div>
        </div>
    );
}
