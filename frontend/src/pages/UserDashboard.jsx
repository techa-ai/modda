import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import api from '../utils/api';
import {
    FileText,
    Clock,
    CheckCircle2,
    AlertCircle,
    ChevronRight,
    Search,
    Filter
} from 'lucide-react';
import { clsx } from 'clsx';

const UserDashboard = () => {
    const [loans, setLoans] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');
    const [search, setSearch] = useState('');

    useEffect(() => {
        const fetchLoans = async () => {
            try {
                const response = await api.get('/user/loans');
                setLoans(response.data.loans);
            } catch (error) {
                console.error('Error fetching loans:', error);
            } finally {
                setLoading(false);
            }
        };

        fetchLoans();
    }, []);

    const getStatusColor = (status) => {
        switch (status) {
            case 'completed': return 'text-green-600 bg-green-50 border-green-200';
            case 'processing': return 'text-blue-600 bg-blue-50 border-blue-200';
            case 'failed': return 'text-red-600 bg-red-50 border-red-200';
            default: return 'text-amber-600 bg-amber-50 border-amber-200';
        }
    };

    const getStatusIcon = (status) => {
        switch (status) {
            case 'completed': return <CheckCircle2 size={16} />;
            case 'processing': return <Clock size={16} />;
            case 'failed': return <AlertCircle size={16} />;
            default: return <Clock size={16} />;
        }
    };

    const filteredLoans = loans.filter(loan => {
        const matchesFilter = filter === 'all' || loan.status === filter;
        const matchesSearch = loan.loan_number.toLowerCase().includes(search.toLowerCase()) ||
            (loan.loan_name && loan.loan_name.toLowerCase().includes(search.toLowerCase()));
        return matchesFilter && matchesSearch;
    });

    return (
        <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">My Assigned Loans</h1>
                    <p className="text-slate-500 mt-1">Manage and review your loan portfolio</p>
                </div>

                <div className="flex items-center gap-3">
                    <div className="relative">
                        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input
                            type="text"
                            placeholder="Search loans..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="pl-10 pr-4 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 w-full sm:w-64"
                        />
                    </div>
                    <div className="relative">
                        <select
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="appearance-none pl-4 pr-10 py-2 rounded-lg border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 bg-white"
                        >
                            <option value="all">All Status</option>
                            <option value="pending">Pending</option>
                            <option value="processing">Processing</option>
                            <option value="completed">Completed</option>
                        </select>
                        <Filter size={16} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
                    </div>
                </div>
            </div>

            {loading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {[1, 2, 3].map(i => (
                        <div key={i} className="h-48 rounded-xl bg-slate-100 animate-pulse" />
                    ))}
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredLoans.map((loan) => (
                        <Link
                            key={loan.id}
                            to={`/loans/${loan.id}`}
                            className="group bg-white rounded-xl p-6 border border-slate-200 shadow-sm hover:shadow-md hover:border-primary-200 transition-all duration-200"
                        >
                            <div className="flex items-start justify-between mb-4">
                                <div className="w-10 h-10 rounded-lg bg-primary-50 flex items-center justify-center text-primary-600 group-hover:bg-primary-100 transition-colors">
                                    <FileText size={20} />
                                </div>
                                <span className={clsx(
                                    "px-2.5 py-1 rounded-full text-xs font-medium border flex items-center gap-1.5",
                                    getStatusColor(loan.status)
                                )}>
                                    {getStatusIcon(loan.status)}
                                    {loan.status.charAt(0).toUpperCase() + loan.status.slice(1)}
                                </span>
                            </div>

                            <h3 className="text-lg font-semibold text-slate-900 mb-1 group-hover:text-primary-600 transition-colors">
                                Loan #{loan.loan_number}
                            </h3>
                            <p className="text-sm text-slate-500 mb-4">
                                {loan.loan_name || 'Unnamed Loan'}
                            </p>

                            <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-sm text-slate-500">
                                <span>Created {new Date(loan.created_at).toLocaleDateString()}</span>
                                <ChevronRight size={16} className="text-slate-300 group-hover:text-primary-500 transition-colors" />
                            </div>
                        </Link>
                    ))}

                    {filteredLoans.length === 0 && (
                        <div className="col-span-full py-12 text-center bg-slate-50 rounded-xl border border-dashed border-slate-300">
                            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-3 text-slate-400">
                                <FileText size={24} />
                            </div>
                            <h3 className="text-sm font-medium text-slate-900">No loans found</h3>
                            <p className="text-sm text-slate-500 mt-1">Try adjusting your search or filters</p>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default UserDashboard;
