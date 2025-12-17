import React, { useState, useEffect } from 'react';
import { FileText, Code, Link2, ChevronRight, X, ExternalLink } from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import { JSONTree } from 'react-json-tree';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const EvidenceDocumentModal = ({ isOpen, onClose, document, loanId }) => {
    const [activeTab, setActiveTab] = useState('usage');
    const [numPages, setNumPages] = useState(null);
    const [pageNumber, setPageNumber] = useState(1);
    const [scale, setScale] = useState(1.0);
    const [selectedUsage, setSelectedUsage] = useState(null);

    useEffect(() => {
        if (isOpen) {
            setActiveTab('usage'); // Always start with Usage tab
            setPageNumber(document?.initial_page || 1);
            setScale(1.0);
            setSelectedUsage(null);
            
            // Auto-select usage if filter_step_id is provided
            if (document?.filter_step_id && document?.usage) {
                const matchingUsage = document.usage.find(u => u.step_id === document.filter_step_id);
                if (matchingUsage) {
                    setSelectedUsage(matchingUsage);
                    if (matchingUsage.page_number) {
                        setPageNumber(matchingUsage.page_number);
                    }
                }
            }
            // Fallback: auto-select by highlight_value if no step_id match
            else if (document?.highlight_value && document?.usage) {
                const normalizeValue = (v) => (v || '').toString().replace(/[\$,\s]/g, '').replace(/\.00$/, '');
                const targetValue = normalizeValue(document.highlight_value);
                const matchingUsage = document.usage.find(u => normalizeValue(u.value) === targetValue);
                if (matchingUsage) {
                    setSelectedUsage(matchingUsage);
                    if (matchingUsage.page_number) {
                        setPageNumber(matchingUsage.page_number);
                    }
                }
            }
        }
    }, [isOpen, document?.file_name, document?.initial_page, document?.filter_step_id, document?.highlight_value]); // Reset when document changes too

    if (!isOpen || !document) return null;

    const docUrl = `http://localhost:8006/api/admin/loans/${loanId}/documents/${document.file_name}/content`;

    const onDocumentLoadSuccess = ({ numPages }) => {
        setNumPages(numPages);
    };

    const handleUsageClick = (usage) => {
        setSelectedUsage(usage);
        const targetPage = usage.page_number || 1;
        setPageNumber(targetPage);
        // Don't switch tabs - keep user on Usage tab with PDF on right
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-0">
            <div className="bg-white w-full h-full flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-slate-50">
                    <div className="flex items-center gap-3">
                        <FileText size={24} className="text-primary-600" />
                        <div>
                            <h2 className="text-lg font-semibold text-gray-900">
                                {document.file_name}
                            </h2>
                            <p className="text-sm text-gray-500 mt-0.5">
                                {document.doc_type || 'Evidence Document'}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => window.open(docUrl, '_blank', 'noopener,noreferrer')}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded border border-blue-200 transition-colors"
                        >
                            <ExternalLink size={16} />
                            Open in New Tab
                        </button>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-2">
                        <X size={24} />
                    </button>
                    </div>
                </div>

                {/* Tabs */}
                <div className="border-b border-gray-200 bg-white">
                    <nav className="flex px-6">
                        <button
                            onClick={() => setActiveTab('pdf')}
                            className={`flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm transition-colors ${
                                activeTab === 'pdf'
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                            }`}
                        >
                            <FileText size={16} />
                            Raw PDF
                        </button>
                        <button
                            onClick={() => setActiveTab('json')}
                            className={`flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm transition-colors ${
                                activeTab === 'json'
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                            }`}
                        >
                            <Code size={16} />
                            Extracted JSON
                        </button>
                        <button
                            onClick={() => setActiveTab('usage')}
                            className={`flex items-center gap-2 px-6 py-3 border-b-2 font-medium text-sm transition-colors ${
                                activeTab === 'usage'
                                    ? 'border-blue-600 text-blue-600'
                                    : 'border-transparent text-gray-500 hover:text-gray-700'
                            }`}
                        >
                            <Link2 size={16} />
                            Usage ({document.usage?.length || 0})
                        </button>
                    </nav>
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-hidden">
                    {activeTab === 'pdf' && (
                        <div className="flex h-full flex-col bg-gray-50">
                            {/* PDF Controls */}
                            <div className="flex items-center justify-between p-3 bg-gray-100 border-b border-gray-200">
                                <div className="flex items-center gap-3">
                                    <button
                                        onClick={() => setPageNumber(prev => Math.max(prev - 1, 1))}
                                        disabled={pageNumber <= 1}
                                        className="px-3 py-1.5 text-sm rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        Previous
                                    </button>
                                    <span className="text-sm text-gray-700">
                                        Page {pageNumber} of {numPages || '?'}
                                    </span>
                                    <button
                                        onClick={() => setPageNumber(prev => Math.min(prev + 1, numPages))}
                                        disabled={pageNumber >= numPages}
                                        className="px-3 py-1.5 text-sm rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        Next
                                    </button>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => setScale(s => Math.max(s - 0.1, 0.5))}
                                        className="px-3 py-1.5 text-sm rounded hover:bg-gray-200"
                                    >
                                        Zoom Out
                                    </button>
                                    <span className="text-sm text-gray-700 min-w-[60px] text-center">
                                        {Math.round(scale * 100)}%
                                    </span>
                                    <button
                                        onClick={() => setScale(s => Math.min(s + 0.1, 2.0))}
                                        className="px-3 py-1.5 text-sm rounded hover:bg-gray-200"
                                    >
                                        Zoom In
                                    </button>
                                </div>
                            </div>

                            {/* PDF Viewer */}
                            <div className="flex-1 overflow-auto flex items-center justify-center p-4">
                                <Document
                                    file={docUrl}
                                    onLoadSuccess={onDocumentLoadSuccess}
                                    loading={<div className="text-gray-500">Loading PDF...</div>}
                                >
                                    <Page
                                        pageNumber={pageNumber}
                                        scale={scale}
                                        renderTextLayer={true}
                                        renderAnnotationLayer={true}
                                    />
                                </Document>
                            </div>
                        </div>
                    )}

                    {activeTab === 'json' && (
                        <div className="h-full overflow-auto p-6 bg-slate-900">
                            <div className="bg-slate-800 rounded-lg border border-slate-700 p-6">
                                <h3 className="text-sm font-semibold text-white mb-3">Extracted Data</h3>
                                <div className="bg-slate-900 p-4 rounded overflow-auto">
                                    <JSONTree 
                                        data={document.analysis || {}}
                                        theme={{
                                            scheme: 'monokai',
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
                            </div>
                        </div>
                    )}

                    {activeTab === 'usage' && (
                        <div className="flex h-full">
                            {/* Usage List - Left Side */}
                            <div className="w-1/4 border-r border-gray-200 bg-white overflow-y-auto">
                                <div className="p-4">
                                    <h3 className="text-sm font-semibold text-gray-900 mb-3">
                                        Values Used From This Document
                                        {document.filter_step_id && (
                                            <span className="ml-2 text-xs font-normal text-blue-600">
                                                (Filtered)
                                            </span>
                                        )}
                                    </h3>
                                    {document.usage && document.usage.length > 0 ? (
                                        <div className="space-y-3">
                                            {document.usage
                                                .filter(usage => {
                                                    // If filter_step_id is set, only show that step (robust ID-based filtering)
                                                    if (document.filter_step_id) {
                                                        return usage.step_id === document.filter_step_id;
                                                    }
                                                    // Fallback: filter by highlight_value
                                                    if (document.highlight_value) {
                                                        const normalizeValue = (val) => {
                                                            if (!val) return '';
                                                            return val.toString()
                                                                .replace(/[\$,\s]/g, '')
                                                                .replace(/\.00$/, '')
                                                                .toLowerCase();
                                                        };
                                                        return normalizeValue(usage.value) === normalizeValue(document.highlight_value);
                                                    }
                                                    return true; // Show all if no filter
                                                })
                                                .map((usage, idx) => (
                                                <button
                                                    key={idx}
                                                    onClick={() => handleUsageClick(usage)}
                                                    className={`w-full text-left p-3 rounded-lg border transition-colors ${
                                                        selectedUsage === usage
                                                            ? 'bg-blue-50 border-blue-300'
                                                            : 'bg-white border-gray-200 hover:bg-gray-50'
                                                    }`}
                                                >
                                                    {/* Value */}
                                                    <div className="flex items-baseline gap-2 mb-2">
                                                        <span className="text-base font-bold text-blue-600">
                                                            {usage.value}
                                                        </span>
                                                        {usage.page_number && (
                                                            <span className="text-xs text-gray-500">
                                                                📄 Page {usage.page_number}
                                                            </span>
                                                        )}
                                                    </div>
                                                    
                                                    {/* Description/Reason */}
                                                    {usage.description && (
                                                        <p className="text-xs text-gray-700 mb-2 leading-relaxed">
                                                            <strong>Why:</strong> {usage.description}
                                                        </p>
                                                    )}
                                                    
                                                    {/* Attributes using this value */}
                                                    {usage.attributes && usage.attributes.length > 0 && (
                                                        <div className="mt-2 pt-2 border-t border-gray-100">
                                                            <p className="text-xs font-medium text-gray-500 mb-1">
                                                                Used in:
                                                            </p>
                                                            <div className="space-y-0.5">
                                                                {usage.attributes.map((attr, attrIdx) => (
                                                                    <div key={attrIdx} className="text-xs text-gray-600">
                                                                        • {attr.attribute_label}
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                </button>
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="text-center py-8 text-gray-500 text-sm">
                                            No values are being used from this document yet
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* PDF Viewer - Right Side */}
                            <div className="flex-1 flex flex-col bg-gray-50">
                                {/* Controls */}
                                <div className="flex items-center justify-between p-3 bg-gray-100 border-b border-gray-200">
                                    <div className="flex items-center gap-3">
                                        <button
                                            onClick={() => setPageNumber(prev => Math.max(prev - 1, 1))}
                                            disabled={pageNumber <= 1}
                                            className="px-3 py-1.5 text-sm rounded hover:bg-gray-200 disabled:opacity-50"
                                        >
                                            Previous
                                        </button>
                                        <span className="text-sm text-gray-700">
                                            Page {pageNumber} of {numPages || '?'}
                                        </span>
                                        <button
                                            onClick={() => setPageNumber(prev => Math.min(prev + 1, numPages))}
                                            disabled={pageNumber >= numPages}
                                            className="px-3 py-1.5 text-sm rounded hover:bg-gray-200 disabled:opacity-50"
                                        >
                                            Next
                                        </button>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => setScale(s => Math.max(s - 0.1, 0.5))}
                                            className="px-3 py-1.5 text-sm rounded hover:bg-gray-200"
                                        >
                                            -
                                        </button>
                                        <span className="text-sm text-gray-700 min-w-[60px] text-center">
                                            {Math.round(scale * 100)}%
                                        </span>
                                        <button
                                            onClick={() => setScale(s => Math.min(s + 0.1, 2.0))}
                                            className="px-3 py-1.5 text-sm rounded hover:bg-gray-200"
                                        >
                                            +
                                        </button>
                                    </div>
                                </div>

                                {/* PDF */}
                                <div className="flex-1 overflow-auto flex items-center justify-center p-4">
                                    <Document
                                        file={docUrl}
                                        onLoadSuccess={onDocumentLoadSuccess}
                                        loading={<div className="text-gray-500">Loading PDF...</div>}
                                    >
                                        <Page
                                            pageNumber={pageNumber}
                                            scale={scale}
                                            renderTextLayer={true}
                                            renderAnnotationLayer={true}
                                        />
                                    </Document>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default EvidenceDocumentModal;

