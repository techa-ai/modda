import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../utils/api';
import VerificationModal from '../components/VerificationModal';
import RAGStatusModal from '../components/RAGStatusModal';
import {
    Plus,
    Search,
    UserPlus,
    Play,
    MoreVertical,
    FileText,
    Loader2,
    Activity,
    RefreshCw,
    RotateCcw,
    X,
    Terminal,
    Trash2,
    LayoutGrid,
    List,
    Home,
    DollarSign,
    Percent,
    User,
    Building2,
    MapPin,
    TrendingUp,
    CreditCard,
    Briefcase,
    FileCheck,
    AlertCircle,
    CheckCircle2,
    Clock,
    Grid3X3,
    Rows3,
    ArrowUpDown,
    ArrowUp,
    ArrowDown,
    Filter,
    ChevronDown
} from 'lucide-react';

const AdminLoans = () => {
    const navigate = useNavigate();
    const [loans, setLoans] = useState([]);
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showAssignModal, setShowAssignModal] = useState(false);
    const [showLogsModal, setShowLogsModal] = useState(false);
    const [selectedLoan, setSelectedLoan] = useState(null);
    const [logs, setLogs] = useState([]);
    const [logsLoading, setLogsLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('summary'); // 'summary' or 'details'
    const [viewMode, setViewMode] = useState('list'); // 'grid' or 'list' (for summary tab)

    // Sorting and filtering
    const [sortField, setSortField] = useState('rag');
    const [sortDirection, setSortDirection] = useState('asc');
    const [searchTerm, setSearchTerm] = useState('');
    const [purposeFilter, setPurposeFilter] = useState('all');
    const [lienFilter, setLienFilter] = useState('all');
    const [statusFilter, setStatusFilter] = useState('all');
    const [showKeyDecisionFactors, setShowKeyDecisionFactors] = useState(true);

    // Form states
    const [newLoan, setNewLoan] = useState({ loan_number: '', document_location: '', assigned_to: '' });
    const [assignUser, setAssignUser] = useState('');
    const [processing, setProcessing] = useState(false);

    // Verification Modal State
    const [verificationModal, setVerificationModal] = useState({
        isOpen: false,
        evidence: [],
        attributeLabel: '',
        attributeValue: '',
        initialTab: 'summary',
        calculationSteps: []
    });

    // RAG Status Modal State
    const [ragStatusModal, setRagStatusModal] = useState({
        isOpen: false,
        loanData: null
    });

    // MT360 Validation Status cache
    const [mt360Validation, setMt360Validation] = useState({});

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const [loansRes, usersRes] = await Promise.all([
                api.get('/admin/loans'),
                api.get('/admin/users')
            ]);
            setLoans(loansRes.data.loans);
            setUsers(usersRes.data.users);

            // Fetch MT360 validation status for all loans
            const validationPromises = loansRes.data.loans.map(async (loan) => {
                try {
                    // Get cached validation for ALL doc types (matching detail page)
                    const docTypes = ['1008', 'URLA', 'Note', 'LoanEstimate', 'ClosingDisclosure', 'CreditReport', '1004'];
                    let totalMatches = 0;
                    let totalMismatches = 0;
                    let hasAnyValidation = false;

                    for (const docType of docTypes) {
                        try {
                            const resp = await api.get(`/admin/loans/${loan.id}/validation-cache/${docType}`);
                            if (resp.data && resp.data.matches !== undefined) {
                                totalMatches += resp.data.matches || 0;
                                totalMismatches += resp.data.mismatches || 0;
                                hasAnyValidation = true;
                            }
                        } catch (e) {
                            // No cache for this doc type
                        }
                    }

                    if (hasAnyValidation) {
                        const total = totalMatches + totalMismatches;
                        const accuracy = total > 0 ? ((totalMatches / total) * 100).toFixed(1) : 0;
                        return { loanId: loan.id, accuracy, matches: totalMatches, mismatches: totalMismatches };
                    }
                    return { loanId: loan.id, accuracy: null };
                } catch (e) {
                    return { loanId: loan.id, accuracy: null };
                }
            });

            const validationResults = await Promise.all(validationPromises);
            const validationMap = {};
            validationResults.forEach(r => {
                validationMap[r.loanId] = r;
            });
            setMt360Validation(validationMap);
        } catch (error) {
            console.error('Error fetching data:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateLoan = async (e) => {
        e.preventDefault();
        setProcessing(true);
        try {
            await api.post('/admin/loans', newLoan);
            await fetchData();
            setShowCreateModal(false);
            setNewLoan({ loan_number: '', document_location: '', assigned_to: '' });
        } catch (error) {
            alert('Error creating loan: ' + (error.response?.data?.message || error.message));
        } finally {
            setProcessing(false);
        }
    };

    const handleAssignLoan = async (e) => {
        e.preventDefault();
        setProcessing(true);
        try {
            await api.post(`/admin/loans/${selectedLoan.id}/assign`, { user_id: assignUser });
            await fetchData();
            setShowAssignModal(false);
            setSelectedLoan(null);
            setAssignUser('');
        } catch (error) {
            alert('Error assigning loan');
        } finally {
            setProcessing(false);
        }
    };

    const handleKickoffProcessing = async (loan, e) => {
        if (e) e.stopPropagation();
        const action = loan.status === 'pending' ? 'Start' : 'Retry';
        if (!window.confirm(`${action} processing for Loan #${loan.loan_number}?`)) return;

        try {
            await api.post(`/admin/loans/${loan.id}/process`);
            await fetchData();
            alert('Processing started successfully');
        } catch (error) {
            alert('Error starting processing');
        }
    };

    const handleDeleteLoan = async (loan, e) => {
        e.stopPropagation();
        if (!window.confirm(`Are you sure you want to delete Loan #${loan.loan_number}? This action cannot be undone.`)) {
            return;
        }

        try {
            await api.delete(`/admin/loans/${loan.id}`);
            await fetchData();
            alert('Loan deleted successfully');
        } catch (error) {
            alert('Error deleting loan: ' + (error.response?.data?.message || error.message));
        }
    };

    const handleViewLogs = async (loan, e) => {
        if (e) e.stopPropagation();
        setSelectedLoan(loan);
        setShowLogsModal(true);
        fetchLogs(loan.id);
    };

    const fetchLogs = async (loanId) => {
        if (!showLogsModal) setLogsLoading(true);
        try {
            const res = await api.get(`/admin/loans/${loanId}/logs`);
            setLogs(res.data.logs);
        } catch (error) {
            console.error('Error fetching logs:', error);
        } finally {
            setLogsLoading(false);
        }
    };

    useEffect(() => {
        let interval;
        if (showLogsModal && selectedLoan) {
            fetchLogs(selectedLoan.id);
            interval = setInterval(() => {
                fetchLogs(selectedLoan.id);
            }, 2000);
        }
        return () => clearInterval(interval);
    }, [showLogsModal, selectedLoan]);

    const handleVerifyClick = async (loan, type, e) => {
        console.log('Verify clicked:', type, loan.id);
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }

        // Map short code to attribute name/category
        const typeMap = {
            'income': 'Borrower Total Income Amount',
            'debt': 'total_all_monthly_payments', // Total Monthly Debt
            'credit': 'borrower_representative_credit_indicator_score',
            'property': 'property_appraised_value'
        };

        const attributeName = typeMap[type];
        if (!attributeName) {
            console.error('Unknown verification type:', type);
            return;
        }

        try {
            console.log('Fetching verification data...');
            // Fetch essential attributes which includes calculation steps
            const res = await api.get(`/user/loans/${loan.id}/essential-attributes`);
            const data = res.data;
            console.log('Verification data received:', data);

            // Debug: Log Underwriting attributes for debt type
            if (type === 'debt' && data.Underwriting) {
                console.log('Underwriting attributes:', data.Underwriting.map(a => ({
                    name: a.attribute_name,
                    label: a.attribute_label,
                    hasSteps: a.calculation_steps?.length || 0
                })));
            }

            // Flatten the categories to find our attribute
            let foundAttr = null;

            // Collect all potential matches
            const allAttributes = Object.values(data).flat();
            const candidates = allAttributes.filter(a =>
                a.attribute_name === attributeName ||
                (type === 'income' && (
                    a.attribute_label.includes('Total Monthly Income') ||
                    a.attribute_label === 'Total Income' ||
                    a.attribute_name === 'total_income'
                )) ||
                (type === 'debt' && (
                    a.attribute_label === 'Total All Monthly Payments' ||
                    a.attribute_name === 'total_all_monthly_payments'
                ))
            );

            console.log('Candidates:', candidates);

            // Prioritize candidates with calculation steps or evidence
            foundAttr = candidates.find(a =>
                (a.calculation_steps && a.calculation_steps.length > 0) ||
                (a.evidence && a.evidence.length > 0)
            );

            // Fallback to first candidate if no evidence found
            if (!foundAttr && candidates.length > 0) {
                foundAttr = candidates[0];
            }

            if (foundAttr) {
                console.log('Found attribute:', foundAttr);
                console.log('  - attribute_label:', foundAttr.attribute_label);
                console.log('  - extracted_value:', foundAttr.extracted_value);
                console.log('  - calculation_steps:', foundAttr.calculation_steps?.length || 0);
                console.log('  - evidence:', foundAttr.evidence?.length || 0);

                setVerificationModal({
                    isOpen: true,
                    evidence: foundAttr.evidence || [],
                    attributeLabel: foundAttr.attribute_label,
                    attributeValue: foundAttr.extracted_value,
                    loanId: loan.id,
                    initialTab: 'summary',
                    calculationSteps: foundAttr.calculation_steps || []
                });

                console.log('Modal state set:', {
                    isOpen: true,
                    stepsCount: foundAttr.calculation_steps?.length || 0,
                    evidenceCount: foundAttr.evidence?.length || 0
                });
            } else {
                console.warn('Attribute not found in response for', type);
                alert(`No detailed verification data found for ${type}`);
            }
        } catch (error) {
            console.error('Error fetching verification data:', error);
            alert('Error fetching verification details');
        }
    };

    const formatCurrency = (value) => {
        if (!value) return 'N/A';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
    };

    const formatPercent = (value) => {
        if (!value) return 'N/A';
        const num = parseFloat(value);
        return isNaN(num) ? 'N/A' : `${num.toFixed(3)}%`;
    };

    // Simplify source display
    const formatSource = (source) => {
        if (!source) return '-';
        const lower = source.toLowerCase();
        if (lower.includes('1008')) {
            return '1008';
        }
        if (lower.includes('non-standard') || lower.includes('non_standard')) {
            return 'Non-Standard';
        }
        return source;
    };

    // Check if rate comes from alternative source (no 1008)
    const isAlternativeRateSource = (source) => {
        if (!source) return false;
        const lower = source.toLowerCase();
        // If 1008 is NOT in the source, rate is from alternative
        return !lower.includes('1008');
    };

    // Format loan purpose - show full names
    const formatPurpose = (purpose) => {
        if (!purpose) return '-';
        if (purpose.toLowerCase().includes('cash-out') || purpose.toLowerCase().includes('cashout')) {
            return 'Cash-Out Refinance';
        }
        if (purpose.toLowerCase().includes('rate-term') || purpose.toLowerCase().includes('rate term')) {
            return 'Rate-Term Refinance';
        }
        return purpose;
    };

    // Get purpose style class
    const getPurposeStyle = (purpose) => {
        if (!purpose) return 'bg-slate-100 text-slate-600';
        const lower = purpose.toLowerCase();
        if (lower === 'purchase') return 'bg-blue-50 text-blue-700';
        if (lower.includes('cash-out') || lower.includes('cashout')) return 'bg-amber-50 text-amber-700';
        if (lower.includes('rate-term') || lower.includes('rate term')) return 'bg-green-50 text-green-700';
        return 'bg-slate-100 text-slate-600';
    };

    // Sorting function
    const handleSort = (field) => {
        if (sortField === field) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDirection('asc');
        }
    };

    // Get value for sorting
    const getSortValue = (loan, field) => {
        const profile = loan.profile || {};
        const loanInfo = profile.loan_info || {};
        const ratios = profile.ratios || {};
        const borrowerInfo = profile.borrower_info || {};
        const creditProfile = profile.credit_profile || {};

        switch (field) {
            case 'loan_number': return loan.loan_number || '';
            case 'borrower': return borrowerInfo.primary_borrower_name || '';
            case 'purpose': return loanInfo.loan_purpose || '';
            case 'lien': return loanInfo.lien_position || 'First';
            case 'amount': return loanInfo.loan_amount || 0;
            case 'rate': return loanInfo.interest_rate || 0;
            case 'dti': return ratios.dti_back_end_percent || 0;
            case 'cltv': return ratios.cltv_percent || 0;
            case 'credit_score': return creditProfile.credit_score || 0;
            case 'status': return loan.status || '';
            case 'rag': {
                // Calculate RAG status (EXACT same logic as in render)
                const propertyInfo = profile.property_info || {};
                const incomeProfile = profile.income_profile || {};
                const verificationStatus = profile.verification_status || {};
                const dscrAnalysis = profile.dscr_analysis || {};
                const isInvestment = propertyInfo.occupancy?.toLowerCase().includes('investment');
                const dscrRating = dscrAnalysis.dscr_rating;
                const dtiVal = parseFloat(ratios.dti_back_end_percent) || 0;
                const cltvVal = parseFloat(ratios.cltv_percent) || 0;
                const creditScore = creditProfile.credit_score ? parseInt(creditProfile.credit_score) : null;

                // Helper to determine badge status
                const getBadgeStatus = (verificationData, profileValue) => {
                    if (!verificationData) return 'missing';
                    if (verificationData.verified) return 'verified';
                    if (profileValue || verificationData.profile_value || verificationData.document_value) {
                        return 'mismatch';
                    }
                    return 'missing';
                };

                const incomeStatus = getBadgeStatus(verificationStatus.income, incomeProfile?.total_monthly_income);
                const debtStatus = getBadgeStatus(verificationStatus.debt, creditProfile?.total_monthly_debts);
                const creditStatus = getBadgeStatus(verificationStatus.credit_score, creditProfile?.credit_score);
                const propertyStatus = getBadgeStatus(verificationStatus.property_value, propertyInfo?.appraised_value);

                // DTI/DSCR RAG: For Investment use DSCR rating, otherwise DTI thresholds
                const getDtiDscrRag = () => {
                    if (isInvestment) {
                        // DSCR RAG: ≥1.25 Green, 1.0-1.25 Amber, <1.0 Red
                        return dscrRating || null;
                    }
                    // DTI RAG: ≤36% Green, 36-49% Amber, >49% Red
                    if (dtiVal <= 0) return null;
                    if (dtiVal <= 36) return 'G';
                    if (dtiVal <= 49) return 'A';
                    return 'R';
                };

                // CLTV RAG: ≤80 Green, >80 & ≤90 Amber, >90 Red
                const getCltvRag = () => {
                    if (cltvVal <= 0) return null;
                    if (cltvVal <= 80) return 'G';
                    if (cltvVal <= 90) return 'A';
                    return 'R';
                };

                // Credit Score RAG: ≥740 Green, 670-739 Amber, <670 Red
                const getCreditScoreRag = () => {
                    if (!creditScore) return null;
                    if (creditScore >= 740) return 'G';
                    if (creditScore >= 670) return 'A';
                    return 'R';
                };

                // Verification Status RAG: All verified = Green, Any not verified = Amber
                const getVerificationRag = () => {
                    if (incomeStatus === 'verified' &&
                        debtStatus === 'verified' &&
                        creditStatus === 'verified' &&
                        propertyStatus === 'verified') {
                        return 'G';
                    }
                    if (incomeStatus === 'mismatch' || incomeStatus === 'missing' ||
                        debtStatus === 'mismatch' || debtStatus === 'missing' ||
                        creditStatus === 'mismatch' || creditStatus === 'missing' ||
                        propertyStatus === 'mismatch' || propertyStatus === 'missing') {
                        return 'A';
                    }
                    return null;
                };

                // Overall RAG: worst (max) of DTI/DSCR, CLTV, Credit Score, and Verification Status
                const dtiDscrRag = getDtiDscrRag();
                const cltvRag = getCltvRag();
                const creditScoreRag = getCreditScoreRag();
                const verificationRag = getVerificationRag();

                let overallRag = null;
                // If any is Red, overall is Red
                if (dtiDscrRag === 'R' || cltvRag === 'R' || creditScoreRag === 'R' || verificationRag === 'R') overallRag = 'R';
                // If any is Amber, overall is Amber
                else if (dtiDscrRag === 'A' || cltvRag === 'A' || creditScoreRag === 'A' || verificationRag === 'A') overallRag = 'A';
                // If all are Green (or some null), overall is Green
                else if (dtiDscrRag === 'G' || cltvRag === 'G' || creditScoreRag === 'G') overallRag = 'G';

                // Return sortable value: G=1, A=2, R=3, null=4 (so G comes first)
                if (overallRag === 'G') return 1;
                if (overallRag === 'A') return 2;
                if (overallRag === 'R') return 3;
                return 4;
            }
            default: return '';
        }
    };

    // Filter and sort loans
    const filteredAndSortedLoans = loans
        .filter(loan => {
            const profile = loan.profile || {};
            const loanInfo = profile.loan_info || {};
            const borrowerInfo = profile.borrower_info || {};

            // Search filter
            if (searchTerm) {
                const search = searchTerm.toLowerCase();
                const matchesNumber = loan.loan_number?.toLowerCase().includes(search);
                const matchesBorrower = borrowerInfo.primary_borrower_name?.toLowerCase().includes(search);
                if (!matchesNumber && !matchesBorrower) return false;
            }

            // Purpose filter (HELOC counts as a purpose, use formatted names)
            if (purposeFilter !== 'all') {
                const isHeloc = loanInfo.is_heloc === true;
                const effectivePurpose = isHeloc ? 'HELOC' : formatPurpose(loanInfo.loan_purpose);
                if (effectivePurpose !== purposeFilter) return false;
            }

            // Lien filter
            if (lienFilter !== 'all') {
                const lien = loanInfo.lien_position || 'First';
                if (lien !== lienFilter) return false;
            }

            // Status filter
            if (statusFilter !== 'all' && loan.status !== statusFilter) return false;

            return true;
        })
        .sort((a, b) => {
            const aVal = getSortValue(a, sortField);
            const bVal = getSortValue(b, sortField);

            let comparison = 0;
            if (typeof aVal === 'number' && typeof bVal === 'number') {
                comparison = aVal - bVal;
            } else {
                comparison = String(aVal).localeCompare(String(bVal));
            }

            const primaryComparison = sortDirection === 'asc' ? comparison : -comparison;

            // If sorting by RAG and values are equal, use credit score as secondary sort (descending)
            if (sortField === 'rag' && primaryComparison === 0) {
                const aCreditScore = getSortValue(a, 'credit_score');
                const bCreditScore = getSortValue(b, 'credit_score');
                return bCreditScore - aCreditScore; // Descending (highest first)
            }

            return primaryComparison;
        });

    // Get unique values for filters (include HELOC as a purpose, use formatted names)
    const uniquePurposes = [...new Set(loans.map(l => {
        const isHeloc = l.profile?.loan_info?.is_heloc === true;
        if (isHeloc) return 'HELOC';
        return formatPurpose(l.profile?.loan_info?.loan_purpose);
    }).filter(Boolean))];
    const uniqueStatuses = [...new Set(loans.map(l => l.status).filter(Boolean))];

    // Sort header component
    const SortHeader = ({ field, children, className = '' }) => (
        <th
            className={`px-4 py-3 cursor-pointer hover:bg-slate-100 transition-colors select-none text-center ${className}`}
            onClick={() => handleSort(field)}
        >
            <div className="flex items-center justify-center gap-1">
                {children}
                {sortField === field ? (
                    sortDirection === 'asc' ? <ArrowUp size={14} /> : <ArrowDown size={14} />
                ) : (
                    <ArrowUpDown size={14} className="opacity-30" />
                )}
            </div>
        </th>
    );

    // Loan Profile Summary Card
    const LoanProfileCard = ({ loan }) => {
        const profile = loan.profile;
        const hasProfile = profile && !profile.error;

        if (!hasProfile) {
            return (
                <div
                    onClick={() => navigate(`/admin/loans/${loan.id}`)}
                    className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-lg hover:border-primary-300 transition-all cursor-pointer"
                >
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-slate-100 flex items-center justify-center">
                                <FileText className="w-5 h-5 text-slate-400" />
                            </div>
                            <div>
                                <h3 className="font-semibold text-slate-900">#{loan.loan_number}</h3>
                                <p className="text-xs text-slate-500">{loan.status}</p>
                            </div>
                        </div>
                        <span className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded-full">
                            No Profile
                        </span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400 text-sm">
                        <AlertCircle size={16} />
                        <span>Profile not extracted. Process loan to generate.</span>
                    </div>
                </div>
            );
        }

        const borrowerInfo = profile.borrower_info || {};
        const loanInfo = profile.loan_info || {};
        const propertyInfo = profile.property_info || {};
        const ratios = profile.ratios || {};
        const incomeProfile = profile.income_profile || {};
        const creditProfile = profile.credit_profile || {};
        const isHeloc = loanInfo.is_heloc === true;

        return (
            <div
                onClick={() => navigate(`/admin/loans/${loan.id}`)}
                className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-lg hover:border-primary-300 transition-all cursor-pointer group"
            >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${loanInfo.lien_position === 'Second'
                            ? 'bg-amber-100'
                            : 'bg-emerald-100'
                            }`}>
                            <Home className={`w-5 h-5 ${loanInfo.lien_position === 'Second'
                                ? 'text-amber-600'
                                : 'text-emerald-600'
                                }`} />
                        </div>
                        <div>
                            <h3 className="font-semibold text-slate-900">#{loan.loan_number}</h3>
                            <p className="text-xs text-slate-500">{borrowerInfo.primary_borrower_name || 'Unknown'}</p>
                        </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                        <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${loan.status === 'completed' ? 'bg-green-100 text-green-700' :
                            loan.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                                loan.status === 'evidencing' ? 'bg-purple-100 text-purple-700' :
                                    'bg-amber-100 text-amber-700'
                            }`}>
                            {loan.status}
                        </span>
                        <span className={`px-2 py-0.5 text-xs rounded-full ${loanInfo.lien_position === 'Second'
                            ? 'bg-amber-50 text-amber-700'
                            : 'bg-slate-100 text-slate-600'
                            }`}>
                            {loanInfo.lien_position || 'First'} Lien
                        </span>
                    </div>
                </div>

                {/* Key Metrics Grid */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                            <DollarSign size={12} />
                            <span>Loan Amount</span>
                        </div>
                        <p className="font-semibold text-slate-900">{formatCurrency(loanInfo.loan_amount)}</p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                            <Percent size={12} />
                            <span>Rate</span>
                        </div>
                        {(() => {
                            const isAltSource = isAlternativeRateSource(loan.analysis_source);
                            const rate = formatPercent(loanInfo.interest_rate);

                            return isAltSource && rate !== 'N/A' ? (
                                <p
                                    className="font-semibold text-purple-600 cursor-help"
                                    title="Rate from alternative source (HELOC Agreement/Rate Lock)"
                                >
                                    {rate}*
                                </p>
                            ) : (
                                <p className="font-semibold text-slate-900">{rate}</p>
                            );
                        })()}
                    </div>
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                            <TrendingUp size={12} />
                            <span>DTI</span>
                        </div>
                        <p className="font-semibold text-slate-900">{formatPercent(ratios.dti_back_end_percent)}</p>
                    </div>
                    <div className="bg-slate-50 rounded-lg p-3">
                        <div className="flex items-center gap-2 text-slate-500 text-xs mb-1">
                            <CreditCard size={12} />
                            <span>Credit Score</span>
                        </div>
                        {(() => {
                            const score = creditProfile.credit_score ? parseInt(creditProfile.credit_score) : null;
                            if (!score) return <p className="font-semibold text-slate-900">N/A</p>;

                            // Credit Score RAG: ≥740 Green, 670-739 Amber, <670 Red
                            const getCreditScoreColor = () => {
                                if (score >= 740) return 'text-green-600';
                                if (score >= 670) return 'text-amber-600';
                                return 'text-red-600';
                            };

                            return (
                                <p className={`font-semibold ${getCreditScoreColor()}`} title="Credit Score RAG: ≥740 Green, 670-739 Amber, <670 Red">
                                    {score}
                                </p>
                            );
                        })()}
                    </div>
                </div>

                {/* Loan Details */}
                <div className="space-y-2 text-sm">
                    <div className="flex items-center justify-between">
                        <span className="text-slate-500 flex items-center gap-2">
                            <Building2 size={14} />
                            Purpose
                        </span>
                        <span className={`font-medium ${isHeloc ? 'text-purple-700' : 'text-slate-700'}`}>
                            {isHeloc ? 'HELOC' : formatPurpose(loanInfo.loan_purpose)}
                        </span>
                    </div>
                    <div className="flex items-center justify-between">
                        <span className="text-slate-500 flex items-center gap-2">
                            <MapPin size={14} />
                            Property
                        </span>
                        <span className="font-medium text-slate-700">
                            {propertyInfo.state || 'N/A'} • {propertyInfo.property_type || 'N/A'}
                        </span>
                    </div>
                    <div className="flex items-center justify-between">
                        <span className="text-slate-500 flex items-center gap-2">
                            <Briefcase size={14} />
                            Income
                        </span>
                        <span className="font-medium text-slate-700">
                            {formatCurrency(incomeProfile.total_monthly_income)}/mo
                        </span>
                    </div>
                    {incomeProfile.income_types && incomeProfile.income_types.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-2 border-t border-slate-100">
                            {incomeProfile.income_types.slice(0, 3).map((type, i) => (
                                <span key={i} className="px-2 py-0.5 text-xs bg-blue-50 text-blue-700 rounded">
                                    {type}
                                </span>
                            ))}
                            {incomeProfile.income_types.length > 3 && (
                                <span className="px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded">
                                    +{incomeProfile.income_types.length - 3}
                                </span>
                            )}
                        </div>
                    )}
                </div>

                {/* Analysis Source Badge */}
                <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-100">
                    {loan.source_document ? (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                window.open(`/admin/loans/${loan.id}?doc=${encodeURIComponent(loan.source_document)}`, '_blank');
                            }}
                            className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1"
                            title={`View ${loan.source_document}`}
                        >
                            <FileCheck size={12} />
                            {formatSource(loan.analysis_source)}
                        </button>
                    ) : (
                        <span className="text-xs text-slate-400 flex items-center gap-1">
                            <FileCheck size={12} />
                            Source: {formatSource(loan.analysis_source)}
                        </span>
                    )}
                    <div className="flex items-center gap-2">
                        <button
                            onClick={(e) => handleViewLogs(loan, e)}
                            className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                            title="View Logs"
                        >
                            <Activity size={16} />
                        </button>
                        <button
                            onClick={(e) => handleKickoffProcessing(loan, e)}
                            className="p-1.5 text-slate-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                            title="Process"
                        >
                            <Play size={16} />
                        </button>
                    </div>
                </div>

                {/* LTV/CLTV bar */}
                {(ratios.ltv_percent || ratios.cltv_percent) && (
                    <div className="mt-3">
                        <div className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>LTV: {formatPercent(ratios.ltv_percent)}</span>
                            <span>CLTV: {formatPercent(ratios.cltv_percent)}</span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div
                                className={`h-full transition-all ${(ratios.cltv_percent || ratios.ltv_percent) > 80
                                    ? 'bg-amber-500'
                                    : 'bg-emerald-500'
                                    }`}
                                style={{ width: `${Math.min(ratios.cltv_percent || ratios.ltv_percent || 0, 100)}%` }}
                            />
                        </div>
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Loan Management</h1>
                    <p className="text-slate-500 mt-1">Create, assign, and process loans</p>
                </div>
                <div className="flex items-center gap-3">
                    {/* Tab Toggle */}
                    <div className="flex items-center bg-slate-100 rounded-lg p-1">
                        <button
                            onClick={() => setActiveTab('summary')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'summary'
                                ? 'bg-white text-slate-900 shadow-sm'
                                : 'text-slate-500 hover:text-slate-700'
                                }`}
                        >
                            <LayoutGrid size={16} />
                            Summary
                        </button>
                        <button
                            onClick={() => setActiveTab('details')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${activeTab === 'details'
                                ? 'bg-white text-slate-900 shadow-sm'
                                : 'text-slate-500 hover:text-slate-700'
                                }`}
                        >
                            <List size={16} />
                            Details
                        </button>
                    </div>
                    <button
                        onClick={() => setShowCreateModal(true)}
                        className="btn btn-primary flex items-center gap-2"
                    >
                        <Plus size={18} />
                        New Loan
                    </button>
                </div>
            </div>

            {/* Summary Tab - Card Grid or List */}
            {activeTab === 'summary' && (
                <div className="space-y-4">
                    {/* Filters and View Toggle */}
                    <div className="bg-white rounded-xl border border-slate-200 p-4">
                        <div className="flex flex-wrap items-center gap-4">
                            {/* Search */}
                            <div className="relative flex-1 min-w-[200px]">
                                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input
                                    type="text"
                                    placeholder="Search by loan # or borrower..."
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                                />
                            </div>

                            {/* Purpose Filter */}
                            <select
                                value={purposeFilter}
                                onChange={(e) => setPurposeFilter(e.target.value)}
                                className="px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                            >
                                <option value="all">All Purposes</option>
                                {uniquePurposes.map(p => (
                                    <option key={p} value={p}>{p}</option>
                                ))}
                            </select>

                            {/* Lien Filter */}
                            <select
                                value={lienFilter}
                                onChange={(e) => setLienFilter(e.target.value)}
                                className="px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                            >
                                <option value="all">All Liens</option>
                                <option value="First">First Lien</option>
                                <option value="Second">Second Lien</option>
                            </select>

                            {/* Status Filter */}
                            <select
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value)}
                                className="px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
                            >
                                <option value="all">All Status</option>
                                {uniqueStatuses.map(s => (
                                    <option key={s} value={s}>{s}</option>
                                ))}
                            </select>

                            {/* View Toggle */}
                            <div className="flex items-center bg-slate-100 rounded-lg p-0.5 ml-auto">
                                <button
                                    onClick={() => setViewMode('grid')}
                                    className={`p-1.5 rounded-md transition-colors ${viewMode === 'grid'
                                        ? 'bg-white text-slate-900 shadow-sm'
                                        : 'text-slate-500 hover:text-slate-700'
                                        }`}
                                    title="Grid View"
                                >
                                    <Grid3X3 size={16} />
                                </button>
                                <button
                                    onClick={() => setViewMode('list')}
                                    className={`p-1.5 rounded-md transition-colors ${viewMode === 'list'
                                        ? 'bg-white text-slate-900 shadow-sm'
                                        : 'text-slate-500 hover:text-slate-700'
                                        }`}
                                    title="List View"
                                >
                                    <Rows3 size={16} />
                                </button>
                            </div>
                        </div>

                        {/* Results count and toggles */}
                        <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                            <div className="flex items-center gap-4">
                                <p className="text-sm text-slate-500">
                                    Showing <span className="font-medium text-slate-700">{filteredAndSortedLoans.length}</span> of {loans.length} loans
                                </p>
                                <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={showKeyDecisionFactors}
                                        onChange={(e) => setShowKeyDecisionFactors(e.target.checked)}
                                        className="w-4 h-4 text-primary-600 bg-white border-slate-300 rounded focus:ring-primary-500 focus:ring-2"
                                    />
                                    <span>Show Loan Key Decision Factors</span>
                                </label>
                            </div>
                            {(searchTerm || purposeFilter !== 'all' || lienFilter !== 'all' || statusFilter !== 'all') && (
                                <button
                                    onClick={() => {
                                        setSearchTerm('');
                                        setPurposeFilter('all');
                                        setLienFilter('all');
                                        setStatusFilter('all');
                                    }}
                                    className="text-sm text-primary-600 hover:text-primary-700"
                                >
                                    Clear filters
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Grid View */}
                    {viewMode === 'grid' && (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                            {filteredAndSortedLoans.map((loan) => (
                                <LoanProfileCard key={loan.id} loan={loan} />
                            ))}
                            {filteredAndSortedLoans.length === 0 && !loading && (
                                <div className="col-span-full flex flex-col items-center justify-center py-16 text-slate-500">
                                    <FileText size={48} className="mb-4 text-slate-300" />
                                    <p>No loans match your filters.</p>
                                </div>
                            )}
                        </div>
                    )}

                    {/* List View */}
                    {viewMode === 'list' && (
                        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                            <div className="overflow-x-auto">
                                <table className="w-full text-left text-xs">
                                    <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
                                        <tr>
                                            <SortHeader field="loan_number">Loan</SortHeader>
                                            <SortHeader field="purpose">Loan Characteristics</SortHeader>
                                            {showKeyDecisionFactors && (
                                                <>
                                                    <SortHeader field="amount" className="text-right">Loan Amount</SortHeader>
                                                    <SortHeader field="dti" className="text-right">DTI/DSCR</SortHeader>
                                                    <SortHeader field="cltv" className="text-right">CLTV</SortHeader>
                                                    <SortHeader field="credit_score" className="text-center">Credit Score</SortHeader>
                                                </>
                                            )}
                                            <th className="px-4 py-3 text-center">MT360 OCR Validation Status</th>
                                            <th className="px-4 py-3 text-center">Data Verification Status</th>
                                            <SortHeader field="rag" className="text-center">RAG</SortHeader>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        {filteredAndSortedLoans.map((loan) => {
                                            const profile = loan.profile;
                                            const borrowerInfo = profile?.borrower_info || {};
                                            const loanInfo = profile?.loan_info || {};
                                            const propertyInfo = profile?.property_info || {};
                                            const ratios = profile?.ratios || {};
                                            const incomeProfile = profile?.income_profile || {};
                                            const creditProfile = profile?.credit_profile || {};
                                            const dscrAnalysis = profile?.dscr_analysis || {};
                                            const isHeloc = loanInfo.is_heloc === true;
                                            const isInvestment = propertyInfo.occupancy?.toLowerCase().includes('investment');
                                            const dscrVal = dscrAnalysis.dscr ? parseFloat(dscrAnalysis.dscr) : null;
                                            const dscrRating = dscrAnalysis.dscr_rating;

                                            // Format number to 3 decimal places
                                            const formatRate = (val) => {
                                                if (!val) return '-';
                                                const num = parseFloat(val);
                                                return isNaN(num) ? '-' : `${num.toFixed(3)}%`;
                                            };

                                            // Format DSCR to 3 decimal places
                                            const formatDscr = (val) => {
                                                if (!val) return '-';
                                                return val.toFixed(3);
                                            };

                                            // Get verification statuses from profile
                                            const verificationStatus = profile?.verification_status || {};

                                            // Helper to determine badge status: 'verified', 'mismatch', or 'missing'
                                            const getBadgeStatus = (verificationData, profileValue) => {
                                                if (!verificationData) return 'missing';
                                                if (verificationData.verified) return 'verified';
                                                // If not verified but has profile value or document value, it's a mismatch/gap
                                                if (profileValue || verificationData.profile_value || verificationData.document_value) {
                                                    return 'mismatch';
                                                }
                                                return 'missing';
                                            };

                                            const incomeStatus = getBadgeStatus(
                                                verificationStatus.income,
                                                incomeProfile?.total_monthly_income
                                            );
                                            const debtStatus = getBadgeStatus(
                                                verificationStatus.debt,
                                                creditProfile?.total_monthly_debts
                                            );
                                            const creditStatus = getBadgeStatus(
                                                verificationStatus.credit_score,
                                                creditProfile?.credit_score
                                            );
                                            const propertyStatus = getBadgeStatus(
                                                verificationStatus.property_value,
                                                propertyInfo?.appraised_value
                                            );

                                            // RAG status calculation
                                            const dtiVal = parseFloat(ratios.dti_back_end_percent) || 0;
                                            const cltvVal = parseFloat(ratios.cltv_percent) || 0;

                                            // DTI/DSCR RAG: For Investment use DSCR rating, otherwise DTI thresholds
                                            const getDtiDscrRag = () => {
                                                if (isInvestment) {
                                                    // DSCR RAG: ≥1.25 Green, 1.0-1.25 Amber, <1.0 Red
                                                    return dscrRating || null;
                                                }
                                                // DTI RAG: ≤36% Green, 36-49% Amber, >49% Red
                                                if (dtiVal <= 0) return null;
                                                if (dtiVal <= 36) return 'G';
                                                if (dtiVal <= 49) return 'A';
                                                return 'R';
                                            };

                                            // CLTV RAG: ≤80 Green, >80 & ≤90 Amber, >90 Red
                                            const getCltvRag = () => {
                                                if (cltvVal <= 0) return null;
                                                if (cltvVal <= 80) return 'G';
                                                if (cltvVal <= 90) return 'A';
                                                return 'R';
                                            };

                                            // Credit Score RAG: ≥740 Green, 670-739 Amber, <670 Red
                                            const getCreditScoreRag = () => {
                                                const score = creditProfile.credit_score ? parseInt(creditProfile.credit_score) : null;
                                                if (!score) return null;
                                                if (score >= 740) return 'G';
                                                if (score >= 670) return 'A';
                                                return 'R';
                                            };

                                            // Verification Status RAG: All verified = Green, Any not verified = Amber
                                            const getVerificationRag = () => {
                                                // If all 4 badges are verified, verification is Green
                                                if (incomeStatus === 'verified' &&
                                                    debtStatus === 'verified' &&
                                                    creditStatus === 'verified' &&
                                                    propertyStatus === 'verified') {
                                                    return 'G';
                                                }
                                                // If any badge is mismatch or missing, verification is Amber
                                                if (incomeStatus === 'mismatch' || incomeStatus === 'missing' ||
                                                    debtStatus === 'mismatch' || debtStatus === 'missing' ||
                                                    creditStatus === 'mismatch' || creditStatus === 'missing' ||
                                                    propertyStatus === 'mismatch' || propertyStatus === 'missing') {
                                                    return 'A';
                                                }
                                                return null;
                                            };

                                            // Overall RAG: worst (max) of DTI/DSCR, CLTV, Credit Score, and Verification Status
                                            const getOverallRag = () => {
                                                const dtiDscrRag = getDtiDscrRag();
                                                const cltvRag = getCltvRag();
                                                const creditScoreRag = getCreditScoreRag();
                                                const verificationRag = getVerificationRag();

                                                // If any is Red, overall is Red
                                                if (dtiDscrRag === 'R' || cltvRag === 'R' || creditScoreRag === 'R' || verificationRag === 'R') return 'R';
                                                // If any is Amber, overall is Amber
                                                if (dtiDscrRag === 'A' || cltvRag === 'A' || creditScoreRag === 'A' || verificationRag === 'A') return 'A';
                                                // If all are Green (or some null), overall is Green
                                                if (dtiDscrRag === 'G' || cltvRag === 'G' || creditScoreRag === 'G') return 'G';
                                                return null;
                                            };

                                            const overallRag = getOverallRag();

                                            return (
                                                <tr
                                                    key={loan.id}
                                                    className="hover:bg-slate-50/50 transition-colors"
                                                >
                                                    <td className="px-4 py-3">
                                                        <button
                                                            onClick={() => navigate(`/admin/loans/${loan.id}`)}
                                                            className="font-medium text-primary-600 hover:text-primary-700 hover:underline"
                                                        >
                                                            #{loan.loan_number}
                                                        </button>
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex flex-wrap items-center gap-1">
                                                            {/* Purpose Badge */}
                                                            <span className={`inline-flex px-2 py-0.5 text-xs rounded-full ${isHeloc ? 'bg-purple-100 text-purple-700 font-medium' : getPurposeStyle(loanInfo.loan_purpose)
                                                                }`}>
                                                                {isHeloc ? 'HELOC' : formatPurpose(loanInfo.loan_purpose)}
                                                            </span>

                                                            {/* Lien Position Badge */}
                                                            <span className={`inline-flex px-2 py-0.5 text-xs rounded-full font-medium ${loanInfo.lien_position === 'Second'
                                                                ? 'bg-amber-100 text-amber-700'
                                                                : 'bg-slate-100 text-slate-600'
                                                                }`}>
                                                                {loanInfo.lien_position || 'First'} Lien
                                                            </span>

                                                            {/* Investment Property Badge */}
                                                            {isInvestment && (
                                                                <span
                                                                    className="inline-flex px-2 py-0.5 text-xs rounded-full bg-orange-100 text-orange-700 font-medium"
                                                                    title="Investment Property"
                                                                >
                                                                    Investment
                                                                </span>
                                                            )}

                                                            {/* Bank Statement Badge - Only for non-DSCR bank statement loans */}
                                                            {(() => {
                                                                const underwritingNotes = profile?.underwriting_notes || {};
                                                                const incomeProfile = profile?.income_profile || {};
                                                                // Check if this is a bank statement loan (NOT DSCR)
                                                                const isBankStatementLoan =
                                                                    (underwritingNotes.is_bank_statement_loan === true ||
                                                                        incomeProfile.documentation_type === 'Bank Statement') &&
                                                                    !isInvestment; // Exclude investment/DSCR loans

                                                                if (isBankStatementLoan) {
                                                                    return (
                                                                        <span
                                                                            className="inline-flex px-2 py-0.5 text-xs rounded-full bg-blue-100 text-blue-700 font-medium"
                                                                            title="Bank Statement Underwriting"
                                                                        >
                                                                            Bank Statement
                                                                        </span>
                                                                    );
                                                                }
                                                                return null;
                                                            })()}
                                                        </div>
                                                    </td>
                                                    {showKeyDecisionFactors && (
                                                        <>
                                                            <td className="px-4 py-3 text-right font-medium text-slate-900">
                                                                {loanInfo.loan_amount ? formatCurrency(loanInfo.loan_amount) : '-'}
                                                            </td>
                                                            <td className="px-4 py-3 text-right">
                                                                {isInvestment ? (
                                                                    <span
                                                                        className={`font-medium cursor-help ${dscrRating === 'R' ? 'text-red-600' :
                                                                            dscrRating === 'A' ? 'text-amber-600' :
                                                                                dscrRating === 'G' ? 'text-green-600' :
                                                                                    'text-slate-400'
                                                                            }`}
                                                                        title={dscrVal ? `DSCR: ${dscrVal.toFixed(3)} | RAG Criteria: ≥1.25 Green, 1.0-1.25 Amber, <1.0 Red` : 'DSCR not calculated'}
                                                                    >
                                                                        {dscrVal ? formatDscr(dscrVal) : '-'}
                                                                    </span>
                                                                ) : (
                                                                    <span
                                                                        className={`font-medium cursor-help ${dtiVal > 49 ? 'text-red-600' :
                                                                            dtiVal > 36 ? 'text-amber-600' :
                                                                                dtiVal > 0 ? 'text-green-600' :
                                                                                    'text-slate-400'
                                                                            }`}
                                                                        title={ratios.dti_calculated
                                                                            ? `DTI calculated: ${ratios.dti_calculation_method || 'Estimated from available data'}`
                                                                            : "DTI RAG Criteria: ≤36% Green, 36-49% Amber, >49% Red"}
                                                                    >
                                                                        {formatRate(ratios.dti_back_end_percent)}{ratios.dti_calculated ? '*' : ''}
                                                                    </span>
                                                                )}
                                                            </td>
                                                            <td className="px-4 py-3 text-right">
                                                                <span
                                                                    className={`font-medium cursor-help ${cltvVal > 90 ? 'text-red-600' :
                                                                        cltvVal > 80 ? 'text-amber-600' :
                                                                            cltvVal > 0 ? 'text-green-600' :
                                                                                'text-slate-400'
                                                                        }`}
                                                                    title="CLTV RAG Criteria: ≤80% Green, 80-90% Amber, >90% Red"
                                                                >
                                                                    {formatRate(ratios.cltv_percent)}
                                                                </span>
                                                            </td>
                                                            <td className="px-4 py-3 text-center">
                                                                {(() => {
                                                                    const creditProfile = profile?.credit_profile || {};
                                                                    const creditScore = creditProfile.credit_score;
                                                                    const score = creditScore ? parseInt(creditScore) : null;

                                                                    if (!score) return <span className="text-slate-400">-</span>;

                                                                    // Credit Score RAG: ≥740 Green, 670-739 Amber, <670 Red
                                                                    const getCreditScoreColor = () => {
                                                                        if (score >= 740) return 'text-green-600';
                                                                        if (score >= 670) return 'text-amber-600';
                                                                        return 'text-red-600';
                                                                    };

                                                                    return (
                                                                        <span
                                                                            className={`font-medium cursor-help ${getCreditScoreColor()}`}
                                                                            title="Credit Score RAG Criteria: ≥740 Green, 670-739 Amber, <670 Red"
                                                                        >
                                                                            {score}
                                                                        </span>
                                                                    );
                                                                })()}
                                                            </td>
                                                        </>
                                                    )}
                                                    <td className="px-4 py-3 text-center">
                                                        {(() => {
                                                            const validation = mt360Validation[loan.id];
                                                            if (!validation || validation.accuracy === null) {
                                                                return <span className="text-slate-400 text-xs">-</span>;
                                                            }
                                                            const accuracy = parseFloat(validation.accuracy);
                                                            const colorClass = accuracy >= 90 ? 'text-green-600 bg-green-50 border-green-200' :
                                                                accuracy >= 75 ? 'text-amber-600 bg-amber-50 border-amber-200' :
                                                                    'text-red-600 bg-red-50 border-red-200';
                                                            return (
                                                                <button
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        navigate(`/admin/loans/${loan.id}?tab=mt360-ocr`);
                                                                    }}
                                                                    className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${colorClass} hover:ring-2 hover:ring-offset-1 cursor-pointer`}
                                                                    title={`${validation.matches} matches, ${validation.mismatches} mismatches - Click to view details`}
                                                                >
                                                                    {validation.accuracy}%
                                                                </button>
                                                            );
                                                        })()}
                                                    </td>
                                                    <td className="px-4 py-3">
                                                        <div className="flex gap-1 justify-center">
                                                            <span
                                                                className={`inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold rounded cursor-pointer hover:ring-2 hover:ring-offset-1 ${incomeStatus === 'verified'
                                                                    ? 'bg-green-100 text-green-700 hover:ring-green-400'
                                                                    : 'bg-amber-100 text-amber-700 hover:ring-amber-400'
                                                                    }`}
                                                                title={
                                                                    incomeStatus === 'verified' ? 'Income Verified - Click for details' :
                                                                        incomeStatus === 'mismatch' ? 'Income Mismatch/Gap - Click for details' :
                                                                            'Income Not Available'
                                                                }
                                                                onClick={(e) => handleVerifyClick(loan, 'income', e)}
                                                            >
                                                                I
                                                            </span>
                                                            <span
                                                                className={`inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold rounded cursor-pointer hover:ring-2 hover:ring-offset-1 ${debtStatus === 'verified'
                                                                    ? 'bg-green-100 text-green-700 hover:ring-green-400'
                                                                    : 'bg-amber-100 text-amber-700 hover:ring-amber-400'
                                                                    }`}
                                                                title={
                                                                    debtStatus === 'verified' ? 'Debt/Expense Verified - Click for details' :
                                                                        debtStatus === 'mismatch' ? 'Debt/Expense Mismatch/Gap - Click for details' :
                                                                            'Debt/Expense Not Available'
                                                                }
                                                                onClick={(e) => handleVerifyClick(loan, 'debt', e)}
                                                            >
                                                                D
                                                            </span>
                                                            <span
                                                                className={`inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold rounded cursor-pointer hover:ring-2 hover:ring-offset-1 ${creditStatus === 'verified'
                                                                    ? 'bg-green-100 text-green-700 hover:ring-green-400'
                                                                    : 'bg-amber-100 text-amber-700 hover:ring-amber-400'
                                                                    }`}
                                                                title={
                                                                    creditStatus === 'verified' ? 'Credit Score Verified - Click for details' :
                                                                        creditStatus === 'mismatch' ? 'Credit Score Mismatch/Gap - Click for details' :
                                                                            'Credit Score Not Available'
                                                                }
                                                                onClick={(e) => handleVerifyClick(loan, 'credit', e)}
                                                            >
                                                                C
                                                            </span>
                                                            <span
                                                                className={`inline-flex items-center justify-center w-5 h-5 text-[10px] font-bold rounded cursor-pointer hover:ring-2 hover:ring-offset-1 ${propertyStatus === 'verified'
                                                                    ? 'bg-green-100 text-green-700 hover:ring-green-400'
                                                                    : 'bg-amber-100 text-amber-700 hover:ring-amber-400'
                                                                    }`}
                                                                title={
                                                                    propertyStatus === 'verified' ? 'Property Value Verified - Click for details' :
                                                                        propertyStatus === 'mismatch' ? 'Property Value Mismatch/Gap - Click for details' :
                                                                            'Property Value Not Available'
                                                                }
                                                                onClick={(e) => handleVerifyClick(loan, 'property', e)}
                                                            >
                                                                V
                                                            </span>
                                                        </div>
                                                    </td>
                                                    <td className="px-4 py-3 text-center">
                                                        {overallRag ? (
                                                            <button
                                                                onClick={(e) => {
                                                                    e.stopPropagation();
                                                                    setRagStatusModal({
                                                                        isOpen: true,
                                                                        loanData: {
                                                                            id: loan.id,
                                                                            loan_number: loan.loan_number,
                                                                            profile: profile
                                                                        }
                                                                    });
                                                                }}
                                                                className={`inline-flex items-center justify-center w-6 h-6 text-xs font-bold rounded cursor-pointer hover:ring-2 hover:ring-offset-1 transition-all ${overallRag === 'R'
                                                                    ? 'bg-red-100 text-red-700 hover:ring-red-400 hover:bg-red-200'
                                                                    : overallRag === 'A'
                                                                        ? 'bg-amber-100 text-amber-700 hover:ring-amber-400 hover:bg-amber-200'
                                                                        : 'bg-green-100 text-green-700 hover:ring-green-400 hover:bg-green-200'
                                                                    }`}
                                                                title={`RAG Status: ${overallRag === 'R' ? 'Red' : overallRag === 'A' ? 'Amber' : 'Green'} - Click for details`}
                                                            >
                                                                {overallRag}
                                                            </button>
                                                        ) : (
                                                            <span className="text-slate-400">-</span>
                                                        )}
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                        {filteredAndSortedLoans.length === 0 && !loading && (
                                            <tr>
                                                <td colSpan={showKeyDecisionFactors ? 8 : 4} className="px-6 py-12 text-center text-slate-500">
                                                    No loans match your filters.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Details Tab - Table View */}
            {activeTab === 'details' && (
                <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm">
                            <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
                                <tr>
                                    <th className="px-6 py-4">Loan Details</th>
                                    <th className="px-6 py-4">Status</th>
                                    <th className="px-6 py-4">Assigned To</th>
                                    <th className="px-6 py-4">Document Location</th>
                                    <th className="px-6 py-4 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {loans.map((loan) => (
                                    <tr
                                        key={loan.id}
                                        onClick={() => navigate(`/admin/loans/${loan.id}`)}
                                        className="hover:bg-slate-50/50 transition-colors cursor-pointer"
                                    >
                                        <td className="px-6 py-4">
                                            <div className="font-medium text-slate-900">#{loan.loan_number}</div>
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${loan.status === 'completed' ? 'bg-green-50 text-green-700 border-green-200' :
                                                loan.status === 'processing' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                                                    'bg-amber-50 text-amber-700 border-amber-200'
                                                }`}>
                                                {loan.status}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4">
                                            {loan.assigned_to_name ? (
                                                <div className="flex items-center gap-2">
                                                    <div className="w-6 h-6 rounded-full bg-slate-200 flex items-center justify-center text-xs font-medium text-slate-600">
                                                        {loan.assigned_to_name[0].toUpperCase()}
                                                    </div>
                                                    <span className="text-slate-700">{loan.assigned_to_name}</span>
                                                </div>
                                            ) : (
                                                <span className="text-slate-400 italic">Unassigned</span>
                                            )}
                                        </td>
                                        <td className="px-6 py-4 max-w-xs truncate text-slate-500" title={loan.document_location}>
                                            {loan.document_location}
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="flex items-center justify-end gap-2">
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        setSelectedLoan(loan);
                                                        setAssignUser(loan.assigned_to || '');
                                                        setShowAssignModal(true);
                                                    }}
                                                    className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                                                    title="Assign User"
                                                >
                                                    <UserPlus size={18} />
                                                </button>
                                                {loan.status === 'processing' ? (
                                                    <button disabled className="p-1.5 text-slate-300 cursor-not-allowed">
                                                        <Loader2 size={18} className="animate-spin" />
                                                    </button>
                                                ) : (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            handleKickoffProcessing(loan, e);
                                                        }}
                                                        className="p-1.5 text-slate-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                                                        title={loan.status === 'pending' ? "Start Processing" : "Retry Processing"}
                                                    >
                                                        {loan.status === 'pending' ? <Play size={18} /> : <RotateCcw size={18} />}
                                                    </button>
                                                )}
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleViewLogs(loan, e);
                                                    }}
                                                    className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                                                    title="View Activity Logs"
                                                >
                                                    <Activity size={18} />
                                                </button>
                                                <button
                                                    onClick={(e) => handleDeleteLoan(loan, e)}
                                                    className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                                                    title="Delete Loan"
                                                >
                                                    <Trash2 size={18} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                                {loans.length === 0 && !loading && (
                                    <tr>
                                        <td colSpan="5" className="px-6 py-12 text-center text-slate-500">
                                            No loans found. Create one to get started.
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Create Loan Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-slate-900/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 animate-in fade-in zoom-in-95 duration-200">
                        <h2 className="text-xl font-bold text-slate-900 mb-4">Create New Loan</h2>
                        <form onSubmit={handleCreateLoan} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Loan Number</label>
                                <input
                                    type="text"
                                    required
                                    value={newLoan.loan_number}
                                    onChange={(e) => setNewLoan({ ...newLoan, loan_number: e.target.value })}
                                    className="input-field"
                                    placeholder="e.g., LN-2024-001"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Document Location</label>
                                <input
                                    type="text"
                                    required
                                    value={newLoan.document_location}
                                    onChange={(e) => setNewLoan({ ...newLoan, document_location: e.target.value })}
                                    className="input-field"
                                    placeholder="/path/to/loan/documents"
                                />
                                <p className="text-xs text-slate-500 mt-1">System will scan this path for Form 1008 and extract data automatically</p>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Assign To (Optional)</label>
                                <select
                                    value={newLoan.assigned_to}
                                    onChange={(e) => setNewLoan({ ...newLoan, assigned_to: e.target.value })}
                                    className="input-field"
                                >
                                    <option value="">Unassigned</option>
                                    {users.map(user => (
                                        <option key={user.id} value={user.id}>
                                            {user.username} ({user.email})
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setShowCreateModal(false)}
                                    className="btn btn-secondary"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={processing}
                                    className="btn btn-primary flex items-center gap-2"
                                >
                                    {processing && <Loader2 size={16} className="animate-spin" />}
                                    Create Loan
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Assign User Modal */}
            {showAssignModal && (
                <div className="fixed inset-0 bg-slate-900/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6 animate-in fade-in zoom-in-95 duration-200">
                        <h2 className="text-xl font-bold text-slate-900 mb-4">Assign Loan</h2>
                        <p className="text-sm text-slate-500 mb-4">
                            Assign Loan #{selectedLoan?.loan_number} to a user for review.
                        </p>
                        <form onSubmit={handleAssignLoan} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-slate-700 mb-1">Select User</label>
                                <select
                                    required
                                    value={assignUser}
                                    onChange={(e) => setAssignUser(e.target.value)}
                                    className="input-field"
                                >
                                    <option value="">Select a user...</option>
                                    {users.map(user => (
                                        <option key={user.id} value={user.id}>
                                            {user.username} ({user.email})
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex justify-end gap-3 mt-6">
                                <button
                                    type="button"
                                    onClick={() => setShowAssignModal(false)}
                                    className="btn btn-secondary"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={processing}
                                    className="btn btn-primary flex items-center gap-2"
                                >
                                    {processing && <Loader2 size={16} className="animate-spin" />}
                                    Assign
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* Logs Modal - Terminal Style */}
            {showLogsModal && (
                <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                    <div className="bg-slate-950 rounded-lg shadow-2xl w-full max-w-[95vw] h-[90vh] flex flex-col border border-slate-800 overflow-hidden font-mono antialiased text-sm">

                        {/* Terminal Header */}
                        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 select-none">
                            <div className="flex items-center gap-4">
                                <div className="flex gap-1.5">
                                    <button onClick={() => setShowLogsModal(false)} className="w-3 h-3 rounded-full bg-red-500 hover:bg-red-600 transition-colors" />
                                    <div className="w-3 h-3 rounded-full bg-yellow-500" />
                                    <div className="w-3 h-3 rounded-full bg-green-500" />
                                </div>
                                <div className="flex items-center gap-2 text-slate-400">
                                    <Terminal size={14} />
                                    <span className="opacity-75">modda-cli — process_loan.py — Loan #{selectedLoan?.loan_number}</span>
                                </div>
                            </div>
                            <button
                                onClick={() => fetchLogs(selectedLoan.id)}
                                disabled={logsLoading}
                                className="text-slate-500 hover:text-slate-300 transition-colors"
                                title="Refresh Logs"
                            >
                                <RefreshCw size={16} className={logsLoading ? 'animate-spin' : ''} />
                            </button>
                        </div>

                        {/* Terminal Content */}
                        <div className="flex-1 overflow-y-auto p-4 bg-[#0c0c0c] text-slate-300 space-y-1">
                            {logs.length === 0 ? (
                                <div className="text-slate-600 italic animate-pulse">&gt; Waiting for logs...</div>
                            ) : (
                                logs.map((log) => (
                                    <div key={log.id} className="flex gap-3 hover:bg-white/5 py-[1px] px-2 rounded group items-center text-[12px] font-mono leading-none">
                                        <span className="text-slate-500 shrink-0 select-none w-20 text-right font-light opacity-60">
                                            {new Date(log.created_at).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                        </span>
                                        <span className={`shrink-0 font-bold uppercase w-32 tracking-wider text-[11px] ${log.status === 'completed' ? 'text-emerald-500' :
                                            log.status === 'failed' ? 'text-red-500' :
                                                log.status === 'running' ? 'text-blue-400' :
                                                    'text-slate-500'
                                            }`}>
                                            [{log.step}]
                                        </span>
                                        <div className="flex items-center gap-2 flex-1 min-w-0">
                                            <span className={`truncate ${log.status === 'completed' ? 'text-emerald-500/90' :
                                                log.status === 'failed' ? 'text-red-400' :
                                                    'text-slate-300'
                                                }`}>
                                                {log.message}
                                            </span>
                                        </div>
                                    </div>
                                ))
                            )}
                            <div className="h-4" />
                            <div className="flex gap-2 text-slate-500 animate-pulse">
                                <span>&gt;</span>
                                <span className="w-2 h-4 bg-slate-500 block"></span>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Verification Modal */}
            <VerificationModal
                isOpen={verificationModal.isOpen}
                onClose={() => setVerificationModal({ ...verificationModal, isOpen: false })}
                evidence={verificationModal.evidence}
                attributeLabel={verificationModal.attributeLabel}
                attributeValue={verificationModal.attributeValue}
                loanId={verificationModal.loanId}
                initialTab={verificationModal.initialTab}
                calculationSteps={verificationModal.calculationSteps}
            />

            {/* RAG Status Modal */}
            <RAGStatusModal
                isOpen={ragStatusModal.isOpen}
                onClose={() => setRagStatusModal({ isOpen: false, loanData: null })}
                loanData={ragStatusModal.loanData}
            />
        </div>
    );
};

export default AdminLoans;
