import React from 'react';
import { CheckCircle2, XCircle, AlertCircle, FileText, Award, DollarSign } from 'lucide-react';

/**
 * Structured Summary Renderer (New Format)
 * Renders JSON-structured verification summaries
 */
const StructuredSummaryRenderer = ({ summary, onDocumentClick }) => {
    const isDebt = summary.summary_type === 'debt';
    const isIncome = summary.summary_type === 'income';
    const isCredit = summary.summary_type === 'credit';
    const isProperty = summary.summary_type === 'property';
    
    const themeColor = isDebt ? 'red' : isIncome ? 'green' : isCredit ? 'purple' : isProperty ? 'blue' : 'gray';
    
    return (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-blue-900 mb-4 flex items-center gap-2">
                <FileText size={16} />
                MODDA's Verification Summary
            </h3>
            
            {/* Verification Badge */}
            <div className="flex items-center gap-3 mb-4">
                <div className={`flex items-center gap-2 bg-white border-2 px-4 py-2 rounded-lg shadow-md ${
                    isCredit ? 'border-purple-600' : isProperty ? 'border-blue-600' : 'border-green-600'
                }`}>
                    <div className={`flex items-center justify-center w-8 h-8 rounded-md ${
                        isCredit ? 'bg-purple-600' : isProperty ? 'bg-blue-600' : 'bg-green-600'
                    }`}>
                        <span className="text-white font-black text-lg">G</span>
                    </div>
                    <span className="font-bold text-sm text-gray-900">Verification</span>
                </div>
            </div>
            
            <div className="space-y-4">
                {/* Header */}
                {summary.header && (
                    <div className="bg-white border border-slate-200 rounded-lg p-3 shadow-sm">
                        <p className="text-xs text-slate-800 leading-relaxed">
                            {summary.header}
                        </p>
                    </div>
                )}

                {/* Sections */}
                {summary.sections && summary.sections.map((section, idx) => {
                    // Special rendering for credit verification result section
                    if (isCredit && section.result) {
                        return (
                            <div key={idx} className="bg-white border border-purple-200 rounded-lg p-4 shadow-sm">
                                <h3 className="text-sm font-bold text-purple-900 mb-3 flex items-center gap-2">
                                    <CheckCircle2 size={16} className="text-purple-600" />
                                    {section.title}
                                </h3>
                                <div className="space-y-2">
                                    <div className="flex justify-between items-center bg-purple-50 p-2 rounded">
                                        <span className="text-xs font-semibold text-gray-700">Reported Score:</span>
                                        <span className="text-sm font-bold text-purple-700">{section.result.reported_score}</span>
                                    </div>
                                    <div className="flex justify-between items-center bg-purple-50 p-2 rounded">
                                        <span className="text-xs font-semibold text-gray-700">Verified Score:</span>
                                        <span className="text-sm font-bold text-purple-700">{section.result.verified_score}</span>
                                    </div>
                                    <div className="flex justify-between items-center bg-green-50 p-2 rounded">
                                        <span className="text-xs font-semibold text-gray-700">Match Status:</span>
                                        <span className={`text-xs font-bold px-2 py-1 rounded ${
                                            section.result.match_status === 'VERIFIED' 
                                                ? 'bg-green-100 text-green-700' 
                                                : 'bg-red-100 text-red-700'
                                        }`}>
                                            {section.result.match_status}
                                        </span>
                                    </div>
                                    {section.result.explanation && (
                                        <p className="text-xs text-gray-600 mt-2 leading-relaxed">
                                            {section.result.explanation}
                                        </p>
                                    )}
                                </div>
                            </div>
                        );
                    }
                    
                    // Special rendering for property verification result section
                    if (isProperty && section.result) {
                        return (
                            <div key={idx} className="bg-white border border-blue-200 rounded-lg p-4 shadow-sm">
                                <h3 className="text-sm font-bold text-blue-900 mb-3 flex items-center gap-2">
                                    <CheckCircle2 size={16} className="text-blue-600" />
                                    {section.title}
                                </h3>
                                <div className="space-y-2">
                                    {section.result.property_value && (
                                        <div className="flex justify-between items-center bg-blue-50 p-2 rounded">
                                            <span className="text-xs font-semibold text-gray-700">Property Value:</span>
                                            <span className="text-sm font-bold text-blue-700">{section.result.property_value}</span>
                                        </div>
                                    )}
                                    <div className="grid grid-cols-2 gap-2">
                                        <div className="bg-blue-50 p-2 rounded">
                                            <p className="text-xs text-gray-600">Calculated LTV:</p>
                                            <p className="text-sm font-bold text-blue-700">{section.result.ltv_calculated}%</p>
                                        </div>
                                        <div className="bg-blue-50 p-2 rounded">
                                            <p className="text-xs text-gray-600">Reported LTV:</p>
                                            <p className="text-sm font-bold text-blue-700">{section.result.ltv_reported}%</p>
                                        </div>
                                        <div className="bg-blue-50 p-2 rounded">
                                            <p className="text-xs text-gray-600">Calculated CLTV:</p>
                                            <p className="text-sm font-bold text-blue-700">{section.result.cltv_calculated}%</p>
                                        </div>
                                        <div className="bg-blue-50 p-2 rounded">
                                            <p className="text-xs text-gray-600">Reported CLTV:</p>
                                            <p className="text-sm font-bold text-blue-700">{section.result.cltv_reported}%</p>
                                        </div>
                                    </div>
                                    <div className="flex justify-between items-center bg-green-50 p-2 rounded">
                                        <span className="text-xs font-semibold text-gray-700">Match Status:</span>
                                        <span className={`text-xs font-bold px-2 py-1 rounded ${
                                            section.result.match_status === 'VERIFIED' 
                                                ? 'bg-green-100 text-green-700' 
                                                : 'bg-red-100 text-red-700'
                                        }`}>
                                            {section.result.match_status}
                                        </span>
                                    </div>
                                    {section.result.explanation && (
                                        <p className="text-xs text-gray-600 mt-2 leading-relaxed">
                                            {section.result.explanation}
                                        </p>
                                    )}
                                </div>
                            </div>
                        );
                    }
                    
                    return (
                        <div key={idx} className={`bg-white border border-${themeColor}-200 rounded-lg p-4 shadow-sm`}>
                            <h3 className={`text-sm font-bold text-${themeColor}-900 mb-3 flex items-center gap-2`}>
                                <CheckCircle2 size={16} className={`text-${themeColor}-600`} />
                                {section.title}
                                {section.subtotal_formatted && (
                                    <span className={`ml-auto text-xs font-bold text-${themeColor}-700 bg-${themeColor}-100 px-2 py-0.5 rounded`}>
                                        {section.subtotal_formatted}
                                    </span>
                                )}
                            </h3>
                            
                            <div className="space-y-2">
                                {section.items && section.items.map((item, itemIdx) => {
                                    // Credit score item rendering
                                    if (isCredit && item.score) {
                                        return (
                                            <div key={itemIdx} className="border-l-2 border-purple-400 pl-3 py-1 bg-purple-50/30">
                                                <div className="flex items-start justify-between gap-2">
                                                    <p className="text-xs font-semibold text-gray-900">
                                                        {item.description}
                                                    </p>
                                                    <div className="flex items-center gap-2 flex-shrink-0">
                                                        <span className="text-sm font-bold text-purple-900">{item.score}</span>
                                                        {item.document && (
                                                            <DocReferenceBadge 
                                                                page={item.page} 
                                                                document={item.document}
                                                                onClick={() => onDocumentClick && onDocumentClick(item.document, item.page)}
                                                            />
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    }
                                    
                                    // Credit calculation step rendering
                                    if (isCredit && item.details) {
                                        return (
                                            <div key={itemIdx} className="border-l-2 border-purple-400 pl-3 py-1 bg-purple-50/30">
                                                <p className="text-xs font-semibold text-gray-900 mb-1">
                                                    {item.description}
                                                </p>
                                                <p className="text-xs text-gray-700">
                                                    {item.details}
                                                </p>
                                            </div>
                                        );
                                    }
                                    
                                    // Property value item rendering (with amount_formatted or details)
                                    if (isProperty && (item.amount_formatted || item.details)) {
                                        return (
                                            <div key={itemIdx} className="border-l-2 border-blue-400 pl-3 py-1 bg-blue-50/30">
                                                <div className="flex items-start justify-between gap-2">
                                                    <p className="text-xs font-semibold text-gray-900">
                                                        {item.description}
                                                    </p>
                                                    <div className="flex items-center gap-2 flex-shrink-0">
                                                        {item.amount_formatted && (
                                                            <span className="text-sm font-bold text-blue-900">{item.amount_formatted}</span>
                                                        )}
                                                        {item.details && !item.amount_formatted && (
                                                            <span className="text-xs text-gray-700">{item.details}</span>
                                                        )}
                                                        {item.document && (
                                                            <DocReferenceBadge 
                                                                page={item.page} 
                                                                document={item.document}
                                                                onClick={() => onDocumentClick && onDocumentClick(item.document, item.page)}
                                                            />
                                                        )}
                                                    </div>
                                                </div>
                                                {item.details && item.amount_formatted && (
                                                    <p className="text-xs text-gray-600 mt-1">{item.details}</p>
                                                )}
                                            </div>
                                        );
                                    }
                                    
                                    // Default debt/income rendering
                                    return (
                                        <div key={itemIdx} className={`border-l-2 border-${themeColor}-400 pl-3 py-1 bg-${themeColor}-50/30`}>
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="flex-1">
                                                    <p className="text-xs font-semibold text-gray-900">
                                                        {item.description || item.creditor}
                                                        {item.account_type && <span className="text-gray-600 ml-1">({item.account_type})</span>}
                                                    </p>
                                                    {item.account_number && (
                                                        <p className="text-xs text-gray-500">
                                                            Account: •••{item.account_number.slice(-4)}
                                                        </p>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-2 flex-shrink-0">
                                                    <span className={`text-sm font-bold text-${themeColor}-900`}>
                                                        {item.amount_formatted || item.monthly_payment_formatted}
                                                    </span>
                                                    {item.document && (
                                                        <DocReferenceBadge 
                                                            page={item.page} 
                                                            document={item.document}
                                                            onClick={() => onDocumentClick && onDocumentClick(item.document, item.page)}
                                                        />
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    );
                })}

                {/* Total */}
                {summary.total_formatted && (
                    <div className={`bg-white border border-${themeColor}-200 rounded-lg p-4 shadow-sm`}>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <DollarSign size={20} className={`text-${themeColor}-600`} />
                                <span className="text-sm font-bold text-gray-900">GRAND TOTAL:</span>
                            </div>
                            <span className={`text-lg font-black text-${themeColor}-900`}>
                                {summary.total_formatted}
                            </span>
                        </div>
                        {summary.variance && summary.variance.show_variance !== false && summary.variance.difference > 0.01 && (
                            <div className="mt-2 pt-2 border-t border-gray-200">
                                <p className="text-xs text-gray-600">
                                    <span className="font-semibold">Variance:</span> ${summary.variance.difference.toFixed(2)} ({summary.variance.percentage.toFixed(2)}%)
                                    {summary.variance.explanation && <span className="ml-1">- {summary.variance.explanation}</span>}
                                </p>
                            </div>
                        )}
                    </div>
                )}

                {/* Methodology */}
                {summary.methodology && summary.methodology.length > 0 && (
                    <div className="bg-white border border-purple-200 rounded-lg p-4 shadow-sm">
                        <h3 className="text-sm font-bold text-purple-900 mb-3 flex items-center gap-2">
                            <AlertCircle size={16} className="text-purple-600" />
                            Underwriting Methodology & Compliance
                        </h3>
                        <ul className="space-y-2">
                            {summary.methodology.map((item, idx) => (
                                <li key={idx} className="text-xs text-gray-700 flex items-start gap-2">
                                    <span className="text-purple-600 mt-0.5">✓</span>
                                    <div className="flex-1">
                                        <span className="font-semibold text-gray-900">{item.title}:</span> {item.description}
                                    </div>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {/* Confidence */}
                {summary.confidence && (
                    <div className="bg-gradient-to-r from-green-50 to-blue-50 border border-green-300 rounded-lg p-4 shadow-sm">
                        <h3 className="text-sm font-bold text-green-900 mb-3 flex items-center gap-2">
                            <Award size={16} className="text-green-600" />
                            Verification Confidence
                            <span className="ml-auto text-xs font-bold text-green-700 bg-green-100 px-2 py-0.5 rounded">
                                {summary.confidence.level} ({summary.confidence.percentage}%)
                            </span>
                        </h3>
                        {summary.confidence.checks && (
                            <ul className="space-y-1">
                                {summary.confidence.checks.map((check, idx) => (
                                    <li key={idx} className="text-xs text-gray-700 flex items-start gap-2">
                                        <span className="text-green-600 mt-0.5">✓</span>
                                        <span className="flex-1">{check}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

/**
 * Polished renderer for MODDA's Verification Summary
 * Parses structured text and renders with proper formatting (Old Format - Fallback)
 */
const VerificationSummaryRenderer = ({ summary, onDocumentClick, attributeLabel }) => {
    if (!summary) {
        return (
            <div className="text-xs text-gray-500 italic">
                No verification information available
            </div>
        );
    }

    // Check if summary is structured JSON (new format) or string (old format)
    const isStructuredFormat = typeof summary === 'object' && summary.summary_type;
    
    if (isStructuredFormat) {
        // Use new structured renderer
        return <StructuredSummaryRenderer summary={summary} onDocumentClick={onDocumentClick} />;
    }

    // Parse the summary into sections (old format)
    const sections = parseSummary(summary);
    
    const isIncome = attributeLabel && (
        attributeLabel.toLowerCase().includes('income') || 
        attributeLabel.toLowerCase().includes('cash flow') ||
        attributeLabel.toLowerCase().includes('salary')
    );
    
    const isDebt = attributeLabel && (
        attributeLabel.toLowerCase().includes('debt') ||
        attributeLabel.toLowerCase().includes('payment') ||
        attributeLabel.toLowerCase().includes('obligation') ||
        attributeLabel.toLowerCase().includes('piti')
    );

    return (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-blue-900 mb-4 flex items-center gap-2">
                <FileText size={16} />
                MODDA's Verification Summary
            </h3>
            
            {/* Verification & Compliance Badges */}
            <div className="flex items-center gap-3 mb-4">
                <div className="flex items-center gap-2 bg-white border-2 border-green-600 px-4 py-2 rounded-lg shadow-md hover:bg-green-50 transition-colors">
                    <div className="flex items-center justify-center w-8 h-8 bg-green-600 rounded-md">
                        <span className="text-white font-black text-lg">G</span>
                    </div>
                    <span className="font-bold text-sm text-gray-900">Verification</span>
                </div>
                
                {/* Compliance Badge - Hidden for now */}
                {/* 
                <div className="flex items-center gap-2 bg-white border-2 border-green-600 px-4 py-2 rounded-lg shadow-md hover:bg-green-50 transition-colors">
                    <div className="flex items-center justify-center w-8 h-8 bg-green-600 rounded-md">
                        <span className="text-white font-black text-lg">G</span>
                    </div>
                    <span className="font-bold text-sm text-gray-900">Compliance</span>
                </div>
                */}
            </div>
            
            <div className="space-y-4">
            {/* Header / Overview */}
            {sections.header && (
                <div className="bg-white border border-slate-200 rounded-lg p-3 shadow-sm">
                    <p className="text-xs text-slate-800 leading-relaxed">
                        {sections.header}
                    </p>
                </div>
            )}

            {/* Income Sources Included */}
            {sections.includedIncome && isIncome && (
                <div className="bg-white border border-green-200 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-bold text-green-900 mb-3 flex items-center gap-2">
                        <CheckCircle2 size={16} className="text-green-600" />
                        Income Sources Included
                        <span className="ml-auto text-xs font-normal text-green-700 bg-green-100 px-2 py-0.5 rounded">
                            Conservative Underwriting
                        </span>
                    </h3>
                    <div className="space-y-4">
                        {sections.includedIncome.map((source, idx) => (
                            <div key={idx} className="border-l-2 border-green-400 pl-4 py-2 bg-green-50/30">
                                <p className="text-xs font-semibold text-gray-900 mb-2">
                                    {source.title}
                                </p>
                                <ul className="space-y-1">
                                    {source.items.map((item, itemIdx) => {
                                        const docRef = extractDocReference(item);
                                        const lineValue = extractLineValue(item);
                                        const itemText = docRef 
                                            ? item.replace(/\(Page\s+\d+[^)]*\)/gi, '').replace(/Page\s+\d+[^•\-\n]+/gi, '').trim()
                                            : item;
                                        
                                        return (
                                            <li key={itemIdx} className="text-xs text-gray-700 flex items-start gap-2">
                                                <span className="text-green-600 mt-0.5">•</span>
                                                <span className="flex-1 flex items-center flex-wrap gap-1">
                                                    <span>{itemText}</span>
                                                    {docRef && (
                                                        <DocReferenceBadge 
                                                            page={docRef.page} 
                                                            document={docRef.document}
                                                            lineValue={lineValue}
                                                            onClick={(value) => onDocumentClick && onDocumentClick(docRef.document, docRef.page, value)}
                                                        />
                                                    )}
                                                </span>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </div>
                        ))}
                    </div>
                    {sections.totalIncome && (
                        <div className="mt-4 pt-3 border-t-2 border-green-300 bg-green-50 p-3 rounded">
                            <p className="text-sm font-bold text-green-900">{sections.totalIncome}</p>
                        </div>
                    )}
                </div>
            )}

            {/* Debt Obligations Included (for debt verification) */}
            {sections.includedDebts && isDebt && (
                <div className="bg-white border border-red-200 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-bold text-red-900 mb-3 flex items-center gap-2">
                        <CheckCircle2 size={16} className="text-red-600" />
                        Debt Obligations Included
                        <span className="ml-auto text-xs font-normal text-red-700 bg-red-100 px-2 py-0.5 rounded">
                            Complete PITI + All Debts
                        </span>
                    </h3>
                    <div className="space-y-4">
                        {sections.includedDebts.map((source, idx) => (
                            <div key={idx} className="border-l-2 border-red-400 pl-4 py-2 bg-red-50/30">
                                <p className="text-xs font-semibold text-gray-900 mb-2">
                                    {source.title}
                                </p>
                                <ul className="space-y-1">
                                    {source.items.map((item, itemIdx) => {
                                        const docRef = extractDocReference(item);
                                        const lineValue = extractLineValue(item);
                                        const itemText = docRef 
                                            ? item.replace(/\(Page\s+\d+[^)]*\)/gi, '').replace(/Page\s+\d+[^•\-\n]+/gi, '').trim()
                                            : item;
                                        
                                        return (
                                            <li key={itemIdx} className="text-xs text-gray-700 flex items-start gap-2">
                                                <span className="text-red-600 mt-0.5">•</span>
                                                <span className="flex-1 flex items-center flex-wrap gap-1">
                                                    <span>{itemText}</span>
                                                    {docRef && (
                                                        <DocReferenceBadge 
                                                            page={docRef.page} 
                                                            document={docRef.document}
                                                            lineValue={lineValue}
                                                            onClick={(value) => onDocumentClick && onDocumentClick(docRef.document, docRef.page, value)}
                                                        />
                                                    )}
                                                </span>
                                            </li>
                                        );
                                    })}
                                </ul>
                            </div>
                        ))}
                    </div>
                    {sections.totalDebt && (
                        <div className="mt-4 pt-3 border-t-2 border-red-300 bg-red-50 p-3 rounded">
                            <p className="text-sm font-bold text-red-900">{sections.totalDebt}</p>
                        </div>
                    )}
                </div>
            )}

            {/* Income Sources Excluded */}
            {sections.excludedIncome && sections.excludedIncome.length > 0 && (
                <div className="bg-white border border-amber-200 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-bold text-amber-900 mb-3 flex items-center gap-2">
                        <XCircle size={16} className="text-amber-600" />
                        Income Sources Identified But Properly Excluded
                    </h3>
                    <div className="space-y-3">
                        {sections.excludedIncome.map((source, idx) => {
                            const titleDocRef = extractDocReference(source.title);
                            const titleValue = extractLineValue(source.title);
                            const titleText = titleDocRef
                                ? source.title.replace(/\(Page\s+[^)]*\)/gi, '').trim()
                                : source.title;
                            
                            return (
                                <div key={idx} className="border-l-2 border-amber-400 pl-4 py-2 bg-amber-50/30">
                                    <p className="text-xs font-semibold text-gray-900 mb-1 flex items-center gap-2 flex-wrap">
                                        <span className="text-amber-600">❌</span>
                                        <span>{titleText}</span>
                                        {titleDocRef && (
                                            <DocReferenceBadge 
                                                page={titleDocRef.page} 
                                                document={titleDocRef.document}
                                                lineValue={titleValue}
                                                onClick={(value) => onDocumentClick && onDocumentClick(titleDocRef.document, titleDocRef.page, value)}
                                            />
                                        )}
                                    </p>
                                    <ul className="space-y-1 ml-4">
                                        {source.items.map((item, itemIdx) => {
                                            const docRef = extractDocReference(item);
                                            const lineValue = extractLineValue(item);
                                            const itemText = docRef
                                                ? item.replace(/\(Page\s+[^)]*\)/gi, '').replace(/Page\s+\d+[^•\-\n]+/gi, '').trim()
                                                : item;
                                            
                                            return (
                                                <li key={itemIdx} className="text-xs text-gray-700 flex items-start gap-1 flex-wrap">
                                                    <span>{itemText}</span>
                                                    {docRef && (
                                                        <DocReferenceBadge 
                                                            page={docRef.page} 
                                                            document={docRef.document}
                                                            lineValue={lineValue}
                                                            onClick={(value) => onDocumentClick && onDocumentClick(docRef.document, docRef.page, value)}
                                                        />
                                                    )}
                                                </li>
                                            );
                                        })}
                                    </ul>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Underwriting Methodology */}
            {sections.methodology && sections.methodology.length > 0 && (
                <div className="bg-white border border-purple-200 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-bold text-purple-900 mb-3 flex items-center gap-2">
                        <AlertCircle size={16} className="text-purple-600" />
                        Underwriting Methodology & Compliance
                    </h3>
                    <ul className="space-y-2">
                        {sections.methodology.map((item, idx) => (
                            <li key={idx} className="text-xs text-gray-700">
                                <div className="flex items-start gap-2">
                                    <span className="text-purple-600 mt-0.5">✓</span>
                                    <div className="flex-1">
                                        <p className="font-semibold text-gray-900">{item.title}</p>
                                        {item.details && (
                                            <ul className="ml-4 mt-1 space-y-0.5">
                                                {item.details.map((detail, detailIdx) => (
                                                    <li key={detailIdx} className="text-gray-600">
                                                        - {detail}
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Document Package Overview */}
            {sections.documentPackage && sections.documentPackage.length > 0 && (
                <div className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-bold text-slate-900 mb-3 flex items-center gap-2">
                        <FileText size={16} className="text-slate-600" />
                        Document Package Overview
                        {sections.totalPages && (
                            <span className="ml-auto text-xs font-normal text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
                                {sections.totalPages}
                            </span>
                        )}
                    </h3>
                    <ul className="space-y-1">
                        {sections.documentPackage.map((item, idx) => (
                            <li key={idx} className="text-xs text-gray-700 flex items-start gap-2">
                                <span className="text-slate-500 mt-0.5">•</span>
                                <span className="flex-1">{item}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Verification Confidence */}
            {sections.confidence && (
                <div className="bg-gradient-to-r from-green-50 to-blue-50 border border-green-300 rounded-lg p-4 shadow-sm">
                    <h3 className="text-sm font-bold text-green-900 mb-3 flex items-center gap-2">
                        <Award size={16} className="text-green-600" />
                        Verification Confidence
                        <span className="ml-auto text-xs font-bold text-green-700 bg-green-100 px-2 py-0.5 rounded">
                            {sections.confidence.level}
                        </span>
                    </h3>
                    {sections.confidence.items && (
                        <ul className="space-y-1 mb-3">
                            {sections.confidence.items.map((item, idx) => (
                                <li key={idx} className="text-xs text-gray-700 flex items-start gap-2">
                                    <span className="text-green-600 mt-0.5">✓</span>
                                    <span className="flex-1">{item}</span>
                                </li>
                            ))}
                        </ul>
                    )}
                    {sections.confidence.footer && (
                        <p className="text-xs text-gray-800 bg-white/70 p-2 rounded border border-green-200">
                            {sections.confidence.footer}
                        </p>
                    )}
                </div>
            )}
            </div>
        </div>
    );
};

/**
 * Extract line value (e.g., "$195,329" from "Base ordinary income: $195,329")
 */
function extractLineValue(text) {
    // Match currency values like $195,329 or -$1,954
    const match = text.match(/(-?\$[\d,]+\.?\d*)/);
    return match ? match[1] : null;
}

/**
 * Extract document reference from text (e.g., "Page 2, W-2" or "(Page 1033, Schedule E)")
 * Handles page ranges like "Page 2227-2228, tax_returns_65.pdf"
 */
function extractDocReference(text) {
    // Match patterns like: (Page 2, W-2) or Page 1033, Schedule E or Page 2227-2228, tax_returns_65.pdf
    const patterns = [
        /\(Page\s+(\d+)(?:-\d+)?,?\s*([^)]+)\)/i,  // (Page 123-456, doc.pdf)
        /Page\s+(\d+)(?:-\d+)?,?\s*([^\n•\-,]+(?:,\s*[^\n•\-]+)?)/i,  // Page 123-456, doc.pdf
    ];
    
    for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
            return {
                page: parseInt(match[1]),  // Use first page of range
                document: match[2].trim()
            };
        }
    }
    return null;
}

/**
 * Document reference badge component (now clickable!)
 */
function DocReferenceBadge({ page, document, onClick, lineValue }) {
    return (
        <button
            onClick={() => onClick && onClick(lineValue)}
            className="inline-flex items-center gap-1.5 ml-2 px-2 py-0.5 bg-blue-100 text-blue-800 border border-blue-300 rounded text-xs font-medium whitespace-nowrap hover:bg-blue-200 hover:border-blue-400 transition-colors cursor-pointer"
        >
            <FileText size={10} className="text-blue-600" />
            <span>{document}</span>
            <span className="text-blue-600 font-bold">p.{page}</span>
        </button>
    );
}
function parseSummary(summary) {
    const sections = {
        header: null,
        includedIncome: [],
        excludedIncome: [],
        includedDebts: [],  // For debt verification
        methodology: [],
        documentPackage: [],
        totalPages: null,
        confidence: null,
        totalIncome: null,
        totalDebt: null  // For debt verification
    };
    
    // Pre-process: normalize line breaks and split properly
    // Replace common separators with actual newlines
    let normalized = summary
        .replace(/\|\s*\|/g, '\n')  // Table separators
        .replace(/\*\*([^*]+)\*\*/g, '\n\n**$1**\n')  // Bold headers
        .replace(/━{3,}/g, '\n━━━\n')  // Separator lines
        .replace(/\s+•\s+/g, '\n• ')  // Bullet points
        .replace(/\s+✓\s+/g, '\n✓ ')  // Check marks
        .replace(/\s+❌\s+/g, '\n❌ ')  // X marks
        .replace(/\s+\|\s+/g, ' | ');  // Table cells
    
    const lines = normalized.split('\n').map(l => l.trim()).filter(l => l && l !== '|');
    let currentSection = null;
    let currentSubsection = null;
    let buffer = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // Remove bold markers for comparison
        const cleanLine = line.replace(/\*\*/g, '');
        
        // Section headers
        if (cleanLine.includes('INCOME SOURCES INCLUDED')) {
            currentSection = 'includedIncome';
            currentSubsection = null;
            continue;
        } else if (cleanLine.includes('DEBT OBLIGATIONS INCLUDED') || 
                   cleanLine.includes('PROPOSED HOUSING PAYMENT') || 
                   cleanLine.includes('MONTHLY DEBTS')) {
            // This is a debt section header - could be subsection title
            if (!currentSection || currentSection !== 'includedDebts') {
                currentSection = 'includedDebts';
                currentSubsection = null;
            } else {
                // This is a subsection within debts
                if (currentSubsection) {
                    sections.includedDebts.push(currentSubsection);
                }
                // Clean the title - remove any table headers
                let cleanTitle = cleanLine;
                if (cleanTitle.includes('|')) {
                    // Remove table header part (everything after first | that contains column names)
                    const parts = cleanTitle.split('|');
                    const headerKeywords = ['Creditor', 'Account Type', 'Monthly Payment', 'Component', 'Monthly Amount', 'Source'];
                    const firstHeaderIndex = parts.findIndex(p => headerKeywords.some(k => p.includes(k)));
                    if (firstHeaderIndex > 0) {
                        cleanTitle = parts.slice(0, firstHeaderIndex).join('|').trim();
                    }
                }
                currentSubsection = {
                    title: cleanTitle,
                    items: []
                };
            }
            continue;
        } else if (cleanLine.includes('INCOME SOURCES IDENTIFIED BUT PROPERLY EXCLUDED')) {
            currentSection = 'excludedIncome';
            currentSubsection = null;
            continue;
        } else if (line.includes('UNDERWRITING METHODOLOGY')) {
            currentSection = 'methodology';
            currentSubsection = null;
            continue;
        } else if (line.includes('DOCUMENT PACKAGE OVERVIEW')) {
            currentSection = 'documentPackage';
            const match = line.match(/\(([^)]+)\)/);
            if (match) sections.totalPages = match[1];
            continue;
        } else if (line.includes('VERIFICATION CONFIDENCE')) {
            currentSection = 'confidence';
            const match = line.match(/:\s*(.+?)(?:\s*\(|$)/);
            sections.confidence = {
                level: match ? match[1].trim() : 'HIGH (100%)',
                items: [],
                footer: null
            };
            continue;
        }

        // Skip separator lines and table header separators
        if (line.startsWith('━') || line.match(/^[\|\-\s]+$/)) continue;
        
        // Handle markdown table rows (lines with |)
        if (line.includes('|')) {
            const cells = line.split('|').map(c => c.trim()).filter(c => c);
            
            // A table HEADER has ONLY column names and no data values
            // Check if this is purely a header row (no $ signs, no .pdf, no numbers like $1,234)
            const hasDataValue = cells.some(cell => 
                cell.includes('$') ||           // Has dollar amount
                cell.includes('.pdf') ||        // Has document reference
                /\d{1,3},\d{3}/.test(cell) ||  // Has formatted number
                /\d+\.\d{2}/.test(cell)        // Has decimal number
            );
            
            // Column name keywords that appear ONLY in headers
            const headerKeywords = ['Component', 'Creditor', 'Account Type', 'Monthly Payment', 'Monthly Amount', 'Source'];
            const isAllColumnNames = cells.every(cell => 
                headerKeywords.some(keyword => cell === keyword || cell.includes(keyword)) ||
                cell === '' || 
                cell.length < 3
            );
            
            // Skip if it's a pure header row (only column names, no data)
            if (isAllColumnNames && !hasDataValue) {
                continue;
            }
            
            // This is a data row - parse it
            if (cells.length >= 2 && hasDataValue) {
                // Format the row as a readable string
                const itemText = cells.join(' | ');
                if (currentSubsection) {
                    currentSubsection.items.push(itemText);
                } else if (currentSection === 'includedDebts' || currentSection === 'includedIncome') {
                    // Create a subsection if we're in debt/income section
                    currentSubsection = {
                        title: 'Items',
                        items: [itemText]
                    };
                }
                continue;
            }
        }

        // Header (before first section)
        if (!currentSection) {
            if (!sections.header) sections.header = line;
            else sections.header += ' ' + line;
            continue;
        }

        // Total income line
        if (line.includes('TOTAL MONTHLY INCOME:') && currentSection === 'includedIncome') {
            sections.totalIncome = line;
            continue;
        }
        
        // Total debt line
        if ((line.includes('TOTAL MONTHLY DEBT') || line.includes('TOTAL') && line.includes('$')) && currentSection === 'includedDebts') {
            sections.totalDebt = line;
            continue;
        }

        // Process content by section
        if (currentSection === 'includedIncome' || currentSection === 'includedDebts') {
            // Numbered income sources
            const match = line.match(/^(\d+)\.\s+(.+)/);
            if (match) {
                if (currentSubsection) {
                    sections.includedIncome.push(currentSubsection);
                }
                currentSubsection = {
                    title: match[2],
                    items: []
                };
            } else if (line.startsWith('•')) {
                if (currentSubsection) {
                    currentSubsection.items.push(line.substring(1).trim());
                }
            } else if (currentSubsection && !line.includes(':') && line.length > 20) {
                // Continuation of title or description
                currentSubsection.items.push(line);
            }
            // Store subsection when moving to next section
            if (currentSection === 'includedIncome' && currentSubsection && (i === lines.length - 1 || lines[i+1].includes('━'))) {
                sections.includedIncome.push(currentSubsection);
                currentSubsection = null;
            } else if (currentSection === 'includedDebts' && currentSubsection && (i === lines.length - 1 || lines[i+1].includes('━'))) {
                sections.includedDebts.push(currentSubsection);
                currentSubsection = null;
            }
        } else if (currentSection === 'excludedIncome') {
            if (line.startsWith('❌')) {
                if (currentSubsection) {
                    sections.excludedIncome.push(currentSubsection);
                }
                currentSubsection = {
                    title: line.substring(1).trim(),
                    items: []
                };
            } else if (line.startsWith('•')) {
                if (currentSubsection) {
                    currentSubsection.items.push(line.substring(1).trim());
                }
            }
        } else if (currentSection === 'methodology') {
            if (line.startsWith('✓')) {
                if (currentSubsection) {
                    sections.methodology.push(currentSubsection);
                }
                const parts = line.substring(1).trim().split(':');
                currentSubsection = {
                    title: parts[0].trim(),
                    details: parts.length > 1 ? [parts.slice(1).join(':').trim()] : []
                };
            } else if (line.startsWith('-') && currentSubsection) {
                currentSubsection.details.push(line.substring(1).trim());
            }
        } else if (currentSection === 'documentPackage') {
            if (line.startsWith('•')) {
                sections.documentPackage.push(line.substring(1).trim());
            }
        } else if (currentSection === 'confidence') {
            if (line.startsWith('✓')) {
                sections.confidence.items.push(line.substring(1).trim());
            } else if (!line.startsWith('All components') && line.length > 30) {
                sections.confidence.footer = line;
            }
        }
    }

    // Push last subsection
    if (currentSubsection) {
        if (currentSection === 'includedIncome') {
            sections.includedIncome.push(currentSubsection);
        } else if (currentSection === 'includedDebts') {
            sections.includedDebts.push(currentSubsection);
        } else if (currentSection === 'excludedIncome') {
            sections.excludedIncome.push(currentSubsection);
        } else if (currentSection === 'methodology') {
            sections.methodology.push(currentSubsection);
        }
    }

    return sections;
}

export default VerificationSummaryRenderer;

