import React, { useState, useEffect } from 'react';
import { X, ZoomIn, CheckCircle2, FileText } from 'lucide-react';

const EvidenceModal = ({ isOpen, onClose, evidence, attributeLabel, attributeValue }) => {
    const [documentUrl, setDocumentUrl] = useState(null);
    const [zoomLevel, setZoomLevel] = useState(1);

    useEffect(() => {
        if (isOpen && evidence && evidence.file_path) {
            // Construct document URL using file path
            const docUrl = `http://localhost:8006/api/admin/loans/1/documents/${encodeURIComponent(evidence.file_name)}/content`;
            setDocumentUrl(docUrl);
        }
    }, [isOpen, evidence]);

    if (!isOpen || !evidence) return null;

    // Parse evidence notes to get narrative and details
    let evidenceDetails = {};
    try {
        if (evidence.notes) {
            evidenceDetails = typeof evidence.notes === 'string' 
                ? JSON.parse(evidence.notes) 
                : evidence.notes;
        }
    } catch (e) {
        console.error('Error parsing evidence notes:', e);
    }

    const narrative = evidenceDetails.notes || 
        `This document contains evidence that verifies the ${attributeLabel} value.`;
    
    const match = evidenceDetails.match;
    const documentValue = evidenceDetails.value_in_document;
    const calculation = evidenceDetails.calculation;
    const pageRef = evidenceDetails.page_reference;

    return (
        <div className="fixed inset-0 z-50 overflow-hidden">
            {/* Backdrop */}
            <div 
                className="absolute inset-0 bg-black/50 backdrop-blur-sm"
                onClick={onClose}
            />
            
            {/* Modal */}
            <div className="relative h-full flex items-center justify-center p-4">
                <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-7xl h-[90vh] flex flex-col">
                    {/* Header */}
                    <div className="flex items-center justify-between p-6 border-b border-slate-200">
                        <div className="flex items-center gap-3">
                            <div className="p-2 bg-green-100 rounded-lg">
                                <CheckCircle2 className="w-6 h-6 text-green-600" />
                            </div>
                            <div>
                                <h2 className="text-xl font-semibold text-slate-900">
                                    Evidence Document
                                </h2>
                                <p className="text-sm text-slate-500 mt-0.5">
                                    {evidence.file_name}
                                </p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
                        >
                            <X className="w-5 h-5 text-slate-400" />
                        </button>
                    </div>

                    {/* Narrative Section */}
                    <div className="px-6 py-4 bg-green-50 border-b border-green-100">
                        <div className="flex items-start gap-3">
                            <FileText className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                            <div className="flex-1">
                                <h3 className="text-sm font-semibold text-green-900 mb-1">
                                    Why This Document Verifies the Value
                                </h3>
                                <p className="text-sm text-green-800 leading-relaxed">
                                    {narrative}
                                </p>
                                
                                {/* Value Comparison */}
                                <div className="mt-3 grid grid-cols-2 gap-4">
                                    <div className="bg-white rounded-lg p-3 border border-green-200">
                                        <div className="text-xs font-medium text-slate-500 mb-1">
                                            1008 Form Value
                                        </div>
                                        <div className="text-sm font-semibold text-slate-900">
                                            {attributeValue}
                                        </div>
                                    </div>
                                    <div className="bg-white rounded-lg p-3 border border-green-200">
                                        <div className="text-xs font-medium text-slate-500 mb-1">
                                            Document Value
                                        </div>
                                        <div className="text-sm font-semibold text-slate-900 flex items-center gap-2">
                                            {documentValue || attributeValue}
                                            {match && (
                                                <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs rounded-full font-medium">
                                                    ✓ Match
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                </div>

                                {/* Calculation if present */}
                                {calculation && (
                                    <div className="mt-3 bg-white rounded-lg p-3 border border-green-200">
                                        <div className="text-xs font-medium text-slate-500 mb-1">
                                            Calculation
                                        </div>
                                        <div className="text-sm font-mono text-slate-700">
                                            {calculation}
                                        </div>
                                    </div>
                                )}

                                {/* Page Reference */}
                                {pageRef && (
                                    <div className="mt-2 text-xs text-green-700">
                                        📄 Found on: {pageRef}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Document Viewer Section */}
                    <div className="flex-1 flex overflow-hidden">
                        {/* Left: Full Document */}
                        <div className="flex-1 border-r border-slate-200 overflow-auto bg-slate-50">
                            <div className="p-4">
                                <div className="bg-white rounded-lg shadow-sm p-2">
                                    <div className="flex items-center justify-between mb-2 pb-2 border-b border-slate-200">
                                        <span className="text-sm font-medium text-slate-700">
                                            Full Document
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <button
                                                onClick={() => setZoomLevel(Math.max(0.5, zoomLevel - 0.25))}
                                                className="px-2 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded transition-colors"
                                            >
                                                -
                                            </button>
                                            <span className="text-xs text-slate-600 min-w-[50px] text-center">
                                                {Math.round(zoomLevel * 100)}%
                                            </span>
                                            <button
                                                onClick={() => setZoomLevel(Math.min(3, zoomLevel + 0.25))}
                                                className="px-2 py-1 text-xs bg-slate-100 hover:bg-slate-200 rounded transition-colors"
                                            >
                                                +
                                            </button>
                                        </div>
                                    </div>
                                    <div className="overflow-auto max-h-[600px]">
                                        {documentUrl ? (
                                            <iframe
                                                src={`${documentUrl}#page=${evidence.page_number || 1}`}
                                                className="w-full border-0"
                                                style={{ 
                                                    height: '600px',
                                                    transform: `scale(${zoomLevel})`,
                                                    transformOrigin: 'top left',
                                                    width: `${100 / zoomLevel}%`
                                                }}
                                                title="Evidence Document"
                                            />
                                        ) : (
                                            <div className="flex items-center justify-center h-96 text-slate-400">
                                                Loading document...
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Right: Zoomed Area */}
                        <div className="w-96 overflow-auto bg-slate-50">
                            <div className="p-4">
                                <div className="bg-white rounded-lg shadow-sm p-4">
                                    <div className="flex items-center gap-2 mb-3 pb-3 border-b border-slate-200">
                                        <ZoomIn className="w-4 h-4 text-primary-600" />
                                        <span className="text-sm font-medium text-slate-700">
                                            Value Location
                                        </span>
                                    </div>
                                    
                                    <div className="space-y-3">
                                        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                                            <div className="text-xs font-medium text-green-900 mb-1">
                                                Attribute
                                            </div>
                                            <div className="text-sm font-semibold text-green-800">
                                                {attributeLabel}
                                            </div>
                                        </div>

                                        <div className="bg-primary-50 border border-primary-200 rounded-lg p-3">
                                            <div className="text-xs font-medium text-primary-900 mb-1">
                                                Expected Value
                                            </div>
                                            <div className="text-sm font-semibold text-primary-800">
                                                {attributeValue}
                                            </div>
                                        </div>

                                        {evidence.page_number && (
                                            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                                                <div className="text-xs font-medium text-slate-700 mb-1">
                                                    Location
                                                </div>
                                                <div className="text-sm text-slate-600">
                                                    Page {evidence.page_number}
                                                </div>
                                            </div>
                                        )}

                                        {evidence.confidence_score && (
                                            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                                                <div className="text-xs font-medium text-slate-700 mb-1">
                                                    Confidence Score
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <div className="flex-1 bg-slate-200 rounded-full h-2">
                                                        <div 
                                                            className="bg-green-500 h-2 rounded-full transition-all"
                                                            style={{ width: `${evidence.confidence_score * 100}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-sm font-semibold text-slate-700">
                                                        {Math.round(evidence.confidence_score * 100)}%
                                                    </span>
                                                </div>
                                            </div>
                                        )}

                                        <div className="text-xs text-slate-500 italic mt-4">
                                            💡 The highlighted area in the document contains the value that matches the 1008 form.
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between p-4 border-t border-slate-200 bg-slate-50">
                        <div className="text-xs text-slate-500">
                            Verification Status: <span className="font-semibold text-green-600">
                                {evidence.verification_status || 'Verified'}
                            </span>
                        </div>
                        <button
                            onClick={onClose}
                            className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors text-sm font-medium"
                        >
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default EvidenceModal;

