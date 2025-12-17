import React from 'react';
import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
    LayoutDashboard,
    FileText,
    Settings,
    LogOut,
    User,
    Shield,
    Menu,
    X,
    ChevronLeft,
    ChevronRight
} from 'lucide-react';
import { clsx } from 'clsx';

const Layout = () => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false);
    const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    const navItems = [
        {
            label: 'Dashboard',
            path: user?.role === 'admin' ? '/admin/dashboard' : '/dashboard',
            icon: LayoutDashboard
        },
        ...(user?.role === 'admin' ? [
            { label: 'Loan Management', path: '/admin/loans', icon: FileText },
            { label: 'Configuration', path: '/admin/config', icon: Settings },
        ] : []),
    ];

    return (
        <div className="min-h-screen bg-slate-50 flex">
            {/* Sidebar */}
            <aside className={clsx(
                "fixed inset-y-0 left-0 z-50 bg-slate-900 text-white transition-all duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0 shadow-xl",
                isMobileMenuOpen ? "translate-x-0" : "-translate-x-full",
                isSidebarCollapsed ? "w-16" : "w-64"
            )}>
                <div className="h-full flex flex-col">
                    {/* Logo */}
                    <div className="h-14 flex items-center px-4 border-b border-slate-800 bg-slate-950">
                        <div className={clsx("flex items-center gap-2", isSidebarCollapsed && "justify-center w-full")}>
                            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center text-white font-bold text-sm shadow-lg shadow-primary-500/20">
                                M
                            </div>
                            {!isSidebarCollapsed && (
                                <span className="text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                                    MODDA
                                </span>
                            )}
                        </div>
                        <button
                            onClick={() => setIsMobileMenuOpen(false)}
                            className={clsx("ml-auto lg:hidden text-slate-400 hover:text-white", isSidebarCollapsed && "hidden")}
                        >
                            <X size={18} />
                        </button>
                    </div>

                    {/* User Info */}
                    <div className={clsx("border-b border-slate-800 bg-slate-900/50", isSidebarCollapsed ? "p-2" : "p-4")}>
                        <div className={clsx("flex items-center", isSidebarCollapsed ? "justify-center" : "gap-2")}>
                            <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-primary-400 border border-slate-700" title={user?.username}>
                                <User size={16} />
                            </div>
                            {!isSidebarCollapsed && (
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs font-medium text-white truncate">
                                        {user?.username}
                                    </p>
                                    <p className="text-xs text-slate-400 flex items-center gap-1">
                                        {user?.role === 'admin' && <Shield size={9} className="text-primary-400" />}
                                        {user?.role === 'admin' ? 'Admin' : 'Officer'}
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Navigation */}
                    <nav className={clsx("flex-1 py-3 space-y-0.5 overflow-y-auto", isSidebarCollapsed ? "px-1" : "px-2")}>
                        {navItems.map((item) => {
                            const isActive = location.pathname === item.path;
                            return (
                                <Link
                                    key={item.path}
                                    to={item.path}
                                    title={isSidebarCollapsed ? item.label : undefined}
                                    className={clsx(
                                        "flex items-center rounded-lg text-xs font-medium transition-all duration-200 group",
                                        isSidebarCollapsed ? "justify-center p-2.5" : "gap-2 px-2.5 py-2",
                                        isActive
                                            ? "bg-primary-600 text-white shadow-lg shadow-primary-900/20"
                                            : "text-slate-400 hover:text-white hover:bg-slate-800"
                                    )}
                                >
                                    <item.icon size={16} className={clsx(
                                        "transition-colors flex-shrink-0",
                                        isActive ? "text-white" : "text-slate-500 group-hover:text-white"
                                    )} />
                                    {!isSidebarCollapsed && item.label}
                                </Link>
                            );
                        })}
                    </nav>

                    {/* Collapse Toggle */}
                    <div className="p-2 border-t border-slate-800 hidden lg:block">
                        <button
                            onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                            className={clsx(
                                "flex items-center w-full rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-all duration-200",
                                isSidebarCollapsed ? "justify-center p-2.5" : "gap-2 px-2.5 py-2"
                            )}
                            title={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                        >
                            {isSidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
                            {!isSidebarCollapsed && "Collapse"}
                        </button>
                    </div>

                    {/* Footer */}
                    <div className={clsx("border-t border-slate-800", isSidebarCollapsed ? "p-2" : "p-3")}>
                        <button
                            onClick={handleLogout}
                            title={isSidebarCollapsed ? "Sign Out" : undefined}
                            className={clsx(
                                "flex items-center w-full rounded-lg text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-800 transition-all duration-200",
                                isSidebarCollapsed ? "justify-center p-2.5" : "gap-2 px-2.5 py-2"
                            )}
                        >
                            <LogOut size={16} />
                            {!isSidebarCollapsed && "Sign Out"}
                        </button>
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                {/* Mobile Header */}
                <header className="lg:hidden h-14 bg-white border-b border-slate-200 flex items-center px-3 justify-between">
                    <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center text-white font-bold text-sm">
                            M
                        </div>
                        <span className="text-lg font-bold text-slate-900">MODDA</span>
                    </div>
                    <button
                        onClick={() => setIsMobileMenuOpen(true)}
                        className="p-1.5 text-slate-600 hover:bg-slate-100 rounded-lg"
                    >
                        <Menu size={20} />
                    </button>
                </header>

                <main className="flex-1 overflow-y-auto p-3 sm:p-4 lg:p-5">
                    <Outlet />
                </main>
            </div>

            {/* Mobile Overlay */}
            {isMobileMenuOpen && (
                <div
                    className="fixed inset-0 bg-slate-900/50 z-40 lg:hidden backdrop-blur-sm"
                    onClick={() => setIsMobileMenuOpen(false)}
                />
            )}
        </div>
    );
};

export default Layout;
