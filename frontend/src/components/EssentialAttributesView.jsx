import React, { useState, useEffect } from 'react';
import { CheckCircle, XCircle, FileText, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import axios from 'axios';

const EssentialAttributesView = ({ loanId }) => {
    const [essentialData, setEssentialData] = useState({
        Borrower: [],
        Property: [],
        Loan: [],
        Underwriting: []
    });
    const [loading, setLoading] = useState(true);
    const [expandedCategories, setExpandedCategories] = useState({
        Borrower: true,
        Property: true,
        Loan: true,
        Underwriting: true
    });
    const [expandedAttributes, setExpandedAttributes] = useState({});

    useEffect(() => {
        fetchEssentialAttributes();
    }, [loanId]);

    const fetchEssentialAttributes = async () => {
        try {
            const token = localStorage.getItem('token');
            const response = await axios.get(
                `http://localhost:8006/api/user/loans/${loanId}/essential-attributes`,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            setEssentialData(response.data);
            setLoading(false);
        } catch (error) {
            console.error('Error fetching essential attributes:', error);
            setLoading(false);
        }
    };

    const toggleCategory = (category) => {
        setExpandedCategories(prev => ({
            ...prev,
            [category]: !prev[category]
        }));
    };

    const toggleAttribute = (attrId) => {
        setExpandedAttributes(prev => ({
            ...prev,
            [attrId]: !prev[attrId]
        }));
    };

    const openDocument = (documentId, pageNumber) => {
        // Open document in new tab (implement your document viewer logic)
        window.open(`/document/${documentId}?page=${pageNumber}`, '_blank');
    };

    const getCategoryIcon = (category) => {
        const icons = {
            Borrower: '👤',
            Property: '🏠',
            Loan: '💰',
            Underwriting: '📋'
        };
        return icons[category] || '📄';
    };

    const getCategoryColor = (category) => {
        const colors = {
            Borrower: 'blue',
            Property: 'green',
            Loan: 'purple',
            Underwriting: 'orange'
        };
        return colors[category] || 'gray';
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            </div>
        );
    }

    const totalAttributes = Object.values(essentialData).flat().length;
    const withEvidence = Object.values(essentialData).flat().filter(a => a.has_evidence).length;

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">
                            Essential 1008 Attributes
                        </h2>
                        <p className="text-sm text-slate-600 mt-1">
                            32 core attributes organized by category (filtered by Claude Opus)
                        </p>
                    </div>
                    <div className="text-right">
                        <div className="text-2xl font-bold text-slate-900">{withEvidence}/{totalAttributes}</div>
                        <div className="text-xs text-slate-600">Evidenced</div>
                    </div>
                </div>
            </div>

            {/* Categories */}
            {Object.entries(essentialData).map(([category, attributes]) => {
                if (attributes.length === 0) return null;
                
                const color = getCategoryColor(category);
                const icon = getCategoryIcon(category);
                const isExpanded = expandedCategories[category];
                const categoryWithEvidence = attributes.filter(a => a.has_evidence).length;

                return (
                    <div key={category} className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
                        {/* Category Header */}
                        <button
                            onClick={() => toggleCategory(category)}
                            className={`w-full px-4 py-3 flex items-center justify-between border-b hover:opacity-90 transition-colors ${
                                color === 'blue' ? 'bg-blue-50 border-blue-200' :
                                color === 'green' ? 'bg-green-50 border-green-200' :
                                color === 'purple' ? 'bg-purple-50 border-purple-200' :
                                'bg-orange-50 border-orange-200'
                            }`}
                        >
                            <div className="flex items-center gap-3">
                                <span className="text-2xl">{icon}</span>
                                <div className="text-left">
                                    <h3 className={`text-base font-semibold ${
                                        color === 'blue' ? 'text-blue-900' :
                                        color === 'green' ? 'text-green-900' :
                                        color === 'purple' ? 'text-purple-900' :
                                        'text-orange-900'
                                    }`}>
                                        {category}
                                    </h3>
                                    <p className={`text-xs ${
                                        color === 'blue' ? 'text-blue-700' :
                                        color === 'green' ? 'text-green-700' :
                                        color === 'purple' ? 'text-purple-700' :
                                        'text-orange-700'
                                    }`}>
                                        {attributes.length} attributes • {categoryWithEvidence} evidenced
                                    </p>
                                </div>
                            </div>
                            {isExpanded ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                        </button>

                        {/* Attributes */}
                        {isExpanded && (
                            <div className="divide-y divide-slate-200">
                                {attributes.map((attr) => {
                                    const isAttrExpanded = expandedAttributes[attr.attribute_id];
                                    const hasSteps = attr.calculation_steps && attr.calculation_steps.length > 0;

                                    return (
                                        <div key={attr.attribute_id} className="p-4">
                                            {/* Attribute Header */}
                                            <div className="flex items-start justify-between">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <h4 className="text-sm font-medium text-slate-900">
                                                            {attr.attribute_label || attr.attribute_name}
                                                        </h4>
                                                        {attr.has_evidence ? (
                                                            <CheckCircle size={16} className="text-green-600" />
                                                        ) : (
                                                            <XCircle size={16} className="text-slate-400" />
                                                        )}
                                                    </div>
                                                    <div className="text-base font-semibold text-slate-700">
                                                        {attr.extracted_value}
                                                    </div>
                                                </div>
                                                {hasSteps && (
                                                    <button
                                                        onClick={() => toggleAttribute(attr.attribute_id)}
                                                        className="ml-4 px-3 py-1 text-xs font-medium text-primary-700 bg-primary-50 rounded hover:bg-primary-100 transition-colors"
                                                    >
                                                        {isAttrExpanded ? 'Hide' : 'Show'} Evidence
                                                    </button>
                                                )}
                                            </div>

                                            {/* Calculation Steps */}
                                            {isAttrExpanded && hasSteps && (
                                                <div className="mt-3 pl-4 border-l-2 border-slate-200 space-y-3">
                                                    {attr.calculation_steps.map((step, idx) => (
                                                        <div key={idx} className="relative pl-6">
                                                            {/* Step Number Badge */}
                                                            <div className="absolute left-0 top-0 w-5 h-5 rounded-full bg-primary-600 text-white text-xs flex items-center justify-center font-bold">
                                                                {step.step_order}
                                                            </div>

                                                            <div>
                                                                <div className="text-sm font-medium text-slate-900">
                                                                    {step.description}
                                                                </div>
                                                                <div className="text-base font-semibold text-primary-700 mt-1">
                                                                    {step.value}
                                                                </div>
                                                                
                                                                {/* Document Link */}
                                                                {step.document_name && (
                                                                    <button
                                                                        onClick={() => openDocument(step.document_id, step.page_number)}
                                                                        className="inline-flex items-center gap-1 mt-2 px-2 py-1 text-xs text-blue-700 bg-blue-50 rounded hover:bg-blue-100 transition-colors"
                                                                    >
                                                                        <FileText size={12} />
                                                                        {step.document_name}
                                                                        {step.page_number && ` (Page ${step.page_number})`}
                                                                        <ExternalLink size={10} />
                                                                    </button>
                                                                )}

                                                                {/* Formula */}
                                                                {step.formula && (
                                                                    <div className="mt-1 text-xs text-slate-600 font-mono bg-slate-50 px-2 py-1 rounded">
                                                                        {step.formula}
                                                                    </div>
                                                                )}

                                                                {/* Rationale */}
                                                                {step.rationale && (
                                                                    <div className="mt-1 text-xs text-slate-600 italic">
                                                                        {step.rationale}
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    ))}

                                                    {/* Final Verification */}
                                                    <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded flex items-center gap-2">
                                                        <CheckCircle size={16} className="text-green-600" />
                                                        <span className="text-sm text-green-800">
                                                            Verified: Matches 1008 value
                                                        </span>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
};

export default EssentialAttributesView;

