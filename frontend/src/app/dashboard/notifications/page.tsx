'use client';

import React, { useEffect, useState } from 'react';
import { Bell, CheckCircle, Pulse } from '@phosphor-icons/react';

import { StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';

export default function NotificationsPage() {
    const [items, setItems] = useState<any[]>([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [loading, setLoading] = useState(true);

    async function load() {
        try {
            const data = await api.getNotifications();
            setItems(data.notifications || []);
            setUnreadCount(data.unread_count || 0);
        } catch (error) {
            console.error('Failed to fetch notifications:', error);
        } finally {
            setLoading(false);
        }
    }

    useEffect(() => {
        load();
    }, []);

    const markRead = async (id: number) => {
        await api.markNotificationRead(id);
        await load();
    };

    const markAllRead = async () => {
        await api.markAllNotificationsRead();
        await load();
    };

    if (loading) {
        return (
            <div className="flex flex-col items-center justify-center h-64 gap-4">
                <div className="relative">
                    <div className="w-12 h-12 rounded-full border-2 border-slate-700 border-t-blue-500 animate-spin" />
                    <Pulse size={24} className="absolute inset-0 m-auto text-blue-400 animate-pulse" />
                </div>
                <p className="text-slate-500 font-mono text-xs uppercase tracking-widest animate-pulse">Loading Notifications...</p>
            </div>
        );
    }

    return (
        <div className="space-y-8 max-w-5xl mx-auto">
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-2xl font-chivo font-bold uppercase tracking-wider flex items-center gap-3">
                        <Bell size={28} weight="duotone" className="text-blue-400" />
                        Notifications
                    </h1>
                    <p className="text-slate-500 mt-1 font-mono text-sm">{unreadCount} unread alerts</p>
                </div>
                <button onClick={markAllRead} className="btn-secondary">Mark All Read</button>
            </div>

            <div className="space-y-3">
                {items.length ? items.map((item) => (
                    <div key={item.id} className="rounded-sm border border-slate-700/60 bg-slate-800/40 p-5">
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <div className="flex items-center gap-2 flex-wrap">
                                    <h3 className="text-lg font-medium text-slate-100">{item.title}</h3>
                                    <StatusBadge status={item.severity || 'info'} />
                                    {!item.read_at && <StatusBadge status="warning" />}
                                </div>
                                <p className="mt-2 text-sm text-slate-400">{item.message}</p>
                                <p className="mt-3 text-xs font-mono text-slate-500">{new Date(item.created_at).toLocaleString()}</p>
                            </div>
                            {!item.read_at && (
                                <button onClick={() => markRead(item.id)} className="btn-secondary flex items-center gap-2">
                                    <CheckCircle size={16} />
                                    Mark Read
                                </button>
                            )}
                        </div>
                    </div>
                )) : (
                    <div className="rounded-sm border border-slate-700/60 bg-slate-800/40 p-10 text-center">
                        <p className="text-slate-500 font-mono">No notifications yet.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
