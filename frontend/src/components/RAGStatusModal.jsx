import React, { useState, useEffect } from 'react';
import { X, CheckCircle2, XCircle, AlertCircle, ChevronDown, ChevronRight, FileText, Sparkles } from 'lucide-react';

const RAGStatusModal = ({ isOpen, onClose, loanData }) => {
    const [expandedSections, setExpandedSections] = useState({
        documentVerification: true,
        dti: false,
        cltv: false,
        creditScore: false
    });
    
    const [verificationSummaries, setVerificationSummaries] = useState({
        income: null,
        debt: null,
        credit_score: null,
        property_value: null,
        dti_dscr: null,
        cltv: null,
        loading: false
    });
    
    const [creditReportModal, setCreditReportModal] = useState(false);
    const [creditReportDetail, setCreditReportDetail] = useState(null);
    const [creditExecutiveSummary, setCreditExecutiveSummary] = useState(null);
    
    // Fetch verification summaries when modal opens
    useEffect(() => {
        if (!isOpen || !loanData?.id) {
            console.log('Modal not open or no loan data:', { isOpen, loanId: loanData?.id });
            return;
        }
        
        const fetchSummaries = async () => {
            const profile = loanData?.profile || {};
            const verificationStatus = profile.verification_status || {};
            
            console.log('Verification Status:', verificationStatus);
            
            // Only fetch summaries for verified items
            const toFetch = [];
            if (verificationStatus.income?.verified) toFetch.push('income');
            if (verificationStatus.debt?.verified) toFetch.push('debt');
            if (verificationStatus.credit_score?.verified) toFetch.push('credit_score');
            if (verificationStatus.property_value?.verified) toFetch.push('property_value');
            if (verificationStatus.dti_dscr?.verified) toFetch.push('dti_dscr');
            if (verificationStatus.cltv?.verified) toFetch.push('cltv');
            
            // Also check for detailed credit summary and executive summary
            if (verificationStatus.credit_score?.detailed_summary) {
                setCreditReportDetail(verificationStatus.credit_score.detailed_summary);
            }
            if (verificationStatus.credit_score?.executive_summary) {
                setCreditExecutiveSummary(verificationStatus.credit_score.executive_summary);
            }
            
            console.log('Items to fetch summaries for:', toFetch);
            
            if (toFetch.length === 0) {
                console.log('No verified items to fetch summaries for');
                return;
            }
            
            setVerificationSummaries(prev => ({ ...prev, loading: true }));
            
            try {
                const token = localStorage.getItem('token');
                const summaries = {};
                
                for (const type of toFetch) {
                    try {
                        console.log(`Fetching ${type} summary for loan ${loanData.id}...`);
                        const response = await fetch(`/api/user/loans/${loanData.id}/verification-summary/${type}`, {
                            headers: {
                                'Authorization': `Bearer ${token}`,
                                'Content-Type': 'application/json'
                            }
                        });
                        
                        console.log(`${type} summary response status:`, response.status);
                        
                        if (response.ok) {
                            const data = await response.json();
                            console.log(`${type} summary data:`, data);
                            summaries[type] = data;
                        } else {
                            console.error(`Failed to fetch ${type} summary:`, await response.text());
                        }
                    } catch (err) {
                        console.error(`Error fetching ${type} summary:`, err);
                    }
                }
                
                console.log('Setting verification summaries:', summaries);
                setVerificationSummaries(prev => ({
                    ...summaries,
                    loading: false
                }));
            } catch (error) {
                console.error('Error fetching verification summaries:', error);
                setVerificationSummaries(prev => ({ ...prev, loading: false }));
            }
        };
        
        fetchSummaries();
    }, [isOpen, loanData?.id]);
    
    // Debug rendering
    console.log('RAGStatusModal render - verificationSummaries:', verificationSummaries);

    if (!isOpen) return null;

    // Extract data from loan profile
    const profile = loanData?.profile || {};
    const ratios = profile.ratios || {};
    const creditProfile = profile.credit_profile || {};
    const incomeProfile = profile.income_profile || {};
    const verificationStatus = profile.verification_status || {};
    const propertyInfo = profile.property_info || {};
    const dscrAnalysis = profile.dscr_analysis || {};
    
    const isInvestment = propertyInfo.occupancy?.toLowerCase().includes('investment');
    const dtiVal = parseFloat(ratios.dti_back_end_percent) || 0;
    const cltvVal = parseFloat(ratios.cltv_percent) || 0;
    const creditScore = creditProfile.credit_score ? parseInt(creditProfile.credit_score) : null;
    const dscrVal = dscrAnalysis.dscr ? parseFloat(dscrAnalysis.dscr) : null;

    // RAG calculation functions
    const getDtiDscrRag = () => {
        if (isInvestment) {
            if (!dscrVal) return null;
            if (dscrVal >= 1.25) return 'G';
            if (dscrVal >= 1.0) return 'A';
            return 'R';
        }
        if (dtiVal <= 0) return null;
        if (dtiVal <= 36) return 'G';
        if (dtiVal <= 49) return 'A';
        return 'R';
    };

    const getCltvRag = () => {
        if (cltvVal <= 0) return null;
        if (cltvVal <= 80) return 'G';
        if (cltvVal <= 90) return 'A';
        return 'R';
    };

    const getCreditScoreRag = () => {
        if (!creditScore) return null;
        if (creditScore >= 740) return 'G';
        if (creditScore >= 670) return 'A';
        return 'R';
    };

    const getDocumentVerificationRag = () => {
        const incomeVerified = verificationStatus.income?.verified || false;
        const debtVerified = verificationStatus.debt?.verified || false;
        const creditVerified = verificationStatus.credit_score?.verified || false;
        const propertyVerified = verificationStatus.property_value?.verified || false;
        
        const verifiedCount = [incomeVerified, debtVerified, creditVerified, propertyVerified].filter(Boolean).length;
        
        if (verifiedCount === 4) return 'G';
        if (verifiedCount >= 2) return 'A';
        return 'R';
    };

    const getOverallRag = () => {
        const rags = [
            getDtiDscrRag(),
            getCltvRag(),
            getCreditScoreRag(),
            getDocumentVerificationRag()
        ].filter(Boolean);

        if (rags.includes('R')) return 'R';
        if (rags.includes('A')) return 'A';
        if (rags.length > 0) return 'G';
        return null;
    };

    const overallRag = getOverallRag();
    const dtiDscrRag = getDtiDscrRag();
    const cltvRag = getCltvRag();
    const creditScoreRag = getCreditScoreRag();
    const docVerificationRag = getDocumentVerificationRag();

    // RAG Badge Component
    const RAGBadge = ({ rag, size = 'md', label = null, value = null, showColorName = true }) => {
        if (!rag) return <span className="text-slate-400 text-xs">N/A</span>;

        const sizeClasses = {
            sm: 'w-6 h-6 text-xs',
            md: 'w-10 h-10 text-base',
            lg: 'w-14 h-14 text-2xl'
        };

        const colorClasses = {
            R: 'bg-red-100 text-red-700 border-red-300',
            A: 'bg-amber-100 text-amber-700 border-amber-300',
            G: 'bg-green-100 text-green-700 border-green-300'
        };

        return (
            <div className="flex flex-col items-center gap-1">
                <div className={`${sizeClasses[size]} ${colorClasses[rag]} rounded-lg border-2 flex items-center justify-center font-bold shadow-sm`}>
                    {rag}
                </div>
                {label && <span className="text-[10px] text-slate-600 font-medium">{label}</span>}
                {value && <span className="text-[10px] text-slate-700 font-semibold">{value}</span>}
            </div>
        );
    };

    // Verification Item Component
    const VerificationItem = ({ label, value, verified, criteria = null }) => {
        return (
            <div className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0">
                <div className="flex-1">
                    <div className="flex items-center gap-1.5">
                        {verified ? (
                            <CheckCircle2 size={14} className="text-green-600" />
                        ) : (
                            <XCircle size={14} className="text-slate-400" />
                        )}
                        <span className="text-sm font-medium text-slate-700">{label}</span>
                    </div>
                    {criteria && <div className="text-[10px] text-slate-500 ml-5">{criteria}</div>}
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">{value}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                        verified 
                            ? 'bg-green-100 text-green-700' 
                            : 'bg-slate-100 text-slate-600'
                    }`}>
                        {verified ? '✓' : '✗'}
                    </span>
                </div>
            </div>
        );
    };

    // Section Component
    const Section = ({ title, ragValue, sectionKey, children }) => {
        const isExpanded = expandedSections[sectionKey];

        return (
            <div className="bg-white border border-slate-200 rounded-lg overflow-hidden mb-2 shadow-sm">
                <button
                    onClick={() => setExpandedSections(prev => ({ ...prev, [sectionKey]: !isExpanded }))}
                    className="w-full flex items-center justify-between px-3 py-2 bg-slate-50 hover:bg-slate-100 transition-colors"
                >
                    <div className="flex items-center gap-2">
                        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                        <h3 className="font-semibold text-sm text-slate-900">{title}</h3>
                    </div>
                    <RAGBadge rag={ragValue} size="sm" />
                </button>
                {isExpanded && (
                    <div className="px-3 py-2 bg-white">
                        {children}
                    </div>
                )}
            </div>
        );
    };

    const formatCurrency = (value) => {
        if (!value) return 'N/A';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
    };

    const formatPercent = (value) => {
        if (!value) return 'N/A';
        return `${parseFloat(value).toFixed(2)}%`;
    };

    return (
        <div className="fixed inset-0 bg-black/80 z-50 backdrop-blur-sm">
            <div className="bg-white w-full h-full overflow-hidden flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-3 border-b border-slate-200 bg-slate-900 text-white">
                    <div>
                        <h2 className="text-xl font-bold">RAG Status Analysis - Loan #{loanData?.loan_number}</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1.5 hover:bg-white/10 rounded-lg transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-4 bg-slate-50">
                    <div className="max-w-7xl mx-auto">
                        {/* Top Summary Row */}
                        <div className="grid grid-cols-5 gap-3 mb-4">
                            {/* Overall RAG Status */}
                            <div className="bg-white border border-slate-200 rounded-lg p-3 text-center shadow-sm">
                                <RAGBadge rag={overallRag} size="md" />
                                <div className="text-xs font-semibold text-slate-600 mt-2">Overall Rating</div>
                            </div>

                            {/* Constituent RAG Badges */}
                            <div className="bg-white border border-slate-200 rounded-lg p-3 text-center shadow-sm">
                                <RAGBadge 
                                    rag={dtiDscrRag} 
                                    size="md" 
                                    label={isInvestment ? "DSCR" : "DTI"} 
                                    value={isInvestment ? (dscrVal ? dscrVal.toFixed(2) : 'N/A') : (dtiVal ? `${dtiVal.toFixed(1)}%` : 'N/A')}
                                />
                            </div>
                            <div className="bg-white border border-slate-200 rounded-lg p-3 text-center shadow-sm">
                                <RAGBadge 
                                    rag={cltvRag} 
                                    size="md" 
                                    label="CLTV" 
                                    value={cltvVal ? `${cltvVal.toFixed(1)}%` : 'N/A'}
                                />
                            </div>
                            <div className="bg-white border border-slate-200 rounded-lg p-3 text-center shadow-sm">
                                <RAGBadge 
                                    rag={creditScoreRag} 
                                    size="md" 
                                    label="Credit Score" 
                                    value={creditScore || 'N/A'}
                                />
                            </div>
                            <div className="bg-white border border-slate-200 border-l-4 border-l-indigo-500 rounded-lg p-3 text-center shadow-sm">
                                <RAGBadge 
                                    rag={docVerificationRag} 
                                    size="md" 
                                    label="Data Verification" 
                                    value={(() => {
                                        const incomeVerified = verificationStatus.income?.verified || false;
                                        const debtVerified = verificationStatus.debt?.verified || false;
                                        const creditVerified = verificationStatus.credit_score?.verified || false;
                                        const propertyVerified = verificationStatus.property_value?.verified || false;
                                        const verifiedCount = [incomeVerified, debtVerified, creditVerified, propertyVerified].filter(Boolean).length;
                                        return `${verifiedCount}/4`;
                                    })()}
                                />
                            </div>
                        </div>

                        {/* Detailed Sections */}
                        
                        {/* Data Verification Section */}
                        <div className="bg-white border-2 border-slate-300 rounded-lg overflow-hidden mb-2 shadow-md">
                        <div className="px-4 py-3 bg-gradient-to-r from-slate-800 to-slate-700 text-white">
                            <h3 className="font-bold text-base">Data Verification</h3>
                            <p className="text-xs text-slate-300 mt-0.5">Systematic validation of essential loan attributes</p>
                        </div>
                        <div className="p-4 space-y-3">
                        <VerificationItem
                            label="Income"
                            value={formatCurrency(incomeProfile.total_monthly_income)}
                            verified={verificationStatus.income?.verified || false}
                        />
                        
                        {/* Professional Income Verification Summary */}
                        {verificationStatus.income?.verified && verificationSummaries.income && (
                            <div className="ml-5 mt-2 mb-3 p-3 bg-gradient-to-r from-blue-50 to-indigo-50 border-l-4 border-indigo-400 rounded-r-lg shadow-sm">
                                <div className="flex items-start gap-2">
                                    <Sparkles size={16} className="text-indigo-600 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="text-xs font-bold text-indigo-900 uppercase tracking-wide">
                                                Verification Summary
                                            </span>
                                        </div>
                                        <p className="text-xs leading-relaxed text-slate-700 font-medium mb-2">
                                            {verificationSummaries.income.summary}
                                        </p>
                                        
                                        {/* Breakdown */}
                                        {verificationSummaries.income.breakdown && verificationSummaries.income.breakdown.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-indigo-200">
                                                <div className="text-[10px] font-bold text-indigo-900 uppercase mb-1.5">Key Components:</div>
                                                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                                                    {verificationSummaries.income.breakdown.slice(0, 6).map((item, idx) => (
                                                        <div key={idx} className="flex justify-between text-[11px]">
                                                            <span className="text-slate-600 truncate mr-2">{item.label}:</span>
                                                            <span className="font-semibold text-indigo-900 whitespace-nowrap">{item.value}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        
                                        {/* Documents */}
                                        {verificationSummaries.income.documents && verificationSummaries.income.documents.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-indigo-200">
                                                <div className="text-[10px] font-bold text-indigo-900 uppercase mb-1.5">Source Documents:</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {verificationSummaries.income.documents.map((doc, idx) => (
                                                        <button
                                                            key={idx}
                                                            onClick={() => {
                                                                const loanNumber = loanData.loan_number;
                                                                const docPath = `/loans/loan_${loanNumber}/${doc}`;
                                                                window.open(docPath, '_blank');
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-100 text-indigo-800 text-[10px] font-medium rounded hover:bg-indigo-200 transition-colors"
                                                        >
                                                            <FileText size={10} />
                                                            <span className="max-w-[150px] truncate">{doc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        <VerificationItem
                            label="Debt / Obligations"
                            value={
                                verificationSummaries.debt?.total_value || 
                                formatCurrency(verificationStatus.debt?.value) || 
                                'N/A'
                            }
                            verified={verificationStatus.debt?.verified || false}
                        />
                        
                        {/* Professional Debt Verification Summary */}
                        {verificationStatus.debt?.verified && verificationSummaries.debt && (
                            <div className="ml-5 mt-2 mb-3 p-3 bg-gradient-to-r from-red-50 to-pink-50 border-l-4 border-red-400 rounded-r-lg shadow-sm">
                                <div className="flex items-start gap-2">
                                    <Sparkles size={16} className="text-red-600 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="text-xs font-bold text-red-900 uppercase tracking-wide">
                                                Verification Summary
                                            </span>
                                        </div>
                                        <p className="text-xs leading-relaxed text-slate-700 font-medium mb-2">
                                            {verificationSummaries.debt.summary}
                                        </p>
                                        
                                        {/* Breakdown */}
                                        {verificationSummaries.debt.breakdown && verificationSummaries.debt.breakdown.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-red-200">
                                                <div className="text-[10px] font-bold text-red-900 uppercase mb-1.5">PITI + Obligations Breakdown:</div>
                                                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                                                    {verificationSummaries.debt.breakdown.slice(0, 6).map((item, idx) => (
                                                        <div key={idx} className="flex justify-between text-[11px]">
                                                            <span className="text-slate-600 truncate mr-2">{item.label}:</span>
                                                            <span className="font-semibold text-red-900 whitespace-nowrap">{item.value}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        
                                        {/* Documents */}
                                        {verificationSummaries.debt.documents && verificationSummaries.debt.documents.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-red-200">
                                                <div className="text-[10px] font-bold text-red-900 uppercase mb-1.5">Source Documents:</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {verificationSummaries.debt.documents.map((doc, idx) => (
                                                        <button
                                                            key={idx}
                                                            onClick={() => {
                                                                const loanNumber = loanData.loan_number;
                                                                const docPath = `/loans/loan_${loanNumber}/${doc}`;
                                                                window.open(docPath, '_blank');
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-100 text-red-800 text-[10px] font-medium rounded hover:bg-red-200 transition-colors"
                                                        >
                                                            <FileText size={10} />
                                                            <span className="max-w-[150px] truncate">{doc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        <VerificationItem
                            label="Credit Score"
                            value={creditScore || 'N/A'}
                            verified={verificationStatus.credit_score?.verified || false}
                        />
                        
                        {/* Credit Score Verification Summary */}
                        {verificationStatus.credit_score?.verified && verificationSummaries.credit_score && (
                            <div className="ml-5 mt-2 mb-3 p-3 bg-gradient-to-r from-purple-50 to-indigo-50 border-l-4 border-purple-400 rounded-r-lg shadow-sm">
                                <div className="flex items-start gap-2">
                                    <Sparkles size={16} className="text-purple-600 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="text-xs font-bold text-purple-900 uppercase tracking-wide">
                                                Verification Summary
                                            </span>
                                        </div>
                                        <p className="text-xs leading-relaxed text-slate-700 font-medium mb-2">
                                            {verificationSummaries.credit_score.summary}
                                        </p>
                                        
                                        {/* Documents */}
                                        {verificationSummaries.credit_score.documents && verificationSummaries.credit_score.documents.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-purple-200">
                                                <div className="text-[10px] font-bold text-purple-900 uppercase mb-1.5">Source Documents:</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {verificationSummaries.credit_score.documents.map((doc, idx) => (
                                                        <button
                                                            key={idx}
                                                            onClick={() => {
                                                                const loanNumber = loanData.loan_number;
                                                                const docPath = `/loans/loan_${loanNumber}/${doc}`;
                                                                window.open(docPath, '_blank');
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-purple-100 text-purple-800 text-[10px] font-medium rounded hover:bg-purple-200 transition-colors"
                                                        >
                                                            <FileText size={10} />
                                                            <span className="max-w-[150px] truncate">{doc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        <VerificationItem
                            label="Property Value"
                            value={formatCurrency(propertyInfo.appraised_value)}
                            verified={verificationStatus.property_value?.verified || false}
                        />
                        
                        {/* Property Value Verification Summary */}
                        {verificationStatus.property_value?.verified && verificationSummaries.property_value && (
                            <div className="ml-5 mt-2 mb-3 p-3 bg-gradient-to-r from-green-50 to-emerald-50 border-l-4 border-green-400 rounded-r-lg shadow-sm">
                                <div className="flex items-start gap-2">
                                    <Sparkles size={16} className="text-green-600 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="text-xs font-bold text-green-900 uppercase tracking-wide">
                                                Verification Summary
                                            </span>
                                        </div>
                                        <p className="text-xs leading-relaxed text-slate-700 font-medium mb-2">
                                            {verificationSummaries.property_value.summary}
                                        </p>
                                        
                                        {/* Documents */}
                                        {verificationSummaries.property_value.documents && verificationSummaries.property_value.documents.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-green-200">
                                                <div className="text-[10px] font-bold text-green-900 uppercase mb-1.5">Source Documents:</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {verificationSummaries.property_value.documents.map((doc, idx) => (
                                                        <button
                                                            key={idx}
                                                            onClick={() => {
                                                                const loanNumber = loanData.loan_number;
                                                                const docPath = `/loans/loan_${loanNumber}/${doc}`;
                                                                window.open(docPath, '_blank');
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-green-100 text-green-800 text-[10px] font-medium rounded hover:bg-green-200 transition-colors"
                                                        >
                                                            <FileText size={10} />
                                                            <span className="max-w-[150px] truncate">{doc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        {/* Add DTI/DSCR Calculation Verification */}
                        <VerificationItem
                            label={isInvestment ? "DSCR (Calculated)" : "Back-End DTI (Calculated)"}
                            value={isInvestment ? (dscrVal ? dscrVal.toFixed(2) : 'N/A') : (dtiVal ? `${dtiVal.toFixed(1)}%` : 'N/A')}
                            verified={isInvestment ? (dscrVal !== null) : (dtiVal > 0)}
                        />
                        
                        {/* DTI/DSCR Calculation Summary */}
                        {((!isInvestment && dtiVal > 0) || (isInvestment && dscrVal !== null)) && verificationSummaries.dti_dscr && (
                            <div className="ml-5 mt-2 mb-3 p-3 bg-gradient-to-r from-amber-50 to-yellow-50 border-l-4 border-amber-400 rounded-r-lg shadow-sm">
                                <div className="flex items-start gap-2">
                                    <Sparkles size={16} className="text-amber-600 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="text-xs font-bold text-amber-900 uppercase tracking-wide">
                                                Calculation Verification
                                            </span>
                                        </div>
                                        <p className="text-xs leading-relaxed text-slate-700 font-medium mb-2">
                                            {verificationSummaries.dti_dscr.summary}
                                        </p>
                                        
                                        {/* Documents */}
                                        {verificationSummaries.dti_dscr.documents && verificationSummaries.dti_dscr.documents.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-amber-200">
                                                <div className="text-[10px] font-bold text-amber-900 uppercase mb-1.5">Source Documents:</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {verificationSummaries.dti_dscr.documents.map((doc, idx) => (
                                                        <button
                                                            key={idx}
                                                            onClick={() => {
                                                                const loanNumber = loanData.loan_number;
                                                                const docPath = `/loans/loan_${loanNumber}/${doc}`;
                                                                window.open(docPath, '_blank');
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-amber-100 text-amber-800 text-[10px] font-medium rounded hover:bg-amber-200 transition-colors"
                                                        >
                                                            <FileText size={10} />
                                                            <span className="max-w-[150px] truncate">{doc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                        
                        {/* Add CLTV Calculation Verification */}
                        <VerificationItem
                            label="CLTV (Calculated)"
                            value={formatPercent(ratios.cltv_percent)}
                            verified={!!ratios.cltv_percent}
                        />
                        
                        {/* CLTV Calculation Summary */}
                        {ratios.cltv_percent && verificationSummaries.cltv && (
                            <div className="ml-5 mt-2 mb-3 p-3 bg-gradient-to-r from-teal-50 to-cyan-50 border-l-4 border-teal-400 rounded-r-lg shadow-sm">
                                <div className="flex items-start gap-2">
                                    <Sparkles size={16} className="text-teal-600 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-1.5">
                                            <span className="text-xs font-bold text-teal-900 uppercase tracking-wide">
                                                Calculation Verification
                                            </span>
                                        </div>
                                        <p className="text-xs leading-relaxed text-slate-700 font-medium mb-2">
                                            {verificationSummaries.cltv.summary}
                                        </p>
                                        
                                        {/* Documents */}
                                        {verificationSummaries.cltv.documents && verificationSummaries.cltv.documents.length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-teal-200">
                                                <div className="text-[10px] font-bold text-teal-900 uppercase mb-1.5">Source Documents:</div>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {verificationSummaries.cltv.documents.map((doc, idx) => (
                                                        <button
                                                            key={idx}
                                                            onClick={() => {
                                                                const loanNumber = loanData.loan_number;
                                                                const docPath = `/loans/loan_${loanNumber}/${doc}`;
                                                                window.open(docPath, '_blank');
                                                            }}
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 bg-teal-100 text-teal-800 text-[10px] font-medium rounded hover:bg-teal-200 transition-colors"
                                                        >
                                                            <FileText size={10} />
                                                            <span className="max-w-[150px] truncate">{doc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                    </div>

                    {/* Risk Assessment Section - New */}
                    <div className="bg-white border-2 border-slate-300 rounded-lg overflow-hidden mb-2 shadow-md">
                        <div className="px-4 py-3 bg-gradient-to-r from-slate-800 to-slate-700 text-white">
                            <h3 className="font-bold text-base">Risk Assessment</h3>
                            <p className="text-xs text-slate-300 mt-0.5">Risk analysis with regulatory compliance</p>
                        </div>
                        <div className="p-4 space-y-3">
                            
                            {/* DTI/DSCR Risk Card */}
                            <div className="border-2 border-slate-200 rounded-lg p-3 bg-slate-50">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold text-sm text-slate-900">
                                            {isInvestment ? "DSCR" : "Debt-to-Income Ratio"}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-lg font-bold text-slate-900">
                                            {isInvestment ? (dscrVal ? dscrVal.toFixed(2) : 'N/A') : (dtiVal ? `${dtiVal.toFixed(1)}%` : 'N/A')}
                                        </span>
                                        <RAGBadge rag={dtiDscrRag} size="sm" />
                                    </div>
                                </div>
                                <div className="text-xs text-slate-600 bg-white rounded p-2 border border-slate-200">
                                    <div className="mb-2">
                                        <strong>Thresholds:</strong> {isInvestment ? (
                                            <span className="ml-1">🟢 ≥1.25 Green | 🟡 1.0-1.25 Amber | 🔴 &lt;1.0 Red</span>
                                        ) : (
                                            <span className="ml-1">🟢 ≤36% Green | 🟡 36-49% Amber | 🔴 &gt;49% Red</span>
                                        )}
                                    </div>
                                    {isInvestment ? (
                                        <>
                                            <strong>Assessment:</strong>
                                            {dscrVal >= 1.25 ? " Strong cash flow coverage exceeds regulatory threshold" :
                                             dscrVal >= 1.0 ? " Adequate cash flow coverage meets minimum standards" :
                                             " Cash flow coverage below acceptable threshold"}
                                        </>
                                    ) : (
                                        <>
                                            <strong>Assessment:</strong>
                                            <div className="mt-2 space-y-2">
                                                <div className="pl-2">
                                                    <strong className="text-green-700">≤36% (Green):</strong>
                                                    <div className="ml-2 mt-0.5">
                                                        • Cites Fannie Mae B3-3.1-01 as the preferred lending guideline<br/>
                                                        • Meets traditional industry standards and demonstrates strong debt management capacity
                                                    </div>
                                                </div>
                                                <div className="pl-2">
                                                    <strong className="text-amber-700">36-49% (Amber):</strong>
                                                    <div className="ml-2 mt-0.5">
                                                        • References CFPB Regulation Z (12 CFR § 1026.43) for QM rules<br/>
                                                        • Fannie Mae/Freddie Mac require compensating factors or manual underwriting at this level
                                                    </div>
                                                </div>
                                                <div className="pl-2">
                                                    <strong className="text-red-700">&gt;49% (Red):</strong>
                                                    <div className="ml-2 mt-0.5">
                                                        • Exceeds QM safe harbor thresholds (12 CFR § 1026.43(e)(2))<br/>
                                                        • References Fannie Mae B3-3.1-01 and Freddie Mac guidelines<br/>
                                                        • Requires non-QM products or exceptional circumstances for approval
                                                    </div>
                                                </div>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </div>

                            {/* CLTV Risk Card */}
                            <div className="border-2 border-slate-200 rounded-lg p-3 bg-slate-50">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold text-sm text-slate-900">Combined Loan-to-Value</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-lg font-bold text-slate-900">
                                            {cltvVal ? `${cltvVal.toFixed(1)}%` : 'N/A'}
                                        </span>
                                        <RAGBadge rag={cltvRag} size="sm" />
                                    </div>
                                </div>
                                <div className="text-xs text-slate-600 bg-white rounded p-2 border border-slate-200">
                                    <div className="mb-2">
                                        <strong>Thresholds:</strong>
                                        <span className="ml-1">🟢 ≤80% Green | 🟡 80-90% Amber | 🔴 &gt;90% Red</span>
                                    </div>
                                    <strong>Assessment:</strong>
                                    {cltvVal <= 80 ? " Conservative leverage with substantial equity cushion enhances collateral security" :
                                     cltvVal <= 90 ? " Moderate leverage within acceptable risk parameters for the loan program" :
                                     " High leverage position requires additional credit strength and documentation"}
                                </div>
                            </div>

                            {/* Credit Score Risk Card */}
                            <div className="border-2 border-slate-200 rounded-lg p-3 bg-slate-50">
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className="font-semibold text-sm text-slate-900">Credit Score</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className="text-lg font-bold text-slate-900">
                                            {creditScore || 'N/A'}
                                        </span>
                                        <RAGBadge rag={creditScoreRag} size="sm" />
                                    </div>
                                </div>
                                <div className="text-xs text-slate-600 bg-white rounded p-2 border border-slate-200">
                                    <div className="mb-2">
                                        <strong>Thresholds:</strong>
                                        <span className="ml-1">🟢 ≥740 Green | 🟡 670-739 Amber | 🔴 &lt;670 Red</span>
                                    </div>
                                    <strong>Assessment:</strong>
                                    {creditExecutiveSummary ? (
                                        <span className="ml-1">{creditExecutiveSummary}</span>
                                    ) : (
                                        creditScore >= 740 ? " Excellent credit profile demonstrates strong payment history and credit management" :
                                        creditScore >= 670 ? " Good credit standing meets conventional lending requirements" :
                                        " Credit profile below prime threshold may require compensating factors"
                                    )}
                                </div>
                                
                                {/* View Detailed Credit Report Button */}
                                {creditReportDetail && (
                                    <button
                                        onClick={() => setCreditReportModal(true)}
                                        className="mt-2 w-full px-3 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white text-xs font-semibold rounded transition-all shadow-sm flex items-center justify-center gap-2"
                                    >
                                        <FileText size={14} />
                                        View Comprehensive Credit Report Analysis
                                    </button>
                                )}
                            </div>

                        </div>
                    </div>

                    {/* Old sections removed */}
                    </div>
                </div>

                {/* Footer */}
                <div className="border-t border-slate-200 px-4 py-2 bg-slate-900 text-white flex justify-between items-center">
                    <div className="text-xs">
                        RAG Status: Risk Assessment Guide
                    </div>
                    <button
                        onClick={onClose}
                        className="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded transition-colors text-sm font-medium"
                    >
                        Close
                    </button>
                </div>
            </div>
            
            {/* Credit Report Detail Modal */}
            {creditReportModal && creditReportDetail && (
                <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
                    <div className="bg-white rounded-lg shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col">
                        {/* Header */}
                        <div className="px-6 py-4 border-b border-slate-200 bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-t-lg">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h2 className="text-xl font-bold">Comprehensive Credit Report Analysis</h2>
                                    <p className="text-sm text-purple-100 mt-1">Institutional Investor & Underwriting Review - Loan ID {loanData?.id}</p>
                                </div>
                                <button
                                    onClick={() => setCreditReportModal(false)}
                                    className="p-2 hover:bg-white/20 rounded-full transition-colors"
                                >
                                    <X size={24} />
                                </button>
                            </div>
                        </div>
                        
                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-6 bg-slate-50">
                            <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-6">
                                <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800 leading-relaxed">
                                    {creditReportDetail}
                                </pre>
                            </div>
                        </div>
                        
                        {/* Footer */}
                        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 rounded-b-lg flex justify-between items-center">
                            <div className="text-xs text-slate-600">
                                Generated by Claude Opus 4.5 • Regulatory Compliance Review
                            </div>
                            <button
                                onClick={() => setCreditReportModal(false)}
                                className="px-4 py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded font-medium text-sm transition-all shadow-sm"
                            >
                                Close Report
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default RAGStatusModal;

