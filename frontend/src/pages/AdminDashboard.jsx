import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../utils/api';
import {
    Users,
    FileText,
    Activity,
    Plus,
    ArrowRight
} from 'lucide-react';

const AdminDashboard = () => {
    const [stats, setStats] = useState({
        totalLoans: 0,
        activeUsers: 0,
        processingLoans: 0
    });
    const [recentLoans, setRecentLoans] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [loansRes, usersRes] = await Promise.all([
                    api.get('/admin/loans'),
                    api.get('/admin/users')
                ]);

                const loans = loansRes.data.loans;
                const users = usersRes.data.users;

                setStats({
                    totalLoans: loans.length,
                    activeUsers: users.length,
                    processingLoans: loans.filter(l => l.status === 'processing').length
                });

                setRecentLoans(loans.slice(0, 5));
            } catch (error) {
                console.error('Error fetching admin data:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, []);

    const StatCard = ({ title, value, icon: Icon, color }) => (
        <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <div className="flex items-center justify-between">
                <div>
                    <p className="text-sm font-medium text-slate-500">{title}</p>
                    <h3 className="text-2xl font-bold text-slate-900 mt-1">{value}</h3>
                </div>
                <div className={`p-3 rounded-lg ${color}`}>
                    <Icon size={24} className="text-white" />
                </div>
            </div>
        </div>
    );

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900">Admin Dashboard</h1>
                <p className="text-slate-500 mt-1">System overview and management</p>
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <StatCard
                    title="Total Loans"
                    value={loading ? '-' : stats.totalLoans}
                    icon={FileText}
                    color="bg-blue-500"
                />
                <StatCard
                    title="Active Users"
                    value={loading ? '-' : stats.activeUsers}
                    icon={Users}
                    color="bg-indigo-500"
                />
                <StatCard
                    title="Processing"
                    value={loading ? '-' : stats.processingLoans}
                    icon={Activity}
                    color="bg-amber-500"
                />
            </div>

            {/* Quick Actions */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-xl p-6 text-white relative overflow-hidden group">
                    <div className="relative z-10">
                        <h3 className="text-lg font-semibold mb-2">New Loan Analysis</h3>
                        <p className="text-slate-300 text-sm mb-6">Setup a new loan for due diligence processing and assignment.</p>
                        <Link
                            to="/admin/loans/new"
                            className="inline-flex items-center gap-2 px-4 py-2 bg-white text-slate-900 rounded-lg text-sm font-medium hover:bg-slate-100 transition-colors"
                        >
                            <Plus size={16} />
                            Create Loan
                        </Link>
                    </div>
                    <FileText className="absolute right-4 bottom-4 text-slate-700 w-24 h-24 opacity-20 group-hover:scale-110 transition-transform duration-500" />
                </div>

                <div className="bg-white rounded-xl p-6 border border-slate-200">
                    <div className="flex items-center justify-between mb-6">
                        <h3 className="text-lg font-semibold text-slate-900">Recent Activity</h3>
                        <Link to="/admin/loans" className="text-sm text-primary-600 hover:text-primary-700 flex items-center gap-1">
                            View All <ArrowRight size={14} />
                        </Link>
                    </div>
                    <div className="space-y-4">
                        {recentLoans.map(loan => (
                            <div key={loan.id} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 hover:bg-slate-100 transition-colors">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded bg-white border border-slate-200 flex items-center justify-center text-slate-500">
                                        <FileText size={14} />
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium text-slate-900">Loan #{loan.loan_number}</p>
                                        <p className="text-xs text-slate-500">{loan.status}</p>
                                    </div>
                                </div>
                                <span className="text-xs text-slate-400">
                                    {new Date(loan.created_at).toLocaleDateString()}
                                </span>
                            </div>
                        ))}
                        {recentLoans.length === 0 && !loading && (
                            <p className="text-sm text-slate-500 text-center py-4">No recent activity</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AdminDashboard;
