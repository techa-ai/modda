import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import EssentialAttributesView from '../components/EssentialAttributesView';
import {
    FileText,
    Copy,
    Star,
    Trash2,
    ArrowLeft,
    Folder,
    File,
    BarChart3,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Download,
    Eye,
    ChevronDown,
    ChevronUp,
    Shield,
    RefreshCw,
    Sparkles
, AlertCircle } from 'lucide-react';
import { clsx } from 'clsx';
import { JSONTree } from 'react-json-tree';
import VerificationModal from '../components/VerificationModal';
import EvidenceDocumentModal from '../components/EvidenceDocumentModal';
import EvidenceDocumentsView from '../components/EvidenceDocumentsView';
import ComplianceView from '../components/ComplianceView';
import KnowledgeGraphView from '../components/KnowledgeGraphView';

const LoanDetailPage = () => {
    const { loanId } = useParams();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [loan, setLoan] = useState(null);
    const [stats, setStats] = useState(null);
    const [extractedData, setExtractedData] = useState([]);
    const [calculationSteps, setCalculationSteps] = useState({}); // Map: attribute_id -> steps[]
    const [documents, setDocuments] = useState({
        raw: [],
        unique: [],
        important: []
    });
    const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'stats');
    const [loading, setLoading] = useState(true);
    const [selectedDocFromUrl, setSelectedDocFromUrl] = useState(null);

    // Handle doc query parameter - open specific document
    useEffect(() => {
        const docParam = searchParams.get('doc');
        if (docParam) {
            setSelectedDocFromUrl(docParam);
            // Switch to raw documents tab to show the document
            setActiveTab('raw');
        }
    }, [searchParams]);

    useEffect(() => {
        fetchLoanData();
    }, [loanId]);

    const fetchLoanData = async () => {
        try {
            setLoading(true);
            const token = localStorage.getItem('token');

            // Fetch loan details
            const loanResponse = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setLoan(loanResponse.data);

            // Fetch loan statistics
            const statsResponse = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}/stats`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setStats(statsResponse.data);

            // Fetch documents
            const docsResponse = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}/documents`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            setDocuments(docsResponse.data);

            // Fetch extracted data (filtered to 32 essential attributes)
            try {
                const extResponse = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}/extracted_data?essential_only=false`, {
                    headers: { Authorization: `Bearer ${token}` }
                });
                setExtractedData(extResponse.data || []);
                
                // Fetch calculation steps for all attributes
                try {
                    const stepsResponse = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}/calculation-steps`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    
                    // Group steps by attribute_id
                    const stepsMap = {};
                    (stepsResponse.data.steps || []).forEach(step => {
                        if (!stepsMap[step.attribute_id]) {
                            stepsMap[step.attribute_id] = [];
                        }
                        stepsMap[step.attribute_id].push(step);
                    });
                    console.log('Calculation steps loaded:', Object.keys(stepsMap).length, 'attributes');
                    console.log('Sample:', stepsMap[268]); // Sales Price
                    setCalculationSteps(stepsMap);
                } catch (error) {
                    console.error('Error fetching calculation steps:', error);
                    setCalculationSteps({});
                }
            } catch (e) {
                console.error("Failed to fetch extracted data", e);
                setCalculationSteps({});
            }
        } catch (error) {
            console.error('Error fetching loan data:', error);
        } finally {
            setLoading(false);
        }
    };

    // Handle tab change with URL update
    const handleTabChange = (tabId) => {
        setActiveTab(tabId);
        setSearchParams({ tab: tabId });
    };

    const handleDeleteLoan = async () => {
        if (!window.confirm('Are you sure you want to delete this loan? This action cannot be undone.')) {
            return;
        }

        try {
            const token = localStorage.getItem('token');
            await axios.delete(`http://localhost:8006/api/admin/loans/${loanId}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            navigate('/admin/loans');
        } catch (error) {
            console.error('Error deleting loan:', error);
            alert('Failed to delete loan');
        }
    };

    const handleTriggerDedup = async () => {
        try {
            const token = localStorage.getItem('token');
            await axios.post(`http://localhost:8006/api/admin/loans/${loanId}/deduplicate`, {}, {
                headers: { Authorization: `Bearer ${token}` }
            });
            alert('Deduplication analysis started in background');
            // Refresh data after a moment
            setTimeout(fetchLoanData, 2000);
        } catch (error) {
            console.error('Error triggering deduplication:', error);
            alert(error.response?.data?.message || 'Failed to trigger deduplication');
        }
    };

    // Calculate verified count for 1008 Evidencing
    const verified1008Count = extractedData.filter(item => 
        item.evidence && item.evidence.length > 0 && 
        item.evidence.some(e => e.verification_status === 'verified')
    ).length;
    
    const total1008WithValues = extractedData.filter(item => 
        item.extracted_value && item.extracted_value !== '0.00' && item.extracted_value !== ''
    ).length;

    const rawTotal = documents.raw?.length || 0;
    const uniqueCount = documents.unique?.length || 0;
    const uniquePercentage = rawTotal > 0 ? Math.round((uniqueCount / rawTotal) * 100) : 0;
    const evidencing1008Percentage = total1008WithValues > 0 ? Math.round((verified1008Count / total1008WithValues) * 100) : 0;

    const tabs = [
        { id: 'stats', name: 'Overview', icon: BarChart3 },
        { id: 'raw', name: 'Raw Documents', icon: FileText, count: rawTotal, displayCount: `${rawTotal}` },
        { id: 'unique', name: 'Unique Documents', icon: Copy, count: uniqueCount, displayCount: `${uniqueCount} (${uniquePercentage}%)` },
        { id: 'important', name: 'Data Tape Validation', icon: Star, count: verified1008Count, displayCount: `${verified1008Count} (${evidencing1008Percentage}%)` },
        { id: 'evidence', name: 'Evidence Documents', icon: FileText },
        { id: 'compliance', name: 'Compliance', icon: Shield },
        { id: 'knowledge-graph', name: 'Knowledge Graph', icon: Sparkles }
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50">
            {/* Header */}
            <div className="bg-white border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                            <button
                                onClick={() => navigate('/admin/loans')}
                                className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                            >
                                <ArrowLeft className="h-4 w-4 text-gray-600" />
                            </button>
                            <div>
                                <h1 className="text-lg font-bold text-gray-900">
                                    Loan #{loan?.loan_number || loanId}
                                </h1>
                                <p className="text-xs text-gray-500 mt-0.5">
                                    Borrower: {loan?.borrower_name || 'N/A'}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center space-x-2">
                            {/* Dedup Status and Run Analysis - Hidden */}
                            {false && documents.dedup_status && (
                                <div className="flex items-center space-x-2">
                                    <span className={`inline-flex px-2 py-0.5 text-xs font-semibold rounded-full ${documents.dedup_status === 'completed' ? 'bg-green-100 text-green-800' :
                                        documents.dedup_status === 'running' ? 'bg-blue-100 text-blue-800' :
                                            documents.dedup_status === 'failed' ? 'bg-red-100 text-red-800' :
                                                'bg-yellow-100 text-yellow-800'
                                        }`}>
                                        Dedup: {documents.dedup_status}
                                    </span>
                                    {documents.dedup_status !== 'running' && (
                                        <button
                                            onClick={handleTriggerDedup}
                                            className="px-2 py-1 text-xs font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-colors"
                                        >
                                            Run Analysis
                                        </button>
                                    )}
                                </div>
                            )}
                            <button
                                onClick={handleDeleteLoan}
                                className="flex items-center space-x-1.5 px-3 py-1.5 bg-red-600 text-white text-xs rounded-lg hover:bg-red-700 transition-colors"
                            >
                                <Trash2 className="h-4 w-4" />
                                <span>Delete Loan</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div className="bg-white border-b border-gray-200">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <nav className="flex space-x-6">
                        {tabs.map((tab) => {
                            const Icon = tab.icon;
                            return (
                                <button
                                    key={tab.id}
                                    onClick={() => handleTabChange(tab.id)}
                                    className={`
                    flex items-center space-x-1.5 py-3 px-1 border-b-2 font-medium text-xs transition-colors
                    ${activeTab === tab.id
                                            ? 'border-blue-600 text-blue-600'
                                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                                        }
                  `}
                                >
                                    <Icon className="h-4 w-4" />
                                    <span>{tab.name}</span>
                                    {tab.displayCount !== undefined && (
                                        <span className={`
                      px-1.5 py-0.5 rounded-full text-xs font-medium
                      ${activeTab === tab.id ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-600'}
                    `}>
                                            {tab.displayCount}
                                        </span>
                                    )}
                                </button>
                            );
                        })}
                    </nav>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
                {activeTab === 'stats' && <StatsView stats={stats} loan={loan} />}
                {activeTab === 'raw' && <DocumentsView documents={documents.raw} title="Raw Documents" highlightDoc={selectedDocFromUrl} />}
                {activeTab === 'unique' && <DocumentsView documents={documents.unique} title="Unique Documents" />}
                {activeTab === 'important' && <ImportantDocumentsView extractedData={extractedData} loanId={loanId} calculationSteps={calculationSteps} allDocuments={documents.unique} />}
                {activeTab === 'evidence' && <EvidenceDocumentsView loanId={loanId} />}
                {activeTab === 'compliance' && <ComplianceView loanId={loanId} />}
                {activeTab === 'knowledge-graph' && <KnowledgeGraphView />}
            </div>
        </div>
    );
};

const StatsView = ({ stats, loan }) => {
    const [loanData, setLoanData] = useState({});
    const [loanSummary, setLoanSummary] = useState(null);
    const [generatingSummary, setGeneratingSummary] = useState(false);
    const { loanId } = useParams();

    useEffect(() => {
        const fetchLoanData = async () => {
            try {
                const token = localStorage.getItem('token');
                const response = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}/extracted_data`, {
                    headers: { Authorization: `Bearer ${token}` }
                });
                
                // Extract key values
                const data = {};
                response.data.forEach(item => {
                    if (item.attribute_label === 'Mort Original Loan Amount') {
                        data.loanAmount = item.extracted_value;
                    } else if (item.attribute_label === 'Property Address') {
                        data.propertyAddress = item.extracted_value;
                    } else if (item.attribute_label === 'Loan Type') {
                        data.loanType = item.extracted_value;
                    } else if (item.attribute_label === 'Mort Interest Rate') {
                        data.interestRate = item.extracted_value;
                    } else if (item.attribute_label === 'Mort Loan Term Months') {
                        data.loanTerm = item.extracted_value;
                    }
                });
                setLoanData(data);
            } catch (error) {
                console.error('Error fetching loan data:', error);
            }
        };

        fetchLoanData();
    }, [loanId]);

    // Fetch loan summary
    useEffect(() => {
        const fetchLoanSummary = async () => {
            try {
                const token = localStorage.getItem('token');
                const response = await axios.get(`http://localhost:8006/api/admin/loans/${loanId}`, {
                    headers: { Authorization: `Bearer ${token}` }
                });
                if (response.data.loan_summary) {
                    setLoanSummary(response.data.loan_summary);
                }
            } catch (error) {
                console.error('Error fetching loan summary:', error);
            }
        };

        fetchLoanSummary();
    }, [loanId]);

    const handleGenerateSummary = async () => {
        setGeneratingSummary(true);
        try {
            const token = localStorage.getItem('token');
            const response = await axios.post(
                `http://localhost:8006/api/admin/loans/${loanId}/generate-summary`,
                {},
                { headers: { Authorization: `Bearer ${token}` } }
            );
            if (response.data.summary) {
                setLoanSummary(response.data.summary);
            }
        } catch (error) {
            console.error('Error generating summary:', error);
            alert('Failed to generate summary. Please try again.');
        } finally {
            setGeneratingSummary(false);
        }
    };

    // Count verified attributes
    const verified1008Count = stats?.verified_1008_count || 0;
    const total1008WithValues = stats?.total_1008_with_values || 0;
    const evidencingDisplay = total1008WithValues > 0 
        ? `${verified1008Count} (${Math.round((verified1008Count / total1008WithValues) * 100)}%)`
        : verified1008Count;

    const uniqueDocs = stats?.unique_documents || 0;
    const totalDocs = stats?.total_documents || 0;
    const versionsIdentified = stats?.versions_identified || 0;
    const duplicatesIdentified = stats?.duplicates_identified || 0;
    const uniquePercentage = totalDocs > 0 ? Math.round((uniqueDocs / totalDocs) * 100) : 0;
    const versionsPercentage = totalDocs > 0 ? Math.round((versionsIdentified / totalDocs) * 100) : 0;
    const duplicatesPercentage = totalDocs > 0 ? Math.round((duplicatesIdentified / totalDocs) * 100) : 0;

    const statCards = [
        { label: 'Total Documents', value: totalDocs, color: 'blue' },
        { label: 'Unique Documents', value: `${uniqueDocs} (${uniquePercentage}%)`, color: 'green' },
        { label: 'Versions Identified', value: `${versionsIdentified} (${versionsPercentage}%)`, color: 'orange' },
        { label: 'Duplicates Identified', value: `${duplicatesIdentified} (${duplicatesPercentage}%)`, color: 'yellow' },
        { label: 'Data Tape Validation', value: evidencingDisplay, color: 'purple' },
        { label: 'Loan Amount', value: loanData.loanAmount ? `$${loanData.loanAmount}` : 'N/A', color: 'indigo' },
        { label: 'Property Address', value: loanData.propertyAddress || 'N/A', color: 'gray', span: 2 }
    ];

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Loan Overview</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {statCards.map((stat, index) => (
                    <div
                        key={index}
                        className={`bg-white rounded-lg shadow p-3 border-l-4 border-${stat.color}-500 ${stat.span === 2 ? 'md:col-span-2' : ''}`}
                    >
                        <p className="text-xs font-medium text-gray-600">{stat.label}</p>
                        <p className="mt-1 text-xl font-bold text-gray-900">{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Additional loan details */}
            <div className="bg-white rounded-lg shadow p-3">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">Loan Details</h3>
                <dl className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                        <dt className="text-xs font-medium text-gray-500">Loan Type</dt>
                        <dd className="mt-0.5 text-xs text-gray-900">{loanData.loanType || 'N/A'}</dd>
                    </div>
                    <div>
                        <dt className="text-xs font-medium text-gray-500">Interest Rate</dt>
                        <dd className="mt-0.5 text-xs text-gray-900">{loanData.interestRate || 'N/A'}</dd>
                    </div>
                    <div>
                        <dt className="text-xs font-medium text-gray-500">Loan Term</dt>
                        <dd className="mt-0.5 text-xs text-gray-900">{loanData.loanTerm ? `${Math.round(Number(loanData.loanTerm.replace(/,/g, '')) / 12)} years` : 'N/A'}</dd>
                    </div>
                    <div>
                        <dt className="text-xs font-medium text-gray-500">Status</dt>
                        <dd className="mt-0.5">
                            <span className={`inline-flex px-1.5 py-0.5 text-xs font-semibold rounded-full ${loan?.status === 'approved' ? 'bg-green-100 text-green-800' :
                                loan?.status === 'pending' ? 'bg-yellow-100 text-yellow-800' :
                                    'bg-gray-100 text-gray-800'
                                }`}>
                                {loan?.status || 'completed'}
                            </span>
                        </dd>
                    </div>
                </dl>
            </div>

            {/* Loan Summary */}
            <div className="bg-white rounded-lg shadow overflow-hidden">
                <div className="p-4 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-indigo-50">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <FileText className="w-5 h-5 text-blue-600" />
                            <h3 className="text-sm font-semibold text-gray-900">Loan Summary</h3>
                        </div>
                        <button
                            onClick={handleGenerateSummary}
                            disabled={generatingSummary}
                            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                generatingSummary
                                    ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                    : 'bg-blue-600 text-white hover:bg-blue-700'
                            }`}
                        >
                            {generatingSummary ? (
                                <>
                                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                                    Generating...
                                </>
                            ) : (
                                <>
                                    <RefreshCw className="w-3.5 h-3.5" />
                                    {loanSummary ? 'Regenerate' : 'Generate Summary'}
                                </>
                            )}
                        </button>
                    </div>
                </div>
                
                <div className="p-4">
                    {loanSummary ? (
                        <div className="prose prose-sm max-w-none">
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                    h1: ({node, ...props}) => <h1 className="text-lg font-bold text-gray-900 border-b pb-2 mb-4" {...props} />,
                                    h2: ({node, ...props}) => <h2 className="text-base font-semibold text-gray-900 mt-6 mb-3" {...props} />,
                                    h3: ({node, ...props}) => <h3 className="text-sm font-medium text-gray-800 mt-4 mb-2" {...props} />,
                                    p: ({node, ...props}) => <p className="text-xs text-gray-700 mb-2 leading-relaxed" {...props} />,
                                    ul: ({node, ...props}) => <ul className="list-disc pl-4 mb-3 space-y-1" {...props} />,
                                    ol: ({node, ...props}) => <ol className="list-decimal pl-4 mb-3 space-y-1" {...props} />,
                                    li: ({node, ...props}) => <li className="text-xs text-gray-700" {...props} />,
                                    table: ({node, ...props}) => (
                                        <div className="overflow-x-auto my-4 border border-gray-200 rounded-lg">
                                            <table className="min-w-full divide-y divide-gray-200" {...props} />
                                        </div>
                                    ),
                                    thead: ({node, ...props}) => <thead className="bg-gray-50" {...props} />,
                                    tbody: ({node, ...props}) => <tbody className="bg-white divide-y divide-gray-100" {...props} />,
                                    tr: ({node, ...props}) => <tr className="hover:bg-gray-50" {...props} />,
                                    th: ({node, ...props}) => <th className="px-4 py-2 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200" {...props} />,
                                    td: ({node, ...props}) => <td className="px-4 py-2 text-xs text-gray-600 whitespace-nowrap" {...props} />,
                                    strong: ({node, ...props}) => <strong className="font-semibold text-gray-900" {...props} />,
                                    em: ({node, ...props}) => <em className="text-gray-600" {...props} />,
                                    hr: ({node, ...props}) => <hr className="my-4 border-gray-200" {...props} />,
                                    blockquote: ({node, ...props}) => (
                                        <blockquote className="border-l-4 border-blue-300 pl-3 py-1 my-2 text-xs text-gray-600 bg-blue-50 rounded-r" {...props} />
                                    ),
                                }}
                            >
                                {loanSummary}
                            </ReactMarkdown>
                        </div>
                    ) : (
                        <div className="text-center py-12">
                            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                            <p className="text-sm text-gray-500 mb-1">No summary generated yet</p>
                            <p className="text-xs text-gray-400 mb-4">Click "Generate Summary" to analyze all loan documents</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

const DocumentsView = ({ documents, title, highlightDoc }) => {
    const [selectedDoc, setSelectedDoc] = useState(null);
    const [showDuplicateModal, setShowDuplicateModal] = useState(false);
    const [showVersionModal, setShowVersionModal] = useState(false);
    const [showPreviewModal, setShowPreviewModal] = useState(false);
    const [previewDoc, setPreviewDoc] = useState(null);
    const [selectedVersionDoc, setSelectedVersionDoc] = useState(null);
    const [sortField, setSortField] = useState('name');
    const [sortDirection, setSortDirection] = useState('asc');
    const [groupBy, setGroupBy] = useState(false);
    const [collapsedGroups, setCollapsedGroups] = useState({});
    const [viewMode, setViewMode] = useState('full'); // 'full' or 'gallery'
    const [defaultTab, setDefaultTab] = useState('summary'); // 'summary', 'pdf', 'json'
    const highlightedDocRef = useRef(null);

    // Handle highlightDoc - scroll to and open the document in PDF view
    useEffect(() => {
        if (highlightDoc && documents?.length > 0) {
            const doc = documents.find(d => d.filename === highlightDoc || d.name === highlightDoc);
            if (doc) {
                // Open in Version Modal with PDF tab and gallery mode (single doc view)
                setSelectedVersionDoc(doc);
                setViewMode('gallery');
                setDefaultTab('pdf');
                setShowVersionModal(true);
                // Scroll to the document in the list after a short delay
                setTimeout(() => {
                    if (highlightedDocRef.current) {
                        highlightedDocRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 100);
            }
        }
    }, [highlightDoc, documents]);

    const toggleGroup = (group) => {
        setCollapsedGroups(prev => ({ ...prev, [group]: !prev[group] }));
    };

    const getCategory = (doc) => {
        const meta = typeof doc.version_metadata === 'string' ? JSON.parse(doc.version_metadata) : doc.version_metadata || {};
        return meta.financial_category;
    };

    const getSecondaryName = (doc) => {
        const meta = typeof doc.version_metadata === 'string' ? JSON.parse(doc.version_metadata) : doc.version_metadata || {};
        return meta.secondary_name;
    };

    const getFilenameMismatch = (doc) => {
        const meta = typeof doc.version_metadata === 'string' ? JSON.parse(doc.version_metadata) : doc.version_metadata || {};
        return meta.filename_match === 'MISMATCH' || meta.filename_match === 'GENERIC' ? meta.mismatch_reason : null;
    };

    const handleSort = (field) => {
        if (sortField === field) {
            setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
        } else {
            setSortField(field);
            setSortDirection('asc');
        }
    };

    const sortedDocuments = [...(documents || [])].sort((a, b) => {
        let aVal, bVal;

        switch (sortField) {
            case 'name':
                aVal = a.name || '';
                bVal = b.name || '';
                break;
            case 'type':
                aVal = a.document_type || '';
                bVal = b.document_type || '';
                break;
            case 'date':
                aVal = a.upload_date || '';
                bVal = b.upload_date || '';
                break;
            case 'size':
                aVal = a.size || 0;
                bVal = b.size || 0;
                break;
            case 'duplicates':
                aVal = a.aggregate_duplicate_count || a.duplicate_count || 0;
                bVal = b.aggregate_duplicate_count || b.duplicate_count || 0;
                break;
            case 'versions':
                aVal = a.version_count || 0;
                bVal = b.version_count || 0;
                break;
            default:
                return 0;
        }

        if (typeof aVal === 'string') {
            return sortDirection === 'asc'
                ? aVal.localeCompare(bVal)
                : bVal.localeCompare(aVal);
        } else {
            return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
        }
    });



    const handleViewDuplicates = (doc) => {
        setSelectedDoc(doc);
        setShowDuplicateModal(true);
    };

    const handleViewVersions = (doc) => {
        setSelectedVersionDoc(doc);
        setViewMode('full');
        setShowVersionModal(true);
    };

    const handleViewDocument = (doc) => {
        // Formerly Preview, now opens Gallery View (Left Pane Only)
        setSelectedVersionDoc(doc);
        setViewMode('gallery');
        setShowVersionModal(true);
    };

    const SortIcon = ({ field }) => {
        if (sortField !== field) return <span className="ml-1 text-gray-400">↕</span>;
        return <span className="ml-1">{sortDirection === 'asc' ? '↑' : '↓'}</span>;
    };

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
                <div className="flex items-center space-x-2">
                    <span className="text-sm text-gray-700">Group by:</span>
                    <button
                        onClick={() => setGroupBy(!groupBy)}
                        className={`px-3 py-1 text-xs font-medium rounded-full border transition-colors ${groupBy
                            ? 'bg-blue-100 text-blue-800 border-blue-200'
                            : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                            }`}
                    >
                        Functionality
                    </button>
                </div>
            </div>

            {documents && documents.length > 0 ? (
                <div className="bg-white rounded-lg shadow overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('name')}
                                >
                                    Document Name <SortIcon field="name" />
                                </th>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('type')}
                                >
                                    Type <SortIcon field="type" />
                                </th>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('date')}
                                >
                                    Upload Date <SortIcon field="date" />
                                </th>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('size')}
                                >
                                    Size <SortIcon field="size" />
                                </th>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('duplicates')}
                                >
                                    # Duplicates <SortIcon field="duplicates" />
                                </th>
                                <th
                                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                                    onClick={() => handleSort('versions')}
                                >
                                    # Versions <SortIcon field="versions" />
                                </th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Unique Docs
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {Object.entries(groupBy ? {
                                'FINANCIAL': sortedDocuments.filter(d => getCategory(d) === 'FINANCIAL'),
                                'NON-FINANCIAL': sortedDocuments.filter(d => getCategory(d) === 'NON-FINANCIAL'),
                                'Uncategorized': sortedDocuments.filter(d => {
                                    const c = getCategory(d);
                                    return c !== 'FINANCIAL' && c !== 'NON-FINANCIAL';
                                })
                            } : { 'All': sortedDocuments }).map(([groupName, groupDocs]) => {
                                if (groupDocs.length === 0) return null;
                                const isGrouped = groupName !== 'All';
                                const isCollapsed = isGrouped && collapsedGroups[groupName];

                                return (
                                    <React.Fragment key={groupName}>
                                        {isGrouped && (
                                            <tr
                                                className="bg-gray-100 cursor-pointer hover:bg-gray-200 transition-colors"
                                                onClick={() => toggleGroup(groupName)}
                                            >
                                                <td colSpan="7" className="px-6 py-2 text-xs font-bold text-gray-700 uppercase tracking-wider">
                                                    <div className="flex items-center">
                                                        <span className="mr-2 text-gray-500 w-4">{isCollapsed ? '▶' : '▼'}</span>
                                                        {groupName}
                                                        <span className="ml-2 text-gray-500 font-normal">({groupDocs.length})</span>
                                                    </div>
                                                </td>
                                            </tr>
                                        )}

                                        {!isCollapsed && groupDocs.map((doc, index) => {
                                            const category = getCategory(doc);
                                            const secondaryName = getSecondaryName(doc);
                                            const mismatchReason = getFilenameMismatch(doc);
                                            // Get additional metadata from individual_analysis
                                            const analysis = doc.individual_analysis || {};
                                            const hasSig = analysis.has_signature;
                                            const docDate = analysis.document_date;
                                            const docType = analysis.document_type;
                                            const borrower = analysis.borrower_name;
                                            const coBorrower = analysis.co_borrower_name;
                                            const isHighlighted = highlightDoc && (doc.filename === highlightDoc || doc.name === highlightDoc);
                                            
                                            return (
                                                <tr 
                                                    key={index} 
                                                    ref={isHighlighted ? highlightedDocRef : null}
                                                    className={`hover:bg-blue-50 cursor-pointer transition-colors ${isHighlighted ? 'bg-yellow-100 ring-2 ring-yellow-400' : ''}`} 
                                                    onClick={() => handleViewDocument(doc)}
                                                >
                                                    <td className="px-6 py-4 whitespace-nowrap">
                                                        <div className="flex items-start">
                                                            <File className="h-5 w-5 text-blue-500 mr-3 mt-1" />
                                                            <div className="min-w-0 flex-1">
                                                                <div className="text-sm font-medium text-blue-600 hover:text-blue-800 truncate max-w-md" title={doc.name}>{doc.name}</div>
                                                                {/* Secondary name for generic/mismatched files */}
                                                                {secondaryName && secondaryName !== doc.name && (
                                                                    <div className="text-xs text-blue-600 mt-0.5 truncate max-w-md" title={secondaryName}>
                                                                        → {secondaryName}
                                                                    </div>
                                                                )}
                                                                {/* Document type from content analysis */}
                                                                {docType && !secondaryName && (
                                                                    <div className="text-xs text-gray-500 mt-0.5 truncate max-w-md">
                                                                        {docType}
                                                                    </div>
                                                                )}
                                                                <div className="flex flex-wrap gap-1.5 mt-1.5">
                                                                    {category && (
                                                                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${category === 'FINANCIAL' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                                                                            }`}>
                                                                            {category === 'FINANCIAL' ? 'Financial' : 'Non-Financial'}
                                                                        </span>
                                                                    )}
                                                                    {/* Signed/Unsigned badge */}
                                                                    {hasSig !== undefined && (
                                                                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${hasSig ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-700'}`}>
                                                                            {hasSig ? '✓ Signed' : 'Unsigned'}
                                                                        </span>
                                                                    )}
                                                                    {/* Co-borrower badge */}
                                                                    {coBorrower && coBorrower !== 'null' && (
                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800">
                                                                            👥 Co-Borrower
                                                                        </span>
                                                                    )}
                                                                    {doc.is_latest_version && doc.detected_date && doc.latest_count === 1 && (
                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-800">
                                                                            Latest Version
                                                                        </span>
                                                                    )}
                                                                    {/* Document date */}
                                                                    {(doc.detected_date || docDate) && (
                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                                                            📅 {doc.detected_date || docDate}
                                                                        </span>
                                                                    )}
                                                                    {/* Mismatch warning */}
                                                                    {mismatchReason && (
                                                                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800" title={mismatchReason}>
                                                                            ⚠️ Name Mismatch
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </td>
                                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{doc.type || 'PDF'}</td>
                                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{doc.upload_date ? new Date(doc.upload_date).toLocaleDateString() : 'N/A'}</td>
                                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{doc.size ? `${(doc.size / 1024).toFixed(2)} KB` : 'N/A'}</td>
                                                    {(() => {
                                                        const dupCount = doc.aggregate_duplicate_count || doc.duplicate_count || 0;
                                                        return (
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                                                {dupCount > 0 ? (
                                                                    <button onClick={() => handleViewDuplicates(doc)} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 hover:bg-yellow-200 transition-colors">
                                                                        {dupCount} {dupCount === 1 ? 'duplicate' : 'duplicates'}
                                                                    </button>
                                                                ) : (
                                                                    <span className="text-gray-400">-</span>
                                                                )}
                                                            </td>
                                                        );
                                                    })()}
                                                    <td className="px-6 py-4 whitespace-nowrap">
                                                        {doc.version_count > 1 ? (
                                                            <button onClick={() => handleViewVersions(doc)} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800 hover:bg-purple-200 transition-colors">
                                                                {doc.version_count} versions
                                                            </button>
                                                        ) : <span className="text-sm text-gray-400">-</span>}
                                                    </td>
                                                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                                        <div className="flex items-center justify-end gap-2">
                                                            {(doc.latest_count || 1) > 1 && (
                                                                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                                                                    {doc.latest_count} documents
                                                                </span>
                                                            )}
                                                            <span className="text-gray-400 text-xs">Click to view →</span>
                                                        </div>
                                                    </td>
                                                </tr>
                                            );
                                        })}
                                    </React.Fragment>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="bg-white rounded-lg shadow p-12 text-center">
                    <Folder className="mx-auto h-12 w-12 text-gray-400" />
                    <h3 className="mt-2 text-sm font-medium text-gray-900">No documents</h3>
                    <p className="mt-1 text-sm text-gray-500">No documents found in this category.</p>
                </div>
            )}

            {showDuplicateModal && selectedDoc && (
                <DuplicateViewerModal
                    masterDoc={selectedDoc}
                    onClose={() => setShowDuplicateModal(false)}
                />
            )}

            {showVersionModal && selectedVersionDoc && (
                <VersionViewerModal
                    masterDoc={selectedVersionDoc}
                    onClose={() => { setShowVersionModal(false); setDefaultTab('summary'); }}
                    viewMode={viewMode}
                    defaultTab={defaultTab}
                />
            )}

            {showPreviewModal && previewDoc && (
                <DocumentPreviewModal
                    doc={previewDoc}
                    onClose={() => setShowPreviewModal(false)}
                />
            )}
        </div>
    );
};

const DocumentPreviewModal = ({ doc, onClose }) => {
    const { loanId } = useParams();

    const getDocumentUrl = (filename) => {
        return `http://localhost:8006/api/admin/loans/${loanId}/documents/${encodeURIComponent(filename)}/content`;
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-6xl w-full h-[90vh] flex flex-col">
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h2 className="text-xl font-semibold text-gray-900 flex items-center">
                        <File className="h-5 w-5 mr-2 text-gray-500" />
                        {doc.name}
                    </h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
                <div className="flex-1 bg-gray-100 p-2">
                    <iframe
                        src={getDocumentUrl(doc.name)}
                        className="w-full h-full rounded border border-gray-300 bg-white"
                        title="Document Preview"
                    />
                </div>
            </div>
        </div>
    );
};

const DuplicateViewerModal = ({ masterDoc, onClose }) => {
    const { loanId } = useParams();
    const [currentDuplicateIndex, setCurrentDuplicateIndex] = useState(0);

    // Duplicates are now fetched from backend and passed in masterDoc.duplicates
    const duplicates = masterDoc.duplicates || [];
    const totalDuplicates = duplicates.length;

    const handlePrevious = () => {
        setCurrentDuplicateIndex((prev) => (prev > 0 ? prev - 1 : totalDuplicates - 1));
    };

    const handleNext = () => {
        setCurrentDuplicateIndex((prev) => (prev < totalDuplicates - 1 ? prev + 1 : 0));
    };

    // Use params from parent context or prop if not available?
    // useParams is available since DuplicateViewerModal is rendered inside LoanDetailPage

    const getDocumentUrl = (filename) => {
        return `http://localhost:8006/api/admin/loans/${loanId}/documents/${encodeURIComponent(filename)}/content`;
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-7xl w-full h-[90vh] flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h2 className="text-xl font-semibold text-gray-900">
                        Duplicate Documents Viewer
                    </h2>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 transition-colors"
                    >
                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 flex overflow-hidden">
                    {/* Left Side - Master Document */}
                    <div className="w-1/2 border-r border-gray-200 flex flex-col">
                        <div className="px-6 py-4 bg-green-50 border-b border-green-200 flex flex-col justify-center h-[88px]">
                            <div className="flex items-center space-x-2">
                                <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-green-600 text-white">
                                    MASTER
                                </span>
                                <span className="text-sm font-medium text-gray-900 truncate" title={masterDoc.name}>{masterDoc.name}</span>
                            </div>
                            <p className="text-xs text-gray-600 mt-1">
                                {masterDoc.size ? `${(masterDoc.size / 1024).toFixed(2)} KB` : 'N/A'} •
                                {masterDoc.upload_date ? ` ${new Date(masterDoc.upload_date).toLocaleDateString()}` : ' N/A'}
                            </p>
                        </div>
                        <div className="flex-1 bg-gray-100 p-2">
                            <iframe
                                src={getDocumentUrl(masterDoc.name)}
                                className="w-full h-full rounded border border-gray-300 bg-white"
                                title="Master Document"
                            />
                        </div>
                    </div>

                    {/* Right Side - Duplicate Documents Slideshow */}
                    <div className="w-1/2 flex flex-col">
                        <div className="px-6 py-4 bg-yellow-50 border-b border-yellow-200 flex flex-col justify-center h-[88px]">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center space-x-2 overflow-hidden">
                                    <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-yellow-600 text-white flex-shrink-0">
                                        DUPLICATE {currentDuplicateIndex + 1} of {totalDuplicates}
                                    </span>
                                    {totalDuplicates > 0 && (
                                        <span className="text-sm font-medium text-gray-900 truncate" title={duplicates[currentDuplicateIndex]}>
                                            {duplicates[currentDuplicateIndex]}
                                        </span>
                                    )}
                                </div>
                                {totalDuplicates > 1 && (
                                    <div className="flex items-center space-x-2 flex-shrink-0 ml-2">
                                        <button
                                            onClick={handlePrevious}
                                            className="p-1 rounded-lg hover:bg-yellow-100 transition-colors"
                                            title="Previous"
                                        >
                                            <svg className="h-5 w-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                                            </svg>
                                        </button>
                                        <button
                                            onClick={handleNext}
                                            className="p-1 rounded-lg hover:bg-yellow-100 transition-colors"
                                            title="Next"
                                        >
                                            <svg className="h-5 w-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                            </svg>
                                        </button>
                                    </div>
                                )}
                            </div>
                            {/* Placeholder to match left side height */}
                            <p className="text-xs text-transparent mt-1 select-none">
                                Placeholder Metadata
                            </p>
                        </div>
                        <div className="flex-1 bg-gray-100 p-2">
                            {totalDuplicates > 0 ? (
                                <iframe
                                    src={getDocumentUrl(duplicates[currentDuplicateIndex])}
                                    className="w-full h-full rounded border border-gray-300 bg-white"
                                    title="Duplicate Document"
                                />
                            ) : (
                                <div className="flex items-center justify-center h-full text-gray-500">
                                    No duplicates found
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50">
                    <div className="flex items-center justify-between">
                        <p className="text-sm text-gray-600">
                            These documents have identical content based on text hash matching
                        </p>
                        <button
                            onClick={onClose}
                            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
                        >
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

const VersionViewerModal = ({ masterDoc, onClose, viewMode = 'full', defaultTab = 'summary' }) => {
    const { loanId } = useParams();
    const [allVersions, setAllVersions] = useState([]);
    const [latestVersions, setLatestVersions] = useState([]);
    const [nonLatestVersions, setNonLatestVersions] = useState([]);
    const [leftIndex, setLeftIndex] = useState(0);
    const [rightIndex, setRightIndex] = useState(0);
    const [leftTab, setLeftTab] = useState(defaultTab);
    const [rightTab, setRightTab] = useState('summary');
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const main = { ...masterDoc };
        delete main.versions;
        const others = masterDoc.versions || [];
        const allDocs = [main, ...others];

        // Separate into latest (left) and non-latest (right)
        const latestDocs = allDocs.filter(d => d.is_latest_version === true);
        const nonLatestDocs = allDocs.filter(d => d.is_latest_version !== true);

        setAllVersions(allDocs); // Keep all for reference
        setLatestVersions(latestDocs);
        setNonLatestVersions(nonLatestDocs);
        setLeftIndex(0);
        setRightIndex(0);
    }, [masterDoc]);

    const handleLeftPrev = () => {
        setLeftIndex((prev) => (prev > 0 ? prev - 1 : latestVersions.length - 1));
    };

    const handleLeftNext = () => {
        setLeftIndex((prev) => (prev < latestVersions.length - 1 ? prev + 1 : 0));
    };

    const handleRightPrev = () => {
        setRightIndex((prev) => (prev > 0 ? prev - 1 : nonLatestVersions.length - 1));
    };

    const handleRightNext = () => {
        setRightIndex((prev) => (prev < nonLatestVersions.length - 1 ? prev + 1 : 0));
    };

    const handleMarkAsLatest = async () => {
        const targetDoc = nonLatestVersions[rightIndex];
        if (!targetDoc?.id) return;

        if (!window.confirm(`Are you sure you want to mark "${targetDoc.name}" as the latest version?`)) {
            return;
        }

        try {
            setLoading(true);
            const token = localStorage.getItem('token');
            // Assuming endpoint is /api/admin/loans/:loanId/documents/:docId/set_latest
            await axios.post(`http://localhost:8006/api/admin/loans/${loanId}/documents/${targetDoc.id}/set_latest`, {}, {
                headers: { Authorization: `Bearer ${token}` }
            });
            // Reload to reflect changes
            window.location.reload();
        } catch (error) {
            console.error("Failed to set latest version:", error);
            alert("Failed to update version status.");
            setLoading(false);
        }
    };

    const getDocumentUrl = (filename) => {
        return `http://localhost:8006/api/admin/loans/${loanId}/documents/${encodeURIComponent(filename)}/content`;
    };

    const renderMetadata = (doc) => {
        let meta = doc.version_metadata;
        if (typeof meta === 'string') {
            try { meta = JSON.parse(meta); } catch (e) { return null; }
        }
        
        // Also get individual_analysis for additional details
        let analysis = doc.individual_analysis || {};
        if (typeof analysis === 'string') {
            try { analysis = JSON.parse(analysis); } catch (e) { analysis = {}; }
        }

        // Check for rich display_summary first
        const summary = meta?.display_summary;
        
        if (summary) {
            return (
                <div className="space-y-4">
                    {/* Title and Type */}
                    {summary.title && (
                        <div>
                            <h3 className="text-lg font-semibold text-gray-900">{summary.title}</h3>
                            {summary.document_type && (
                                <p className="text-sm text-gray-500">{summary.document_type}</p>
                            )}
                        </div>
                    )}
                    
                    {/* Description */}
                    {summary.brief_description && (
                        <p className="text-sm text-gray-700 bg-gray-50 p-3 rounded-lg border border-gray-200">
                            {summary.brief_description}
                        </p>
                    )}
                    
                    {/* Key Parties */}
                    {summary.key_parties?.length > 0 && (
                        <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Key Parties</h4>
                            <div className="flex flex-wrap gap-2">
                                {summary.key_parties.map((party, i) => (
                                    <span key={i} className="px-2 py-1 bg-blue-50 text-blue-700 rounded-md text-sm border border-blue-200">
                                        {party}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    {/* Key Dates */}
                    {summary.key_dates?.length > 0 && (
                        <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Key Dates</h4>
                            <div className="grid grid-cols-2 gap-2">
                                {summary.key_dates.map((item, i) => (
                                    <div key={i} className="bg-gray-50 p-2 rounded border border-gray-200">
                                        <p className="text-xs text-gray-500">{item.label}</p>
                                        <p className="text-sm font-medium text-gray-900">{item.value}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    {/* Key Amounts */}
                    {summary.key_amounts?.length > 0 && (
                        <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Key Amounts</h4>
                            <div className="grid grid-cols-2 gap-2">
                                {summary.key_amounts.map((item, i) => (
                                    <div key={i} className="bg-green-50 p-2 rounded border border-green-200">
                                        <p className="text-xs text-green-600">{item.label}</p>
                                        <p className="text-sm font-bold text-green-800">{item.value}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    {/* Status Indicators */}
                    {summary.status_indicators?.length > 0 && (
                        <div>
                            <h4 className="text-xs font-semibold text-gray-500 uppercase mb-2">Status</h4>
                            <div className="flex flex-wrap gap-2">
                                {summary.status_indicators.map((item, i) => (
                                    <span key={i} className={`px-2 py-1 rounded-md text-sm border ${
                                        item.status === 'success' ? 'bg-green-50 text-green-700 border-green-200' :
                                        item.status === 'warning' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                                        'bg-gray-50 text-gray-700 border-gray-200'
                                    }`}>
                                        {item.label}: {item.value}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                    
                    {/* Important Notes */}
                    {summary.important_notes?.length > 0 && (
                        <div className="bg-amber-50 p-3 rounded-lg border border-amber-200">
                            <h4 className="text-xs font-semibold text-amber-700 uppercase mb-1">⚠️ Notes</h4>
                            <ul className="text-sm text-amber-800 space-y-1">
                                {summary.important_notes.map((note, i) => (
                                    <li key={i}>• {note}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                    
                    {/* Financial Category Badge */}
                    {meta?.financial_category && (
                        <div className="pt-2 border-t border-gray-200">
                            <span className={`px-2 py-1 rounded text-xs font-bold ${
                                meta.financial_category === 'FINANCIAL' 
                                    ? 'bg-green-100 text-green-800' 
                                    : 'bg-gray-100 text-gray-700'
                            }`}>
                                {meta.financial_category}
                            </span>
                        </div>
                    )}
                </div>
            );
        }

        // Fallback to old metadata display if no rich summary
        if (!meta && !analysis.document_type) return null;

        return (
            <div className="space-y-3">
                {/* Document Type from analysis */}
                {analysis.document_type && (
                    <div>
                        <h3 className="text-base font-semibold text-gray-900">{analysis.document_type}</h3>
                    </div>
                )}
                
                {/* Borrower info */}
                {analysis.borrower_name && (
                    <div className="flex flex-wrap gap-2">
                        <span className="px-2 py-1 bg-blue-50 text-blue-700 rounded-md text-sm border border-blue-200">
                            {analysis.borrower_name}
                        </span>
                        {analysis.co_borrower_name && analysis.co_borrower_name !== 'null' && (
                            <span className="px-2 py-1 bg-indigo-50 text-indigo-700 rounded-md text-sm border border-indigo-200">
                                Co: {analysis.co_borrower_name}
                            </span>
                        )}
                    </div>
                )}
                
                {/* Status badges */}
                <div className="flex flex-wrap gap-2">
                    {analysis.has_signature !== undefined && (
                        <span className={`px-2 py-1 rounded-md text-sm border ${
                            analysis.has_signature 
                                ? 'bg-green-50 text-green-700 border-green-200' 
                                : 'bg-amber-50 text-amber-700 border-amber-200'
                        }`}>
                            {analysis.has_signature ? '✓ Signed' : 'Unsigned'}
                        </span>
                    )}
                    {analysis.document_date && (
                        <span className="px-2 py-1 bg-gray-50 text-gray-700 rounded-md text-sm border border-gray-200">
                            📅 {analysis.document_date}
                        </span>
                    )}
                    {analysis.version_indicator && (
                        <span className="px-2 py-1 bg-purple-50 text-purple-700 rounded-md text-sm border border-purple-200">
                            {analysis.version_indicator}
                        </span>
                    )}
                </div>
                
                {/* Financial category */}
                {meta?.financial_category && (
                    <div className="pt-2 border-t border-gray-200">
                        <span className={`px-2 py-1 rounded text-xs font-bold ${
                            meta.financial_category === 'FINANCIAL' 
                                ? 'bg-green-100 text-green-800' 
                                : 'bg-gray-100 text-gray-700'
                        }`}>
                            {meta.financial_category}
                        </span>
                    </div>
                )}

                {/* AI grouping info */}
                {meta?.ai_group_description && (
                    <div className="bg-purple-50 p-2 rounded border border-purple-100 text-xs">
                        <p className="text-purple-900">AI: {meta.ai_group_description}</p>
                    </div>
                )}
            </div>
        );
    };

    const renderMetadataOld = (doc) => {
        let meta = doc.version_metadata;
        if (typeof meta === 'string') {
            try { meta = JSON.parse(meta); } catch (e) { return null; }
        }
        if (!meta) return null;

        return (
            <div className="mt-2 text-xs border-t border-purple-200 pt-2 space-y-2">
                <div className="flex flex-wrap gap-1">
                    {meta.category && (
                        <span className="px-1.5 py-0.5 rounded border bg-white border-gray-200 text-gray-600 shadow-sm">
                            {meta.category}
                        </span>
                    )}
                    {meta.status && (
                        <span className={`px-1.5 py-0.5 rounded border shadow-sm ${meta.status.toLowerCase().includes('signed') || meta.status.toLowerCase().includes('complete') ? 'bg-green-50 border-green-200 text-green-700' :
                            'bg-yellow-50 border-yellow-200 text-yellow-700'
                            }`}>
                            {meta.status}
                        </span>
                    )}
                    {meta.borrower && (
                        <span className="px-1.5 py-0.5 rounded border bg-blue-50 border-blue-200 text-blue-700 shadow-sm">
                            {meta.borrower}
                        </span>
                    )}
                </div>

                {(meta.financial_category || meta.financial_reason) && (
                    <div className="bg-gray-50 p-1.5 rounded border border-gray-100">
                        {meta.financial_category && (
                            <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold mb-1 ${meta.financial_category === 'FINANCIAL' ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-800'
                                }`}>
                                {meta.financial_category}
                            </span>
                        )}
                        {meta.financial_reason && (
                            <p className="text-gray-600 text-[10px] italic leading-snug">
                                {meta.financial_reason}
                            </p>
                        )}
                    </div>
                )}

                {(meta.ai_group_id || meta.ai_group_reason) && (
                    <div className="bg-purple-50 p-1.5 rounded border border-purple-100">
                        {meta.ai_group_description && (
                            <p className="text-[10px] font-bold text-purple-900 mb-0.5">{meta.ai_group_description}</p>
                        )}
                        {meta.ai_group_id && (
                            <div className="flex items-center gap-1 mb-1">
                                <span className="text-[10px] font-semibold text-purple-800">Group ID:</span>
                                <span className="font-mono text-[10px] bg-white px-1 rounded border border-purple-200 text-purple-700">{meta.ai_group_id}</span>
                            </div>
                        )}
                        {meta.ai_group_reason && (
                            <p className="text-purple-800 text-[10px] italic leading-snug">
                                {meta.ai_group_reason}
                            </p>
                        )}
                    </div>
                )}

                {/* Detailed AI Classification */}
                {(meta.doc_type || meta.signers || meta.signed_status || meta.doc_date_ai) && (
                    <div className="bg-blue-50 p-1.5 rounded border border-blue-100 mt-1">
                        <div className="flex flex-wrap gap-2 text-[10px] mb-1">
                            {meta.doc_type && <span className="font-bold text-blue-900">{meta.doc_type}</span>}
                            {meta.doc_date_ai && <span className="text-blue-800 whitespace-nowrap">📅 {meta.doc_date_ai}</span>}
                        </div>
                        <div className="flex flex-wrap gap-1">
                            {meta.signers && <span className="px-1.5 py-0.5 bg-white rounded border border-blue-200 text-blue-700 text-[10px] shadow-sm">{meta.signers}</span>}
                            {meta.signed_status && <span className={`px-1.5 py-0.5 rounded border text-[10px] shadow-sm ${meta.signed_status.toLowerCase() === 'signed' ? 'bg-green-100 border-green-200 text-green-800' : 'bg-orange-50 border-orange-200 text-orange-800'}`}>{meta.signed_status}</span>}
                        </div>
                    </div>
                )}

                {meta.primary_reason && (
                    <p className="text-gray-500 text-[9px] mt-1 pt-1 border-t border-gray-100">
                        <span className="font-semibold">Selection Logic:</span> {meta.primary_reason}
                    </p>
                )}

                {meta.filename_warning && (
                    <div className="mt-1 p-1.5 bg-red-50 border border-red-200 rounded text-[10px] text-red-800 flex items-start gap-1">
                        <span>⚠️</span>
                        <span><span className="font-bold">Filename Mismatch:</span> {meta.filename_warning}</span>
                    </div>
                )}

                {meta.reasoning && !meta.ai_group_id && (
                    <p className="text-gray-600 italic text-[10px] leading-tight line-clamp-3" title={meta.reasoning}>
                        AI: {meta.reasoning}
                    </p>
                )}
            </div>
        );
    };

    if (allVersions.length === 0) return null;

    const leftDoc = latestVersions[leftIndex];
    let rightDoc = nonLatestVersions[rightIndex];

    // In Gallery Mode, force Single Pane (Left Only) logic
    if (viewMode === 'gallery') {
        rightDoc = null;
    }

    // Fallback comparison logic removed per user request.
    // Groups with multiple primaries (e.g. 5 Bank Statements) should display as 
    // a single Full-Width viewer by default, allowing navigation via the Left Pane arrows.

    if (latestVersions.length === 0 && nonLatestVersions.length === 0) return null;

    // Helper to detect peer groups (Borrower/Co-borrower) or Multi-Primary groups
    const isPeerGroup = () => {
        // Structural check: Multiple "Latest" docs and no "Old" docs -> Valid Peer Group
        // This solves the "1 of 0" issue by treating flat groups as peers
        if (latestVersions.length > 1 && nonLatestVersions.length === 0) return true;

        const doc = leftDoc || rightDoc;
        if (!doc) return false;
        const meta = typeof doc.version_metadata === 'string' ? JSON.parse(doc.version_metadata) : doc.version_metadata || {};
        const reason = (meta.ai_group_reason || "").toLowerCase();
        return reason.includes('borrower') && reason.includes('co-borrower');
    };
    const isPeers = isPeerGroup();

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-[95vw] w-full h-[95vh] flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h2 className="text-xl font-semibold text-gray-900">
                        {viewMode === 'gallery' ? "Unique Documents" : (isPeers ? "Related Documents Group" : "Version Comparison")}
                    </h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
                        <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                <div className="flex-1 flex overflow-hidden">
                    {/* LEFT PANE - SELECTION */}
                    <div className={`${rightDoc ? 'w-1/2 border-r' : 'w-full'} border-gray-200 flex flex-col transition-all duration-300`}>
                        <div className="px-4 py-3 bg-purple-50 border-b border-purple-200 flex flex-col">
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <span className="text-xs font-bold text-purple-700 uppercase tracking-wide">
                                        {isPeers ?
                                            `Document 1 (${leftIndex + 1} of ${latestVersions.length})` :
                                            `Latest Version (${leftIndex + 1} of ${latestVersions.length})`
                                        }
                                    </span>
                                    <span className="inline-flex px-2 py-0.5 rounded text-[10px] font-bold bg-purple-600 text-white">
                                        {isPeers ? "PRIMARY VIEW" : "CURRENT LATEST"}
                                    </span>
                                </div>
                                {latestVersions.length > 1 && (
                                    <div className="flex space-x-1">
                                        <button onClick={handleLeftPrev} className="p-1 rounded hover:bg-purple-200"><svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg></button>
                                        <button onClick={handleLeftNext} className="p-1 rounded hover:bg-purple-200"><svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg></button>
                                    </div>
                                )}
                            </div>
                            <div className="text-sm font-medium text-gray-900 truncate mb-1" title={leftDoc?.name}>{leftDoc?.name}</div>
                            <div className="text-xs text-gray-600">
                                {leftDoc?.detected_date ? `Date: ${leftDoc.detected_date}` : 'Undated'} • {(leftDoc?.size / 1024).toFixed(1)} KB
                            </div>

                            {/* Tabs */}
                            <div className="flex border-t border-purple-200 mt-2">
                                <button
                                    onClick={() => setLeftTab('summary')}
                                    className={`flex-1 py-1.5 text-xs font-medium text-center ${leftTab === 'summary' ? 'bg-purple-100 text-purple-700 border-b-2 border-purple-600' : 'text-gray-500 hover:bg-gray-50'}`}
                                >
                                    Summary
                                </button>
                                <button
                                    onClick={() => setLeftTab('pdf')}
                                    className={`flex-1 py-1.5 text-xs font-medium text-center ${leftTab === 'pdf' ? 'bg-purple-100 text-purple-700 border-b-2 border-purple-600' : 'text-gray-500 hover:bg-gray-50'}`}
                                >
                                    PDF
                                </button>
                                <button
                                    onClick={() => setLeftTab('json')}
                                    className={`flex-1 py-1.5 text-xs font-medium text-center ${leftTab === 'json' ? 'bg-purple-100 text-purple-700 border-b-2 border-purple-600' : 'text-gray-500 hover:bg-gray-50'}`}
                                >
                                    JSON
                                </button>
                            </div>
                        </div>
                        <div className="flex-1 bg-gray-100 p-2 relative overflow-auto">
                            {leftTab === 'summary' ? (
                                <div className="w-full h-full bg-white rounded p-4 overflow-auto">
                                    {renderMetadata(leftDoc)}
                                </div>
                            ) : leftTab === 'pdf' ? (
                                <>
                                    <button
                                        onClick={() => window.open(getDocumentUrl(leftDoc?.name), '_blank')}
                                        className="absolute top-4 right-4 z-10 p-2 bg-white rounded-lg shadow-lg hover:bg-gray-50 transition-colors border border-gray-300"
                                        title="Open in full screen"
                                    >
                                        <svg className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                                        </svg>
                                    </button>
                                    <iframe
                                        src={getDocumentUrl(leftDoc?.name)}
                                        className="w-full h-full rounded border border-gray-300 bg-white"
                                        title="Left Doc"
                                    />
                                </>
                            ) : (
                                <>
                                    <button
                                        onClick={() => {
                                            // ALWAYS prefer individual_analysis if it has document_summary (deep extraction)
                                            const jsonData = leftDoc?.individual_analysis?.document_summary 
                                                ? leftDoc.individual_analysis 
                                                : (leftDoc?.individual_analysis || leftDoc?.vlm_analysis || { message: "No extracted JSON data available" });
                                            const displayData = leftDoc?.individual_analysis?.document_summary
                                                ? leftDoc.individual_analysis
                                                : ((leftDoc?.vlm_analysis?.error && leftDoc?.individual_analysis) 
                                                ? leftDoc.individual_analysis 
                                                : jsonData);
                                            const data = JSON.stringify(displayData, null, 2);
                                            const blob = new Blob([data], { type: 'application/json' });
                                            const url = URL.createObjectURL(blob);
                                            window.open(url, '_blank');
                                        }}
                                        className="absolute top-4 right-4 z-10 p-2 bg-slate-800 rounded-lg shadow-lg hover:bg-slate-700 transition-colors border border-slate-600"
                                        title="Open in full screen"
                                    >
                                        <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                                        </svg>
                                    </button>
                                    <div className="w-full h-full bg-slate-900 rounded p-4 overflow-auto">
                                        <JSONTree
                                            data={(() => {
                                                // ALWAYS prefer individual_analysis if it has document_summary (deep extraction)
                                                if (leftDoc?.individual_analysis?.document_summary) {
                                                    return leftDoc.individual_analysis;
                                                }
                                                // Fall back to individual_analysis if vlm_analysis has error
                                                if (leftDoc?.individual_analysis && leftDoc?.vlm_analysis?.error) {
                                                    return leftDoc.individual_analysis;
                                                }
                                                return leftDoc?.individual_analysis || leftDoc?.vlm_analysis || { message: "No extracted JSON data available" };
                                            })()}
                                            theme={{
                                                scheme: 'monokai',
                                                author: 'wimer hazenberg (http://www.monokai.nl)',
                                                base00: '#1e1e1e',
                                                base01: '#383830',
                                                base02: '#49483e',
                                                base03: '#75715e',
                                                base04: '#a59f85',
                                                base05: '#f8f8f2',
                                                base06: '#f5f4f1',
                                                base07: '#f9f8f5',
                                                base08: '#f92672',
                                                base09: '#fd971f',
                                                base0A: '#f4bf75',
                                                base0B: '#a6e22e',
                                                base0C: '#a1efe4',
                                                base0D: '#66d9ef',
                                                base0E: '#ae81ff',
                                                base0F: '#cc6633'
                                            }}
                                            invertTheme={false}
                                            hideRoot={false}
                                            shouldExpandNodeInitially={(keyPath, data, level) => level < 2}
                                        />
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* RIGHT PANE - REFERENCE */}
                    {rightDoc && (
                        <div className="w-1/2 flex flex-col">
                            <div className="px-4 py-3 bg-gray-50 border-b border-gray-200 flex flex-col">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-bold text-gray-500 uppercase tracking-wide">
                                        {isPeers ?
                                            `Document 2` :
                                            `Other Version (${rightIndex + 1} of ${nonLatestVersions.length})`
                                        }
                                    </span>
                                    {nonLatestVersions.length > 1 && (
                                        <div className="flex space-x-1">
                                            <button onClick={handleRightPrev} className="p-1 rounded hover:bg-gray-200"><svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" /></svg></button>
                                            <button onClick={handleRightNext} className="p-1 rounded hover:bg-gray-200"><svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" /></svg></button>
                                        </div>
                                    )}
                                </div>
                                <div className="flex items-center justify-between mb-1">
                                    <span className="text-sm font-medium text-gray-900 truncate" title={rightDoc.name}>{rightDoc.name}</span>
                                    {!isPeers && (
                                        <button
                                            onClick={handleMarkAsLatest}
                                            disabled={loading}
                                            className="px-2 py-1 bg-purple-600 text-white text-xs rounded hover:bg-purple-700 disabled:opacity-50"
                                        >
                                            {loading ? 'Saving...' : 'Mark as Latest'}
                                        </button>
                                    )}
                                </div>
                                <div className="text-xs text-gray-600 mb-2">
                                    {rightDoc?.detected_date ? `Date: ${rightDoc.detected_date}` : 'Undated'} • {(rightDoc?.size / 1024).toFixed(1)} KB
                                </div>

                                {/* Tabs */}
                                <div className="flex border-t border-gray-200 mt-2">
                                    <button
                                        onClick={() => setRightTab('summary')}
                                        className={`flex-1 py-1.5 text-xs font-medium text-center ${rightTab === 'summary' ? 'bg-gray-100 text-gray-700 border-b-2 border-gray-600' : 'text-gray-500 hover:bg-gray-50'}`}
                                    >
                                        Summary
                                    </button>
                                    <button
                                        onClick={() => setRightTab('pdf')}
                                        className={`flex-1 py-1.5 text-xs font-medium text-center ${rightTab === 'pdf' ? 'bg-gray-100 text-gray-700 border-b-2 border-gray-600' : 'text-gray-500 hover:bg-gray-50'}`}
                                    >
                                        PDF
                                    </button>
                                    <button
                                        onClick={() => setRightTab('json')}
                                        className={`flex-1 py-1.5 text-xs font-medium text-center ${rightTab === 'json' ? 'bg-gray-100 text-gray-700 border-b-2 border-gray-600' : 'text-gray-500 hover:bg-gray-50'}`}
                                    >
                                        JSON
                                    </button>
                                </div>
                            </div>
                            <div className="flex-1 bg-gray-100 p-2 relative overflow-auto">
                                {rightTab === 'summary' ? (
                                    <div className="w-full h-full bg-white rounded p-4 overflow-auto">
                                        {renderMetadata(rightDoc)}
                                    </div>
                                ) : rightTab === 'pdf' ? (
                                    <>
                                        <button
                                            onClick={() => window.open(getDocumentUrl(rightDoc.name), '_blank')}
                                            className="absolute top-4 right-4 z-10 p-2 bg-white rounded-lg shadow-lg hover:bg-gray-50 transition-colors border border-gray-300"
                                            title="Open in full screen"
                                        >
                                            <svg className="h-5 w-5 text-gray-700" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                                            </svg>
                                        </button>
                                        <iframe
                                            src={getDocumentUrl(rightDoc.name)}
                                            className="w-full h-full rounded border border-gray-300 bg-white"
                                            title="Right Doc"
                                        />
                                    </>
                                ) : (
                                    <>
                                        <button
                                            onClick={() => {
                                                // ALWAYS prefer individual_analysis if it has document_summary (deep extraction)
                                                const jsonData = rightDoc?.individual_analysis?.document_summary 
                                                    ? rightDoc.individual_analysis 
                                                    : (rightDoc?.individual_analysis || rightDoc?.vlm_analysis || { message: "No extracted JSON data available" });
                                                const displayData = rightDoc?.individual_analysis?.document_summary
                                                    ? rightDoc.individual_analysis
                                                    : ((rightDoc?.vlm_analysis?.error && rightDoc?.individual_analysis) 
                                                    ? rightDoc.individual_analysis 
                                                    : jsonData);
                                                const data = JSON.stringify(displayData, null, 2);
                                                const blob = new Blob([data], { type: 'application/json' });
                                                const url = URL.createObjectURL(blob);
                                                window.open(url, '_blank');
                                            }}
                                            className="absolute top-4 right-4 z-10 p-2 bg-slate-800 rounded-lg shadow-lg hover:bg-slate-700 transition-colors border border-slate-600"
                                            title="Open in full screen"
                                        >
                                            <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                                            </svg>
                                        </button>
                                        <div className="w-full h-full bg-slate-900 rounded p-4 overflow-auto">
                                            <JSONTree
                                                data={(() => {
                                                    // ALWAYS prefer individual_analysis if it has document_summary (deep extraction)
                                                    if (rightDoc?.individual_analysis?.document_summary) {
                                                        return rightDoc.individual_analysis;
                                                    }
                                                    // Fall back to individual_analysis if vlm_analysis has error
                                                    if (rightDoc?.individual_analysis && rightDoc?.vlm_analysis?.error) {
                                                        return rightDoc.individual_analysis;
                                                    }
                                                    return rightDoc?.individual_analysis || rightDoc?.vlm_analysis || { message: "No extracted JSON data available" };
                                                })()}
                                                theme={{
                                                    scheme: 'monokai',
                                                    author: 'wimer hazenberg (http://www.monokai.nl)',
                                                    base00: '#1e1e1e',
                                                    base01: '#383830',
                                                    base02: '#49483e',
                                                    base03: '#75715e',
                                                    base04: '#a59f85',
                                                    base05: '#f8f8f2',
                                                    base06: '#f5f4f1',
                                                    base07: '#f9f8f5',
                                                    base08: '#f92672',
                                                    base09: '#fd971f',
                                                    base0A: '#f4bf75',
                                                    base0B: '#a6e22e',
                                                    base0C: '#a1efe4',
                                                    base0D: '#66d9ef',
                                                    base0E: '#ae81ff',
                                                    base0F: '#cc6633'
                                                }}
                                                invertTheme={false}
                                                hideRoot={false}
                                                shouldExpandNodeInitially={(keyPath, data, level) => level < 2}
                                            />
                                        </div>
                                    </>
                                )}
                            </div>
                        </div>
                    )}
                </div>

                <div className="px-6 py-3 border-t border-gray-200 bg-gray-50 flex justify-between items-center text-xs text-gray-500">
                    <p>Use the Left Panel to find and select the correct latest version. AI analysis helps identify status.</p>
                    <button onClick={onClose} className="px-4 py-2 bg-white border border-gray-300 rounded text-gray-700 hover:bg-gray-50">
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
};

const ImportantDocumentsView = ({ extractedData = [], loanId, calculationSteps = {}, allDocuments = [] }) => {
    const [expandedSections, setExpandedSections] = useState({});
    const [showOnlyWithValues, setShowOnlyWithValues] = useState(true);
    const [showVerifiedOnly, setShowVerifiedOnly] = useState(false);
    const [evidenceModal, setEvidenceModal] = useState({
        isOpen: false,
        evidence: null,
        attributeLabel: '',
        attributeValue: ''
    });
    const [documentModal, setDocumentModal] = useState({
        isOpen: false,
        document: null
    });

    // Initialize all sections as expanded
    useEffect(() => {
        if (extractedData.length > 0) {
            const sections = {};
            extractedData.forEach(item => {
                if (item.section) sections[item.section] = true;
            });
            setExpandedSections(sections);
        }
    }, [extractedData]);

    const toggleSection = (section) => {
        setExpandedSections(prev => ({
            ...prev,
            [section]: !prev[section]
        }));
    };

    // Filter data
    let filteredData = extractedData;
    
    // Filter by values - show only non-empty, non-zero values found on 1008 form
    let dataAfterValueFilter = extractedData;
    if (showOnlyWithValues) {
        dataAfterValueFilter = extractedData.filter(item => {
            const value = item.extracted_value;
            if (!value || value.trim() === '' || value.toLowerCase() === 'false') {
                return false;
            }
            // Also exclude zero values
            const numValue = parseFloat(value.replace(/[$,\s%]/g, ''));
            if (!isNaN(numValue) && numValue === 0) {
                return false;
            }
            return true;
        });
        filteredData = dataAfterValueFilter;
    }
    
    // Filter by verified status
    if (showVerifiedOnly) {
        filteredData = filteredData.filter(item => {
            return item.evidence && item.evidence.length > 0 && 
                   item.evidence.some(ev => ev.verification_status === 'verified');
        });
    }

    // Group by section and sort
    const sectionOrder = {
        'Property and Mortgage Details': 1,
        'Borrower Info': 2,
        'Co-Borrower Info': 3,
        'Underwriting Info': 4
    };
    
    const groupedData = filteredData.reduce((acc, item) => {
        const section = item.section || 'Other';
        if (!acc[section]) acc[section] = [];
        acc[section].push(item);
        return acc;
    }, {});
    
    // Sort items within each section by display_order
    Object.keys(groupedData).forEach(section => {
        groupedData[section].sort((a, b) => {
            const orderA = a.display_order || 999;
            const orderB = b.display_order || 999;
            return orderA - orderB;
        });
    });
    
    // Sort sections by predefined order
    const sortedSections = Object.keys(groupedData).sort((a, b) => {
        const orderA = sectionOrder[a] || 999;
        const orderB = sectionOrder[b] || 999;
        return orderA - orderB;
    });

    return (
        <div className="space-y-3">
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
                <div className="px-3 py-2 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <FileText size={16} className="text-primary-600" />
                        <h2 className="text-sm font-semibold text-slate-900">
                            1008 Form Extraction Analysis
                        </h2>
                    </div>
                    <div className="flex items-center gap-3">
                        <label className="flex items-center gap-1.5 text-xs text-slate-600 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={showOnlyWithValues}
                                onChange={(e) => setShowOnlyWithValues(e.target.checked)}
                                className="rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                            />
                            Show only with values
                        </label>
                        <label className="flex items-center gap-1.5 text-xs text-green-700 font-medium cursor-pointer">
                            <input
                                type="checkbox"
                                checked={showVerifiedOnly}
                                onChange={(e) => setShowVerifiedOnly(e.target.checked)}
                                className="rounded border-green-300 text-green-600 focus:ring-green-500"
                            />
                            Show verified only
                        </label>
                        <div className="text-xs text-slate-500">
                            {filteredData.length} of {showOnlyWithValues ? dataAfterValueFilter.length : extractedData.length}
                        </div>
                    </div>
                </div>

                <div className="divide-y divide-slate-200">
                    {sortedSections.map((section) => {
                        const items = groupedData[section];
                        return (
                        <div key={section} className="bg-white">
                            <button
                                onClick={() => toggleSection(section)}
                                className="w-full px-3 py-2 bg-slate-50/50 flex items-center justify-between hover:bg-slate-50 transition-colors"
                            >
                                <span className="font-medium text-xs text-slate-700">{section}</span>
                                {expandedSections[section] ? (
                                    <ChevronUp size={14} className="text-slate-400" />
                                ) : (
                                    <ChevronDown size={14} className="text-slate-400" />
                                )}
                            </button>

                            {expandedSections[section] && (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                                <thead className="bg-slate-50 text-slate-500 font-semibold">
                                                    <tr>
                                                        <th className="px-2 py-1.5 text-xs w-[5%] border border-slate-200">ID</th>
                                                        <th className="px-2 py-1.5 text-xs w-[15%] border border-slate-200">Attribute</th>
                                                        <th className="px-2 py-1.5 text-xs w-[12%] border border-slate-200">Extracted Value</th>
                                                        <th className="px-2 py-1.5 text-xs w-[18%] border border-slate-200">Evidence Attribute</th>
                                                        <th className="px-2 py-1.5 text-xs w-[12%] border border-slate-200">Evidence Value</th>
                                                        <th className="px-2 py-1.5 text-xs w-[18%] border border-slate-200">Evidence Document</th>
                                                        <th className="px-2 py-1.5 text-xs w-[10%] border border-slate-200">Verification</th>
                                                    </tr>
                                                </thead>
                                        <tbody>
                                            {items.map((item) => {
                                                const hasEvidence = item.evidence && item.evidence.length > 0;
                                                
                                                // Get calculation steps - try new API first, fallback to old JSON
                                                let steps = calculationSteps[item.attribute_id] || [];
                                                
                                                // Fallback: if few steps from API but more in old JSON, use old JSON
                                                if (steps.length < 2 && hasEvidence) {
                                                    const primaryEvidence = item.evidence.find(ev => {
                                                        try {
                                                            const notes = typeof ev.notes === 'string' ? JSON.parse(ev.notes) : ev.notes;
                                                            return notes?.document_classification === 'primary';
                                                        } catch { return false; }
                                                    });
                                                    
                                                    if (primaryEvidence) {
                                                        try {
                                                            const notes = typeof primaryEvidence.notes === 'string' 
                                                                ? JSON.parse(primaryEvidence.notes) 
                                                                : primaryEvidence.notes;
                                                            const oldSteps = notes?.step_by_step_calculation || [];
                                                            // Only use old steps if there are MORE steps in old format
                                                            if (oldSteps.length > steps.length) {
                                                                // Convert old format to new format
                                                                steps = oldSteps.map((s, idx) => {
                                                                    // Determine document name
                                                                    let docName = null;
                                                                    
                                                                    // Priority 1: Use 'document' field if present (direct filename)
                                                                    if (s.document) {
                                                                        docName = s.document;
                                                                    }
                                                                    // Priority 2: Try keyword matching on 'source' field
                                                                    else if (s.source && !s.formula) {
                                                                        const sourceKeywords = s.source.toLowerCase();
                                                                        const matchingDoc = allDocuments.find(doc => {
                                                                            const fileName = (doc.name || '').toLowerCase();
                                                                            if (sourceKeywords.includes('purchase') && fileName.includes('purchase')) return true;
                                                                            if (sourceKeywords.includes('tax') && fileName.includes('tax')) return true;
                                                                            if (sourceKeywords.includes('appraisal') && fileName.includes('appraisal')) return true;
                                                                            if (sourceKeywords.includes('urla') && fileName.includes('urla')) return true;
                                                                            if (sourceKeywords.includes('credit') && fileName.includes('credit')) return true;
                                                                            if (sourceKeywords.includes('note') && fileName.includes('note')) return true;
                                                                            if (sourceKeywords.includes('loan estimate') && fileName.includes('loan_estimate')) return true;
                                                                            if (sourceKeywords.includes('insurance') && fileName.includes('insurance')) return true;
                                                                            if (sourceKeywords.includes('evidence') && fileName.includes('evidence')) return true;
                                                                            return false;
                                                                        });
                                                                        docName = matchingDoc?.name || null;
                                                                    }
                                                                    
                                                                    // Determine if calculated: has formula OR no document reference
                                                                    const isCalculated = !!s.formula || (!s.document && !docName);
                                                                    
                                                                    return {
                                                                        step_id: `temp-${item.id}-${idx}`,
                                                                        step_order: s.step || idx + 1,
                                                                        value: s.amount || s.value,
                                                                        description: s.description || s.label,
                                                                        document_name: docName,
                                                                        page_number: s.page,
                                                                        notes: s.notes || s.explanation || null,
                                                                        source: s.source,
                                                                        formula: s.formula,
                                                                        is_calculated: isCalculated
                                                                    };
                                                                });
                                                            }
                                                        } catch(e) {
                                                            console.error(`Error parsing steps for ${item.attribute_label}:`, e);
                                                        }
                                                    }
                                                }
                                                
                                                // If has steps, render with rowspan
                                                if (steps.length > 1) {
                                                    // Multiple steps - show with rowspan
                                                    return (
                                                        <React.Fragment key={item.id}>
                                                            {steps.map((step, idx) => (
                                                                <tr key={`${item.id}-step-${step.step_id}`} className="hover:bg-blue-50/30 transition-colors">
                                                                    {/* ID - only on first row */}
                                                                    {idx === 0 && (
                                                                        <td rowSpan={steps.length} className="px-2 py-2 font-medium text-xs text-slate-500 align-top border border-slate-200 bg-slate-50/30">
                                                                            {item.attribute_id}
                                                                        </td>
                                                                    )}
                                                                    {/* Attribute Name - only on first row */}
                                                                    {idx === 0 && (
                                                                        <td rowSpan={steps.length} className="px-2 py-2 font-medium text-xs text-slate-700 align-top border border-slate-200 bg-slate-50/30">
                                                                            {item.attribute_label}
                                                                        </td>
                                                                    )}
                                                                    {/* Extracted Value - only on first row */}
                                                                    {idx === 0 && (
                                                                        <td rowSpan={steps.length} className="px-2 py-2 text-xs font-semibold text-slate-900 align-top border border-slate-200 bg-slate-50/30">
                                                                            {item.extracted_value}
                                                                        </td>
                                                                    )}
                                                                    {/* Evidence Attribute Name */}
                                                                    <td className="px-2 py-1.5 text-xs text-slate-600 border border-slate-200">
                                                                        <div>
                                                                            <div>{step.description}</div>
                                                                            {step.notes && (
                                                                                <div className="text-slate-500 italic text-[11px] mt-0.5 leading-relaxed">
                                                                                    {step.notes}
                                                                                </div>
                                                                            )}
                                                                        </div>
                                                                    </td>
                                                                    {/* Evidence Value */}
                                                                    <td className="px-2 py-1.5 text-xs font-medium text-slate-700 border border-slate-200">
                                                                        {step.value}
                                                                    </td>
                                                                    {/* Evidence Document */}
                                                                    <td className="px-2 py-1.5 border border-slate-200">
                                                                        {/* Check if this is the final step that matches 1008 value */}
                                                                        {idx === steps.length - 1 && step.value && item.extracted_value && 
                                                                         step.value.toString().replace(/[\$,\s]/g, '') === item.extracted_value.toString().replace(/[\$,\s]/g, '') ? (
                                                                            <div className="flex items-center">
                                                                                <div className="flex items-center justify-center w-6 h-6 bg-green-100 border border-green-300 rounded-full" title="Matches 1008 extracted value">
                                                                                    <CheckCircle2 size={14} className="text-green-600" />
                                                                                </div>
                                                                            </div>
                                                                        ) : step.document_name && !step.is_calculated && !step.document_name.startsWith('See ID -') ? (
                                                                            <button
                                                                                onClick={async () => {
                                                                                    // Open document with step_id filter
                                                                                    try {
                                                                                        const token = localStorage.getItem('token');
                                                                                        const response = await fetch(`http://localhost:8006/api/admin/loans/${loanId}/evidence-documents-v2`, {
                                                                                            headers: {
                                                                                                'Authorization': `Bearer ${token}`
                                                                                            }
                                                                                        });
                                                                                        const result = await response.json();
                                                                                        const evidenceDocs = Array.isArray(result) ? result : (result.documents || []);
                                                                                        const fullDoc = evidenceDocs.find(d => d.file_name === step.document_name);
                                                                                        
                                                                                        setDocumentModal({
                                                                                            isOpen: true,
                                                                                            document: {
                                                                                                ...(fullDoc || { file_name: step.document_name, usage: [] }),
                                                                                                initial_page: step.page_number || 1,
                                                                                                filter_step_id: step.step_id
                                                                                            }
                                                                                        });
                                                                                    } catch (error) {
                                                                                        console.error('Error fetching document:', error);
                                                                                    }
                                                                                }}
                                                                                className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 rounded text-xs transition-colors text-left"
                                                                                title={`Click to view ${step.document_name}`}
                                                                            >
                                                                                <FileText size={12} className="flex-shrink-0" />
                                                                                <span className="max-w-[140px] truncate">
                                                                                    {step.document_name.replace(/\.(pdf|json)$/i, '').replace(/_/g, ' ')}
                                                                                </span>
                                                                            </button>
                                                                        ) : step.document_name && step.document_name.startsWith('See ID -') ? (
                                                                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-gray-100 text-gray-700 border border-gray-200 rounded text-xs">
                                                                                <code className="font-mono text-[10px]">{step.document_name}</code>
                                                                            </span>
                                                                        ) : step.is_calculated ? (
                                                                            <span className="text-slate-400 text-xs italic">Calculated</span>
                                                                        ) : (
                                                                            <span className="text-slate-400 text-xs">-</span>
                                                                        )}
                                                                    </td>
                                                                    {/* Verification Status - only on first row */}
                                                                    {idx === 0 && hasEvidence && (
                                                                        <td rowSpan={steps.length} className="px-2 py-2 align-middle border border-slate-200 bg-slate-50/30 text-center">
                                                                            <button
                                                                                onClick={() => setEvidenceModal({
                                                                                    isOpen: true,
                                                                                    evidence: item.evidence,
                                                                                    attributeLabel: item.attribute_label,
                                                                                    attributeValue: item.extracted_value,
                                                                                    attributeId: item.attribute_id,
                                                                                    calculationSteps: calculationSteps[item.attribute_id] || []
                                                                                })}
                                                                                className={clsx(
                                                                                    "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border cursor-pointer hover:shadow-sm transition-all min-w-[80px] justify-center",
                                                                                    item.evidence[0].verification_status === 'verified'
                                                                                        ? "bg-green-50 text-green-700 border-green-200 hover:bg-green-100"
                                                                                        : "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"
                                                                                )}
                                                                            >
                                                                                {item.evidence[0].verification_status === 'verified' ? (
                                                                                    <CheckCircle2 size={12} className="text-green-600" />
                                                                                ) : (
                                                                                    <AlertCircle size={12} className="text-amber-600" />
                                                                                )}
                                                                                <span>
                                                                                    {item.evidence[0].verification_status === 'verified' ? 'Verified' : 'Review'}
                                                                                </span>
                                                                            </button>
                                                                        </td>
                                                                    )}
                                                                </tr>
                                                            ))}
                                                        </React.Fragment>
                                                    );
                                                }
                                                
                                                // Regular single row for non-calculated attributes
                                                const uniqueDocs = hasEvidence 
                                                    ? [...new Set(item.evidence.map(e => e.file_name).filter(Boolean))]
                                                    : [];
                                                
                                                return (
                                                    <tr key={item.id} className="hover:bg-slate-50/50 transition-colors">
                                                        <td className="px-2 py-1.5 font-medium text-xs text-slate-500 border border-slate-200">
                                                            {item.attribute_id}
                                                        </td>
                                                        <td className="px-2 py-1.5 font-medium text-xs text-slate-700 border border-slate-200">
                                                            {item.attribute_label}
                                                        </td>
                                                        <td className="px-2 py-1.5 text-xs text-slate-600 border border-slate-200">
                                                            {item.extracted_value || '-'}
                                                        </td>
                                                        <td className="px-2 py-1.5 text-xs text-slate-600 border border-slate-200">
                                                            {hasEvidence ? item.attribute_label : '-'}
                                                        </td>
                                                        <td className="px-2 py-1.5 text-xs text-slate-600 border border-slate-200">
                                                            {hasEvidence ? (item.extracted_value || '-') : '-'}
                                                        </td>
                                                        <td className="px-2 py-1.5 border border-slate-200">
                                                            {uniqueDocs.length > 0 ? (
                                                                <div className="flex flex-wrap gap-1">
                                                                    {uniqueDocs.slice(0, 2).map((docName, idx) => (
                                                                        <button
                                                                            key={idx}
                                                                            onClick={async () => {
                                                                                try {
                                                                                    const token = localStorage.getItem('token');
                                                                                    const response = await fetch(`http://localhost:8006/api/admin/loans/${loanId}/evidence-documents-v2`, {
                                                                                        headers: {
                                                                                            'Authorization': `Bearer ${token}`
                                                                                        }
                                                                                    });
                                                                                    const result = await response.json();
                                                                                    const evidenceDocs = Array.isArray(result) ? result : (result.documents || []);
                                                                                    const fullDoc = evidenceDocs.find(d => d.file_name === docName);
                                                                                    
                                                                                    // Find step_id for this attribute from calculation_steps
                                                                                    let matchingStepId = null;
                                                                                    if (fullDoc?.usage) {
                                                                                        // Look for step matching this attribute
                                                                                        const match = fullDoc.usage.find(u => 
                                                                                            u.attributes && u.attributes.some(attr => 
                                                                                                attr.attribute_label.includes(item.attribute_label)
                                                                                            )
                                                                                        );
                                                                                        if (match) {
                                                                                            matchingStepId = match.step_id;
                                                                                        }
                                                                                    }
                                                                                    
                                                                                    setDocumentModal({
                                                                                        isOpen: true,
                                                                                        document: {
                                                                                            ...(fullDoc || { file_name: docName, usage: [] }),
                                                                                            filter_step_id: matchingStepId
                                                                                        }
                                                                                    });
                                                                                } catch (error) {
                                                                                    console.error('Error fetching document:', error);
                                                                                    setDocumentModal({
                                                                                        isOpen: true,
                                                                                        document: { file_name: docName, usage: [] }
                                                                                    });
                                                                                }
                                                                            }}
                                                                            className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200 rounded text-xs transition-colors"
                                                                            title={`Click to view ${docName}`}
                                                                        >
                                                                            <FileText size={12} />
                                                                            <span className="max-w-[120px] truncate">
                                                                                {docName.replace(/\.(pdf|json)$/i, '').replace(/_/g, ' ')}
                                                                            </span>
                                                                        </button>
                                                                    ))}
                                                                    {uniqueDocs.length > 2 && (
                                                                        <button
                                                                            onClick={() => setEvidenceModal({
                                                                                isOpen: true,
                                                                                evidence: item.evidence,
                                                                                attributeLabel: item.attribute_label,
                                                                                attributeValue: item.extracted_value,
                                                                                initialTab: 'secondary',
                                                                                attributeId: item.attribute_id,
                                                                                calculationSteps: calculationSteps[item.attribute_id] || []
                                                                            })}
                                                                            className="px-1.5 py-0.5 bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-300 rounded text-xs transition-colors"
                                                                        >
                                                                            +{uniqueDocs.length - 2} more
                                                                        </button>
                                                                    )}
                                                                </div>
                                                            ) : (
                                                                <span className="text-slate-400 text-xs">-</span>
                                                            )}
                                                        </td>
                                                        <td className="px-2 py-1.5 border border-slate-200 text-center">
                                                            {hasEvidence ? (
                                                                <button
                                                                    onClick={() => setEvidenceModal({
                                                                        isOpen: true,
                                                                        evidence: item.evidence,
                                                                        attributeLabel: item.attribute_label,
                                                                        attributeValue: item.extracted_value,
                                                                        attributeId: item.attribute_id,
                                                                        calculationSteps: calculationSteps[item.attribute_id] || []
                                                                    })}
                                                                    className={clsx(
                                                                        "inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border cursor-pointer hover:shadow-sm transition-all min-w-[80px] justify-center",
                                                                        item.evidence[0].verification_status === 'verified'
                                                                            ? "bg-green-50 text-green-700 border-green-200 hover:bg-green-100"
                                                                            : item.evidence[0].verification_status === 'needs_review'
                                                                            ? "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"
                                                                            : "bg-red-50 text-red-700 border-red-200 hover:bg-red-100"
                                                                    )}
                                                                >
                                                                    {item.evidence[0].verification_status === 'verified' ? (
                                                                        <CheckCircle2 size={12} className="text-green-600" />
                                                                    ) : item.evidence[0].verification_status === 'needs_review' ? (
                                                                        <AlertCircle size={12} className="text-amber-600" />
                                                                    ) : (
                                                                        <XCircle size={12} className="text-red-600" />
                                                                    )}
                                                                    <span>
                                                                        {item.evidence[0].verification_status === 'verified' 
                                                                            ? 'Verified' 
                                                                            : item.evidence[0].verification_status === 'needs_review'
                                                                            ? 'Needs Review'
                                                                            : 'Not Verified'}
                                                                    </span>
                                                                </button>
                                                            ) : (
                                                                <span className="text-slate-400 text-xs">-</span>
                                                            )}
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                        );
                    })}
                </div>
            </div >

            {/* Verification Modal */}
            <VerificationModal
                isOpen={evidenceModal.isOpen}
                onClose={() => setEvidenceModal({ ...evidenceModal, isOpen: false })}
                evidence={evidenceModal.evidence}
                attributeLabel={evidenceModal.attributeLabel}
                attributeValue={evidenceModal.attributeValue}
                loanId={loanId}
                calculationSteps={evidenceModal.calculationSteps || []}
                initialTab={evidenceModal.initialTab}
            />
            
            {/* Evidence Document Modal */}
            <EvidenceDocumentModal
                isOpen={documentModal.isOpen}
                onClose={() => setDocumentModal({ isOpen: false, document: null })}
                document={documentModal.document}
                loanId={loanId}
            />
        </div>
    );
};


export default LoanDetailPage;
