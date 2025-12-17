import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { CheckCircle2, XCircle, AlertTriangle, Info, RefreshCw, ChevronDown, ChevronRight, FileText, Calculator, Database } from 'lucide-react';

const ComplianceView = ({ loanId }) => {
    const [complianceData, setComplianceData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [expandedCategories, setExpandedCategories] = useState({});
    const [expandedEvidence, setExpandedEvidence] = useState({});

    const fetchComplianceData = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('token');
            const response = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}/compliance`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setComplianceData(response.data);
            
            // Expand all categories by default
            const categories = {};
            response.data.results.forEach(result => {
                categories[result.category] = true;
            });
            setExpandedCategories(categories);
        } catch (err) {
            console.error('Error fetching compliance data:', err);
            setError(err.response?.data?.message || err.message || 'Failed to fetch compliance data');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchComplianceData();
    }, [loanId]);

    const getStatusIcon = (status) => {
        switch (status) {
            case 'PASS': return <CheckCircle2 className="text-green-500" size={18} />;
            case 'FAIL': return <XCircle className="text-red-500" size={18} />;
            case 'WARNING': return <AlertTriangle className="text-yellow-500" size={18} />;
            case 'INFO': return <Info className="text-blue-500" size={18} />;
            case 'NA': return <Info className="text-gray-400" size={18} />;
            default: return null;
        }
    };

    const getStatusBadge = (status) => {
        const colors = {
            'PASS': 'bg-green-100 text-green-800 border-green-300',
            'FAIL': 'bg-red-100 text-red-800 border-red-300',
            'WARNING': 'bg-yellow-100 text-yellow-800 border-yellow-300',
            'INFO': 'bg-blue-100 text-blue-800 border-blue-300',
            'NA': 'bg-gray-100 text-gray-600 border-gray-300'
        };
        return (
            <span className={`px-2 py-0.5 rounded-md text-xs font-semibold border ${colors[status] || colors.INFO}`}>
                {status}
            </span>
        );
    };

    const getOverallStatusColor = (status) => {
        switch (status) {
            case 'PASS': return 'text-green-600 bg-green-50 border-green-200';
            case 'FAIL': return 'text-red-600 bg-red-50 border-red-200';
            case 'WARNING': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
            default: return 'text-gray-600 bg-gray-50 border-gray-200';
        }
    };

    const toggleCategory = (category) => {
        setExpandedCategories(prev => ({
            ...prev,
            [category]: !prev[category]
        }));
    };

    const toggleEvidence = (ruleCode) => {
        setExpandedEvidence(prev => ({
            ...prev,
            [ruleCode]: !prev[ruleCode]
        }));
    };

    const groupByCategory = (results) => {
        const grouped = {};
        results.forEach(result => {
            if (!grouped[result.category]) {
                grouped[result.category] = [];
            }
            grouped[result.category].push(result);
        });
        return grouped;
    };

    const getCategoryCounts = (results) => {
        const counts = {};
        results.forEach(result => {
            if (!counts[result.category]) {
                counts[result.category] = { pass: 0, fail: 0, warning: 0, total: 0 };
            }
            counts[result.category].total++;
            if (result.status === 'PASS') counts[result.category].pass++;
            else if (result.status === 'FAIL') counts[result.category].fail++;
            else if (result.status === 'WARNING') counts[result.category].warning++;
        });
        return counts;
    };

    const renderEvidence = (evidence) => {
        if (!evidence || Object.keys(evidence).length === 0) {
            return (
                <div className="text-xs text-gray-500 italic">
                    No detailed evidence available
                </div>
            );
        }

        const { documents, extracted_values, calculations, rationale } = evidence;

        return (
            <div className="mt-3 space-y-3 text-xs">
                {/* Rationale Summary */}
                {rationale && rationale.summary && (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                        <div className="font-semibold text-blue-900 mb-2">📝 Compliance Rationale</div>
                        <p className="text-blue-800 leading-relaxed mb-2">{rationale.summary}</p>
                        
                        {rationale.key_findings && rationale.key_findings.length > 0 && (
                            <div className="mt-2">
                                <div className="font-medium text-blue-900 mb-1">Key Findings:</div>
                                <ul className="space-y-1 text-blue-800">
                                    {rationale.key_findings.map((finding, idx) => (
                                        <li key={idx} className="flex items-start space-x-2">
                                            <span className="text-blue-500 mt-0.5">✓</span>
                                            <span>{finding}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}

                        {rationale.conclusion && (
                            <div className="mt-2 pt-2 border-t border-blue-300">
                                <span className="font-medium text-blue-900">Conclusion: </span>
                                <span className="text-blue-800">{rationale.conclusion}</span>
                            </div>
                        )}

                        {rationale.regulatory_reference && (
                            <div className="mt-2 text-blue-700 font-mono text-xs">
                                📖 {rationale.regulatory_reference}
                            </div>
                        )}
                    </div>
                )}

                {/* Documents */}
                {documents && documents.length > 0 && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                        <div className="flex items-center space-x-2 font-semibold text-gray-900 mb-2">
                            <FileText size={14} className="text-gray-600" />
                            <span>Supporting Documents ({documents.length})</span>
                        </div>
                        <div className="space-y-1.5">
                            {documents.map((doc, idx) => (
                                <div key={idx} className="flex items-start space-x-2 text-gray-700">
                                    <span className="text-gray-400">•</span>
                                    <div>
                                        <div className="font-medium">
                                            {doc.doc_type ? doc.doc_type.replace(/_/g, ' ') : 'Document'}
                                            {doc.page_number && ` (Page ${doc.page_number})`}
                                        </div>
                                        {doc.section && (
                                            <div className="text-gray-600">Section: {doc.section}</div>
                                        )}
                                        {doc.field_location && (
                                            <div className="text-gray-500">Field: {doc.field_location}</div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Extracted Values */}
                {extracted_values && extracted_values.length > 0 && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                        <div className="flex items-center space-x-2 font-semibold text-gray-900 mb-2">
                            <Database size={14} className="text-gray-600" />
                            <span>Values Extracted ({extracted_values.length})</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                            {extracted_values.map((val, idx) => (
                                <div key={idx} className="bg-white border border-gray-200 rounded p-2">
                                    <div className="text-gray-600 text-xs mb-0.5">{val.field_name}</div>
                                    <div className="font-semibold text-gray-900">
                                        {val.unit === 'USD' && '$'}
                                        {typeof val.value === 'number' ? val.value.toLocaleString() : val.value}
                                        {val.unit && val.unit !== 'USD' && ` ${val.unit}`}
                                    </div>
                                    {val.source_field && (
                                        <div className="text-gray-500 text-xs mt-1">
                                            from {val.source_field}
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Calculations */}
                {calculations && calculations.length > 0 && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                        <div className="flex items-center space-x-2 font-semibold text-gray-900 mb-2">
                            <Calculator size={14} className="text-gray-600" />
                            <span>Calculations ({calculations.length})</span>
                        </div>
                        <div className="space-y-2">
                            {calculations.map((calc, idx) => (
                                <div key={idx} className="bg-white border border-gray-200 rounded p-2">
                                    <div className="font-medium text-gray-900 mb-1">{calc.calc_name}</div>
                                    <div className="text-gray-600 font-mono text-xs mb-2">
                                        Formula: {calc.formula}
                                    </div>
                                    {calc.inputs && calc.inputs.length > 0 && (
                                        <div className="space-y-1 mb-2">
                                            {calc.inputs.map((input, iidx) => (
                                                <div key={iidx} className="flex items-center space-x-2 text-gray-700">
                                                    <span className="text-gray-400">→</span>
                                                    <span>{input.variable}: {input.value}</span>
                                                    {input.unit && <span className="text-gray-500">({input.unit})</span>}
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                    <div className="flex items-center justify-between pt-2 border-t border-gray-200">
                                        <div>
                                            <span className="text-gray-600">Result: </span>
                                            <span className="font-semibold text-gray-900">
                                                {typeof calc.result === 'number' ? calc.result.toFixed(3) : calc.result}
                                                {calc.result_unit === 'PERCENT' && '%'}
                                                {calc.result_unit === 'USD' && ' USD'}
                                            </span>
                                        </div>
                                        {calc.threshold_operator && calc.threshold_value && (
                                            <div className={`flex items-center space-x-1 ${calc.threshold_met ? 'text-green-600' : 'text-red-600'}`}>
                                                <span>{calc.threshold_operator}</span>
                                                <span>
                                                    {calc.threshold_value}
                                                    {calc.result_unit === 'PERCENT' && '%'}
                                                </span>
                                                <span className="ml-2">{calc.threshold_met ? '✓' : '✗'}</span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        );
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <RefreshCw className="animate-spin text-blue-500 mr-3" size={24} />
                <span className="text-lg text-gray-600">Running compliance checks...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-lg p-6 m-4">
                <div className="flex items-center">
                    <XCircle className="text-red-500 mr-3" size={24} />
                    <div>
                        <h3 className="text-lg font-semibold text-red-800">Error Loading Compliance Data</h3>
                        <p className="text-red-600 mt-1">{error}</p>
                    </div>
                </div>
            </div>
        );
    }

    if (!complianceData) {
        return (
            <div className="text-center py-12 text-gray-500">
                No compliance data available for this loan.
            </div>
        );
    }

    const groupedResults = groupByCategory(complianceData.results);
    const categoryCounts = getCategoryCounts(complianceData.results);

    return (
        <div className="p-6 space-y-6 bg-gray-50">
            {/* Header with Refresh Button */}
            <div className="flex justify-between items-center">
                <div className="flex items-center space-x-3">
                    <div className="p-2 bg-blue-100 rounded-lg">
                        <CheckCircle2 className="text-blue-600" size={28} />
                    </div>
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900">Compliance Dashboard</h2>
                        <p className="text-sm text-gray-500">
                            Last checked: {new Date(complianceData.execution_timestamp).toLocaleString()}
                        </p>
                    </div>
                </div>
                <button
                    onClick={fetchComplianceData}
                    className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                    <RefreshCw size={18} />
                    <span>Refresh Check</span>
                </button>
            </div>

            {/* Overall Status Card */}
            <div className={`border-2 rounded-xl p-6 ${getOverallStatusColor(complianceData.overall_status)}`}>
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-sm font-medium uppercase tracking-wide mb-2">Overall Compliance Status</h3>
                        <div className="text-4xl font-bold">{complianceData.overall_status}</div>
                        <p className="text-sm mt-2 opacity-80">
                            Loan #{complianceData.loan_number} • {complianceData.total_rules} rules checked
                        </p>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-white bg-opacity-50 rounded-lg p-3 text-center min-w-[100px]">
                            <div className="text-2xl font-bold text-green-600">{complianceData.passed}</div>
                            <div className="text-xs uppercase tracking-wide mt-1">Passed</div>
                        </div>
                        <div className="bg-white bg-opacity-50 rounded-lg p-3 text-center min-w-[100px]">
                            <div className="text-2xl font-bold text-yellow-600">{complianceData.warnings}</div>
                            <div className="text-xs uppercase tracking-wide mt-1">Warnings</div>
                        </div>
                        <div className="bg-white bg-opacity-50 rounded-lg p-3 text-center min-w-[100px]">
                            <div className="text-2xl font-bold text-red-600">{complianceData.failed}</div>
                            <div className="text-xs uppercase tracking-wide mt-1">Failed</div>
                        </div>
                        <div className="bg-white bg-opacity-50 rounded-lg p-3 text-center min-w-[100px]">
                            <div className="text-2xl font-bold text-gray-600">{complianceData.not_applicable}</div>
                            <div className="text-xs uppercase tracking-wide mt-1">N/A</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Key Determinations */}
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                    <Info className="mr-2 text-blue-500" size={20} />
                    Key Compliance Determinations
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">QM Type</div>
                        <div className="text-sm font-semibold text-gray-900">{complianceData.qm_type || 'Pending'}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">ATR Type</div>
                        <div className="text-sm font-semibold text-gray-900">{complianceData.atr_type || 'Pending'}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">HPML Status</div>
                        <div className="text-sm font-semibold text-gray-900">{complianceData.is_hpml ? 'Yes' : 'No'}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">HOEPA Status</div>
                        <div className="text-sm font-semibold text-gray-900">{complianceData.is_hoepa ? 'Yes' : 'No'}</div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Calculated APR</div>
                        <div className="text-sm font-semibold text-gray-900">
                            {complianceData.calculated_apr ? `${complianceData.calculated_apr}%` : 'N/A'}
                        </div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">APOR Spread</div>
                        <div className="text-sm font-semibold text-gray-900">
                            {complianceData.apor_spread ? `${complianceData.apor_spread}%` : 'N/A'}
                        </div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">QM Points & Fees</div>
                        <div className="text-sm font-semibold text-gray-900">
                            {complianceData.qm_points_fees_pct ? `${complianceData.qm_points_fees_pct}%` : 'N/A'}
                        </div>
                    </div>
                    <div className="p-3 bg-gray-50 rounded-lg">
                        <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Back-End DTI</div>
                        <div className="text-sm font-semibold text-gray-900">
                            {complianceData.back_end_dti ? `${complianceData.back_end_dti}%` : 'N/A'}
                        </div>
                    </div>
                </div>
            </div>

            {/* Compliance Rules by Category */}
            <div className="space-y-4">
                <h3 className="text-lg font-semibold text-gray-900">Compliance Rules ({complianceData.total_rules})</h3>
                
                {Object.entries(groupedResults).map(([category, results]) => {
                    const counts = categoryCounts[category];
                    const isExpanded = expandedCategories[category];
                    
                    return (
                        <div key={category} className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
                            {/* Category Header */}
                            <button
                                onClick={() => toggleCategory(category)}
                                className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
                            >
                                <div className="flex items-center space-x-3">
                                    {isExpanded ? <ChevronDown size={20} className="text-gray-500" /> : <ChevronRight size={20} className="text-gray-500" />}
                                    <h4 className="text-base font-semibold text-gray-900">{category}</h4>
                                    <span className="text-sm text-gray-500">({counts.total} rules)</span>
                                </div>
                                <div className="flex items-center space-x-2">
                                    {counts.fail > 0 && (
                                        <span className="px-2 py-1 bg-red-100 text-red-700 rounded-md text-xs font-medium">
                                            {counts.fail} Failed
                                        </span>
                                    )}
                                    {counts.warning > 0 && (
                                        <span className="px-2 py-1 bg-yellow-100 text-yellow-700 rounded-md text-xs font-medium">
                                            {counts.warning} Warnings
                                        </span>
                                    )}
                                    {counts.pass > 0 && (
                                        <span className="px-2 py-1 bg-green-100 text-green-700 rounded-md text-xs font-medium">
                                            {counts.pass} Passed
                                        </span>
                                    )}
                                </div>
                            </button>

                            {/* Category Rules */}
                            {isExpanded && (
                                <div className="border-t border-gray-200 divide-y divide-gray-100">
                                    {results.map((result, index) => {
                                        const hasEvidence = result.evidence && Object.keys(result.evidence).length > 0;
                                        const showEvidence = result.status === 'PASS' && hasEvidence;
                                        const evidenceExpanded = expandedEvidence[result.rule_code];
                                        
                                        return (
                                            <div key={index} className="p-4 hover:bg-gray-50 transition-colors">
                                                <div className="flex items-start space-x-3">
                                                    <div className="mt-0.5">{getStatusIcon(result.status)}</div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center justify-between mb-1">
                                                            <div className="flex items-center space-x-2">
                                                                <h5 className="text-sm font-semibold text-gray-900">
                                                                    {result.rule_name}
                                                                </h5>
                                                                {getStatusBadge(result.status)}
                                                            </div>
                                                            <span className="text-xs text-gray-500 font-mono">{result.rule_code}</span>
                                                        </div>
                                                        <p className="text-sm text-gray-700 leading-relaxed mb-2">
                                                            {result.message}
                                                        </p>
                                                        {(result.expected_value || result.actual_value) && (
                                                            <div className="flex items-center space-x-4 text-xs text-gray-600 mt-2">
                                                                {result.expected_value && (
                                                                    <div className="flex items-center space-x-1">
                                                                        <span className="font-medium text-gray-500">Expected:</span>
                                                                        <span className="font-mono bg-gray-100 px-2 py-0.5 rounded">
                                                                            {result.expected_value}
                                                                        </span>
                                                                    </div>
                                                                )}
                                                                {result.actual_value && (
                                                                    <div className="flex items-center space-x-1">
                                                                        <span className="font-medium text-gray-500">Actual:</span>
                                                                        <span className="font-mono bg-gray-100 px-2 py-0.5 rounded">
                                                                            {result.actual_value}
                                                                        </span>
                                                                    </div>
                                                                )}
                                                            </div>
                                                        )}
                                                        {result.requires_manual_review && (
                                                            <div className="mt-2 flex items-center space-x-1 text-xs text-orange-600">
                                                                <AlertTriangle size={14} />
                                                                <span className="font-medium">Requires Manual Review</span>
                                                            </div>
                                                        )}
                                                        
                                                        {/* Evidence Section for PASS cases */}
                                                        {showEvidence && (
                                                            <div className="mt-3">
                                                                <button
                                                                    onClick={() => toggleEvidence(result.rule_code)}
                                                                    className="flex items-center space-x-2 text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors"
                                                                >
                                                                    {evidenceExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                                                    <span>
                                                                        {evidenceExpanded ? 'Hide' : 'Show'} Evidence & Rationale
                                                                    </span>
                                                                    <span className="text-gray-500">
                                                                        ({result.evidence.documents?.length || 0} docs, 
                                                                         {result.evidence.extracted_values?.length || 0} values, 
                                                                         {result.evidence.calculations?.length || 0} calculations)
                                                                    </span>
                                                                </button>
                                                                
                                                                {evidenceExpanded && (
                                                                    <div className="mt-2">
                                                                        {renderEvidence(result.evidence)}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>

            {/* Footer Note */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                <p className="text-sm text-blue-800">
                    <strong>Note:</strong> This compliance dashboard checks key federal regulations including ATR/QM, TILA, RESPA, and HPML requirements. 
                    Results are based on extracted loan data and current regulatory thresholds. Items marked as "Requires Manual Review" need additional verification.
                </p>
            </div>
        </div>
    );
};

export default ComplianceView;
