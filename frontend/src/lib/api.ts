const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class ApiClient {
    private token: string | null = null;

    setToken(token: string) {
        this.token = token;
        if (typeof window !== 'undefined') {
            localStorage.setItem('deepshield_token', token);
        }
    }

    getToken() {
        if (!this.token && typeof window !== 'undefined') {
            this.token = localStorage.getItem('deepshield_token');
        }
        return this.token;
    }

    clearToken() {
        this.token = null;
        if (typeof window !== 'undefined') {
            localStorage.removeItem('deepshield_token');
        }
    }

    private async request(endpoint: string, options: RequestInit = {}) {
        const token = this.getToken();
        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
            ...(options.headers as Record<string, string>),
        };

        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }

        const response = await fetch(`${API_URL}${endpoint}`, {
            ...options,
            headers,
            cache: 'no-store',
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.message || 'Request failed');
        }

        return response.json();
    }

    private async requestRaw(endpoint: string, options: RequestInit = {}) {
        const token = this.getToken();
        const headers: Record<string, string> = {
            ...(options.headers as Record<string, string>),
        };

        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }

        const response = await fetch(`${API_URL}${endpoint}`, {
            ...options,
            headers,
            cache: 'no-store',
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.message || 'Request failed');
        }

        return response;
    }

    async login(username: string, password: string) {
        const data = await this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
        this.setToken(data.access_token);
        return data;
    }

    async register(username: string, email: string, password: string) {
        const data = await this.request('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, email, password }),
        });
        this.setToken(data.access_token);
        return data;
    }

    async getMe() {
        return this.request('/api/auth/me');
    }

    async uploadMedia(file: File) {
        const token = this.getToken();
        const headers: Record<string, string> = {};
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }

        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_URL}/api/upload`, {
            method: 'POST',
            headers,
            body: formData,
            cache: 'no-store',
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
            throw new Error(error.detail || 'Upload failed');
        }

        return response.json();
    }

    async startAnalysis(analysisId: number) {
        return this.request(`/api/analysis/start/${analysisId}`, {
            method: 'POST',
        });
    }

    async getAnalysis(analysisId: number) {
        return this.request(`/api/analysis/${analysisId}`);
    }

    async getHistory() {
        return this.request('/api/analysis/history/list');
    }

    async getUnifiedHistory() {
        return this.request('/api/history/unified');
    }

    async getDashboardStats() {
        return this.request('/api/dashboard/stats');
    }

    async getReport(analysisId: number) {
        return this.request(`/api/reports/${analysisId}`);
    }

    async downloadReport(analysisId: number, format: 'pdf' | 'json' = 'pdf') {
        return this.requestRaw(`/api/reports/${analysisId}/download?format=${format}`);
    }

    async downloadMedia(analysisId: number) {
        return this.requestRaw(`/api/files/media/${analysisId}/download`);
    }

    async analyzeText(text: string, sourceUrl?: string) {
        return this.request('/api/text/analyze', {
            method: 'POST',
            body: JSON.stringify({ text, source_url: sourceUrl || null }),
        });
    }

    async analyzeLink(url: string) {
        return this.request('/api/link/analyze', {
            method: 'POST',
            body: JSON.stringify({ url }),
        });
    }

    async getTextAnalysis(analysisId: number) {
        return this.request(`/api/text/analysis/${analysisId}`);
    }

    async getLinkAnalysis(analysisId: number) {
        return this.request(`/api/link/analysis/${analysisId}`);
    }

    async getTextHistory() {
        return this.request('/api/text/history');
    }

    async getLinkHistory() {
        return this.request('/api/link/history');
    }

    async createShareLink(contentType: 'media' | 'text' | 'link', contentId: number) {
        return this.request(`/api/content/${contentType}/${contentId}/share-link`, {
            method: 'POST',
        });
    }

    async getPublicShare(token: string) {
        const response = await fetch(`${API_URL}/api/public/share/${token}`, {
            cache: 'no-store',
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.message || 'Request failed');
        }
        return response.json();
    }

    async getNotifications() {
        return this.request('/api/notifications');
    }

    async getUnreadNotificationCount() {
        return this.request('/api/notifications/unread-count');
    }

    async markNotificationRead(notificationId: number) {
        return this.request(`/api/notifications/${notificationId}/read`, {
            method: 'POST',
        });
    }

    async markAllNotificationsRead() {
        return this.request('/api/notifications/read-all', {
            method: 'POST',
        });
    }

    async getAdminOverview() {
        return this.request('/api/admin/overview');
    }

    async getAdminUsers() {
        return this.request('/api/admin/users');
    }

    async updateUserStatus(userId: number, status: 'active' | 'suspended') {
        return this.request(`/api/admin/users/${userId}/status`, {
            method: 'POST',
            body: JSON.stringify({ status }),
        });
    }

    async getRules() {
        return this.request('/api/admin/rules');
    }

    async createRule(payload: Record<string, unknown>) {
        return this.request('/api/admin/rules', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    async updateRule(ruleId: number, payload: Record<string, unknown>) {
        return this.request(`/api/admin/rules/${ruleId}`, {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
    }

    async deleteRule(ruleId: number) {
        return this.request(`/api/admin/rules/${ruleId}`, {
            method: 'DELETE',
        });
    }

    async getReviewQueue() {
        return this.request('/api/admin/review-queue');
    }

    async moderateContent(
        contentType: 'media' | 'text' | 'link',
        contentId: number,
        payload: Record<string, unknown>,
    ) {
        return this.request(`/api/admin/content/${contentType}/${contentId}/moderate`, {
            method: 'POST',
            body: JSON.stringify(payload),
        });
    }

    async healthCheck() {
        return this.request('/api/health');
    }

    getUploadUrl(filename: string) {
        const token = this.getToken();
        const query = token ? `?token=${encodeURIComponent(token)}` : '';
        return `${API_URL}/api/files/upload/${encodeURIComponent(filename)}${query}`;
    }

    getEvidenceUrl(filename: string) {
        const token = this.getToken();
        const query = token ? `?token=${encodeURIComponent(token)}` : '';
        return `${API_URL}/api/files/evidence/${encodeURIComponent(filename)}${query}`;
    }
}

export const api = new ApiClient();
