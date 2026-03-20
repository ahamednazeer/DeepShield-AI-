'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    ArrowLeft,
    Bell,
    Clock,
    Download,
    Eye,
    FileText,
    HardDrive,
    Pulse,
    ShareNetwork,
    Warning,
} from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function AnalysisDetailPage() {
    const router = useRouter();
    const params = useParams();
    const analysisId = Number(params.id);
    const [analysis, setAnalysis] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [shareMessage, setShareMessage] = useState('');

    const fetchAnalysis = useCallback(async () => {
        if (!analysisId) return;
        try {
            const data = await api.getAnalysis(analysisId);
            setAnalysis(data);
        } catch (err: any) {
            setError(err.message || 'Failed to load analysis');
        } finally {
            setLoading(false);
        }
    }, [analysisId]);

    useEffect(() => {
        fetchAnalysis();
    }, [fetchAnalysis]);

    useEffect(() => {
        if (!analysis || (analysis.status !== 'processing' && analysis.status !== 'pending')) return;
        const interval = setInterval(fetchAnalysis, 2000);
        return () => clearInterval(interval);
    }, [analysis?.status, fetchAnalysis]);

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const downloadOriginal = async () => {
        try {
            const response = await api.downloadMedia(analysis.id);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = analysis.original_filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (err: any) {
            setShareMessage(err.message || 'Download failed');
        }
    };

    const createShareLink = async () => {
        try {
            const result = await api.createShareLink('media', analysis.id);
            const shareUrl = `${window.location.origin}${result.share_url}`;
            await navigator.clipboard.writeText(shareUrl);
            setShareMessage(`Share link copied. Expires ${new Date(result.expires_at).toLocaleString()}`);
        } catch (err: any) {
            setShareMessage(err.message || 'Could not create share link');
        }
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Loading Analysis...</p>
            </div>
        );
    }

    if (error || !analysis) {
        return (
            <div className="bg-red-950/50 border border-red-800 rounded-sm p-6 text-center">
                <p className="text-red-400 font-mono">{error || 'Analysis not found'}</p>
                <button onClick={() => router.back()} className="mt-4 btn-secondary">Go Back</button>
            </div>
        );
    }

    const progressPercent = analysis.progress_percent ?? (analysis.frames_total ? ((analysis.frames_processed || 0) / analysis.frames_total) * 100 : null);
    const progressValue = Math.min(Math.max(progressPercent ?? 0, 0), 100);

    return (
        <div className="space-y-8 max-w-5xl mx-auto">
            <div className="flex items-center justify-between flex-wrap gap-4">
                <div className="flex items-center gap-4">
                    <button onClick={() => router.back()} className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors">
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                            <Eye size={28} weight="duotone" className="text-blue-400" />
                            Analysis #{analysis.id}
                        </h1>
                        <p className="text-slate-500 mt-1 font-mono text-sm">{analysis.original_filename}</p>
                    </div>
                </div>
                <div className="flex gap-3 flex-wrap">
                    {analysis.status === 'completed' && (
                        <button onClick={() => router.push(`/dashboard/report/${analysis.id}`)} className="btn-primary flex items-center gap-2">
                            <FileText size={16} />
                            Forensic Report
                        </button>
                    )}
                    <button
                        onClick={downloadOriginal}
                        disabled={!analysis.permissions?.can_download}
                        className="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <Download size={16} />
                        {analysis.permissions?.can_download ? 'Download Original' : 'Download Disabled'}
                    </button>
                    <button
                        onClick={createShareLink}
                        disabled={!analysis.permissions?.can_share}
                        className="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <ShareNetwork size={16} />
                        {analysis.permissions?.can_share ? 'Share Summary' : 'Sharing Disabled'}
                    </button>
                </div>
            </div>

            {analysis.permissions?.blocked_reason && (
                <div className="bg-amber-950/30 border border-amber-800/50 rounded-sm p-4 flex items-start gap-3">
                    <Warning size={18} className="text-amber-300 mt-0.5" />
                    <p className="text-amber-200 text-sm font-mono">{analysis.permissions.blocked_reason}</p>
                </div>
            )}

            {shareMessage && (
                <div className="bg-cyan-950/20 border border-cyan-800/40 rounded-sm p-4 text-sm text-cyan-200 font-mono">
                    {shareMessage}
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                    <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-2">Effective Verdict</p>
                    <StatusBadge status={analysis.effective_verdict || analysis.verdict || 'UNKNOWN'} />
                </div>
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                    <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-2">Review Status</p>
                    <div className="flex gap-2 flex-wrap">
                        <StatusBadge status={analysis.moderation?.review_status || 'clear'} />
                        {analysis.moderation?.is_flagged && <StatusBadge status="flagged" />}
                        {analysis.moderation?.is_quarantined && <StatusBadge status="quarantined" />}
                    </div>
                </div>
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <HardDrive size={14} className="text-slate-500" />
                        <p className="text-xs text-slate-500 font-mono uppercase tracking-wider">File Size</p>
                    </div>
                    <p className="text-lg text-slate-300 font-mono font-bold">{formatFileSize(analysis.file_size)}</p>
                </div>
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                    <div className="flex items-center gap-2 mb-2">
                        <Clock size={14} className="text-slate-500" />
                        <p className="text-xs text-slate-500 font-mono uppercase tracking-wider">Processing</p>
                    </div>
                    <p className="text-lg text-slate-300 font-mono font-bold">{analysis.processing_time ? `${analysis.processing_time}s` : '—'}</p>
                </div>
            </div>

            {analysis.status === 'processing' && (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                    <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                            <Pulse size={14} className="text-blue-400 animate-pulse" />
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider">Frame Progress</p>
                        </div>
                        <p className="text-xs text-slate-400 font-mono">{analysis.frames_processed ?? 0} / {analysis.frames_total ?? '—'} frames</p>
                    </div>
                    <div className="h-2 bg-slate-900/70 rounded-sm overflow-hidden">
                        <div className="h-2 bg-blue-500 transition-all duration-300" style={{ width: `${progressValue}%` }} />
                    </div>
                    <div className="mt-2 text-right text-xs text-slate-500 font-mono">{progressPercent != null ? `${progressPercent.toFixed(1)}%` : '—'}</div>
                </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2 bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5">Forensic Evidence</h3>
                    {analysis.evidence?.length ? (
                        <div className="space-y-4">
                            {analysis.evidence.map((ev: any, index: number) => (
                                <div key={index} className="bg-slate-900/50 border border-slate-800/50 rounded-sm p-5">
                                    <div className="flex items-start justify-between gap-4">
                                        <div>
                                            <h4 className="text-slate-200 font-medium text-sm">{ev.title}</h4>
                                            <p className="text-xs text-slate-500 font-mono mt-1">Type: {ev.evidence_type}</p>
                                        </div>
                                        <StatusBadge status={ev.severity} />
                                    </div>
                                    {ev.description && <p className="text-sm text-slate-400 mt-2">{ev.description}</p>}
                                    {ev.file_path && (
                                        <div className="mt-3">
                                            {ev.evidence_type === 'heatmap' && analysis.media_type === 'image' ? (
                                                <div className="space-y-3">
                                                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                                        <div className="space-y-2">
                                                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider">Original Image</p>
                                                            <img
                                                                src={api.getUploadUrl(analysis.filename)}
                                                                alt="Original analyzed media"
                                                                className="w-full max-h-[520px] object-contain rounded-sm border border-slate-700 bg-slate-950/60"
                                                            />
                                                        </div>
                                                        <div className="space-y-2">
                                                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider">Forensic Overlay</p>
                                                            <img
                                                                src={api.getEvidenceUrl(ev.file_path)}
                                                                alt={ev.title}
                                                                className="w-full max-h-[520px] object-contain rounded-sm border border-slate-700 bg-slate-950/60"
                                                            />
                                                        </div>
                                                    </div>
                                                    <p className="text-xs text-slate-500 font-mono">
                                                        Brighter yellow and red areas indicate stronger anomaly intensity. Darker areas indicate lower forensic signal.
                                                    </p>
                                                </div>
                                            ) : (
                                                <img
                                                    src={api.getEvidenceUrl(ev.file_path)}
                                                    alt={ev.title}
                                                    className="max-w-full max-h-[520px] object-contain rounded-sm border border-slate-700 bg-slate-950/60"
                                                />
                                            )}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-slate-500 font-mono text-sm">No evidence items were stored for this analysis.</p>
                    )}
                </div>

                <div className="space-y-6">
                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                        <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Moderation</h3>
                        <div className="space-y-3 text-sm text-slate-300">
                            <div className="flex items-center justify-between"><span>Flagged</span><span>{analysis.moderation?.is_flagged ? 'Yes' : 'No'}</span></div>
                            <div className="flex items-center justify-between"><span>Quarantined</span><span>{analysis.moderation?.is_quarantined ? 'Yes' : 'No'}</span></div>
                            <div className="flex items-center justify-between"><span>Manual Verdict</span><span>{analysis.moderation?.manual_verdict || 'None'}</span></div>
                            <div className="flex items-center justify-between"><span>Auto Actions</span><span>{(analysis.moderation?.auto_actions || []).join(', ') || 'None'}</span></div>
                            {analysis.moderation?.review_notes && (
                                <div className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                    <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Review Notes</p>
                                    <p className="mt-2 text-sm text-slate-300">{analysis.moderation.review_notes}</p>
                                </div>
                            )}
                        </div>
                    </div>

                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                        <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Details</h3>
                        <div className="space-y-3 text-sm text-slate-300">
                            <div className="flex items-center justify-between"><span>Media Type</span><StatusBadge status={analysis.media_type} /></div>
                            <div className="flex items-center justify-between"><span>Created</span><span className="font-mono text-xs">{new Date(analysis.created_at).toLocaleString()}</span></div>
                            <div className="flex items-center justify-between"><span>Completed</span><span className="font-mono text-xs">{analysis.completed_at ? new Date(analysis.completed_at).toLocaleString() : '—'}</span></div>
                            <button onClick={() => router.push('/dashboard/notifications')} className="btn-secondary w-full flex items-center justify-center gap-2">
                                <Bell size={16} />
                                Open Alerts
                            </button>
                        </div>
                    </div>
                </div>
            </div>

        </div>
    );
}
