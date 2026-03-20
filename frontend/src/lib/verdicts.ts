export function getCommonVerdict(verdict?: string | null) {
    if (!verdict) return verdict ?? undefined;

    const map: Record<string, string> = {
        AUTHENTIC: 'AUTHENTIC',
        REAL: 'AUTHENTIC',
        LIKELY_REAL: 'AUTHENTIC',
        SAFE: 'AUTHENTIC',
        LEGITIMATE: 'AUTHENTIC',
        MANIPULATED: 'MANIPULATED',
        FAKE: 'MANIPULATED',
        MISLEADING: 'MANIPULATED',
        UNSAFE: 'MANIPULATED',
        MALICIOUS: 'MANIPULATED',
        PHISHING: 'MANIPULATED',
        SUSPICIOUS: 'SUSPICIOUS',
        LIKELY_FAKE: 'SUSPICIOUS',
        UNCERTAIN: 'SUSPICIOUS',
        UNVERIFIED: 'SUSPICIOUS',
        SPAM: 'SUSPICIOUS',
        RISKY: 'SUSPICIOUS',
        UNKNOWN: 'UNKNOWN',
        ERROR: 'UNKNOWN',
    };

    return map[verdict] || verdict;
}

export function getVerdictDisplayLabel(verdict?: string | null, verdictLabel?: string | null) {
    const commonVerdict = getCommonVerdict(verdict);
    if (!commonVerdict) return 'UNKNOWN';
    if (verdictLabel && verdictLabel !== verdict) {
        return `${commonVerdict} (${verdictLabel})`;
    }
    return commonVerdict;
}
