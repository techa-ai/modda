import React from 'react';
import { FileText, User, Home, TrendingUp, AlertTriangle, CheckCircle2, Building2, DollarSign, Calendar, Briefcase, CreditCard, MapPin, Shield } from 'lucide-react';

/**
 * Loan Summary Renderer - Renders structured loan summary JSON
 * Similar to VerificationSummaryRenderer but for loan overview
 */
const LoanSummaryRenderer = ({ summary }) => {
    // If no summary, return null
    if (!summary) {
        return null;
    }

    // Parse if it's a JSON string
    let data = summary;
    if (typeof summary === 'string') {
        try {
            data = JSON.parse(summary);
        } catch {
            // If it's not valid JSON, it might be markdown - return null so parent can handle
            return null;
        }
    }

    // If data doesn't have expected keys, try to render as generic JSON
    if (!data.loan_number && !data.loan_overview && !data.financial_ratios) {
        return (
            <div className="text-xs text-gray-700 whitespace-pre-wrap font-mono bg-gray-50 p-2 rounded">
                {JSON.stringify(data, null, 2)}
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {/* Loan Header */}
            {data.loan_number && (
                <div className="bg-gradient-to-r from-slate-700 to-slate-800 text-white rounded-lg px-3 py-2">
                    <h3 className="text-xs font-bold">Loan Summary Report</h3>
                    <p className="text-[11px] text-slate-300 mt-0.5">
                        <span className="font-medium text-white">Loan #:</span> {data.loan_number}
                        {data.lender_loan_number && (
                            <span className="ml-2"><span className="font-medium text-white">Lender #:</span> {data.lender_loan_number}</span>
                        )}
                    </p>
                </div>
            )}

            {/* Key Financial Ratios Section - AT TOP */}
            {data.financial_ratios && (
                <SectionCard
                    icon={<TrendingUp size={12} className="text-indigo-600" />}
                    title="Key Financial Ratios"
                    color="indigo"
                >
                    <div className="space-y-1">
                        {/* Header row */}
                        <div className="grid grid-cols-[80px_60px_1fr] gap-2 py-1 px-1.5 border-b border-gray-200">
                            <span className="text-[10px] font-semibold text-gray-500 uppercase">Ratio</span>
                            <span className="text-[10px] font-semibold text-gray-500 uppercase text-right">Value</span>
                            <span className="text-[10px] font-semibold text-gray-500 uppercase">Assessment</span>
                        </div>
                        {data.financial_ratios.map((ratio, idx) => {
                            return (
                                <div key={idx} className="grid grid-cols-[80px_60px_1fr] gap-2 py-1 px-1.5 rounded hover:bg-gray-50 items-center">
                                    <span className="text-[11px] font-medium text-gray-700">{ratio.ratio}</span>
                                    <span className="text-[11px] font-bold text-indigo-700 text-right">{ratio.value}</span>
                                    {ratio.assessment && (
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${ratio.assessment.toLowerCase().includes('excellent') ? 'bg-green-100 text-green-700' :
                                            ratio.assessment.toLowerCase().includes('good') ? 'bg-blue-100 text-blue-700' :
                                                ratio.assessment.toLowerCase().includes('acceptable') ? 'bg-amber-100 text-amber-700' :
                                                    'bg-gray-100 text-gray-700'
                                            }`}>
                                            {ratio.assessment}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                    {data.financial_analysis && (
                        <div className="mt-2 pt-2 border-t border-gray-100">
                            <p className="text-[11px] text-gray-600 leading-relaxed">{data.financial_analysis}</p>
                        </div>
                    )}
                </SectionCard>
            )}

            {/* Risk Factors Section - AT TOP */}
            {data.risk_factors && data.risk_factors.length > 0 && (
                <SectionCard
                    icon={<AlertTriangle size={12} className="text-amber-600" />}
                    title="Risk Factors & Concerns"
                    color="amber"
                >
                    <ul className="space-y-1">
                        {data.risk_factors.map((risk, idx) => (
                            <li key={idx} className="flex items-start gap-1.5 text-[11px] text-gray-700">
                                <span className="text-amber-500 mt-0.5 text-[10px]">⚠</span>
                                <span>{risk}</span>
                            </li>
                        ))}
                    </ul>
                </SectionCard>
            )}

            {/* Positive Factors Section - AT TOP */}
            {data.positive_factors && data.positive_factors.length > 0 && (
                <SectionCard
                    icon={<CheckCircle2 size={12} className="text-green-600" />}
                    title="Positive Factors"
                    color="green"
                >
                    <ul className="space-y-1">
                        {data.positive_factors.map((factor, idx) => (
                            <li key={idx} className="flex items-start gap-1.5 text-[11px] text-gray-700">
                                <span className="text-green-500 mt-0.5 text-[10px]">✓</span>
                                <span>{factor}</span>
                            </li>
                        ))}
                    </ul>
                </SectionCard>
            )}

            {/* Loan Overview Section */}
            {data.loan_overview && (
                <SectionCard
                    icon={<FileText size={12} className="text-blue-600" />}
                    title="Loan Overview"
                    color="blue"
                >
                    <DataTable items={data.loan_overview} />
                </SectionCard>
            )}

            {/* Borrower Profile Section */}
            {data.borrower_profile && (
                <SectionCard
                    icon={<User size={12} className="text-emerald-600" />}
                    title="Borrower Profile"
                    color="emerald"
                >
                    <DataTable items={data.borrower_profile.personal} />

                    {data.borrower_profile.employment && (
                        <div className="mt-2 pt-2 border-t border-gray-100">
                            <h4 className="text-[11px] font-semibold text-gray-700 mb-1.5 flex items-center gap-1">
                                <Briefcase size={10} className="text-gray-500" />
                                Employment
                            </h4>
                            <DataTable items={data.borrower_profile.employment} />
                        </div>
                    )}

                    {data.borrower_profile.income && (
                        <div className="mt-2 pt-2 border-t border-gray-100">
                            <h4 className="text-[11px] font-semibold text-gray-700 mb-1.5 flex items-center gap-1">
                                <DollarSign size={10} className="text-gray-500" />
                                Income
                            </h4>
                            <DataTable items={data.borrower_profile.income} highlightTotal={true} />
                        </div>
                    )}

                    {data.borrower_profile.credit && (
                        <div className="mt-2 pt-2 border-t border-gray-100">
                            <h4 className="text-[11px] font-semibold text-gray-700 mb-1.5 flex items-center gap-1">
                                <CreditCard size={10} className="text-gray-500" />
                                Credit
                            </h4>
                            <DataTable items={data.borrower_profile.credit} />
                        </div>
                    )}
                </SectionCard>
            )}

            {/* Property Details Section */}
            {data.property_details && (
                <SectionCard
                    icon={<Home size={12} className="text-purple-600" />}
                    title="Property Details"
                    color="purple"
                >
                    <DataTable items={data.property_details} />
                </SectionCard>
            )}
        </div>
    );
};

/**
 * Section Card Component
 */
const SectionCard = ({ icon, title, color, children }) => {
    const colorClasses = {
        blue: 'border-blue-200 bg-blue-50/30',
        emerald: 'border-emerald-200 bg-emerald-50/30',
        purple: 'border-purple-200 bg-purple-50/30',
        indigo: 'border-indigo-200 bg-indigo-50/30',
        amber: 'border-amber-200 bg-amber-50/30',
        green: 'border-green-200 bg-green-50/30',
    };

    return (
        <div className={`border rounded-lg p-2.5 ${colorClasses[color] || 'border-gray-200'}`}>
            <h3 className="text-xs font-semibold text-gray-800 mb-2 flex items-center gap-1.5">
                {icon}
                {title}
            </h3>
            {children}
        </div>
    );
};

/**
 * Data Table Component - Renders key-value pairs
 */
const DataTable = ({ items, highlightTotal = false }) => {
    if (!items || (Array.isArray(items) && items.length === 0)) return null;

    // Handle array format [{ item: "Label", details: "Value" }]
    if (Array.isArray(items)) {
        return (
            <div className="space-y-0.5">
                {items.map((item, idx) => {
                    const isTotal = highlightTotal && item.item?.toLowerCase().includes('total');
                    return (
                        <div
                            key={idx}
                            className={`flex items-center justify-between py-0.5 px-1 rounded ${isTotal ? 'bg-gray-100 font-semibold' : 'hover:bg-gray-50'
                                }`}
                        >
                            <span className={`text-[11px] ${isTotal ? 'text-gray-900' : 'text-gray-600'}`}>
                                {item.item || item.label}
                            </span>
                            <span className={`text-[11px] ${isTotal ? 'text-gray-900' : 'text-gray-800'}`}>
                                {item.details || item.value}
                            </span>
                        </div>
                    );
                })}
            </div>
        );
    }

    // Handle object format { key: value }
    return (
        <div className="space-y-0.5">
            {Object.entries(items).map(([key, value], idx) => (
                <div key={idx} className="flex items-center justify-between py-0.5 px-1 rounded hover:bg-gray-50">
                    <span className="text-[11px] text-gray-600">{formatLabel(key)}</span>
                    <span className="text-[11px] text-gray-800">{value}</span>
                </div>
            ))}
        </div>
    );
};

/**
 * Format label from camelCase or snake_case to Title Case
 */
const formatLabel = (key) => {
    return key
        .replace(/_/g, ' ')
        .replace(/([A-Z])/g, ' $1')
        .replace(/^./, str => str.toUpperCase())
        .trim();
};

export default LoanSummaryRenderer;
