'use client';

import React, { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
    Bell,
    ClockCounterClockwise,
    Gauge,
    Globe,
    List,
    NewspaperClipping,
    ShieldCheck,
    ShieldWarning,
    SignOut,
    Upload,
} from '@phosphor-icons/react';

import { api } from '@/lib/api';

interface MenuItem {
    icon: React.ElementType;
    label: string;
    path: string;
    adminOnly?: boolean;
}

interface DashboardLayoutProps {
    children: ReactNode;
}

const MIN_WIDTH = 60;
const COLLAPSED_WIDTH = 64;
const DEFAULT_WIDTH = 64;
const MAX_WIDTH = 320;

const MENU_ITEMS: MenuItem[] = [
    { icon: Gauge, label: 'Dashboard', path: '/dashboard' },
    { icon: Upload, label: 'Upload & Analyze', path: '/dashboard/upload' },
    { icon: NewspaperClipping, label: 'Text Analysis', path: '/dashboard/text-analysis' },
    { icon: Globe, label: 'Link Detection', path: '/dashboard/link-analysis' },
    { icon: ClockCounterClockwise, label: 'Content History', path: '/dashboard/history' },
    { icon: ClockCounterClockwise, label: 'Text History', path: '/dashboard/text-history' },
    { icon: Bell, label: 'Notifications', path: '/dashboard/notifications' },
    { icon: ShieldWarning, label: 'Admin Console', path: '/dashboard/admin', adminOnly: true },
];

export default function DashboardLayout({ children }: DashboardLayoutProps) {
    const router = useRouter();
    const pathname = usePathname();

    const [user, setUser] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_WIDTH);
    const [isResizing, setIsResizing] = useState(false);
    const [isHidden, setIsHidden] = useState(false);
    const [unreadCount, setUnreadCount] = useState(0);
    const sidebarRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const savedWidth = localStorage.getItem('ds_sidebarWidth');
        const savedHidden = localStorage.getItem('ds_sidebarHidden');
        if (savedWidth) {
            setSidebarWidth(parseInt(savedWidth));
        }
        if (savedHidden === 'true') {
            setIsHidden(true);
        }
    }, []);

    useEffect(() => {
        if (!isResizing) {
            localStorage.setItem('ds_sidebarWidth', sidebarWidth.toString());
            localStorage.setItem('ds_sidebarHidden', isHidden.toString());
        }
    }, [sidebarWidth, isHidden, isResizing]);

    const startResizing = useCallback((e: React.MouseEvent) => {
        e.preventDefault();
        setIsResizing(true);
    }, []);

    const stopResizing = useCallback(() => {
        setIsResizing(false);
    }, []);

    const resize = useCallback((e: MouseEvent) => {
        if (isResizing && sidebarRef.current) {
            const newWidth = e.clientX;
            if (newWidth < MIN_WIDTH) {
                setIsHidden(true);
                setSidebarWidth(COLLAPSED_WIDTH);
            } else {
                setIsHidden(false);
                setSidebarWidth(Math.min(MAX_WIDTH, Math.max(COLLAPSED_WIDTH, newWidth)));
            }
        }
    }, [isResizing]);

    useEffect(() => {
        window.addEventListener('mousemove', resize);
        window.addEventListener('mouseup', stopResizing);
        return () => {
            window.removeEventListener('mousemove', resize);
            window.removeEventListener('mouseup', stopResizing);
        };
    }, [resize, stopResizing]);

    useEffect(() => {
        async function bootstrap() {
            try {
                const userData = await api.getMe();
                setUser(userData);
                const notificationData = await api.getUnreadNotificationCount();
                setUnreadCount(notificationData.unread_count || 0);
            } catch (error) {
                console.error('Auth check failed', error);
                api.clearToken();
                router.replace('/');
            } finally {
                setLoading(false);
            }
        }
        bootstrap();
    }, [router]);

    const handleLogout = () => {
        api.clearToken();
        router.push('/');
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center">
                <div className="text-center space-y-4">
                    <ShieldCheck size={48} className="text-blue-500 animate-pulse mx-auto" />
                    <div className="text-slate-500 font-mono text-sm animate-pulse">VERIFYING CREDENTIALS...</div>
                </div>
            </div>
        );
    }

    const name = user ? user.username : 'Analyst';
    const email = user?.email || 'analyst@deepshield.ai';
    const isCollapsed = sidebarWidth < 150;
    const showLabels = sidebarWidth >= 150 && !isHidden;
    const menuItems = MENU_ITEMS.filter((item) => !item.adminOnly || user?.role === 'admin');

    return (
        <div className="min-h-screen bg-slate-950 flex">
            <div className="scanlines print:hidden" />

            <aside
                ref={sidebarRef}
                className={`print:hidden bg-slate-900 border-r border-slate-800 h-screen sticky top-0 flex flex-col z-50 transition-all ${isResizing ? 'transition-none' : 'duration-200'} ${isHidden ? 'w-0 overflow-hidden border-0' : ''}`}
                style={{ width: isHidden ? 0 : sidebarWidth }}
            >
                <div className={`p-4 border-b border-slate-800 flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'}`}>
                    <ShieldCheck size={28} weight="duotone" className="text-blue-400 flex-shrink-0" />
                    {showLabels && (
                        <div className="overflow-hidden">
                            <h1 className="font-chivo font-bold text-sm uppercase tracking-wider whitespace-nowrap">DeepShield AI</h1>
                            <p className="text-xs text-slate-500 font-mono">TRUST COMMAND CENTER</p>
                        </div>
                    )}
                </div>

                <nav className="flex-1 p-2 overflow-y-auto overflow-x-hidden">
                    <ul className="space-y-1">
                        {menuItems.map((item) => {
                            const Icon = item.icon;
                            const isActive = pathname === item.path || pathname.startsWith(`${item.path}/`);
                            return (
                                <li key={item.path}>
                                    <button
                                        onClick={() => router.push(item.path)}
                                        className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-sm transition-all duration-150 text-sm font-medium ${isCollapsed ? 'justify-center' : ''} ${isActive ? 'text-blue-400 bg-blue-950/50 border-l-2 border-blue-400' : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'}`}
                                        title={isCollapsed ? item.label : undefined}
                                    >
                                        <Icon size={20} weight="duotone" className="flex-shrink-0" />
                                        {showLabels && (
                                            <span className="truncate flex items-center gap-2">
                                                {item.label}
                                                {item.path === '/dashboard/notifications' && unreadCount > 0 && (
                                                    <span className="inline-flex min-w-5 justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                                        {unreadCount}
                                                    </span>
                                                )}
                                            </span>
                                        )}
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </nav>

                <div className="p-3 border-t border-slate-800 space-y-3">
                    {showLabels && (
                        <div className="rounded-sm border border-slate-800 bg-slate-950/60 p-3">
                            <p className="text-xs uppercase tracking-wider font-mono text-slate-500">Account</p>
                            <p className="mt-2 text-sm font-mono text-slate-300">{email}</p>
                            <p className="mt-1 text-[11px] font-mono uppercase tracking-wider text-slate-500">
                                {user?.role || 'analyst'} · {user?.status || 'active'}
                            </p>
                        </div>
                    )}
                    <button
                        onClick={handleLogout}
                        className={`w-full flex items-center gap-3 px-3 py-2.5 text-red-400 hover:text-red-300 hover:bg-slate-800 rounded-sm transition-all duration-150 text-sm font-medium ${isCollapsed ? 'justify-center' : ''}`}
                        title={isCollapsed ? 'Sign Out' : undefined}
                    >
                        <SignOut size={20} className="flex-shrink-0" />
                        {showLabels && 'Sign Out'}
                    </button>
                </div>

                <div
                    className="absolute right-0 top-0 h-full w-1 cursor-ew-resize hover:bg-blue-500/50 active:bg-blue-500 transition-colors z-50"
                    onMouseDown={startResizing}
                    style={{ transform: 'translateX(50%)' }}
                />
            </aside>

            <main className="flex-1 overflow-auto relative z-10">
                <div className="print:hidden backdrop-blur-md bg-slate-950/80 border-b border-slate-700 sticky top-0 z-40">
                    <div className="flex items-center justify-between px-6 py-4">
                        <div className="flex items-center gap-4">
                            {isHidden && (
                                <button
                                    onClick={() => { setIsHidden(false); setSidebarWidth(DEFAULT_WIDTH); }}
                                    className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition-colors"
                                    title="Show Sidebar"
                                >
                                    <List size={24} />
                                </button>
                            )}
                            <div>
                                <h2 className="font-chivo font-bold text-xl uppercase tracking-wider">DeepShield AI</h2>
                                <p className="text-xs text-slate-400 font-mono mt-1">Welcome back, {name}</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-4">
                            <button
                                onClick={() => router.push('/dashboard/notifications')}
                                className="relative rounded-sm border border-slate-800 bg-slate-900/70 p-2 text-slate-300 hover:border-slate-600"
                                title="Notifications"
                            >
                                <Bell size={18} />
                                {unreadCount > 0 && (
                                    <span className="absolute -right-1 -top-1 inline-flex min-w-5 justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
                                        {unreadCount}
                                    </span>
                                )}
                            </button>
                            <div className="text-right hidden sm:block">
                                <p className="text-xs text-slate-500 uppercase tracking-wider font-mono">Logged in as</p>
                                <p className="text-sm font-mono text-slate-300">{email}</p>
                            </div>
                            <div className="h-9 w-9 rounded-full flex items-center justify-center shadow-lg overflow-hidden">
                                <div className="w-full h-full bg-gradient-to-br from-blue-600 to-cyan-700 flex items-center justify-center text-white font-bold text-sm">
                                    {name?.charAt(0).toUpperCase() || 'A'}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-6">
                    {children}
                </div>
            </main>

            {isResizing && (
                <div className="fixed inset-0 z-[100] cursor-ew-resize" />
            )}
        </div>
    );
}
