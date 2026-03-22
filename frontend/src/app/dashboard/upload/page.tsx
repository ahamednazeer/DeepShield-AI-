'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { api } from '@/lib/api';
import { StatusBadge } from '@/components/StatusBadge';
import { useRouter } from 'next/navigation';
import {
    Upload,
    FileImage,
    FileVideo,
    ShieldCheck,
    Warning,
    CheckCircle,
    Spinner,
    X,
    ArrowRight,
    Pulse,
} from '@phosphor-icons/react';

interface AnalysisResult {
    id: number;
    filename: string;
    original_filename: string;
    media_type: string;
    file_size: number;
    status: string;
    overall_score?: number;
    verdict?: string;
    processing_time?: number;
    selected_model?: string | null;
    model_version?: string | null;
    evidence?: any[];
    frames_total?: number | null;
    frames_processed?: number | null;
    progress_percent?: number | null;
}

interface ModelOption {
    id: string;
    label: string;
    description?: string;
    available: boolean;
    availability_reason?: string | null;
    recommended?: boolean;
    experimental?: boolean;
    resolved_default?: string | null;
}

export default function UploadPage() {
    const router = useRouter();
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);
    const [error, setError] = useState('');
    const [progress, setProgress] = useState('');
    const [progressPercent, setProgressPercent] = useState<number | null>(null);
    const [progressFrames, setProgressFrames] = useState<{ processed: number; total: number | null } | null>(null);
    const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
    const [selectedModel, setSelectedModel] = useState('auto');
    const [loadingModels, setLoadingModels] = useState(false);

    const detectMediaType = useCallback((file: File | null): 'image' | 'video' | null => {
        if (!file) return null;
        if (file.type.startsWith('image/')) return 'image';
        if (file.type.startsWith('video/')) return 'video';
        const ext = file.name.toLowerCase().split('.').pop() || '';
        if (['jpg', 'jpeg', 'png', 'bmp', 'webp', 'tiff'].includes(ext)) return 'image';
        if (['mp4', 'avi', 'mov', 'mkv', 'webm'].includes(ext)) return 'video';
        return null;
    }, []);

    const selectedMediaType = detectMediaType(selectedFile);

    useEffect(() => {
        const mediaType = detectMediaType(selectedFile);
        setModelOptions([]);
        setSelectedModel('auto');

        if (!mediaType) {
            return;
        }

        let cancelled = false;
        setLoadingModels(true);
        api.getMediaModels(mediaType)
            .then((response) => {
                if (cancelled) return;
                setModelOptions(response.models || []);
                setSelectedModel('auto');
            })
            .catch((err: any) => {
                if (cancelled) return;
                setError(err.message || 'Could not load model options');
            })
            .finally(() => {
                if (!cancelled) {
                    setLoadingModels(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, [detectMediaType, selectedFile]);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            setSelectedFile(files[0]);
            setResult(null);
            setError('');
        }
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            setSelectedFile(e.target.files[0]);
            setResult(null);
            setError('');
        }
    };

    const getFileIcon = (file: File) => {
        const type = file.type;
        if (type.startsWith('image/')) return FileImage;
        if (type.startsWith('video/')) return FileVideo;
        return Upload;
    };

    const formatFileSize = (bytes: number) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const pollAnalysis = async (analysisId: number) => {
        const maxIdleMs = 2 * 60 * 1000;
        const maxTotalMs = 30 * 60 * 1000;
        let lastProgress = -1;
        let lastUpdate = Date.now();
        const start = Date.now();
        let lastStatus: string | null = null;

        while (Date.now() - start < maxTotalMs) {
            try {
                const data = await api.getAnalysis(analysisId);
                if (data.status === 'completed') {
                    setResult(data);
                    setAnalyzing(false);
                    return;
                } else if (data.status === 'failed') {
                    setError('Analysis failed. Please try again.');
                    setAnalyzing(false);
                    return;
                }
                if (data.frames_processed != null) {
                    const total = data.frames_total != null ? `/${data.frames_total}` : '';
                    const percentVal = data.progress_percent != null
                        ? data.progress_percent
                        : (data.frames_total ? (data.frames_processed / data.frames_total) * 100 : null);
                    const percentText = percentVal != null ? ` (${percentVal.toFixed(1)}%)` : '';
                    setProgress(`Processing frames... ${data.frames_processed}${total}${percentText}`);
                    setProgressPercent(percentVal);
                    setProgressFrames({ processed: data.frames_processed, total: data.frames_total ?? null });
                    if (data.frames_processed !== lastProgress) {
                        lastProgress = data.frames_processed;
                        lastUpdate = Date.now();
                    }
                } else {
                    setProgress(`Processing... ${data.status}`);
                    setProgressPercent(null);
                    setProgressFrames(null);
                    if (data.status !== lastStatus) {
                        lastStatus = data.status;
                        lastUpdate = Date.now();
                    }
                }

                if (Date.now() - lastUpdate > maxIdleMs) {
                    setError('Analysis appears stalled. Check history for results.');
                    setAnalyzing(false);
                    return;
                }
            } catch {
                // Keep polling
            }
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
        setError('Analysis is taking longer than expected. Check history for results.');
        setAnalyzing(false);
    };

    const handleUploadAndAnalyze = async () => {
        if (!selectedFile) return;
        setError('');
        setUploading(true);
        setProgress('Uploading file...');
        setProgressPercent(null);
        setProgressFrames(null);

        try {
            // Step 1: Upload
            const uploadResult = await api.uploadMedia(selectedFile);
            setUploading(false);
            setAnalyzing(true);
            setProgress('Starting analysis...');

            // Step 2: Start analysis
            await api.startAnalysis(uploadResult.id, selectedModel);
            setProgress('Analysis in progress...');

            // Step 3: Poll for completion
            await pollAnalysis(uploadResult.id);
        } catch (err: any) {
            setError(err.message || 'Upload failed.');
            setUploading(false);
            setAnalyzing(false);
        }
    };

    const getVerdictStyles = (verdict?: string) => {
        switch (verdict) {
            case 'AUTHENTIC':
                return { color: 'text-green-400', bg: 'from-green-900/40 to-green-950/60', border: 'border-green-700/30', icon: CheckCircle };
            case 'MANIPULATED':
                return { color: 'text-red-400', bg: 'from-red-900/40 to-red-950/60', border: 'border-red-700/30', icon: Warning };
            case 'SUSPICIOUS':
                return { color: 'text-yellow-400', bg: 'from-yellow-900/40 to-yellow-950/60', border: 'border-yellow-700/30', icon: Warning };
            default:
                return { color: 'text-slate-400', bg: 'from-slate-900/40 to-slate-950/60', border: 'border-slate-700/30', icon: ShieldCheck };
        }
    };

    return (
        <div className="space-y-8 max-w-4xl mx-auto">
            <div>
                <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                    <Upload size={28} weight="duotone" className="text-blue-400" />
                    Upload & Analyze
                </h1>
                <p className="text-slate-500 mt-1 font-mono text-sm">Upload media for forensic deepfake analysis</p>
            </div>

            {/* Dropzone */}
            {!result && (
                <div className="space-y-4">
                    <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                        className={`relative border-2 border-dashed rounded-sm p-12 text-center cursor-pointer transition-all duration-300 ${isDragging
                                ? 'border-blue-500 bg-blue-950/30 shadow-[0_0_30px_rgba(59,130,246,0.2)]'
                                : 'border-slate-700 bg-slate-800/30 hover:border-slate-600 hover:bg-slate-800/50'
                            }`}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*,video/*,.mp4,.avi,.mov"
                            onChange={handleFileSelect}
                            className="hidden"
                        />

                        {selectedFile ? (
                            <div className="space-y-4">
                                {React.createElement(getFileIcon(selectedFile), {
                                    size: 48,
                                    weight: 'duotone',
                                    className: 'text-blue-400 mx-auto',
                                })}
                                <div>
                                    <p className="text-slate-200 font-mono text-sm">{selectedFile.name}</p>
                                    <p className="text-slate-500 font-mono text-xs mt-1">{formatFileSize(selectedFile.size)}</p>
                                </div>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setSelectedFile(null);
                                        setModelOptions([]);
                                        setSelectedModel('auto');
                                    }}
                                    className="text-slate-500 hover:text-red-400 transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <Upload size={48} weight="duotone" className="text-slate-600 mx-auto" />
                                <div>
                                    <p className="text-slate-300 text-lg font-medium">Drop media here or click to browse</p>
                                    <p className="text-slate-500 font-mono text-xs mt-2">Supports: Images (PNG, JPG, BMP) · Video (MP4, AVI, MOV)</p>
                                    <p className="text-slate-600 font-mono text-xs mt-1">Max file size: 50MB</p>
                                </div>
                            </div>
                        )}
                    </div>

                    {selectedFile && selectedMediaType && (
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-5 space-y-4">
                            <div className="flex items-center justify-between gap-4 flex-wrap">
                                <div>
                                    <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Analysis Model</p>
                                    <p className="text-sm text-slate-300">
                                        Choose which {selectedMediaType} detector to run for this analysis.
                                    </p>
                                </div>
                                <StatusBadge status={selectedMediaType} />
                            </div>
                            <select
                                value={selectedModel}
                                onChange={(e) => setSelectedModel(e.target.value)}
                                disabled={loadingModels || modelOptions.length === 0}
                                className="w-full rounded-sm border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm text-slate-200 outline-none focus:border-blue-500"
                            >
                                {loadingModels && <option value="auto">Loading models...</option>}
                                {!loadingModels && modelOptions.map((option) => (
                                    <option key={option.id} value={option.id} disabled={!option.available}>
                                        {option.label}
                                        {!option.available ? ' [Unavailable]' : ''}
                                        {option.experimental ? ' [Experimental]' : ''}
                                        {option.recommended ? ' [Recommended]' : ''}
                                    </option>
                                ))}
                            </select>
                            {!loadingModels && modelOptions.length > 0 && (
                                <div className="grid gap-3 md:grid-cols-2">
                                    {modelOptions.map((option) => (
                                        <button
                                            key={option.id}
                                            type="button"
                                            onClick={() => option.available && setSelectedModel(option.id)}
                                            disabled={!option.available}
                                            className={`rounded-sm border p-3 text-left transition-colors ${selectedModel === option.id
                                                ? 'border-blue-500 bg-blue-950/30'
                                                : 'border-slate-800 bg-slate-900/40 hover:border-slate-700'
                                                } ${!option.available ? 'opacity-50 cursor-not-allowed hover:border-slate-800' : ''}`}
                                        >
                                            <div className="flex items-center justify-between gap-3">
                                                <p className="text-sm text-slate-200">{option.label}</p>
                                                <div className="flex gap-2">
                                                    {option.recommended && <StatusBadge status="recommended" />}
                                                    {option.experimental && <StatusBadge status="experimental" />}
                                                    {!option.available && <StatusBadge status="unavailable" />}
                                                </div>
                                            </div>
                                            {option.description && (
                                                <p className="mt-2 text-xs text-slate-500 font-mono">{option.description}</p>
                                            )}
                                            {!option.available && option.availability_reason && (
                                                <p className="mt-2 text-xs text-amber-300 font-mono">{option.availability_reason}</p>
                                            )}
                                            {option.id === 'auto' && option.resolved_default && (
                                                <p className="mt-2 text-xs text-blue-300 font-mono">Current default: {option.resolved_default}</p>
                                            )}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Analyze Button */}
            {selectedFile && !result && !uploading && !analyzing && (
                <button
                    onClick={handleUploadAndAnalyze}
                    className="w-full bg-blue-600 hover:bg-blue-500 text-white rounded-sm font-medium tracking-wide uppercase text-sm px-4 py-4 shadow-[0_0_20px_rgba(59,130,246,0.4)] transition-all duration-150 flex items-center justify-center gap-3"
                >
                    <ShieldCheck size={20} weight="bold" />
                    Start Forensic Analysis
                    <ArrowRight size={18} />
                </button>
            )}

            {/* Progress */}
            {(uploading || analyzing) && (
                <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-8 text-center">
                    <div className="relative inline-block mb-4">
                        <div className="w-16 h-16 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
                        <Pulse size={28} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                    </div>
                    <p className="text-slate-300 font-mono text-sm uppercase tracking-wider">{progress}</p>
                    {progressPercent != null && (
                        <div className="mt-4">
                            <div className="flex items-center justify-between text-xs text-slate-500 font-mono mb-2">
                                <span>Frame Progress</span>
                                <span>
                                    {progressFrames?.processed ?? 0}
                                    {progressFrames?.total != null ? `/${progressFrames.total}` : ''}
                                </span>
                            </div>
                            <div className="h-2 bg-slate-900/70 rounded-sm overflow-hidden">
                                <div
                                    className="h-2 bg-blue-500 transition-all duration-300"
                                    style={{ width: `${Math.min(Math.max(progressPercent, 0), 100)}%` }}
                                />
                            </div>
                            <div className="mt-2 text-right text-xs text-slate-500 font-mono">
                                {progressPercent.toFixed(1)}%
                            </div>
                        </div>
                    )}
                    <p className="text-slate-600 font-mono text-xs mt-2">This may take a few moments...</p>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="bg-red-950/50 border border-red-800 rounded-sm p-4 text-sm text-red-400 font-mono">
                    {error}
                </div>
            )}

            {/* Result */}
            {result && (
                <div className="space-y-6 animate-slide-up">
                    {/* Verdict Card */}
                    <div className={`bg-gradient-to-br ${getVerdictStyles(result.verdict).bg} border ${getVerdictStyles(result.verdict).border} rounded-sm p-8`}>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                {React.createElement(getVerdictStyles(result.verdict).icon, {
                                    size: 48,
                                    weight: 'duotone',
                                    className: getVerdictStyles(result.verdict).color,
                                })}
                                <div>
                                    <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Verdict</p>
                                    <p className={`text-3xl font-chivo font-bold uppercase tracking-wider ${getVerdictStyles(result.verdict).color}`}>
                                        {result.verdict || 'UNKNOWN'}
                                    </p>
                                </div>
                            </div>
                            <div className="text-right">
                                <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Confidence</p>
                                <p className="text-4xl font-bold font-mono text-slate-100">
                                    {result.overall_score != null ? `${(result.overall_score * 100).toFixed(1)}%` : '—'}
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Details Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">File</p>
                            <p className="text-sm text-slate-300 font-mono truncate">{result.original_filename}</p>
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Media Type</p>
                            <StatusBadge status={result.media_type} />
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">File Size</p>
                            <p className="text-sm text-slate-300 font-mono">{formatFileSize(result.file_size)}</p>
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Requested Model</p>
                            <p className="text-sm text-slate-300 font-mono">{result.selected_model || 'auto'}</p>
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Model Used</p>
                            <p className="text-sm text-slate-300 font-mono">{result.model_version || 'default'}</p>
                        </div>
                        <div className="bg-slate-800/40 border border-slate-700/60 rounded-sm p-4">
                            <p className="text-xs text-slate-500 font-mono uppercase tracking-wider mb-1">Processing</p>
                            <p className="text-sm text-slate-300 font-mono">{result.processing_time ? `${result.processing_time}s` : '—'}</p>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-4">
                        <button
                            onClick={() => router.push(`/dashboard/analysis/${result.id}`)}
                            className="flex-1 btn-primary flex items-center justify-center gap-2"
                        >
                            View Full Report
                            <ArrowRight size={16} />
                        </button>
                        <button
                            onClick={() => { setSelectedFile(null); setResult(null); setError(''); }}
                            className="btn-secondary"
                        >
                            New Analysis
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
