import React, { useState, useEffect } from 'react';
import { X, CheckCircle2, XCircle, FileText, ChevronRight, Calculator, ZoomIn, ZoomOut, ChevronLeft, ExternalLink } from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import clsx from 'clsx';
import VerificationSummaryRenderer from './VerificationSummaryRenderer';

// Configure PDF.js worker using jsDelivr CDN (better CORS support)
pdfjs.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const VerificationModal = ({ isOpen, onClose, evidence, attributeLabel, attributeValue, loanId, initialTab = 'summary', calculationSteps = [] }) => {
    const [activeTab, setActiveTab] = useState(initialTab);
    const [numPages, setNumPages] = useState(null);
    const [pageNumber, setPageNumber] = useState(1);
    const [scale, setScale] = useState(1.0);
    const [selectedDocument, setSelectedDocument] = useState(null);
    const [selectedLineValue, setSelectedLineValue] = useState(attributeValue);

    // Get source information from evidence
    const getSourceInfo = () => {
        if (!evidence || evidence.length === 0) return null;
        
        // Check if we have source_document and source_type in evidence
        const firstEvidence = evidence[0];
        if (firstEvidence.source_document && firstEvidence.source_type) {
            return {
                document: firstEvidence.source_document,
                type: firstEvidence.source_type
            };
        }
        
        // Fallback: check in notes
        try {
            const notes = typeof firstEvidence.notes === 'string' 
                ? JSON.parse(firstEvidence.notes) 
                : firstEvidence.notes;
            if (notes?.source_document && notes?.source_type) {
                return {
                    document: notes.source_document,
                    type: notes.source_type
                };
            }
        } catch {}
        
        return null;
    };
    
    const sourceInfo = getSourceInfo();

    // Combine all evidence documents (no primary/secondary distinction)
    const allDocuments = evidence || [];
    
    // Get verification summary from the first document with classification
    const verificationSummary = (() => {
        // Try to find a document with an explicit summary first
        for (const ev of evidence || []) {
            try {
                const notes = typeof ev.notes === 'string' ? JSON.parse(ev.notes) : ev.notes;
                if (notes?.verification_summary) {
                    return notes.verification_summary;
                }
            } catch {}
        }
        
        // Fallback: Construct summary from available metadata
        if (evidence && evidence.length > 0) {
            let firstNotes = {};
            try {
                const ev = evidence[0];
                firstNotes = typeof ev.notes === 'string' ? JSON.parse(ev.notes) : ev.notes;
            } catch {}
            
            if (firstNotes?.methodology) return `UNDERWRITING METHODOLOGY\n\nMethodology: ${firstNotes.methodology}`;
            if (firstNotes?.mismatch_reason) return `VERIFICATION STATUS\n\n❌ ${firstNotes.mismatch_reason}`;
            
            // If verified but no summary
            const status = evidence[0].verification_status;
            if (status === 'verified') {
                return `VERIFICATION STATUS\n\n✓ Verified against ${evidence[0].file_name || 'documents'}${evidence[0].page_number ? ` (Page ${evidence[0].page_number})` : ''}.`;
            }
        }
        
        return null;
    })();
    
    // Handler for clicking document badges
    const handleDocumentClick = (documentName, pageNumber, lineValue) => {
        // Find the document in evidence, or create a minimal doc object for documents referenced in calculation steps
        let doc = allDocuments.find(ev => ev.file_name === documentName);
        
        if (!doc && documentName) {
            // Document not in evidence list but referenced in calculation steps - create minimal object
            doc = {
                file_name: documentName,
                page_number: parseInt(pageNumber) || 1,
                notes: JSON.stringify({ document_type: 'Supporting Document' })
            };
        }
        
        if (doc) {
            setSelectedDocument(doc);
            setPageNumber(parseInt(pageNumber) || 1);
            setSelectedLineValue(lineValue || attributeValue);
            setActiveTab('documents');
        }
    };

    useEffect(() => {
        if (isOpen) {
            setActiveTab(initialTab);
            setScale(1.0);
            setPageNumber(1);
        }
    }, [isOpen, initialTab]);

    if (!isOpen) return null;
    
    // Allow rendering if we have evidence OR calculation steps
    if ((!evidence || evidence.length === 0) && (!calculationSteps || calculationSteps.length === 0)) {
        return null;
    }

    const tabs = [
        { id: 'summary', label: 'Summary', count: null },
        { id: 'documents', label: 'Documents', count: allDocuments.length }
    ];

    const getVerificationStatus = () => {
        if (!evidence || evidence.length === 0) return 'not_verified';
        return evidence[0]?.verification_status || 'not_verified';
    };

    const status = getVerificationStatus();

    const getDocUrl = (filename) => {
        return `http://localhost:8006/api/admin/loans/${loanId}/documents/${encodeURIComponent(filename)}/content`;
    };
    
    const isCalculatedEvidence = (filename) => {
        // Check if this is a calculated field (not a real document)
        return filename && (
            filename.startsWith('calculated_') ||
            filename.endsWith('.json') && !filename.includes('_')
        );
    };

    const parseNotes = (ev) => {
        try {
            if (!ev || !ev.notes) return {};
            return typeof ev.notes === 'string' ? JSON.parse(ev.notes) : (ev.notes || {});
        } catch {
            return {};
        }
    };

    const onDocumentLoadSuccess = ({ numPages }) => {
        setNumPages(numPages);
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-60 z-50 flex items-center justify-center p-0">
            <div className="bg-white w-full h-full flex flex-col">
                {/* Header */}
                <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between bg-slate-50">
                    <div className="flex items-center gap-3">
                        {status === 'verified' ? (
                            <CheckCircle2 size={20} className="text-green-600" />
                        ) : (
                            <XCircle size={20} className="text-red-600" />
                        )}
                        <div>
                            <h2 className="text-base font-semibold text-gray-900">
                                Verification: {attributeLabel}
                            </h2>
                            <p className="text-xs text-gray-500 mt-0.5">
                                Value: <span className="font-medium text-gray-700">{attributeValue}</span>
                            </p>
                            {sourceInfo && (
                                <p className="text-xs mt-1 flex items-center gap-1.5">
                                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                        sourceInfo.type === '1008' 
                                            ? 'bg-green-100 text-green-800 border border-green-200'
                                            : sourceInfo.type === 'URLA'
                                            ? 'bg-amber-100 text-amber-800 border border-amber-200'
                                            : 'bg-gray-100 text-gray-700 border border-gray-200'
                                    }`}>
                                        {sourceInfo.type === '1008' ? '📋 1008' : sourceInfo.type === 'URLA' ? '⚠️ URLA' : '📄 Source'}
                                    </span>
                                    <span className="text-gray-600">{sourceInfo.document}</span>
                                </p>
                            )}
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <span className={clsx(
                            "px-2.5 py-1 rounded-md text-xs font-semibold",
                            status === 'verified' 
                                ? "bg-green-100 text-green-800 border border-green-200"
                                : "bg-red-100 text-red-800 border border-red-200"
                        )}>
                            {status === 'verified' ? 'Verified' : 'Not Verified'}
                        </span>
                        <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Tabs */}
                <div className="border-b border-gray-200 bg-white">
                    <nav className="flex px-4">
                        {tabs.map((tab) => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={clsx(
                                    "flex items-center gap-2 px-4 py-2.5 border-b-2 font-medium text-xs transition-colors",
                                    activeTab === tab.id
                                        ? "border-blue-600 text-blue-600"
                                        : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                                )}
                            >
                                <span>{tab.label}</span>
                                {tab.count !== null && (
                                    <span className={clsx(
                                        "px-1.5 py-0.5 rounded-full text-xs font-medium",
                                        activeTab === tab.id 
                                            ? "bg-blue-100 text-blue-600" 
                                            : "bg-gray-100 text-gray-600"
                                    )}>
                                        {tab.count}
                                    </span>
                                )}
                            </button>
                        ))}
                    </nav>
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-y-auto">
                    {activeTab === 'summary' && (
                        <SummaryTab
                            attributeLabel={attributeLabel}
                            attributeValue={attributeValue}
                            verificationSummary={verificationSummary}
                            allDocuments={allDocuments}
                            status={status}
                            parseNotes={parseNotes}
                            setActiveTab={setActiveTab}
                            setPageNumber={setPageNumber}
                            setSelectedDocument={setSelectedDocument}
                            sourceInfo={sourceInfo}
                            calculationSteps={calculationSteps}
                            loanId={loanId}
                            handleDocumentClick={handleDocumentClick}
                        />
                    )}

                    {activeTab === 'documents' && (
                        <DocumentsTab
                            allDocuments={allDocuments}
                            parseNotes={parseNotes}
                            getDocUrl={getDocUrl}
                            selectedDocument={selectedDocument}
                            setSelectedDocument={setSelectedDocument}
                            pageNumber={pageNumber}
                            setPageNumber={setPageNumber}
                            attributeLabel={attributeLabel}
                            attributeValue={selectedLineValue}
                        />
                    )}
                </div>
            </div>
        </div>
    );
};

// Summary Tab Component
const SummaryTab = ({ attributeLabel, attributeValue, verificationSummary, allDocuments, status, parseNotes, setActiveTab, setPageNumber, setSelectedDocument, sourceInfo, calculationSteps = [], loanId, handleDocumentClick }) => {
    // Get notes from the first document for legacy step-by-step calculation
    const firstDocNotes = allDocuments && allDocuments.length > 0 ? parseNotes(allDocuments[0]) : null;
    
    // Use calculation steps from the new table if available, otherwise fall back to notes
    const hasCalculationSteps = calculationSteps && calculationSteps.length > 0;
    const hasLegacySteps = firstDocNotes?.step_by_step_calculation && firstDocNotes.step_by_step_calculation.length > 0;

    return (
        <div className="p-6 space-y-6">
            {/* Source Attribution Banner */}
            {sourceInfo && (
                <div className={`border rounded-lg p-4 ${
                    sourceInfo.type === '1008'
                        ? 'bg-green-50 border-green-300'
                        : sourceInfo.type === 'URLA'
                        ? 'bg-amber-50 border-amber-300'
                        : 'bg-gray-50 border-gray-300'
                }`}>
                    <div className="flex items-start gap-3">
                        <div className="text-2xl mt-0.5">
                            {sourceInfo.type === '1008' ? '📋' : sourceInfo.type === 'URLA' ? '⚠️' : '📄'}
                        </div>
                        <div className="flex-1">
                            <h3 className={`text-sm font-semibold mb-1 ${
                                sourceInfo.type === '1008'
                                    ? 'text-green-900'
                                    : sourceInfo.type === 'URLA'
                                    ? 'text-amber-900'
                                    : 'text-gray-900'
                            }`}>
                                {sourceInfo.type === '1008' 
                                    ? 'Attributed to 1008 Transmittal Form'
                                    : sourceInfo.type === 'URLA'
                                    ? 'Attributed to URLA (Fallback Source)'
                                    : 'Attributed to Supporting Documents'
                                }
                            </h3>
                            <p className={`text-xs leading-relaxed ${
                                sourceInfo.type === '1008'
                                    ? 'text-green-800'
                                    : sourceInfo.type === 'URLA'
                                    ? 'text-amber-800'
                                    : 'text-gray-700'
                            }`}>
                                {sourceInfo.type === '1008' 
                                    ? 'This attribute value is sourced from the 1008 Transmittal Form, which is the preferred authoritative document for loan attributes.'
                                    : sourceInfo.type === 'URLA'
                                    ? 'This attribute is sourced from URLA as a fallback. Note: 1008 Transmittal Form is the preferred source but was not available.'
                                    : 'This attribute is sourced from supporting loan documents.'
                                }
                            </p>
                            <p className="text-xs font-medium mt-2 opacity-75">
                                Source: {sourceInfo.document}
                            </p>
                        </div>
                    </div>
                </div>
            )}
            
            {/* Verification Summary */}
            <VerificationSummaryRenderer 
                summary={verificationSummary} 
                onDocumentClick={handleDocumentClick}
                attributeLabel={attributeLabel}
            />

            {/* Calculation Steps from Database Table */}
            {hasCalculationSteps && (
                <div className="bg-white border border-blue-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                        📊 Step-by-Step Calculation
                    </h3>
                    <div className="space-y-3">
                        {calculationSteps.map((step, idx) => {
                            const hasDocument = step.document_name;
                            const hasPage = step.page_number;
                            
                            return (
                                <div 
                                    key={step.step_id || idx} 
                                    className="border-l-2 border-blue-300 pl-3 py-1"
                                >
                                    <div className="flex items-start gap-2">
                                        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">
                                            {step.step_order}
                                        </span>
                                        <div className="flex-1">
                                            <p className="font-medium text-gray-800 text-xs">{step.description}</p>
                                            <p className="text-blue-600 font-mono font-semibold mt-1 text-sm">{step.value}</p>
                                            {step.formula && (
                                                <p className="text-gray-500 text-xs mt-0.5 font-mono bg-gray-50 px-2 py-1 rounded">{step.formula}</p>
                                            )}
                                            {hasDocument && (
                                                <button
                                                    onClick={() => {
                                                        if (handleDocumentClick) {
                                                            handleDocumentClick(step.document_name, step.page_number || 1, step.value);
                                                        }
                                                    }}
                                                    className="text-xs mt-1 flex items-center gap-1 px-2 py-1 bg-blue-50 border border-blue-200 rounded-md text-blue-700 hover:bg-blue-100 hover:border-blue-300 transition-colors"
                                                >
                                                    📄 {step.document_name} {hasPage && `(Page ${step.page_number})`}
                                                    <ChevronRight size={12} />
                                                </button>
                                            )}
                                            {step.rationale && (
                                                <p className="text-gray-600 text-xs mt-1 italic leading-relaxed">{step.rationale}</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    
                    {/* Final Result */}
                    <div className="mt-4 pt-3 border-t-2 border-blue-300">
                        {(() => {
                            // Get the last step's value as the calculated result
                            const lastStep = calculationSteps[calculationSteps.length - 1];
                            const calculatedResult = lastStep?.value || '';
                            
                            // Parse the calculated value
                            const match = calculatedResult.match(/\$?([\d,]+\.?\d*)/);
                            const calculatedValue = match ? parseFloat(match[1].replace(/,/g, '')) : 0;
                            
                            // Use attributeValue if available, otherwise use the calculated value as the expected
                            // This handles cases where the field is calculated (like income) and not extracted from 1008
                            const hasExpectedValue = attributeValue && attributeValue !== 'null' && attributeValue !== '';
                            const expectedValue = hasExpectedValue 
                                ? parseFloat(attributeValue.replace(/[$,]/g, '')) 
                                : calculatedValue;
                            
                            const variance = Math.abs(calculatedValue - expectedValue);
                            const variancePercent = expectedValue !== 0 ? (variance / expectedValue * 100) : 0;
                            
                            return (
                                <>
                                    <div className="flex justify-between items-center bg-blue-50 p-2 rounded">
                                        <span className="font-semibold text-gray-800 text-xs">Calculated Result:</span>
                                        <span className="font-mono font-bold text-blue-700 text-sm">{calculatedResult}</span>
                                    </div>
                                    {hasExpectedValue && (
                                        <div className="flex justify-between items-center mt-1 text-xs bg-gray-50 p-2 rounded">
                                            <span className="text-gray-600">Expected (1008):</span>
                                            <span className="font-mono text-gray-700">{attributeValue}</span>
                                        </div>
                                    )}
                                    <div className="flex justify-between items-center mt-1 text-xs bg-green-50 p-2 rounded">
                                        <span className="text-gray-600">{hasExpectedValue ? 'Variance:' : 'Status:'}</span>
                                        <span className={`font-mono font-semibold ${variance < 1 ? 'text-green-600' : variance < 10 ? 'text-amber-600' : 'text-red-600'}`}>
                                            {hasExpectedValue 
                                                ? `$${variance.toFixed(2)} (${variancePercent.toFixed(4)}%) ${variance < 1 ? '✓ MATCH' : variance < 10 ? '⚠ MINOR' : '✗ MISMATCH'}`
                                                : '✓ VERIFIED'
                                            }
                                        </span>
                                    </div>
                                </>
                            );
                        })()}
                    </div>
                </div>
            )}

            {/* Step-by-Step Calculation (Legacy - from notes) */}
            {!hasCalculationSteps && hasLegacySteps && (
                <div className="bg-white border border-blue-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                        📊 Step-by-Step Calculation
                    </h3>
                    <div className="space-y-3">
                        {firstDocNotes.step_by_step_calculation.map((step, idx) => {
                            // Find matching document if step has document and page
                            const matchingDoc = step.document && step.page 
                                ? allDocuments.find(ev => ev.file_name === step.document && ev.page_number === step.page)
                                : null;
                            
                            const isClickable = !!matchingDoc;
                            
                            return (
                                <div 
                                    key={idx} 
                                    className={clsx(
                                        "border-l-2 border-blue-300 pl-3 py-1",
                                        isClickable && "cursor-pointer hover:bg-blue-50 transition-colors rounded-r"
                                    )}
                                    onClick={() => {
                                        if (matchingDoc) {
                                            // Switch to documents tab and select this document
                                            setSelectedDocument(matchingDoc);
                                            setPageNumber(step.page || 1);
                                            setActiveTab('documents');
                                        }
                                    }}
                                >
                                    <div className="flex items-start gap-2">
                                        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold">
                                            {step.step}
                                        </span>
                                        <div className="flex-1">
                                            <p className="font-medium text-gray-800 text-xs">{step.description}</p>
                                            <p className="text-blue-600 font-mono font-semibold mt-1 text-sm">{step.amount}</p>
                                            {step.formula && (
                                                <p className="text-gray-500 text-xs mt-0.5 font-mono bg-gray-50 px-2 py-1 rounded">{step.formula}</p>
                                            )}
                                            {step.document && step.page && (
                                                <button
                                                    className={clsx(
                                                        "text-xs mt-1 flex items-center gap-1",
                                                        isClickable 
                                                            ? "text-blue-600 hover:text-blue-800 hover:underline" 
                                                            : "text-gray-500"
                                                    )}
                                                    onClick={(e) => {
                                                        if (matchingDoc) {
                                                            e.stopPropagation();
                                                            setSelectedDocument(matchingDoc);
                                                            setPageNumber(step.page || 1);
                                                            setActiveTab('documents');
                                                        }
                                                    }}
                                                >
                                                    📄 {step.document} (Page {step.page})
                                                    {isClickable && <ChevronRight size={12} />}
                                                </button>
                                            )}
                                            {step.source && !step.document && (
                                                <p className="text-gray-500 text-xs mt-1">📄 {step.source}</p>
                                            )}
                                            {step.explanation && (
                                                <p className="text-gray-600 text-xs mt-1 italic leading-relaxed">{step.explanation}</p>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    
                    {/* Final Result */}
                    <div className="mt-4 pt-3 border-t-2 border-blue-300">
                        {(() => {
                            // Smart calculation of final result
                            let calculatedResult = '';
                            let calculatedValue = 0;
                            
                            if (firstDocNotes.total_calculated) {
                                // Use the total_calculated field if provided
                                calculatedResult = firstDocNotes.total_calculated;
                                const match = calculatedResult.match(/\$?([\d,]+\.?\d*)/);
                                calculatedValue = match ? parseFloat(match[1].replace(/,/g, '')) : 0;
                            } else if (firstDocNotes.step_by_step_calculation && firstDocNotes.step_by_step_calculation.length > 0) {
                                const lastStep = firstDocNotes.step_by_step_calculation[firstDocNotes.step_by_step_calculation.length - 1];
                                const lastStepAmount = lastStep?.amount || '';
                                
                                // Check if last step contains a formula (like "$3,215.12 + 12 = $267.93")
                                if (lastStepAmount.includes('=')) {
                                    // Extract the result after the equals sign
                                    const parts = lastStepAmount.split('=');
                                    const resultPart = parts[parts.length - 1].trim();
                                    const match = resultPart.match(/\$?([\d,]+\.?\d*)/);
                                    if (match) {
                                        calculatedValue = parseFloat(match[1].replace(/,/g, ''));
                                        calculatedResult = `$${calculatedValue.toFixed(2)}`;
                                    }
                                } else if (lastStepAmount.includes('Excluded') || lastStepAmount.includes('Closed') || lastStepAmount === '$0.00') {
                                    // If last step is an exclusion, sum all non-excluded positive amounts
                                    let total = 0;
                                    firstDocNotes.step_by_step_calculation.forEach(step => {
                                        const amountStr = step.amount || '';
                                        if (amountStr.includes('Excluded') || amountStr.includes('Closed')) return;
                                        
                                        const match = amountStr.match(/\$?([\d,]+\.?\d*)/);
                                        if (match) {
                                            const value = parseFloat(match[1].replace(/,/g, ''));
                                            if (value > 0) total += value;
                                        }
                                    });
                                    calculatedValue = total;
                                    calculatedResult = `$${total.toFixed(2)}`;
                                } else {
                                    // Use the last step's amount directly
                                    const match = lastStepAmount.match(/\$?([\d,]+\.?\d*)/);
                                    if (match) {
                                        calculatedValue = parseFloat(match[1].replace(/,/g, ''));
                                        calculatedResult = lastStepAmount;
                                    }
                                }
                            }
                            
                            const expectedValue = parseFloat(attributeValue?.replace(/[$,]/g, '') || 0);
                            const variance = Math.abs(calculatedValue - expectedValue);
                            const variancePercent = expectedValue !== 0 ? (variance / expectedValue * 100) : 0;
                            
                            return (
                                <>
                                    <div className="flex justify-between items-center bg-blue-50 p-2 rounded">
                                        <span className="font-semibold text-gray-800 text-xs">Calculated Result:</span>
                                        <span className="font-mono font-bold text-blue-700 text-sm">{calculatedResult}</span>
                                    </div>
                                    <div className="flex justify-between items-center mt-1 text-xs bg-gray-50 p-2 rounded">
                                        <span className="text-gray-600">Expected (1008):</span>
                                        <span className="font-mono text-gray-700">{attributeValue}</span>
                                    </div>
                                    <div className="flex justify-between items-center mt-1 text-xs bg-green-50 p-2 rounded">
                                        <span className="text-gray-600">Variance:</span>
                                        <span className={`font-mono font-semibold ${variance < 1 ? 'text-green-600' : variance < 10 ? 'text-amber-600' : 'text-red-600'}`}>
                                            ${variance.toFixed(2)} ({variancePercent.toFixed(4)}%) {variance < 1 ? '✓ MATCH' : variance < 10 ? '⚠ MINOR' : '✗ MISMATCH'}
                                        </span>
                                    </div>
                                </>
                            );
                        })()}
                    </div>
                </div>
            )}

            {/* Business Return Average Explanation */}
            {firstDocNotes?.business_return_average_explanation && (
                <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-2">
                        💡 "Business Return Average" Explained
                    </h3>
                    <div className="space-y-2 text-xs">
                        <p className="text-gray-700">
                            <span className="font-medium">Term:</span> <span className="font-mono bg-amber-100 px-1 py-0.5 rounded">{firstDocNotes.business_return_average_explanation.term}</span>
                        </p>
                        <p className="text-gray-700">
                            <span className="font-medium">Meaning:</span> {firstDocNotes.business_return_average_explanation.meaning}
                        </p>
                        <p className="text-gray-700">
                            <span className="font-medium">Methodology:</span> {firstDocNotes.business_return_average_explanation.methodology}
                        </p>
                        <p className="text-gray-600 italic leading-relaxed">
                            {firstDocNotes.business_return_average_explanation.rationale}
                        </p>
                    </div>
                </div>
            )}

            {/* Key Findings */}
            {firstDocNotes?.key_findings && firstDocNotes.key_findings.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-2">
                        🔑 Key Findings
                    </h3>
                    <ul className="list-disc pl-4 text-xs text-gray-700 space-y-1 leading-relaxed">
                        {firstDocNotes.key_findings.map((finding, idx) => (
                            <li key={idx}>{finding}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Verification Status */}
            <div className="bg-white border border-gray-200 rounded-lg p-4">
                <h3 className="text-sm font-semibold text-gray-900 mb-3">Verification Status</h3>
                <div className="flex items-center gap-3">
                    {status === 'verified' ? (
                        <>
                            <CheckCircle2 size={24} className="text-green-600" />
                            <div>
                                <p className="text-sm font-medium text-green-900">Verified</p>
                                <p className="text-xs text-green-700">Value confirmed in supporting documents</p>
                            </div>
                        </>
                    ) : (
                        <>
                            <XCircle size={24} className="text-red-600" />
                            <div>
                                <p className="text-sm font-medium text-red-900">Not Verified</p>
                                <p className="text-xs text-red-700">Could not confirm value in documents</p>
                            </div>
                        </>
                    )}
                </div>
            </div>

            {/* Supporting Documents Summary */}
            {allDocuments && allDocuments.length > 0 && (
                <div className="bg-white border border-gray-200 rounded-lg p-4">
                    <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
                        <ChevronRight size={16} className="text-blue-600" />
                        Supporting Documents ({allDocuments.length})
                    </h3>
                    <div className="space-y-3">
                        {allDocuments.map((ev, idx) => {
                            const notes = parseNotes(ev) || {};
                            return (
                                <div key={idx} className="pl-3 border-l-2 border-gray-200">
                                    <p className="text-sm font-medium text-gray-900">{ev?.file_name || 'Document'}</p>
                                    <p className="text-xs text-gray-500 mt-0.5">{notes?.document_type || 'Document'}</p>
                                    {notes?.document_purpose && (
                                        <p className="text-xs text-gray-600 mt-1">{notes.document_purpose}</p>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}
        </div>
    );
};

// Document Tab Component (for viewing primary document)
const DocumentTab = ({ evidence, parseNotes, getDocUrl, isPrimary, initialPageNumber, onPageChange, attributeLabel, attributeValue }) => {
    const [numPages, setNumPages] = useState(null);
    const [pageNumber, setPageNumber] = useState(initialPageNumber || 1);
    const [containerWidth, setContainerWidth] = useState(null);
    const containerRef = React.useRef(null);

    const notes = parseNotes(evidence) || {};
    const docUrl = getDocUrl(evidence?.file_name);
    
    // Check if this is a calculated field (not a real PDF)
    const isCalculated = evidence.file_path === 'calculated' || 
                        evidence.file_name?.startsWith('calculated_') ||
                        (evidence.file_name?.endsWith('.json') && evidence.file_path === 'calculated');

    const onDocumentLoadSuccess = ({ numPages }) => {
        setNumPages(numPages);
        
        // Validate and adjust page number if needed
        const requestedPage = initialPageNumber || evidence.page_number || 1;
        if (requestedPage > numPages) {
            // If requested page exceeds document pages, reset to page 1
            setPageNumber(1);
        } else if (requestedPage < 1) {
            setPageNumber(1);
        } else {
            setPageNumber(requestedPage);
        }
    };
    
    // Update page number when initialPageNumber changes
    useEffect(() => {
        if (initialPageNumber && initialPageNumber !== pageNumber) {
            setPageNumber(initialPageNumber);
        }
    }, [initialPageNumber]);
    
    // Only set page after document is loaded and numPages is known
    useEffect(() => {
        if (numPages) {
            const requestedPage = initialPageNumber || evidence.page_number || 1;
            if (requestedPage <= numPages && requestedPage >= 1) {
                setPageNumber(requestedPage);
            }
        }
    }, [initialPageNumber, evidence.page_number, numPages]);
    
    // Notify parent of page changes if callback provided
    useEffect(() => {
        if (onPageChange) {
            onPageChange(pageNumber);
        }
    }, [pageNumber, onPageChange]);
    
    // Measure container width for fit-to-width rendering
    useEffect(() => {
        const updateWidth = () => {
            if (containerRef.current) {
                // Subtract padding (32px total) to get actual available width
                setContainerWidth(containerRef.current.offsetWidth - 32);
            }
        };
        
        updateWidth();
        window.addEventListener('resize', updateWidth);
        return () => window.removeEventListener('resize', updateWidth);
    }, []);
    
    // If this is a calculated field, show calculation breakdown instead of PDF
    if (isCalculated) {
        return (
            <div className="flex h-full">
                <div className="flex-1 p-6 space-y-4 overflow-y-auto">
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                        <h3 className="text-sm font-semibold text-blue-900 mb-2 flex items-center gap-2">
                            <Calculator size={16} />
                            Calculated Field
                        </h3>
                        <p className="text-xs text-blue-800">
                            This value is calculated from verified components. See the Summary tab for the complete breakdown.
                        </p>
                    </div>
                    
                    {notes?.step_by_step_calculation && notes.step_by_step_calculation.length > 0 && (
                        <div className="bg-white border border-slate-200 rounded-lg p-4">
                            <h3 className="text-sm font-semibold text-slate-900 mb-3">Calculation Steps</h3>
                            <ol className="list-decimal list-inside space-y-2 text-xs text-slate-700">
                                {notes.step_by_step_calculation.map((step, index) => (
                                    <li key={index}>
                                        <span className="font-medium">{step.description}:</span> {step.amount}
                                        {step.source && <span className="text-slate-500 ml-2">({step.source})</span>}
                                    </li>
                                ))}
                            </ol>
                        </div>
                    )}
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-full w-full">
            {/* Document Viewer */}
            <div className="flex-1 flex flex-col bg-gray-50 w-full">
                <div className="flex items-center justify-center p-2 bg-gray-100 border-b border-gray-200">
                    <button 
                        onClick={() => setPageNumber(prev => Math.max(prev - 1, 1))} 
                        disabled={pageNumber <= 1}
                        className="px-2 py-1 text-xs rounded hover:bg-gray-200 disabled:opacity-50"
                    >
                        Prev
                    </button>
                    <span className="mx-3 text-xs text-gray-700">Page {pageNumber} of {numPages || '?'}</span>
                    <button 
                        onClick={() => setPageNumber(prev => Math.min(prev + 1, numPages))} 
                        disabled={pageNumber >= numPages}
                        className="px-2 py-1 text-xs rounded hover:bg-gray-200 disabled:opacity-50"
                    >
                        Next
                    </button>
                    <button 
                        onClick={() => window.open(docUrl, '_blank', 'noopener,noreferrer')}
                        className="ml-4 flex items-center gap-1 px-2 py-1 text-xs text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded border border-blue-200 transition-colors"
                    >
                        <ExternalLink size={12} />
                        New Tab
                    </button>
                </div>
                <div ref={containerRef} className="flex-1 overflow-auto p-4 flex justify-center items-start bg-gray-100">
                    {evidence.file_name && evidence.file_name.startsWith('Calculated') ? (
                        <div className="flex flex-col items-center justify-center h-full text-gray-500 w-full pt-20">
                            <Calculator size={48} className="mb-4 text-blue-300" />
                            <h3 className="text-lg font-semibold text-gray-700">Calculated Value</h3>
                            <p className="text-sm mt-2 max-w-md text-center px-4">
                                This value was derived through calculation or reverse-engineering. 
                                There is no single source document to display.
                            </p>
                            <div className="mt-6 p-4 bg-white rounded border border-gray-200 max-w-lg w-full mx-4 shadow-sm">
                                <p className="font-mono text-xs whitespace-pre-wrap text-gray-600">
                                    {parseNotes(evidence)?.methodology || 
                                     parseNotes(evidence)?.mismatch_reason || 
                                     "See calculation details in the Summary tab."}
                                </p>
                            </div>
                        </div>
                    ) : (
                        <Document
                            file={docUrl}
                            onLoadSuccess={onDocumentLoadSuccess}
                            loading={<div className="text-xs text-gray-500">Loading document...</div>}
                            error={<div className="text-xs text-red-500">Failed to load document.</div>}
                        >
                            <Page
                                pageNumber={pageNumber}
                                width={containerWidth}
                                renderTextLayer={true}
                                renderAnnotationLayer={true}
                            />
                        </Document>
                    )}
                </div>
            </div>

            {/* Document Details Sidebar */}
            <div className="w-64 flex-shrink-0 border-l border-gray-200 bg-white p-4 space-y-4 overflow-y-auto">
                {/* Attribute Info */}
                {attributeLabel && attributeValue && (
                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                        <p className="text-xs font-medium text-gray-500 mb-1">Verifying</p>
                        <p className="text-xs font-semibold text-gray-900 leading-tight">{attributeLabel}</p>
                        <p className="text-base font-bold text-blue-700 mt-2">{attributeValue}</p>
                    </div>
                )}
                
                <div>
                    <h3 className="text-sm font-semibold text-gray-900 mb-2">
                        Document Details
                    </h3>
                    <p className="text-xs text-gray-600 font-medium break-all">{evidence.file_name}</p>
                </div>
            </div>
        </div>
    );
};

// Documents Tab Component (Combined - replaces Primary and Secondary)
const DocumentsTab = ({ allDocuments, parseNotes, getDocUrl, selectedDocument, setSelectedDocument, pageNumber, setPageNumber, attributeLabel, attributeValue }) => {
    const [selectedDoc, setSelectedDoc] = useState(selectedDocument || null);

    useEffect(() => {
        if (selectedDocument) {
            setSelectedDoc(selectedDocument);
        } else if (allDocuments.length > 0) {
            setSelectedDoc(allDocuments[0]);
        }
    }, [allDocuments, selectedDocument]);

    if (allDocuments.length === 0) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <FileText size={48} className="text-gray-300 mx-auto mb-3" />
                    <p className="text-sm text-gray-500">No documents found</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-full">
            {/* Document List */}
            <div className="w-64 border-r border-gray-200 bg-gray-50 p-3 space-y-2 overflow-y-auto">
                <h3 className="text-xs font-semibold text-gray-700 mb-2">Documents ({allDocuments.length})</h3>
                {allDocuments.map((ev, idx) => {
                    const notes = parseNotes(ev) || {};
                    return (
                        <button
                            key={idx}
                            onClick={() => setSelectedDoc(ev)}
                            className={clsx(
                                "w-full text-left p-2 rounded-lg border transition-colors",
                                selectedDoc === ev
                                    ? "bg-blue-50 border-blue-300"
                                    : "bg-white border-gray-200 hover:bg-gray-50"
                            )}
                        >
                            <p className="text-xs font-medium text-gray-900 break-all">{ev?.file_name || 'Document'}</p>
                            <p className="text-xs text-gray-500 mt-0.5">{notes?.document_type || 'Document'}</p>
                        </button>
                    );
                })}
            </div>

            {/* Selected Document Viewer */}
            {selectedDoc && (
                <DocumentTab
                    evidence={selectedDoc}
                    parseNotes={parseNotes}
                    getDocUrl={getDocUrl}
                    isPrimary={false}
                    initialPageNumber={pageNumber}
                    onPageChange={setPageNumber}
                    attributeLabel={attributeLabel}
                    attributeValue={attributeValue}
                />
            )}
        </div>
    );
};

// Secondary Documents Tab Component (DEPRECATED - kept for backwards compatibility)
const SecondaryDocumentsTab = ({ secondaryEvidence, parseNotes, getDocUrl, selectedSecondaryDoc, setSelectedSecondaryDoc, pageNumber, setPageNumber }) => {
    const [selectedDoc, setSelectedDoc] = useState(selectedSecondaryDoc || null);

    useEffect(() => {
        if (selectedSecondaryDoc) {
            setSelectedDoc(selectedSecondaryDoc);
        } else if (secondaryEvidence.length > 0) {
            setSelectedDoc(secondaryEvidence[0]);
        }
    }, [secondaryEvidence, selectedSecondaryDoc]);

    if (secondaryEvidence.length === 0) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <FileText size={48} className="text-gray-300 mx-auto mb-3" />
                    <p className="text-sm text-gray-500">No secondary documents found</p>
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-full">
            {/* Document List */}
            <div className="w-64 border-r border-gray-200 bg-gray-50 p-3 space-y-2 overflow-y-auto">
                <h3 className="text-xs font-semibold text-gray-700 mb-2">Secondary Documents</h3>
                {secondaryEvidence.map((ev, idx) => {
                    const notes = parseNotes(ev) || {};
                    return (
                        <button
                            key={idx}
                            onClick={() => setSelectedDoc(ev)}
                            className={clsx(
                                "w-full text-left p-2 rounded-lg border transition-colors",
                                selectedDoc === ev
                                    ? "bg-blue-50 border-blue-300"
                                    : "bg-white border-gray-200 hover:bg-gray-50"
                            )}
                        >
                            <p className="text-xs font-medium text-gray-900 break-all">{ev?.file_name || 'Document'}</p>
                            <p className="text-xs text-gray-500 mt-0.5">{notes?.document_type || 'Document'}</p>
                        </button>
                    );
                })}
            </div>

            {/* Selected Document Viewer */}
            {selectedDoc && (
                <DocumentTab
                    evidence={selectedDoc}
                    parseNotes={parseNotes}
                    getDocUrl={getDocUrl}
                    isPrimary={false}
                    initialPageNumber={pageNumber}
                    onPageChange={setPageNumber}
                />
            )}
        </div>
    );
};

export default VerificationModal;

