'use client';

import React, { useEffect, useState } from 'react';
import {
    ArrowSquareOut,
    Eye,
    FloppyDisk,
    MagnifyingGlass,
    Pulse,
    ShieldWarning,
    Trash,
    UserGear,
    Warning,
} from '@phosphor-icons/react';

import { DataCard } from '@/components/DataCard';
import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

const TARGET_OPTIONS = [
    { value: 'all', label: 'All Content', help: 'Apply the rule to every supported analysis type.' },
    { value: 'media', label: 'Media Only', help: 'Use for image and video analysis results.' },
    { value: 'text', label: 'Text Only', help: 'Use for text and fake-news analysis results.' },
    { value: 'link', label: 'Link Only', help: 'Use for VirusTotal/urlscan link detections.' },
];

const VERDICT_OPTIONS = [
    { value: '', label: 'Any Verdict' },
    { value: 'AUTHENTIC', label: 'Authentic' },
    { value: 'SUSPICIOUS', label: 'Suspicious' },
    { value: 'MANIPULATED', label: 'Manipulated' },
];

const ACTION_OPTIONS = [
    { value: 'flag', label: 'Flag Content', help: 'Highlight the item in admin views.' },
    { value: 'review_queue', label: 'Send To Review', help: 'Place the item in the admin review queue.' },
    { value: 'notify_admin', label: 'Notify Admins', help: 'Create an alert for admin accounts.' },
    { value: 'quarantine', label: 'Quarantine', help: 'Lock the content pending review.' },
    { value: 'block_share', label: 'Block Sharing', help: 'Disable public share links.' },
    { value: 'block_download', label: 'Block Download', help: 'Disable downloads for non-admin users.' },
];

const DEFAULT_RULE = {
    name: '',
    description: '',
    target_type: 'all',
    verdict_match: '',
    min_score: 0.5,
    enabled: true,
    actions: ['flag', 'review_queue'],
};

function formatDate(value?: string | null) {
    return value ? new Date(value).toLocaleString() : '—';
}

function formatPercent(value?: number | null) {
    if (typeof value !== 'number') return 'N/A';
    return `${Math.round(value * 100)}%`;
}

function formatFileSize(bytes?: number | null) {
    if (typeof bytes !== 'number') return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderMediaReviewPreview(detail: any) {
    const fileUrl = detail?.filename ? api.getUploadUrl(detail.filename) : null;

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <div className="xl:col-span-2 rounded-sm border border-slate-800 bg-slate-950/60 p-4">
                    <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
                        <div className="flex gap-2 flex-wrap">
                            <StatusBadge status={detail?.media_type || 'media'} />
                            <StatusBadge status={detail?.effective_verdict || detail?.verdict || 'UNKNOWN'} />
                            <StatusBadge status={detail?.status || 'unknown'} />
                        </div>
                        <p className="text-xs font-mono text-slate-500">{detail?.original_filename || 'Untitled file'}</p>
                    </div>
                    {detail?.media_type === 'image' && fileUrl ? (
                        <img src={fileUrl} alt={detail.original_filename || 'Media preview'} className="w-full max-h-[420px] object-contain rounded-sm border border-slate-800 bg-black/30" />
                    ) : null}
                    {detail?.media_type === 'video' && fileUrl ? (
                        <video controls src={fileUrl} className="w-full max-h-[420px] rounded-sm border border-slate-800 bg-black/30" />
                    ) : null}
                </div>

                <div className="rounded-sm border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">Score</span>
                        <span className="text-sm font-mono text-slate-200">{formatPercent(detail?.overall_score)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">File Size</span>
                        <span className="text-sm font-mono text-slate-200">{formatFileSize(detail?.file_size)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">Processing</span>
                        <span className="text-sm font-mono text-slate-200">{detail?.processing_time ? `${detail.processing_time}s` : '—'}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">Created</span>
                        <span className="text-xs font-mono text-slate-400">{formatDate(detail?.created_at)}</span>
                    </div>
                    {detail?.permissions?.blocked_reason && (
                        <div className="rounded-sm border border-amber-800/50 bg-amber-950/20 p-3">
                            <p className="text-xs font-mono text-amber-200">{detail.permissions.blocked_reason}</p>
                        </div>
                    )}
                </div>
            </div>

            <div>
                <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">Evidence</p>
                {(detail?.evidence || []).length ? (
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                        {detail.evidence.slice(0, 4).map((ev: any, index: number) => (
                            <div key={`${ev.title || 'evidence'}-${index}`} className="rounded-sm border border-slate-800 bg-slate-950/60 p-4">
                                <div className="flex items-center justify-between gap-3">
                                    <p className="text-sm text-slate-200">{ev.title || 'Evidence'}</p>
                                    <StatusBadge status={ev.severity || 'info'} />
                                </div>
                                {ev.description && <p className="mt-2 text-sm text-slate-400">{ev.description}</p>}
                                {ev.file_path && (
                                    <img src={api.getEvidenceUrl(ev.file_path)} alt={ev.title || 'Evidence preview'} className="mt-3 max-h-48 w-full object-contain rounded-sm border border-slate-800 bg-black/30" />
                                )}
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-slate-500 font-mono">No forensic evidence stored for this item.</p>
                )}
            </div>
        </div>
    );
}

function renderTextReviewPreview(detail: any) {
    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <div className="xl:col-span-2 rounded-sm border border-slate-800 bg-slate-950/60 p-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
                        <div className="flex gap-2 flex-wrap">
                            <StatusBadge status={detail?.effective_verdict || detail?.verdict || 'UNKNOWN'} />
                            <StatusBadge status={detail?.status || 'unknown'} />
                        </div>
                        <p className="text-xs font-mono text-slate-500">{formatDate(detail?.created_at)}</p>
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-7 text-slate-200">{detail?.input_text || 'No text submitted.'}</p>
                </div>

                <div className="rounded-sm border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">Final Score</span>
                        <span className="text-sm font-mono text-slate-200">{formatPercent(detail?.final_score)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">NLP</span>
                        <span className="text-sm font-mono text-slate-200">{formatPercent(detail?.nlp_score)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">Fact Match</span>
                        <span className="text-sm font-mono text-slate-200">{formatPercent(detail?.fact_score)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-mono uppercase tracking-wider text-slate-500">Credibility</span>
                        <span className="text-sm font-mono text-slate-200">{formatPercent(detail?.credibility_score)}</span>
                    </div>
                    <div>
                        <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Source URL</p>
                        {detail?.source_url ? (
                            <a href={detail.source_url} target="_blank" rel="noopener noreferrer" className="text-xs font-mono text-cyan-300 break-all hover:text-cyan-200">
                                {detail.source_url}
                            </a>
                        ) : (
                            <p className="text-sm text-slate-500">No source URL provided.</p>
                        )}
                    </div>
                </div>
            </div>

            <div>
                <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">Evidence</p>
                {(detail?.evidence || []).length ? (
                    <div className="space-y-3">
                        {detail.evidence.slice(0, 4).map((ev: any, index: number) => (
                            <div key={`${ev.title || ev.source || 'evidence'}-${index}`} className="rounded-sm border border-slate-800 bg-slate-950/60 p-4">
                                <div className="flex items-center justify-between gap-3 flex-wrap">
                                    <p className="text-sm text-slate-200">{ev.title || ev.source || 'Evidence'}</p>
                                    {ev.source && <StatusBadge status={String(ev.source).toLowerCase()} />}
                                </div>
                                {ev.extract && <p className="mt-2 text-sm text-slate-400">{ev.extract}</p>}
                                {ev.url && (
                                    <a href={ev.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-xs font-mono text-cyan-300 hover:text-cyan-200">
                                        Open source
                                    </a>
                                )}
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-slate-500 font-mono">No evidence stored for this text analysis.</p>
                )}
            </div>
        </div>
    );
}

function renderLinkReviewPreview(detail: any) {
    const vtSummary = detail?.provider_summary?.virustotal || {};
    const urlscanSummary = detail?.provider_summary?.urlscan || {};

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <div className="xl:col-span-2 rounded-sm border border-slate-800 bg-slate-950/60 p-4 space-y-4">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div className="flex gap-2 flex-wrap">
                            <StatusBadge status={detail?.effective_verdict || detail?.verdict || 'UNKNOWN'} />
                            {detail?.raw_verdict && <StatusBadge status={detail.raw_verdict} />}
                            <StatusBadge status={detail?.status || 'unknown'} />
                        </div>
                        <p className="text-xs font-mono text-slate-500">{formatDate(detail?.created_at)}</p>
                    </div>
                    <div>
                        <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-1">Input URL</p>
                        <p className="text-sm font-mono break-all text-slate-200">{detail?.input_url || '—'}</p>
                    </div>
                    <div>
                        <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-1">Final URL</p>
                        <p className="text-sm font-mono break-all text-slate-200">{detail?.final_url || detail?.normalized_url || '—'}</p>
                    </div>
                    <div>
                        <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Redirect Chain</p>
                        {(detail?.redirect_chain || []).length ? (
                            <div className="space-y-2">
                                {detail.redirect_chain.slice(0, 4).map((entry: string, index: number) => (
                                    <div key={`${entry}-${index}`} className="rounded-sm border border-slate-800 bg-slate-900/60 p-3">
                                        <p className="text-[11px] font-mono uppercase tracking-wider text-slate-500">Step {index + 1}</p>
                                        <p className="mt-1 break-all text-xs font-mono text-slate-300">{entry}</p>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <p className="text-sm text-slate-500 font-mono">No redirect information recorded.</p>
                        )}
                    </div>
                </div>

                <div className="rounded-sm border border-slate-800 bg-slate-950/60 p-4 space-y-4">
                    <div>
                        <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Page Metadata</p>
                        <div className="space-y-2 text-sm text-slate-300">
                            <div className="flex items-center justify-between gap-4"><span>Domain</span><span className="font-mono text-right">{detail?.page_metadata?.domain || detail?.domain || '—'}</span></div>
                            <div className="flex items-center justify-between gap-4"><span>Title</span><span className="font-mono text-right">{detail?.page_metadata?.title || '—'}</span></div>
                            <div className="flex items-center justify-between gap-4"><span>Status</span><span className="font-mono">{detail?.page_metadata?.status || '—'}</span></div>
                            <div className="flex items-center justify-between gap-4"><span>IP</span><span className="font-mono">{detail?.page_metadata?.ip || '—'}</span></div>
                        </div>
                    </div>
                    <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-3">
                        <div className="flex items-center justify-between gap-4">
                            <p className="text-sm text-slate-200">VirusTotal</p>
                            <StatusBadge status={vtSummary?.status || 'unknown'} />
                        </div>
                        <div className="mt-2 text-xs font-mono text-slate-400 space-y-1">
                            <div>malicious {(vtSummary?.stats || {}).malicious || 0}</div>
                            <div>suspicious {(vtSummary?.stats || {}).suspicious || 0}</div>
                            <div>risk {formatPercent(vtSummary?.risk_score)}</div>
                        </div>
                    </div>
                    <div className="rounded-sm border border-slate-800 bg-slate-900/60 p-3">
                        <div className="flex items-center justify-between gap-4">
                            <p className="text-sm text-slate-200">urlscan</p>
                            <StatusBadge status={urlscanSummary?.status || 'unknown'} />
                        </div>
                        <div className="mt-2 text-xs font-mono text-slate-400 space-y-1">
                            <div>score {urlscanSummary?.score ?? '—'}</div>
                            <div>downloads {urlscanSummary?.downloads ?? '—'}</div>
                            <div>risk {formatPercent(urlscanSummary?.risk_score)}</div>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">Risk Signals</p>
                {(detail?.signals || []).length ? (
                    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                        {detail.signals.slice(0, 4).map((signal: any, index: number) => (
                            <div key={`${signal.source || 'signal'}-${index}`} className="rounded-sm border border-slate-800 bg-slate-950/60 p-4">
                                <div className="flex items-center justify-between gap-3 flex-wrap">
                                    <p className="text-sm text-slate-200">{signal.label || 'Provider signal'}</p>
                                    <div className="flex gap-2">
                                        <StatusBadge status={signal.severity || 'info'} />
                                        <StatusBadge status={signal.source || 'unknown'} />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className="text-sm text-slate-500 font-mono">No risk signals stored for this link analysis.</p>
                )}
            </div>
        </div>
    );
}

function renderQueuePreview(item: any, detail: any) {
    if (!detail) return null;
    if (item.content_type === 'text') return renderTextReviewPreview(detail);
    if (item.content_type === 'link') return renderLinkReviewPreview(detail);
    return renderMediaReviewPreview(detail);
}

function renderReviewSummary(item: any, detail: any) {
    const commonRows = [
        { label: 'Content Type', value: item.content_type || '—' },
        { label: 'Stored Verdict', value: detail?.verdict || item.verdict || '—' },
        { label: 'Effective Verdict', value: detail?.effective_verdict || item.effective_verdict || '—' },
        { label: 'Raw Verdict', value: detail?.raw_verdict || '—' },
        { label: 'Review Status', value: detail?.moderation?.review_status || item.moderation?.review_status || 'clear' },
        { label: 'Created', value: formatDate(detail?.created_at || item.created_at) },
        { label: 'Share Access', value: ((detail?.permissions?.can_share ?? item.permissions?.can_share) ? 'enabled' : 'blocked') },
        { label: 'Download Access', value: ((detail?.permissions?.can_download ?? item.permissions?.can_download) ? 'enabled' : 'blocked') },
    ];

    let specificRows = [];

    if (item.content_type === 'text') {
        specificRows = [
            { label: 'Final Score', value: formatPercent(detail?.final_score) },
            { label: 'NLP Score', value: formatPercent(detail?.nlp_score) },
            { label: 'Fact Match', value: formatPercent(detail?.fact_score) },
            { label: 'Credibility', value: formatPercent(detail?.credibility_score) },
            { label: 'Claims', value: String((detail?.claims || []).length) },
            { label: 'Evidence Items', value: String((detail?.evidence || []).length) },
        ];
    } else if (item.content_type === 'link') {
        specificRows = [
            { label: 'Risk Score', value: formatPercent(detail?.risk_score) },
            { label: 'Domain', value: detail?.domain || detail?.page_metadata?.domain || '—' },
            { label: 'VirusTotal', value: detail?.provider_summary?.virustotal?.status || 'unknown' },
            { label: 'urlscan', value: detail?.provider_summary?.urlscan?.status || 'unknown' },
            { label: 'Signals', value: String((detail?.signals || []).length) },
            { label: 'Redirects', value: String((detail?.redirect_chain || []).length) },
        ];
    } else {
        specificRows = [
            { label: 'Media Type', value: detail?.media_type || '—' },
            { label: 'Score', value: formatPercent(detail?.overall_score) },
            { label: 'File Size', value: formatFileSize(detail?.file_size) },
            { label: 'Processing Time', value: detail?.processing_time ? `${detail.processing_time}s` : '—' },
            { label: 'Evidence Items', value: String((detail?.evidence || []).length) },
            { label: 'Filename', value: detail?.original_filename || '—' },
        ];
    }

    return (
        <div className="rounded-sm border border-slate-800 bg-slate-950/40 p-4">
            <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-4">Analysis Summary</p>
            <div className="space-y-2">
                {[...commonRows, ...specificRows].map((row) => (
                    <div key={`${row.label}-${row.value}`} className="flex items-start justify-between gap-4 text-sm">
                        <span className="text-slate-500">{row.label}</span>
                        <span className="text-right font-mono text-slate-200 break-all">{row.value}</span>
                    </div>
                ))}
            </div>
            {detail?.permissions?.blocked_reason && (
                <div className="mt-4 rounded-sm border border-amber-800/50 bg-amber-950/20 p-3">
                    <p className="text-xs font-mono text-amber-200">{detail.permissions.blocked_reason}</p>
                </div>
            )}
        </div>
    );
}

export default function AdminPage() {
    const [loading, setLoading] = useState(true);
    const [currentUser, setCurrentUser] = useState<any>(null);
    const [overview, setOverview] = useState<any>(null);
    const [users, setUsers] = useState<any[]>([]);
    const [rules, setRules] = useState<any[]>([]);
    const [queue, setQueue] = useState<any[]>([]);
    const [ruleForm, setRuleForm] = useState<any>(DEFAULT_RULE);
    const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
    const [message, setMessage] = useState('');
    const [messageType, setMessageType] = useState<'success' | 'error'>('success');
    const [busyAction, setBusyAction] = useState<string | null>(null);
    const [reviewDrafts, setReviewDrafts] = useState<Record<string, any>>({});
    const [openedForReview, setOpenedForReview] = useState<Record<string, boolean>>({});
    const [queueDetails, setQueueDetails] = useState<Record<string, any>>({});
    const [queueDetailErrors, setQueueDetailErrors] = useState<Record<string, string>>({});
    const [userQuery, setUserQuery] = useState('');

    async function load() {
        try {
            const [meData, overviewData, usersData, rulesData, queueData] = await Promise.all([
                api.getMe(),
                api.getAdminOverview(),
                api.getAdminUsers(),
                api.getRules(),
                api.getReviewQueue(),
            ]);
            setCurrentUser(meData);
            setOverview(overviewData);
            setUsers(usersData.users || []);
            setRules(rulesData.rules || []);
            setQueue(queueData.items || []);
        } catch (error: any) {
            setMessageType('error');
            setMessage(error.message || 'Failed to load admin data');
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        load();
    }, []);

    const setFeedback = (text: string, type: 'success' | 'error' = 'success') => {
        setMessageType(type);
        setMessage(text);
    };

    const withBusyAction = async (actionKey: string, task: () => Promise<void>) => {
        setBusyAction(actionKey);
        try {
            await task();
        } catch (error: any) {
            setFeedback(error.message || 'Action failed', 'error');
        } finally {
            setBusyAction((current) => (current === actionKey ? null : current));
        }
    };

    const toggleAction = (action: string) => {
        setRuleForm((prev: any) => {
            const hasAction = prev.actions.includes(action);
            return {
                ...prev,
                actions: hasAction ? prev.actions.filter((item: string) => item !== action) : [...prev.actions, action],
            };
        });
    };

    const buildReviewDraft = (item: any, overrides: Record<string, unknown> = {}) => ({
        manual_verdict: item.moderation?.manual_verdict || item.effective_verdict || item.verdict || '',
        review_status: 'reviewed',
        review_notes: '',
        is_flagged: !!item.moderation?.is_flagged,
        is_quarantined: !!item.moderation?.is_quarantined,
        block_share: !item.permissions?.can_share,
        block_download: !item.permissions?.can_download,
        ...(reviewDrafts[item.id] || {}),
        ...overrides,
    });

    const saveRule = async () => {
        if (!ruleForm.name.trim()) {
            setFeedback('Rule name is required', 'error');
            return;
        }
        if (!ruleForm.actions.length) {
            setFeedback('Select at least one rule action', 'error');
            return;
        }

        await withBusyAction('rule:save', async () => {
            if (editingRuleId) {
                await api.updateRule(editingRuleId, ruleForm);
                setFeedback('Rule updated');
            } else {
                await api.createRule(ruleForm);
                setFeedback('Rule created');
            }
            setRuleForm(DEFAULT_RULE);
            setEditingRuleId(null);
            await load();
        });
    };

    const editRule = (rule: any) => {
        setMessage('');
        setEditingRuleId(rule.id);
        setRuleForm({
            name: rule.name,
            description: rule.description || '',
            target_type: rule.target_type || 'all',
            verdict_match: rule.verdict_match || '',
            min_score: rule.min_score ?? 0.5,
            enabled: !!rule.enabled,
            actions: rule.actions || [],
        });
    };

    const removeRule = async (ruleId: number) => {
        if (typeof window !== 'undefined' && !window.confirm('Delete this moderation rule?')) {
            return;
        }
        await withBusyAction(`rule:delete:${ruleId}`, async () => {
            await api.deleteRule(ruleId);
            setFeedback('Rule deleted');
            if (editingRuleId === ruleId) {
                setEditingRuleId(null);
                setRuleForm(DEFAULT_RULE);
            }
            await load();
        });
    };

    const changeUserStatus = async (userId: number, status: 'active' | 'suspended') => {
        if (currentUser?.id === userId && status === 'suspended') {
            setFeedback('You cannot suspend your own admin account', 'error');
            return;
        }
        await withBusyAction(`user:${userId}:${status}`, async () => {
            await api.updateUserStatus(userId, status);
            setFeedback(`User status set to ${status}`);
            await load();
        });
    };

    const updateReviewDraft = (item: any, patch: Record<string, unknown>) => {
        setReviewDrafts((prev) => ({
            ...prev,
            [item.id]: buildReviewDraft(item, { ...(prev[item.id] || {}), ...patch }),
        }));
    };

    const getQueuePath = (item: any) => {
        if (item.content_type === 'text') return `/dashboard/text-history/${item.content_id}`;
        if (item.content_type === 'link') return `/dashboard/link-analysis/${item.content_id}`;
        return `/dashboard/analysis/${item.content_id}`;
    };

    const openQueueItem = (item: any) => {
        const path = getQueuePath(item);
        if (typeof window !== 'undefined') {
            window.open(path, '_blank', 'noopener,noreferrer');
        }
        setOpenedForReview((prev) => ({ ...prev, [item.id]: true }));
        setFeedback(`Opened content ${item.id} in a new tab`);
    };

    const inspectQueueItem = async (item: any) => {
        const actionKey = `inspect:${item.id}`;
        setBusyAction(actionKey);
        try {
            let detail;
            if (item.content_type === 'text') {
                detail = await api.getTextAnalysis(item.content_id);
            } else if (item.content_type === 'link') {
                detail = await api.getLinkAnalysis(item.content_id);
            } else {
                detail = await api.getAnalysis(item.content_id);
            }

            setQueueDetails((prev) => ({ ...prev, [item.id]: detail }));
            setQueueDetailErrors((prev) => {
                const next = { ...prev };
                delete next[item.id];
                return next;
            });
            setOpenedForReview((prev) => ({ ...prev, [item.id]: true }));
            setFeedback(`Loaded content ${item.id} for direct review`);
        } catch (error: any) {
            const errorMessage = error.message || 'Failed to load content for review';
            setQueueDetailErrors((prev) => ({ ...prev, [item.id]: errorMessage }));
            setFeedback(errorMessage, 'error');
        } finally {
            setBusyAction((current) => (current === actionKey ? null : current));
        }
    };

    const submitReview = async (item: any) => {
        if (!openedForReview[item.id]) {
            setFeedback('Inspect the actual content before applying a review decision', 'error');
            return;
        }
        const draft = buildReviewDraft(item);
        const payload = {
            ...draft,
            manual_verdict: draft.manual_verdict || null,
            review_notes: draft.review_notes?.trim() || null,
        };
        await withBusyAction(`review:${item.id}`, async () => {
            await api.moderateContent(item.content_type, item.content_id, payload);
            const keepsInQueue = payload.review_status === 'pending_review';

            if (!keepsInQueue) {
                setQueue((prev) => prev.filter((entry) => entry.id !== item.id));
                setQueueDetails((prev) => {
                    const next = { ...prev };
                    delete next[item.id];
                    return next;
                });
                setQueueDetailErrors((prev) => {
                    const next = { ...prev };
                    delete next[item.id];
                    return next;
                });
                setOpenedForReview((prev) => {
                    const next = { ...prev };
                    delete next[item.id];
                    return next;
                });
                setFeedback(`Content ${item.id} reviewed and removed from the active queue`);
            } else {
                setFeedback(`Content ${item.id} review saved and kept in the queue`);
            }

            setReviewDrafts((prev) => {
                const next = { ...prev };
                delete next[item.id];
                return next;
            });
            await load();
        });
    };

    const filteredUsers = users.filter((user) => {
        const query = userQuery.trim().toLowerCase();
        if (!query) return true;
        return [user.username, user.email, user.role, user.status]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(query));
    });

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-red-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-red-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Loading Admin Console...</p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                    <ShieldWarning size={28} weight="duotone" className="text-red-400" />
                    Admin Console
                </h1>
                <p className="text-slate-500 mt-1 font-mono text-sm">User monitoring, moderation rules, review queue, and system activity</p>
            </div>

            {message && (
                <div className={`rounded-sm px-4 py-3 text-sm font-mono ${messageType === 'error' ? 'border border-red-800/40 bg-red-950/20 text-red-200' : 'border border-cyan-800/40 bg-cyan-950/20 text-cyan-200'}`}>
                    {message}
                </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <DataCard title="Total Users" value={overview?.counts?.total_users || 0} icon={UserGear} />
                <DataCard title="Suspended Users" value={overview?.counts?.suspended_users || 0} icon={Warning} className="border-red-800/40" />
                <DataCard title="Flagged Content" value={overview?.counts?.flagged_content || 0} icon={ShieldWarning} className="border-amber-800/40" />
                <DataCard title="Review Queue" value={overview?.counts?.review_queue || 0} icon={ShieldWarning} className="border-orange-800/40" />
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
                        <div>
                            <h2 className="text-sm font-mono text-slate-400 uppercase tracking-widest">Users</h2>
                            <p className="mt-1 text-xs text-slate-500">Search, verify status, and act on accounts without scrolling cards.</p>
                        </div>
                        <div className="w-full md:w-72 relative">
                            <MagnifyingGlass size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                            <input
                                className="input-modern pl-9"
                                placeholder="Search username, email, role"
                                value={userQuery}
                                onChange={(e) => setUserQuery(e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="mb-4 flex items-center justify-between gap-4 text-xs font-mono text-slate-500">
                        <span>{filteredUsers.length} visible users</span>
                        <span>{users.length} total records</span>
                    </div>

                    <div className="overflow-auto rounded-sm border border-slate-800 bg-slate-900/40 max-h-[420px]">
                        <table className="w-full min-w-[860px]">
                            <thead className="bg-slate-950/60 sticky top-0">
                                <tr>
                                    <th className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-wider text-slate-500">User</th>
                                    <th className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-wider text-slate-500">Role / Status</th>
                                    <th className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-wider text-slate-500">Content</th>
                                    <th className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-wider text-slate-500">Created</th>
                                    <th className="px-4 py-3 text-left text-[11px] font-mono uppercase tracking-wider text-slate-500">Last Login</th>
                                    <th className="px-4 py-3 text-right text-[11px] font-mono uppercase tracking-wider text-slate-500">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800">
                                {filteredUsers.length ? filteredUsers.map((user) => (
                                    <tr key={user.id} className="align-top">
                                        <td className="px-4 py-4">
                                            <p className="text-sm font-medium text-slate-200">{user.username}</p>
                                            <p className="mt-1 text-xs font-mono text-slate-500">{user.email}</p>
                                            {currentUser?.id === user.id && (
                                                <span className="mt-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider border border-cyan-800 bg-cyan-950/30 text-cyan-200">
                                                    You
                                                </span>
                                            )}
                                        </td>
                                        <td className="px-4 py-4">
                                            <div className="flex gap-2 flex-wrap">
                                                <StatusBadge status={user.role} />
                                                <StatusBadge status={user.status || 'active'} />
                                            </div>
                                        </td>
                                        <td className="px-4 py-4 text-xs font-mono text-slate-400">
                                            <div>media {user.media_count}</div>
                                            <div className="mt-1">text {user.text_count}</div>
                                            <div className="mt-1">link {user.link_count || 0}</div>
                                        </td>
                                        <td className="px-4 py-4 text-xs font-mono text-slate-500">{formatDate(user.created_at)}</td>
                                        <td className="px-4 py-4 text-xs font-mono text-slate-500">{formatDate(user.last_login_at)}</td>
                                        <td className="px-4 py-4">
                                            <div className="flex items-center justify-end gap-2">
                                                <button
                                                    onClick={() => changeUserStatus(user.id, 'active')}
                                                    disabled={busyAction === `user:${user.id}:active` || user.status === 'active'}
                                                    className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
                                                >
                                                    {busyAction === `user:${user.id}:active` ? 'Updating...' : 'Activate'}
                                                </button>
                                                <button
                                                    onClick={() => changeUserStatus(user.id, 'suspended')}
                                                    disabled={busyAction === `user:${user.id}:suspended` || user.status === 'suspended' || currentUser?.id === user.id}
                                                    className="btn-danger disabled:opacity-50 disabled:cursor-not-allowed"
                                                >
                                                    {busyAction === `user:${user.id}:suspended` ? 'Updating...' : 'Suspend'}
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                )) : (
                                    <tr>
                                        <td colSpan={6} className="px-4 py-10 text-center text-sm font-mono text-slate-500">
                                            No users match the current search.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                    <p className="mt-3 text-xs font-mono text-slate-500">Self-suspension is blocked for the currently logged-in admin account.</p>
                </div>

                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                    <h2 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">
                        {editingRuleId ? 'Edit Moderation Rule' : 'Create Moderation Rule'}
                    </h2>
                    <div className="grid grid-cols-1 gap-4">
                        <div>
                            <label className="block text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">Rule Name</label>
                            <input className="input-modern" placeholder="Example: Review suspicious links" value={ruleForm.name} onChange={(e) => setRuleForm({ ...ruleForm, name: e.target.value })} />
                        </div>
                        <div>
                            <label className="block text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">What should this rule do?</label>
                            <textarea className="input-modern min-h-24" placeholder="Short explanation shown to admins later" value={ruleForm.description} onChange={(e) => setRuleForm({ ...ruleForm, description: e.target.value })} />
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">Content Type</label>
                                <select className="input-modern" value={ruleForm.target_type} onChange={(e) => setRuleForm({ ...ruleForm, target_type: e.target.value })}>
                                    {TARGET_OPTIONS.map((option) => (
                                        <option key={option.value} value={option.value}>{option.label}</option>
                                    ))}
                                </select>
                                <p className="mt-2 text-xs text-slate-500">
                                    {TARGET_OPTIONS.find((option) => option.value === ruleForm.target_type)?.help}
                                </p>
                            </div>
                            <div>
                                <label className="block text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">When Verdict Is</label>
                                <select className="input-modern" value={ruleForm.verdict_match} onChange={(e) => setRuleForm({ ...ruleForm, verdict_match: e.target.value })}>
                                    {VERDICT_OPTIONS.map((option) => (
                                        <option key={option.value || 'any'} value={option.value}>{option.label}</option>
                                    ))}
                                </select>
                                <p className="mt-2 text-xs text-slate-500">Leave this as “Any Verdict” if the score threshold alone should trigger the rule.</p>
                            </div>
                        </div>
                        <div>
                            <div className="flex items-center justify-between gap-4">
                                <label className="block text-xs font-mono text-slate-500 uppercase tracking-wider">Minimum Confidence</label>
                                <span className="text-sm font-mono text-slate-300">{Math.round((ruleForm.min_score || 0) * 100)}%</span>
                            </div>
                            <input
                                className="mt-3 w-full accent-blue-500"
                                type="range"
                                min="0"
                                max="1"
                                step="0.05"
                                value={ruleForm.min_score}
                                onChange={(e) => setRuleForm({ ...ruleForm, min_score: Number(e.target.value) })}
                            />
                            <p className="mt-2 text-xs text-slate-500">Higher values make the rule stricter. Lower values catch more borderline cases.</p>
                        </div>
                        <div>
                            <label className="block text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">Actions To Apply</label>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {ACTION_OPTIONS.map((action) => (
                                    <button
                                        key={action.value}
                                        onClick={() => toggleAction(action.value)}
                                        className={`rounded-sm border px-4 py-3 text-left transition-colors ${ruleForm.actions.includes(action.value) ? 'border-blue-600 bg-blue-950/30 text-blue-100' : 'border-slate-700 bg-slate-900/50 text-slate-300 hover:bg-slate-900'}`}
                                    >
                                        <p className="text-sm font-medium">{action.label}</p>
                                        <p className="mt-1 text-xs text-slate-500">{action.help}</p>
                                    </button>
                                ))}
                            </div>
                        </div>
                        <label className="flex items-center gap-3 text-sm text-slate-300">
                            <input type="checkbox" checked={ruleForm.enabled} onChange={(e) => setRuleForm({ ...ruleForm, enabled: e.target.checked })} />
                            Enabled
                        </label>
                        <div className="flex gap-3">
                            <button onClick={saveRule} disabled={busyAction === 'rule:save'} className="btn-primary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed">
                                <FloppyDisk size={16} />
                                {busyAction === 'rule:save' ? 'Saving...' : 'Save Rule'}
                            </button>
                            {editingRuleId && (
                                <button onClick={() => { setEditingRuleId(null); setRuleForm(DEFAULT_RULE); setMessage(''); }} className="btn-secondary">
                                    Cancel Edit
                                </button>
                            )}
                        </div>
                    </div>

                    <div className="mt-6 space-y-3 max-h-[320px] overflow-auto pr-2">
                        {rules.map((rule) => (
                            <div key={rule.id} className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                                <div className="flex items-start justify-between gap-3">
                                    <div>
                                        <p className="text-sm font-medium text-slate-200">{rule.name}</p>
                                        <p className="mt-1 text-xs text-slate-500">{rule.description}</p>
                                        <div className="mt-2 flex gap-2 flex-wrap">
                                            <StatusBadge status={rule.target_type} />
                                            {rule.verdict_match && <StatusBadge status={rule.verdict_match} />}
                                            <StatusBadge status={rule.enabled ? 'active' : 'suspended'} />
                                        </div>
                                    </div>
                                    <div className="flex gap-2">
                                        <button onClick={() => editRule(rule)} className="btn-secondary">Edit</button>
                                        <button
                                            onClick={() => removeRule(rule.id)}
                                            disabled={busyAction === `rule:delete:${rule.id}`}
                                            className="btn-danger flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            <Trash size={14} />
                                            {busyAction === `rule:delete:${rule.id}` ? 'Deleting...' : 'Delete'}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                <h2 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Review Queue</h2>
                <div className="space-y-4">
                    {queue.length ? queue.map((item) => {
                        const draft = reviewDrafts[item.id] || buildReviewDraft(item);
                        const reviewDetail = queueDetails[item.id];
                        const inspectError = queueDetailErrors[item.id];
                        return (
                            <div key={item.id} className="rounded-sm border border-slate-800 bg-slate-900/50 p-5">
                                <div className="flex items-start justify-between gap-4 flex-wrap">
                                    <div>
                                        <div className="flex gap-2 flex-wrap">
                                            <StatusBadge status={item.kind || item.content_type} />
                                            <StatusBadge status={item.effective_verdict || item.verdict || 'UNKNOWN'} />
                                            <StatusBadge status={item.moderation?.review_status || 'clear'} />
                                        </div>
                                        <p className="mt-3 text-slate-200 font-medium">{item.title}</p>
                                        <p className="mt-2 text-sm text-slate-400 max-w-2xl">
                                            {item.preview_text || 'Open the content to inspect the full analysis before reviewing it.'}
                                        </p>
                                        <p className="mt-2 text-xs font-mono text-slate-500">{new Date(item.created_at).toLocaleString()}</p>
                                        <div className="mt-3 text-xs font-mono text-slate-500 space-y-1">
                                            <div>Sharing {item.permissions?.can_share ? 'enabled' : 'blocked'}</div>
                                            <div>Download {item.permissions?.can_download ? 'enabled' : 'blocked'}</div>
                                        </div>
                                    </div>
                                    <div className="grid grid-cols-1 gap-3 min-w-[260px]">
                                        <button
                                            onClick={() => inspectQueueItem(item)}
                                            disabled={busyAction === `inspect:${item.id}`}
                                            className="btn-secondary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            <Eye size={16} />
                                            {busyAction === `inspect:${item.id}` ? 'Loading Content...' : reviewDetail ? 'Refresh Direct Review' : 'Inspect Content Here'}
                                        </button>
                                        <button onClick={() => openQueueItem(item)} className="btn-secondary flex items-center justify-center gap-2">
                                            <ArrowSquareOut size={16} />
                                            Open Full Detail Page
                                        </button>
                                    </div>
                                </div>
                                <div className="mt-4 rounded-sm border border-slate-800 bg-slate-950/40 p-4">
                                    <div className="flex items-center justify-between gap-4 flex-wrap mb-4">
                                        <div>
                                            <p className="text-xs font-mono uppercase tracking-wider text-slate-500">Direct Content Review</p>
                                            <p className="mt-1 text-sm text-slate-400">Inspect the real media, text, or link evidence here before applying a moderation decision.</p>
                                        </div>
                                        {reviewDetail && (
                                            <div className="flex gap-2 flex-wrap">
                                                <StatusBadge status={item.content_type} />
                                                <StatusBadge status={reviewDetail.effective_verdict || reviewDetail.verdict || 'UNKNOWN'} />
                                            </div>
                                        )}
                                    </div>
                                    {inspectError ? (
                                        <p className="text-sm font-mono text-red-300">{inspectError}</p>
                                    ) : reviewDetail ? (
                                        renderQueuePreview(item, reviewDetail)
                                    ) : (
                                        <p className="text-sm font-mono text-slate-500">Use “Inspect Content Here” to load the actual item into the admin queue.</p>
                                    )}
                                </div>
                                <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-4">
                                    {reviewDetail ? (
                                        renderReviewSummary(item, reviewDetail)
                                    ) : (
                                        <div className="rounded-sm border border-slate-800 bg-slate-950/40 p-4">
                                            <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">Analysis Summary</p>
                                            <p className="text-sm font-mono text-slate-500">Inspect the content first to load the analysis summary here.</p>
                                        </div>
                                    )}

                                    <div className="rounded-sm border border-slate-800 bg-slate-950/40 p-4">
                                        <p className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-4">Admin Decision</p>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                            <select className="input-modern" value={draft.manual_verdict} onChange={(e) => updateReviewDraft(item, { manual_verdict: e.target.value })}>
                                                <option value="">No override</option>
                                                <option value="AUTHENTIC">AUTHENTIC</option>
                                                <option value="SUSPICIOUS">SUSPICIOUS</option>
                                                <option value="MANIPULATED">MANIPULATED</option>
                                            </select>
                                            <select className="input-modern" value={draft.review_status} onChange={(e) => updateReviewDraft(item, { review_status: e.target.value })}>
                                                <option value="reviewed">reviewed</option>
                                                <option value="pending_review">pending_review</option>
                                                <option value="clear">clear</option>
                                            </select>
                                            <label className="flex items-center gap-2 text-sm text-slate-300">
                                                <input type="checkbox" checked={!!draft.is_quarantined} onChange={(e) => updateReviewDraft(item, { is_quarantined: e.target.checked })} />
                                                Quarantine
                                            </label>
                                            <label className="flex items-center gap-2 text-sm text-slate-300">
                                                <input type="checkbox" checked={!!draft.block_download} onChange={(e) => updateReviewDraft(item, { block_download: e.target.checked })} />
                                                Block Download
                                            </label>
                                            <label className="flex items-center gap-2 text-sm text-slate-300">
                                                <input type="checkbox" checked={!!draft.block_share} onChange={(e) => updateReviewDraft(item, { block_share: e.target.checked })} />
                                                Block Share
                                            </label>
                                            <label className="flex items-center gap-2 text-sm text-slate-300">
                                                <input type="checkbox" checked={!!draft.is_flagged} onChange={(e) => updateReviewDraft(item, { is_flagged: e.target.checked })} />
                                                Flagged
                                            </label>
                                        </div>
                                        <div className="mt-3 rounded-sm border border-slate-800 bg-slate-900/50 p-3">
                                            <p className="text-xs font-mono text-slate-500">
                                                If `Quarantine` stays enabled, the content remains restricted even after review is marked `reviewed`.
                                            </p>
                                        </div>
                                        <textarea
                                            className="input-modern min-h-24 mt-4"
                                            placeholder="Review notes"
                                            value={draft.review_notes}
                                            onChange={(e) => updateReviewDraft(item, { review_notes: e.target.value })}
                                        />
                                        <div className="mt-4 flex items-center justify-between gap-4">
                                            <p className="text-xs font-mono text-slate-500">
                                                {openedForReview[item.id] ? 'Content inspected. Review controls are unlocked.' : 'Load the underlying content first so the decision is based on actual evidence.'}
                                            </p>
                                            <button
                                                onClick={() => submitReview(item)}
                                                disabled={busyAction === `review:${item.id}` || !openedForReview[item.id]}
                                                className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {busyAction === `review:${item.id}` ? 'Applying...' : 'Apply Review Decision'}
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    }) : (
                        <p className="text-slate-500 font-mono text-sm">The review queue is currently empty.</p>
                    )}
                </div>
            </div>

            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                <h2 className="text-sm font-mono text-slate-400 uppercase tracking-widest mb-4">Recent System Activity</h2>
                <div className="space-y-3">
                    {(overview?.recent_activity || []).map((event: any) => (
                        <div key={event.id} className="rounded-sm border border-slate-800 bg-slate-900/50 p-4">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <p className="text-sm text-slate-200">{event.action}</p>
                                    <p className="mt-1 text-xs font-mono text-slate-500">
                                        {event.actor_username || 'system'} · {event.target_type}#{event.target_id ?? '—'}
                                    </p>
                                </div>
                                <p className="text-xs font-mono text-slate-500">{new Date(event.created_at).toLocaleString()}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
