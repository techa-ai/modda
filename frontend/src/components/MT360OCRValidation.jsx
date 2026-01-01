import React, { useState, useEffect } from 'react';
import { FileText, ChevronRight, AlertCircle, CheckCircle2, XCircle, Loader, ChevronUp, ChevronDown } from 'lucide-react';
import axios from 'axios';

const MT360OCRValidation = ({ loanId }) => {
    const [mt360Data, setMt360Data] = useState({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [activeDocTab, setActiveDocTab] = useState('summary');
    const [validationResults, setValidationResults] = useState({});
    const [validating, setValidating] = useState({});

    const documentTypes = [
        { id: '1008', name: '1008 Form', icon: FileText },
        { id: 'URLA', name: 'URLA', icon: FileText },
        { id: 'Note', name: 'Note', icon: FileText },
        { id: 'LoanEstimate', name: 'Loan Estimate', icon: FileText },
        { id: 'ClosingDisclosure', name: 'Closing Disclosure', icon: FileText },
        { id: 'CreditReport', name: 'Credit Report', icon: FileText },
        { id: '1004', name: 'Appraisal Report', icon: FileText }
    ];

    useEffect(() => {
        fetchMT360Data();
    }, [loanId]);

    // Load ALL cached validation results on mount
    useEffect(() => {
        if (Object.keys(mt360Data).length > 0) {
            loadAllCachedValidations();
        }
    }, [mt360Data]);

    const loadAllCachedValidations = async () => {
        const token = localStorage.getItem('token');
        for (const doc of documentTypes) {
            if (mt360Data[doc.id]?.has_data && !validationResults[doc.id]) {
                try {
                    const response = await axios.get(
                        `http://localhost:8006/api/admin/loans/${loanId}/validation-cache/${doc.id}`,
                        { headers: { Authorization: `Bearer ${token}` } }
                    );
                    if (response.data && response.data.success) {
                        setValidationResults(prev => ({
                            ...prev,
                            [doc.id]: response.data
                        }));
                    }
                } catch (err) {
                    // No cached results for this doc type
                }
            }
        }
    };

    const loadCachedValidation = async (docType) => {
        try {
            const token = localStorage.getItem('token');
            const response = await axios.get(
                `http://localhost:8006/api/admin/loans/${loanId}/validation-cache/${docType}`,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            if (response.data && response.data.success) {
                setValidationResults(prev => ({
                    ...prev,
                    [docType]: response.data
                }));
            }
        } catch (err) {
            // No cached results, that's fine - user can click Validate
            console.log('No cached validation for', docType);
        }
    };

    const fetchMT360Data = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('token');

            const response = await axios.get(
                `http://localhost:8006/api/admin/loans/${loanId}/mt360-ocr`,
                { headers: { Authorization: `Bearer ${token}` } }
            );

            setMt360Data(response.data || {});
            setError(null);
        } catch (err) {
            console.error('Error fetching MT360 data:', err);
            setError(err.response?.data?.error || 'Failed to load MT360 OCR data');
        } finally {
            setLoading(false);
        }
    };

    const validateWithOpus = async (docType) => {
        try {
            setValidating(prev => ({ ...prev, [docType]: true }));
            const token = localStorage.getItem('token');

            const response = await axios.post(
                `http://localhost:8006/api/admin/loans/${loanId}/validate-mt360/${docType}`,
                {},
                { headers: { Authorization: `Bearer ${token}` }, timeout: 300000 }
            );

            setValidationResults(prev => ({
                ...prev,
                [docType]: response.data
            }));
        } catch (err) {
            console.error('Error validating with Opus:', err);
            setValidationResults(prev => ({
                ...prev,
                [docType]: { success: false, error: err.response?.data?.error || 'Validation failed' }
            }));
        } finally {
            setValidating(prev => ({ ...prev, [docType]: false }));
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="flex items-center gap-2 text-amber-600">
                    <AlertCircle className="w-5 h-5" />
                    <span>{error}</span>
                </div>
            </div>
        );
    }

    const availableDocs = documentTypes.filter(doc => mt360Data[doc.id]?.has_data || mt360Data[doc.id]?.field_count > 0);
    const summaryData = availableDocs.map(doc => ({
        type: doc.name,
        id: doc.id,
        attributes: mt360Data[doc.id]?.field_count || 0,
        extracted: mt360Data[doc.id]?.extraction_timestamp || 'N/A'
    }));

    return (
        <div className="flex h-full">
            {/* Vertical Tabs */}
            <div className="w-56 border-r border-gray-200 bg-gray-50 p-3">
                <h3 className="text-xs font-semibold text-gray-700 mb-3">MT360 Documents</h3>
                <div className="space-y-1">
                    <button
                        onClick={() => setActiveDocTab('summary')}
                        className={`w-full flex items-center justify-between px-2 py-1.5 text-xs rounded-lg transition-colors ${activeDocTab === 'summary'
                            ? 'bg-blue-100 text-blue-700 font-medium'
                            : 'text-gray-700 hover:bg-gray-100'
                            }`}
                    >
                        <span>Summary</span>
                        {activeDocTab === 'summary' && <ChevronRight className="w-3 h-3" />}
                    </button>

                    {availableDocs.map(doc => (
                        <button
                            key={doc.id}
                            onClick={() => setActiveDocTab(doc.id)}
                            className={`w-full flex items-center justify-between px-2 py-1.5 text-xs rounded-lg transition-colors ${activeDocTab === doc.id
                                ? 'bg-blue-100 text-blue-700 font-medium'
                                : 'text-gray-700 hover:bg-gray-100'
                                }`}
                        >
                            <div className="flex items-center gap-1.5">
                                <doc.icon className="w-3 h-3" />
                                <span>{doc.name}</span>
                            </div>
                            {activeDocTab === doc.id && <ChevronRight className="w-3 h-3" />}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 p-4 overflow-auto">
                {activeDocTab === 'summary' ? (
                    <SummaryView data={summaryData} validationResults={validationResults} />
                ) : (
                    <DocumentDetailView
                        docType={activeDocTab}
                        docName={documentTypes.find(d => d.id === activeDocTab)?.name}
                        data={mt360Data[activeDocTab]}
                        validating={validating[activeDocTab]}
                        validationResult={validationResults[activeDocTab]}
                        onValidate={() => validateWithOpus(activeDocTab)}
                    />
                )}
            </div>
        </div>
    );
};

const SummaryView = ({ data, validationResults }) => {
    const totalAttributes = data.reduce((sum, doc) => sum + doc.attributes, 0);

    // Calculate totals from validation results
    const totalMatches = Object.values(validationResults).reduce((sum, v) => sum + (v?.matches || 0), 0);
    const totalMismatches = Object.values(validationResults).reduce((sum, v) => sum + (v?.mismatches || 0), 0);
    const overallAccuracy = totalMatches + totalMismatches > 0
        ? ((totalMatches / (totalMatches + totalMismatches)) * 100).toFixed(1)
        : 'N/A';

    // Collect all mismatches grouped by document type
    const mismatchesByDoc = {};
    Object.entries(validationResults).forEach(([docType, validation]) => {
        if (validation?.results) {
            const mismatches = validation.results.filter(r => r.status === 'MISMATCH');
            if (mismatches.length > 0) {
                mismatchesByDoc[docType] = mismatches;
            }
        }
    });

    return (
        <div>
            <h2 className="text-xl font-bold text-gray-900 mb-4">MT360 OCR Validation Summary</h2>

            {/* Top Summary Cards */}
            <div className="grid grid-cols-5 gap-3 mb-4">
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <p className="text-xs text-blue-700">Documents</p>
                    <p className="text-2xl font-bold text-blue-900">{data.length}</p>
                </div>
                <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
                    <p className="text-xs text-gray-600">Total Attributes</p>
                    <p className="text-2xl font-bold text-gray-900">{totalAttributes}</p>
                </div>
                <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                    <p className="text-xs text-green-700">Matches</p>
                    <p className="text-2xl font-bold text-green-700">{totalMatches}</p>
                </div>
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                    <p className="text-xs text-red-700">Mismatches</p>
                    <p className="text-2xl font-bold text-red-700">{totalMismatches}</p>
                </div>
                <div className="bg-purple-50 border border-purple-200 rounded-lg p-3">
                    <p className="text-xs text-purple-700">Accuracy</p>
                    <p className="text-2xl font-bold text-purple-700">{overallAccuracy}%</p>
                </div>
            </div>

            {/* Document Type Summary Table */}
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden mb-6">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase">Document Type</th>
                            <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase">Attributes</th>
                            <th className="px-2 py-1 text-left text-[10px] font-medium text-green-600 uppercase">Matches</th>
                            <th className="px-2 py-1 text-left text-[10px] font-medium text-red-600 uppercase">Mismatches</th>
                            <th className="px-2 py-1 text-left text-[10px] font-medium text-purple-600 uppercase">Accuracy</th>
                            <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase">Status</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {data.map((doc, idx) => {
                            const validation = validationResults[doc.id];
                            const hasValidation = validation?.success;
                            return (
                                <tr key={idx} className="hover:bg-gray-50">
                                    <td className="px-2 py-1 text-[11px] font-medium text-gray-900">{doc.type}</td>
                                    <td className="px-2 py-1 text-[11px] text-gray-500">{doc.attributes}</td>
                                    <td className="px-2 py-1 text-[11px] text-green-700 font-medium">
                                        {hasValidation ? validation.matches : '-'}
                                    </td>
                                    <td className="px-2 py-1 text-[11px] text-red-700 font-medium">
                                        {hasValidation ? validation.mismatches : '-'}
                                    </td>
                                    <td className="px-2 py-1 text-[11px] text-purple-700 font-medium">
                                        {hasValidation ? `${Number(validation.accuracy).toFixed(1)}%` : '-'}
                                    </td>
                                    <td className="px-2 py-1 text-[11px]">
                                        {hasValidation ? (
                                            <span className="px-1.5 py-0.5 bg-green-100 text-green-700 rounded text-[10px]">Validated</span>
                                        ) : (
                                            <span className="px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded text-[10px]">Pending</span>
                                        )}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {/* Mismatches by Document Type */}
            {Object.keys(mismatchesByDoc).length > 0 && (
                <div>
                    <h3 className="text-lg font-semibold text-red-700 mb-3">⚠️ MT360 OCR Errors by Document Type</h3>

                    {Object.entries(mismatchesByDoc).map(([docType, mismatches]) => (
                        <div key={docType} className="mb-4 border border-red-200 rounded-lg overflow-hidden">
                            <div className="bg-red-50 px-3 py-2 border-b border-red-200">
                                <span className="font-semibold text-red-800">{docType}</span>
                                <span className="ml-2 text-xs text-red-600">({mismatches.length} mismatches)</span>
                            </div>
                            <table className="min-w-full divide-y divide-gray-200">
                                <thead className="bg-gray-50">
                                    <tr>
                                        <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase">Field</th>
                                        <th className="px-2 py-1 text-left text-[10px] font-medium text-blue-600 uppercase">MT360 Value</th>
                                        <th className="px-2 py-1 text-left text-[10px] font-medium text-green-600 uppercase">PDF Value (Truth)</th>
                                    </tr>
                                </thead>
                                <tbody className="bg-white divide-y divide-gray-200">
                                    {mismatches.map((m, idx) => (
                                        <tr key={idx} className="hover:bg-red-50">
                                            <td className="px-2 py-1 text-[11px] font-medium text-gray-900">{m.mt360_field_name}</td>
                                            <td className="px-2 py-1 text-[11px] text-blue-700 bg-blue-50/50">{m.mt360_value}</td>
                                            <td className="px-2 py-1 text-[11px] text-green-700 bg-green-50/50">{m.pdf_value}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    ))}
                </div>
            )}

            {Object.keys(mismatchesByDoc).length === 0 && totalMatches > 0 && (
                <div className="bg-green-50 border border-green-200 rounded-lg p-4 text-center">
                    <CheckCircle2 className="w-8 h-8 text-green-600 mx-auto mb-2" />
                    <p className="text-green-700 font-medium">All validated fields match! No OCR errors detected.</p>
                </div>
            )}
        </div>
    );
};

const DocumentDetailView = ({ docType, docName, data, validating, validationResult, onValidate }) => {
    if (!data || !data.has_data) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-center text-gray-500">
                    <FileText className="w-12 h-12 mx-auto mb-3 text-gray-400" />
                    <p>No data available for {docName}</p>
                </div>
            </div>
        );
    }

    const showValidation = validationResult && validationResult.success;

    return (
        <div>
            <div className="mb-4 flex items-start justify-between">
                <div>
                    <h2 className="text-xl font-bold text-gray-900">{docName}</h2>
                    <div className="mt-1 flex items-center gap-3 text-xs text-gray-600">
                        <span>Loan: {data.loan_file_id}</span>
                        <span>•</span>
                        <span>{data.field_count} attributes</span>
                        <span>•</span>
                        <span>Extracted: {new Date(data.extraction_timestamp).toLocaleString()}</span>
                    </div>
                </div>
                {!showValidation && !validating && (
                    <button
                        onClick={onValidate}
                        className="px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 flex items-center gap-1.5"
                    >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Validate vs PDF
                    </button>
                )}
            </div>

            {validating && (
                <div className="mb-4 bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-center gap-2">
                    <Loader className="w-4 h-4 animate-spin text-blue-600" />
                    <span className="text-sm text-blue-700">Validating MT360 against PDF with Claude Opus 4.5... (takes ~60 seconds)</span>
                </div>
            )}

            {validationResult && !validationResult.success && (
                <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4 text-red-600" />
                    <span className="text-sm text-red-700">Validation error: {validationResult.error}</span>
                </div>
            )}

            {showValidation && (
                <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                        <div className="grid grid-cols-4 gap-6">
                            <div>
                                <p className="text-xs text-gray-600">Total Fields</p>
                                <p className="text-lg font-bold text-gray-900">{validationResult.total_fields}</p>
                            </div>
                            <div>
                                <p className="text-xs text-green-700">Matches</p>
                                <p className="text-lg font-bold text-green-700">{validationResult.matches}</p>
                            </div>
                            <div>
                                <p className="text-xs text-red-700">Mismatches</p>
                                <p className="text-lg font-bold text-red-700">{validationResult.mismatches}</p>
                            </div>
                            <div>
                                <p className="text-xs text-purple-700">Accuracy</p>
                                <p className="text-lg font-bold text-purple-700">{Number(validationResult.accuracy).toFixed(1)}%</p>
                            </div>
                        </div>
                        <button
                            onClick={onValidate}
                            className="px-2 py-1 text-xs text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded"
                        >
                            Re-validate
                        </button>
                    </div>
                </div>
            )}

            {showValidation ? (
                <ValidationResultsTable results={validationResult.results} docType={docType} docName={docName} />
            ) : !validating ? (
                <MT360DataTable fields={data.fields || {}} />
            ) : null}
        </div>
    );
};

const MT360DataTable = ({ fields }) => {
    const fieldEntries = Object.entries(fields);

    return (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                    <tr>
                        <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase tracking-wider w-1/3">
                            Field Name
                        </th>
                        <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase tracking-wider w-2/3">
                            Value
                        </th>
                    </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                    {fieldEntries.map(([key, value], idx) => (
                        <tr key={idx} className="hover:bg-gray-50">
                            <td className="px-2 py-1 text-[11px] font-medium text-gray-900">
                                {key}
                            </td>
                            <td className="px-2 py-1 text-[11px] text-gray-700">
                                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

const ValidationResultsTable = ({ results, docType, docName }) => {
    // Group results by document source and sort by page number
    const groupedResults = React.useMemo(() => {
        const groups = {};

        results.forEach(result => {
            // Use pdf_document if available, otherwise use the document type
            const doc = result.pdf_document || docType || 'Unknown';
            if (!groups[doc]) {
                groups[doc] = [];
            }
            groups[doc].push(result);
        });

        // Sort each group by page number
        Object.keys(groups).forEach(doc => {
            groups[doc].sort((a, b) => {
                const pageA = parseInt(a.pdf_page) || 999;
                const pageB = parseInt(b.pdf_page) || 999;
                return pageA - pageB;
            });
        });

        return groups;
    }, [results, docType]);

    // Get friendly document name
    const getDocDisplayName = (filename) => {
        if (!filename || filename === 'Unknown') return docName || 'Unknown Source';
        // If filename matches the docType, use the friendly docName
        if (filename === docType) return docName || filename;
        if (filename.toLowerCase().includes('lender_loan_information')) return 'URLA - Lender (L2/L3/L4)';
        if (filename.toLowerCase().includes('urla') && filename.toLowerCase().includes('final')) return 'URLA - Borrower';
        if (filename.toLowerCase().includes('initial_urla')) return 'URLA - Initial';
        if (filename.toLowerCase().includes('borrowers_certification')) return 'Borrower Certification';
        // Clean up filename
        return filename.replace(/___/g, ' - ').replace(/_/g, ' ').replace('.pdf', '').replace(/\d+$/, '').trim();
    };

    // Get document color theme
    const getDocColor = (filename) => {
        if (filename.toLowerCase().includes('lender_loan_information')) return 'purple';
        if (filename.toLowerCase().includes('urla')) return 'blue';
        if (filename.toLowerCase().includes('borrowers_certification')) return 'amber';
        return 'gray';
    };

    const colorClasses = {
        purple: { header: 'bg-purple-100 border-purple-300', badge: 'bg-purple-600' },
        blue: { header: 'bg-blue-100 border-blue-300', badge: 'bg-blue-600' },
        amber: { header: 'bg-amber-100 border-amber-300', badge: 'bg-amber-600' },
        gray: { header: 'bg-gray-100 border-gray-300', badge: 'bg-gray-600' }
    };

    return (
        <div className="space-y-4">
            {Object.entries(groupedResults).map(([docName, docResults]) => {
                const displayName = getDocDisplayName(docName);
                const color = getDocColor(docName);
                const colors = colorClasses[color];
                const matchCount = docResults.filter(r => r.status === 'MATCH').length;
                const mismatchCount = docResults.filter(r => r.status === 'MISMATCH').length;

                return (
                    <div key={docName} className="border border-gray-200 rounded-lg overflow-hidden">
                        {/* Document Header */}
                        <div className={`px-3 py-2 ${colors.header} border-b flex items-center justify-between`}>
                            <div className="flex items-center gap-2">
                                <FileText className="w-4 h-4" />
                                <span className="font-semibold text-sm">{displayName}</span>
                                <span className="text-xs text-gray-500">({docResults.length} fields)</span>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full">
                                    {matchCount} Match
                                </span>
                                {mismatchCount > 0 && (
                                    <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs rounded-full">
                                        {mismatchCount} Mismatch
                                    </span>
                                )}
                            </div>
                        </div>

                        {/* Results Table */}
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase w-8">Pg</th>
                                    <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase bg-blue-50">MT360 Field</th>
                                    <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase bg-blue-50">MT360 Value</th>
                                    <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase bg-green-50">PDF Field</th>
                                    <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase bg-green-50">PDF Value (Truth)</th>
                                    <th className="px-2 py-1 text-left text-[10px] font-medium text-gray-500 uppercase w-20">Status</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {docResults.map((result, idx) => (
                                    <tr key={idx} className={`hover:bg-gray-50 ${result.status === 'MISMATCH' ? 'bg-red-50' : ''}`}>
                                        <td className="px-2 py-1 text-[10px] text-gray-400 text-center">
                                            {result.pdf_page || '-'}
                                        </td>
                                        <td className="px-2 py-1 text-[11px] text-blue-800 bg-blue-50/30">
                                            {result.mt360_field_name}
                                        </td>
                                        <td className="px-2 py-1 text-[11px] text-blue-700 bg-blue-50/30 max-w-32 truncate" title={result.mt360_value}>
                                            {result.mt360_value}
                                        </td>
                                        <td className="px-2 py-1 text-[11px] font-medium text-green-800 bg-green-50/30">
                                            {result.pdf_field_name || '-'}
                                        </td>
                                        <td className="px-2 py-1 text-[11px] text-green-700 bg-green-50/30 max-w-32 truncate" title={result.pdf_value}>
                                            {result.pdf_value || '-'}
                                        </td>
                                        <td className="px-2 py-1 text-[11px]">
                                            {result.status === 'MATCH' ? (
                                                <span className="flex items-center gap-1 text-green-700 font-medium">
                                                    <CheckCircle2 className="w-3 h-3" />
                                                    Match
                                                </span>
                                            ) : result.status === 'NOT_FOUND' ? (
                                                <span className="flex items-center gap-1 text-amber-600 font-medium">
                                                    <AlertCircle className="w-3 h-3" />
                                                    Not Found
                                                </span>
                                            ) : (
                                                <span className="flex items-center gap-1 text-red-700 font-medium">
                                                    <XCircle className="w-3 h-3" />
                                                    Mismatch
                                                </span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                );
            })}
        </div>
    );
};

export default MT360OCRValidation;
