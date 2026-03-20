'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { getCommonVerdict } from '@/lib/verdicts';
import {
    NewspaperClipping,
    MagnifyingGlass,
    ShieldCheck,
    ShieldWarning,
    Warning,
    CheckCircle,
    Question,
    ArrowRight,
    Lightning,
    Globe,
    BookOpen,
    Scales,
    ChartBar,
    Info,
    Lightbulb,
    Pulse,
    CaretDown,
    CaretUp,
} from '@phosphor-icons/react';

interface AnalysisResult {
    id: number;
    source_url?: string | null;
    verdict: string;
    effective_verdict?: string;
    verdict_label: string;
    final_score: number;
    nlp_score: number;
    fact_score: number;
    credibility_score: number;
    claims: any[];
    evidence: any[];
    explanation: any;
    semantic_results: any[];
    claim_context?: any;
    llm_fact_check?: any;
    processing_time: number;
}

const VERDICT_CONFIG: Record<string, { color: string; bg: string; border: string; icon: React.ElementType }> = {
    MANIPULATED: { color: 'text-red-400', bg: 'bg-red-950/40', border: 'border-red-700/50', icon: ShieldWarning },
    UNVERIFIED: { color: 'text-slate-400', bg: 'bg-slate-800/40', border: 'border-slate-600/50', icon: Question },
    SUSPICIOUS: { color: 'text-yellow-400', bg: 'bg-yellow-950/40', border: 'border-yellow-700/50', icon: Warning },
    AUTHENTIC: { color: 'text-green-400', bg: 'bg-green-950/40', border: 'border-green-700/50', icon: ShieldCheck },
    UNKNOWN: { color: 'text-slate-400', bg: 'bg-slate-800/40', border: 'border-slate-600/50', icon: Question },
};

export default function TextAnalysisPage() {
    const [text, setText] = useState('');
    const [sourceUrl, setSourceUrl] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);
    const [error, setError] = useState('');
    const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
        claims: true,
        evidence: true,
        explanation: true,
        scores: false,
        semantics: false,
    });

    const toggleSection = (section: string) => {
        setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
    };

    const handleAnalyze = async () => {
        if (!text.trim()) return;
        setLoading(true);
        setError('');
        setResult(null);

        try {
            const data = await api.analyzeText(text.trim(), sourceUrl.trim() || undefined);
            setResult(data);
        } catch (err: any) {
            setError(err.message || 'Analysis failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const getVerdictConfig = (verdict: string) => {
        return VERDICT_CONFIG[verdict] || VERDICT_CONFIG.UNKNOWN;
    };

    const getConfidenceDisplay = (verdict: string, score: number) => {
        if (verdict === 'AUTHENTIC') {
            return {
                label: 'Authentic Confidence',
                percent: Math.round((1 - score) * 100),
            };
        }

        if (verdict === 'MANIPULATED') {
            return {
                label: 'Manipulated Confidence',
                percent: Math.round(score * 100),
            };
        }

        return {
            label: 'Verification Risk',
            percent: Math.round(score * 100),
        };
    };

    const commonVerdict = result
        ? (getCommonVerdict(result.effective_verdict || result.verdict) || 'UNKNOWN')
        : 'UNKNOWN';
    const confidenceDisplay = result
        ? getConfidenceDisplay(commonVerdict, result.final_score)
        : { label: 'Confidence', percent: 0 };
    const config = result ? getVerdictConfig(commonVerdict) : null;
    const VerdictIcon = config?.icon || Question;
    const evidenceItems = result?.evidence?.filter((e: any) => e.type !== 'none') || [];
    const evidenceFallback = result?.evidence?.find((e: any) => e.type === 'none');
    const llmFactCheck = result?.llm_fact_check || result?.explanation?.llm_fact_check || null;
    const claimContext = result?.claim_context || result?.explanation?.claim_context || null;
    const llmCommonVerdict = getCommonVerdict(llmFactCheck?.verdict) || 'UNVERIFIED';
    const llmConfig = llmFactCheck?.verdict ? getVerdictConfig(llmCommonVerdict) : VERDICT_CONFIG.UNVERIFIED;
    const llmConfidence = typeof llmFactCheck?.confidence === 'number'
        ? Math.round(llmFactCheck.confidence * 100)
        : null;
    const llmStatusLabel = !llmFactCheck?.enabled
        ? 'Groq not configured'
        : llmFactCheck?.available
            ? 'Checked by Groq'
            : 'Groq unavailable';
    const llmReviewBar = llmFactCheck?.enabled
        ? {
            label: 'LLM Review',
            value: llmFactCheck?.confidence != null
                ? (
                    llmCommonVerdict === 'AUTHENTIC'
                        ? 1 - llmFactCheck.confidence
                        : llmCommonVerdict === 'MANIPULATED'
                            ? llmFactCheck.confidence
                            : 0.5
                )
                : 0.5,
            color: llmCommonVerdict === 'AUTHENTIC'
                ? '#22c55e'
                : llmCommonVerdict === 'MANIPULATED'
                    ? '#f97316'
                    : '#94a3b8',
        }
        : null;
    const scoreBars = [
        { label: 'Provider Consensus', value: result?.nlp_score, color: '#06b6d4' },
        { label: 'Claim Match', value: result?.fact_score, color: '#a855f7' },
        { label: 'Coverage Risk', value: result?.credibility_score, color: '#f59e0b' },
        ...(llmReviewBar ? [llmReviewBar] : []),
    ];

    return (
        <div className="space-y-8 max-w-5xl mx-auto">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                    <NewspaperClipping size={28} weight="duotone" className="text-cyan-400" />
                    Fake News Detector
                </h1>
                <p className="text-slate-500 mt-1 font-mono text-sm">
                    Dynamic claim typing with source-first verification and fallback Groq review
                </p>
            </div>

            {/* Input Section */}
            <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6 space-y-4">
                <label className="block text-xs font-mono text-slate-400 uppercase tracking-widest mb-2">
                    <MagnifyingGlass size={14} weight="duotone" className="inline mr-2" />
                    Enter Text to Analyze
                </label>
                <textarea
                    id="text-input"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder='Paste a news article, social media post, or headline... e.g. "NASA confirms aliens landed in India"'
                    rows={5}
                    maxLength={10000}
                    className="w-full bg-slate-900/60 border border-slate-700/50 rounded-sm px-4 py-3 text-slate-200 font-mono text-sm placeholder:text-slate-600 focus:outline-none focus:border-cyan-600/60 focus:ring-1 focus:ring-cyan-600/20 transition-colors resize-y"
                />
                <div className="flex items-center gap-4">
                    <div className="flex-1">
                        <label className="block text-xs font-mono text-slate-500 mb-1">
                            <Globe size={12} className="inline mr-1" />
                            Source URL (optional)
                        </label>
                        <input
                            id="source-url-input"
                            type="url"
                            value={sourceUrl}
                            onChange={(e) => setSourceUrl(e.target.value)}
                            placeholder="https://example.com/article"
                            className="w-full bg-slate-900/60 border border-slate-700/50 rounded-sm px-3 py-2 text-slate-300 font-mono text-xs placeholder:text-slate-600 focus:outline-none focus:border-cyan-600/60 transition-colors"
                        />
                    </div>
                    <div className="pt-5">
                        <button
                            id="analyze-btn"
                            onClick={handleAnalyze}
                            disabled={loading || !text.trim()}
                            className="bg-gradient-to-r from-cyan-700 to-blue-700 hover:from-cyan-600 hover:to-blue-600 disabled:from-slate-700 disabled:to-slate-700 disabled:text-slate-500 text-white font-bold text-sm uppercase tracking-wider px-8 py-2.5 rounded-sm transition-all flex items-center gap-2 shadow-lg shadow-cyan-900/20 hover:shadow-cyan-800/30 disabled:shadow-none"
                        >
                            {loading ? (
                                <>
                                    <Pulse size={18} className="animate-pulse" />
                                    Analyzing...
                                </>
                            ) : (
                                <>
                                    <Lightning size={18} weight="fill" />
                                    Analyze
                                </>
                            )}
                        </button>
                    </div>
                </div>
                <p className="text-xs text-slate-600 font-mono">{text.length}/10,000 characters</p>
            </div>

            {/* Error */}
            {error && (
                <div className="bg-red-950/30 border border-red-800/50 rounded-sm p-4 flex items-center gap-3">
                    <Warning size={20} className="text-red-400 flex-shrink-0" />
                    <p className="text-red-300 text-sm font-mono">{error}</p>
                </div>
            )}

            {/* Loading Animation */}
            {loading && (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-12 flex flex-col items-center gap-4">
                    <div className="relative">
                        <div className="w-16 h-16 rounded-full border-2 border-slate-700 border-t-cyan-500 animate-spin" />
                        <ShieldCheck size={28} className="absolute inset-0 m-auto text-cyan-400 animate-pulse" />
                    </div>
                    <div className="text-center space-y-2">
                        <p className="text-slate-400 font-mono text-sm animate-pulse uppercase tracking-wider">
                            Running Analysis Pipeline
                        </p>
                        <div className="flex flex-wrap justify-center gap-2 text-xs font-mono text-slate-600">
                            {['Preprocessing', 'Claim Extraction', 'News APIs', 'Wikipedia', 'Groq LLM', 'Evidence Scoring'].map((step, i) => (
                                <span key={step} className="px-2 py-1 bg-slate-900/50 border border-slate-800/50 rounded-sm animate-pulse" style={{ animationDelay: `${i * 200}ms` }}>
                                    {step}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Results */}
            {result && config && (
                <div className="space-y-6 animate-in fade-in duration-500">

                    {/* Verdict Banner */}
                    <div className={`${config.bg} border ${config.border} rounded-sm p-6`}>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <div className={`p-3 rounded-full ${config.bg} border ${config.border}`}>
                                    <VerdictIcon size={32} weight="duotone" className={config.color} />
                                </div>
                                <div>
                                    <h2 className={`text-2xl font-chivo font-bold uppercase tracking-wider ${config.color}`}>
                                        {commonVerdict}
                                    </h2>
                                    <p className="text-slate-400 font-mono text-sm mt-1">
                                        {result.explanation?.summary || 'Analysis complete'}
                                    </p>
                                    {result.verdict_label && (
                                        <p className="text-slate-500 font-mono text-xs mt-2 uppercase tracking-wider">
                                            Detector label: {result.verdict_label}
                                        </p>
                                    )}
                                    {claimContext?.primary_type && (
                                        <div className="flex flex-wrap gap-2 mt-2 text-xs font-mono">
                                            <span className="px-2.5 py-1 rounded-sm bg-slate-900/50 border border-slate-700/40 text-slate-300 uppercase">
                                                {claimContext.primary_type.replace(/_/g, ' ')}
                                            </span>
                                            <span className="px-2.5 py-1 rounded-sm bg-slate-900/50 border border-slate-700/40 text-slate-400">
                                                Type confidence {Math.round((claimContext.confidence || 0) * 100)}%
                                            </span>
                                        </div>
                                    )}
                                    {llmFactCheck?.enabled && llmFactCheck?.available && (
                                        <p className="text-slate-500 font-mono text-xs mt-2 uppercase tracking-wider">
                                            Final verdict uses dynamic source and Groq weighting based on claim type
                                        </p>
                                    )}
                                </div>
                            </div>
                            <div className="text-right">
                                <div className={`text-4xl font-bold font-mono ${config.color}`}>
                                    {confidenceDisplay.percent}%
                                </div>
                                <p className="text-slate-500 text-xs font-mono uppercase tracking-wider">
                                    {confidenceDisplay.label}
                                </p>
                            </div>
                        </div>

                        {/* Score Bars */}
                        <div className={`grid gap-4 mt-6 ${scoreBars.length === 4 ? 'grid-cols-2 xl:grid-cols-4' : 'grid-cols-3'}`}>
                            {scoreBars.map(bar => (
                                <div key={bar.label} className="space-y-1">
                                    <div className="flex justify-between text-xs font-mono">
                                        <span className="text-slate-500">{bar.label}</span>
                                        <span className="text-slate-300">{bar.value != null ? `${Math.round(bar.value * 100)}%` : 'N/A'}</span>
                                    </div>
                                    <div className="h-1.5 bg-slate-900/50 rounded-full overflow-hidden">
                                        <div
                                            className="h-full rounded-full transition-all duration-1000"
                                            style={{
                                                width: bar.value != null ? `${Math.round(bar.value * 100)}%` : '0%',
                                                backgroundColor: bar.color,
                                            }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* LLM Fact Check */}
                    {llmFactCheck && (
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-6">
                            <div className="flex items-start justify-between gap-6">
                                <div className="space-y-3">
                                    <div>
                                        <p className="text-xs font-mono text-cyan-400 uppercase tracking-widest">
                                            LLM Fact Check
                                        </p>
                                        <h3 className={`text-xl font-chivo font-bold uppercase tracking-wider mt-2 ${llmConfig.color}`}>
                                            {llmFactCheck.label || llmCommonVerdict || 'UNVERIFIED'}
                                        </h3>
                                        <p className="text-slate-400 font-mono text-sm mt-2">
                                            {llmFactCheck.summary || 'Groq fact check summary unavailable.'}
                                        </p>
                                    </div>
                                    <div className="flex flex-wrap gap-2 text-xs font-mono">
                                        <span className="px-3 py-1 rounded-sm bg-slate-900/50 border border-slate-700/40 text-slate-300">
                                            {llmStatusLabel}
                                        </span>
                                        <span className="px-3 py-1 rounded-sm bg-slate-900/50 border border-slate-700/40 text-amber-300">
                                            Model knowledge only
                                        </span>
                                        <span className="px-3 py-1 rounded-sm bg-slate-900/50 border border-slate-700/40 text-slate-400">
                                            Not from live news sources
                                        </span>
                                        {llmFactCheck.model && (
                                            <span className="px-3 py-1 rounded-sm bg-slate-900/50 border border-slate-700/40 text-slate-400">
                                                {llmFactCheck.model}
                                            </span>
                                        )}
                                    </div>
                                </div>
                                <div className="text-right min-w-[140px]">
                                    <div className={`text-4xl font-bold font-mono ${llmConfig.color}`}>
                                        {llmConfidence != null ? `${llmConfidence}%` : 'N/A'}
                                    </div>
                                    <p className="text-slate-500 text-xs font-mono uppercase tracking-wider">
                                        LLM Confidence
                                    </p>
                                </div>
                            </div>

                            {llmFactCheck.reasoning && llmFactCheck.reasoning.length > 0 && (
                                <div className="mt-4">
                                    <h4 className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">
                                        Groq Reasoning
                                    </h4>
                                    <ul className="space-y-2">
                                        {llmFactCheck.reasoning.map((reason: string, i: number) => (
                                            <li key={i} className="flex items-start gap-2 text-sm text-slate-300 font-mono">
                                                <ArrowRight size={12} className="text-cyan-500 mt-1 flex-shrink-0" />
                                                {reason}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Claims Section */}
                    {result.claims && result.claims.length > 0 && (
                        <CollapsibleSection
                            title="Extracted Claims"
                            icon={Lightbulb}
                            count={result.claims.length}
                            isOpen={expandedSections.claims}
                            onToggle={() => toggleSection('claims')}
                        >
                            <div className="space-y-3">
                                {result.claims.map((claim: any, i: number) => (
                                    <div key={i} className="flex items-start gap-3 bg-slate-900/40 border border-slate-800/50 rounded-sm px-4 py-3">
                                        <span className="text-xs font-mono text-slate-600 bg-slate-800 rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0 mt-0.5">
                                            {i + 1}
                                        </span>
                                        <div className="flex-1">
                                            <p className="text-slate-300 text-sm font-mono">{claim.text}</p>
                                            <div className="flex items-center gap-3 mt-2">
                                                <span className="text-xs font-mono px-2 py-0.5 rounded-sm bg-slate-800 border border-slate-700/50 text-slate-400 uppercase">
                                                    {claim.type}
                                                </span>
                                                {claim.claim_category && (
                                                    <span className="text-xs font-mono px-2 py-0.5 rounded-sm bg-slate-800 border border-cyan-800/40 text-cyan-300 uppercase">
                                                        {claim.claim_category.replace(/_/g, ' ')}
                                                    </span>
                                                )}
                                                <span className="text-xs font-mono text-slate-500">
                                                    Confidence: {Math.round(claim.confidence * 100)}%
                                                </span>
                                                {typeof claim.claim_category_confidence === 'number' && (
                                                    <span className="text-xs font-mono text-slate-500">
                                                        Type: {Math.round(claim.claim_category_confidence * 100)}%
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CollapsibleSection>
                    )}

                    {/* Evidence Section */}
                    <CollapsibleSection
                        title="Evidence Found"
                        icon={BookOpen}
                        count={evidenceItems.length}
                        isOpen={expandedSections.evidence}
                        onToggle={() => toggleSection('evidence')}
                    >
                        <div className="space-y-3">
                            {evidenceItems.length > 0 ? (
                                evidenceItems.map((ev: any, i: number) => (
                                    <div key={i} className="bg-slate-900/40 border border-slate-800/50 rounded-sm px-4 py-3">
                                        <div className="flex items-center gap-2 mb-1">
                                            {ev.type === 'news' ? (
                                                <NewspaperClipping size={14} className="text-cyan-400" />
                                            ) : ev.type === 'wikipedia' ? (
                                                <BookOpen size={14} className="text-purple-400" />
                                            ) : (
                                                <Info size={14} className="text-slate-500" />
                                            )}
                                            <span className="text-xs font-mono text-slate-500 uppercase">{ev.source}</span>
                                        </div>
                                        <p className="text-slate-300 text-sm">{ev.title}</p>
                                        {ev.extract && (
                                            <p className="text-slate-500 text-xs mt-1 font-mono">{ev.extract}</p>
                                        )}
                                        {ev.url && (
                                            <a href={ev.url} target="_blank" rel="noopener noreferrer"
                                                className="text-cyan-500 text-xs hover:text-cyan-400 font-mono mt-1 inline-flex items-center gap-1">
                                                View Source <ArrowRight size={10} />
                                            </a>
                                        )}
                                    </div>
                                ))
                            ) : evidenceFallback ? (
                                <div className="bg-slate-900/40 border border-slate-800/50 rounded-sm px-4 py-3">
                                    <div className="flex items-center gap-2 mb-1">
                                        <Info size={14} className="text-slate-500" />
                                        <span className="text-xs font-mono text-slate-500 uppercase">{evidenceFallback.source}</span>
                                    </div>
                                    <p className="text-slate-300 text-sm">{evidenceFallback.title}</p>
                                    {evidenceFallback.extract && (
                                        <p className="text-slate-500 text-xs mt-1 font-mono">{evidenceFallback.extract}</p>
                                    )}
                                </div>
                            ) : (
                                <p className="text-slate-600 font-mono text-sm text-center py-4">No evidence found</p>
                            )}
                        </div>
                    </CollapsibleSection>

                    {/* Explanation Section */}
                    {result.explanation && (
                        <CollapsibleSection
                            title="Analysis Explanation"
                            icon={Scales}
                            isOpen={expandedSections.explanation}
                            onToggle={() => toggleSection('explanation')}
                        >
                            <div className="space-y-4">
                                {/* Reasons */}
                                {result.explanation.reasons && (
                                    <div>
                                        <h4 className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">Key Reasons</h4>
                                        <ul className="space-y-2">
                                            {result.explanation.reasons.map((reason: string, i: number) => (
                                                <li key={i} className="flex items-start gap-2 text-sm text-slate-300 font-mono">
                                                    <ArrowRight size={12} className="text-cyan-500 mt-1 flex-shrink-0" />
                                                    {reason}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {/* Signals */}
                                {result.explanation.signals && result.explanation.signals.length > 0 && (
                                    <div>
                                        <h4 className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-2">Detected Signals</h4>
                                        <div className="flex flex-wrap gap-2">
                                            {result.explanation.signals.map((signal: any, i: number) => (
                                                <span
                                                    key={i}
                                                    className={`text-xs font-mono px-3 py-1 rounded-sm border ${
                                                        signal.severity === 'high'
                                                            ? 'bg-red-950/30 border-red-800/40 text-red-300'
                                                            : signal.severity === 'medium'
                                                            ? 'bg-amber-950/30 border-amber-800/40 text-amber-300'
                                                            : 'bg-slate-800/50 border-slate-700/40 text-slate-400'
                                                    }`}
                                                >
                                                    {signal.detail}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* Recommendations */}
                                {result.explanation.recommendations && (
                                    <div className="bg-blue-950/20 border border-blue-800/30 rounded-sm p-4">
                                        <h4 className="text-xs font-mono text-blue-400 uppercase tracking-wider mb-2">
                                            💡 Recommendations
                                        </h4>
                                        <ul className="space-y-1">
                                            {result.explanation.recommendations.map((rec: string, i: number) => (
                                                <li key={i} className="text-sm text-blue-200/70 font-mono flex items-start gap-2">
                                                    <span className="text-blue-500 mt-0.5">•</span>
                                                    {rec}
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        </CollapsibleSection>
                    )}

                    {/* Score Breakdown */}
                    <CollapsibleSection
                        title="Score Breakdown"
                        icon={ChartBar}
                        isOpen={expandedSections.scores}
                        onToggle={() => toggleSection('scores')}
                    >
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {result.explanation?.score_breakdown && Object.entries(result.explanation.score_breakdown).map(([key, comp]: [string, any]) => (
                                <div key={key} className="bg-slate-900/40 border border-slate-800/50 rounded-sm p-4">
                                    <h5 className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-3">{key.replace('_', ' ')}</h5>
                                    <div className="text-2xl font-bold font-mono text-slate-200">
                                        {Math.round((comp?.score || 0) * 100)}%
                                    </div>
                                    <div className="text-xs font-mono text-slate-600 mt-1">
                                        Weight: {((comp?.weight || 0) * 100).toFixed(0)}% · Contrib: {Math.round((comp?.weighted || 0) * 100)}%
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CollapsibleSection>

                    {/* Footer */}
                    <div className="flex items-center justify-between text-xs font-mono text-slate-600 border-t border-slate-800 pt-4">
                        <span>Analysis #{result.id} · Processed in {result.processing_time}s</span>
                        <button
                            onClick={() => { setResult(null); setText(''); setSourceUrl(''); }}
                            className="text-cyan-600 hover:text-cyan-400 uppercase tracking-wider transition-colors"
                        >
                            New Analysis
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}


/* ── Collapsible Section Component ── */
function CollapsibleSection({
    title,
    icon: Icon,
    count,
    isOpen,
    onToggle,
    children,
}: {
    title: string;
    icon: React.ElementType;
    count?: number;
    isOpen: boolean;
    onToggle: () => void;
    children: React.ReactNode;
}) {
    return (
        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm overflow-hidden">
            <button
                onClick={onToggle}
                className="w-full flex items-center justify-between px-6 py-4 hover:bg-slate-800/60 transition-colors"
            >
                <div className="flex items-center gap-2">
                    <Icon size={16} weight="duotone" className="text-cyan-400" />
                    <span className="text-sm font-mono text-slate-400 uppercase tracking-widest">{title}</span>
                    {count !== undefined && (
                        <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-900 text-slate-500 border border-slate-700/50">
                            {count}
                        </span>
                    )}
                </div>
                {isOpen ? <CaretUp size={16} className="text-slate-500" /> : <CaretDown size={16} className="text-slate-500" />}
            </button>
            {isOpen && (
                <div className="px-6 pb-6">
                    {children}
                </div>
            )}
        </div>
    );
}
