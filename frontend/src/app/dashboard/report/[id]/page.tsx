'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
    ArrowLeft,
    Download,
    FileText,
    Printer,
    Pulse,
    ShieldCheck,
} from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function ReportPage() {
    const router = useRouter();
    const params = useParams();
    const analysisId = Number(params.id);
    const [report, setReport] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        async function fetchReport() {
            try {
                const data = await api.getReport(analysisId);
                setReport(data);
            } catch (err: any) {
                setError(err.message || 'Failed to load report');
            } finally {
                setLoading(false);
            }
        }
        if (analysisId) fetchReport();
    }, [analysisId]);

    const downloadFile = async (format: 'pdf' | 'json') => {
        const response = await api.downloadReport(analysisId, format);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `deepshield-report-${analysisId}.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Generating Report...</p>
            </div>
        );
    }

    if (error || !report) {
        return (
            <div className="bg-red-950/50 border border-red-800 rounded-sm p-6 text-center">
                <p className="text-red-400 font-mono">{error || 'Report not found'}</p>
                <button onClick={() => router.back()} className="mt-4 btn-secondary">Go Back</button>
            </div>
        );
    }

    return (
        <div className="space-y-8 max-w-5xl mx-auto">
            <div className="flex items-center justify-between flex-wrap gap-4 print:hidden">
                <div className="flex items-center gap-4">
                    <button onClick={() => router.back()} className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors">
                        <ArrowLeft size={20} />
                    </button>
                    <div>
                        <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                            <FileText size={28} weight="duotone" className="text-blue-400" />
                            Signed Forensic Report
                        </h1>
                        <p className="text-slate-500 mt-1 font-mono text-sm">{report.report_id}</p>
                    </div>
                </div>
                <div className="flex gap-3 flex-wrap">
                    <button onClick={() => downloadFile('pdf')} className="btn-primary flex items-center gap-2">
                        <Download size={16} />
                        Download PDF
                    </button>
                    <button onClick={() => downloadFile('json')} className="btn-secondary flex items-center gap-2">
                        <Download size={16} />
                        Download JSON
                    </button>
                    <button onClick={() => window.print()} className="btn-secondary flex items-center gap-2">
                        <Printer size={16} />
                        Print
                    </button>
                </div>
            </div>

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-8">
                <div className="flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex items-center gap-4">
                        <ShieldCheck size={40} weight="duotone" className="text-blue-400" />
                        <div>
                            <h2 className="text-xl font-chivo font-bold uppercase tracking-wider">DeepShield AI</h2>
                            <p className="text-xs text-slate-500 font-mono">Signed forensic export with audit trail</p>
                        </div>
                    </div>
                    <div className="text-right">
                        <p className="text-xs text-slate-500 font-mono uppercase tracking-wider">Effective Verdict</p>
                        <div className="mt-2"><StatusBadge status={report.analysis_results?.effective_verdict || report.analysis_results?.verdict || 'UNKNOWN'} /></div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                        <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5 border-b border-slate-700/50 pb-3">Media Information</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <p className="text-xs text-slate-500 font-mono uppercase">Original Filename</p>
                                <p className="text-sm text-slate-300 font-mono mt-1">{report.media_info?.original_filename}</p>
                            </div>
                            <div>
                                <p className="text-xs text-slate-500 font-mono uppercase">Media Type</p>
                                <p className="text-sm text-slate-300 font-mono mt-1">{report.media_info?.media_type}</p>
                            </div>
                            <div>
                                <p className="text-xs text-slate-500 font-mono uppercase">File Size</p>
                                <p className="text-sm text-slate-300 font-mono mt-1">{report.media_info?.file_size_mb} MB</p>
                            </div>
                            <div>
                                <p className="text-xs text-slate-500 font-mono uppercase">Uploaded</p>
                                <p className="text-sm text-slate-300 font-mono mt-1">{new Date(report.media_info?.uploaded_at).toLocaleString()}</p>
                            </div>
                        </div>
                    </div>

                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                        <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5 border-b border-slate-700/50 pb-3">Moderation State</h3>
                        <div className="flex gap-2 flex-wrap">
                            <StatusBadge status={report.moderation?.review_status || 'clear'} />
                            {report.moderation?.is_flagged && <StatusBadge status="flagged" />}
                            {report.moderation?.is_quarantined && <StatusBadge status="quarantined" />}
                            {report.moderation?.manual_verdict && <StatusBadge status={report.moderation.manual_verdict} />}
                        </div>
                        {report.moderation?.review_notes && (
                            <div className="mt-4 rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                <p className="text-xs font-mono text-slate-500 uppercase tracking-wider">Review Notes</p>
                                <p className="mt-2 text-sm text-slate-300">{report.moderation.review_notes}</p>
                            </div>
                        )}
                    </div>

                    {report.forensic_evidence?.length > 0 && (
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                            <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5 border-b border-slate-700/50 pb-3">
                                Forensic Evidence ({report.forensic_evidence.length})
                            </h3>
                            <div className="space-y-4">
                                {report.forensic_evidence.map((ev: any, idx: number) => (
                                    <div key={idx} className="bg-slate-900/50 border border-slate-800/50 rounded-sm p-4">
                                        <div className="flex items-start justify-between gap-3">
                                            <div>
                                                <h4 className="text-slate-200 font-medium text-sm">{ev.title}</h4>
                                                <p className="text-xs text-slate-500 font-mono mt-1">{ev.type}</p>
                                            </div>
                                            <StatusBadge status={ev.severity} />
                                        </div>
                                        {ev.description && <p className="text-sm text-slate-400 mt-2">{ev.description}</p>}
                                        {ev.file && (
                                            <div className="mt-3">
                                                <img src={api.getEvidenceUrl(ev.file)} alt={ev.title} className="max-w-full rounded-sm border border-slate-700" />
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                <div className="space-y-6">
                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                        <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5 border-b border-slate-700/50 pb-3">Analysis Results</h3>
                        <div className="space-y-4 text-sm text-slate-300">
                            <div className="flex justify-between"><span>Overall Score</span><span className="font-mono">{report.analysis_results?.overall_score?.toFixed(4)}</span></div>
                            <div className="flex justify-between"><span>Confidence</span><span className="font-mono">{report.analysis_results?.confidence_percent}%</span></div>
                            <div className="flex justify-between"><span>Processing Time</span><span className="font-mono">{report.analysis_results?.processing_time_seconds}s</span></div>
                            <div className="flex justify-between"><span>Model Version</span><span className="font-mono">{report.analysis_results?.model_version || 'Default'}</span></div>
                        </div>
                    </div>

                    <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                        <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5 border-b border-slate-700/50 pb-3">Integrity</h3>
                        <div className="space-y-4 text-xs font-mono text-slate-300 break-all">
                            <div>
                                <p className="text-slate-500 uppercase">Payload Hash</p>
                                <p className="mt-1">{report.integrity?.payload_hash}</p>
                            </div>
                            <div>
                                <p className="text-slate-500 uppercase">Signature</p>
                                <p className="mt-1">{report.integrity?.signature}</p>
                            </div>
                            <div>
                                <p className="text-slate-500 uppercase">Algorithm</p>
                                <p className="mt-1">{report.integrity?.signature_algorithm}</p>
                            </div>
                            <div>
                                <p className="text-slate-500 uppercase">Hint</p>
                                <p className="mt-1">{report.integrity?.verification_hint}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                <h3 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-5 border-b border-slate-700/50 pb-3">Audit Trail</h3>
                <div className="space-y-3">
                    {(report.audit_trail || []).length ? report.audit_trail.map((event: any) => (
                        <div key={event.id} className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <p className="text-sm text-slate-200">{event.action}</p>
                                    <p className="mt-1 text-xs font-mono text-slate-500">{event.actor_username || 'system'}</p>
                                </div>
                                <p className="text-xs font-mono text-slate-500">{new Date(event.created_at).toLocaleString()}</p>
                            </div>
                        </div>
                    )) : (
                        <p className="text-slate-500 font-mono text-sm">No audit events recorded.</p>
                    )}
                </div>
            </div>
        </div>
    );
}
