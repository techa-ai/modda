import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../utils/api';
import {
    ArrowLeft,
    FileText,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Download,
    Eye,
    ChevronDown,
    ChevronUp,
    X
} from 'lucide-react';
import { clsx } from 'clsx';

const LoanDetails = () => {
    const { id } = useParams();
    const [loan, setLoan] = useState(null);
    const [extractedData, setExtractedData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [expandedSections, setExpandedSections] = useState({});
    const [showOnlyWithValues, setShowOnlyWithValues] = useState(true);
    const [selectedAttribute, setSelectedAttribute] = useState(null);
    const [showDocumentModal, setShowDocumentModal] = useState(false);
    const [imageError, setImageError] = useState(false);
    const [snippetLoading, setSnippetLoading] = useState(false);

    useEffect(() => {
        const fetchLoanDetails = async () => {
            try {
                const response = await api.get(`/user/loans/${id}`);
                setLoan(response.data.loan);
                setExtractedData(response.data.extracted_data);

                // Initialize all sections as expanded
                const sections = {};
                response.data.extracted_data.forEach(item => {
                    if (item.section) sections[item.section] = true;
                });
                setExpandedSections(sections);
            } catch (err) {
                console.error('Error fetching loan details:', err);
                setError(err.message || 'Failed to load loan details');
            } finally {
                setLoading(false);
            }
        };

        fetchLoanDetails();
    }, [id]);

    const toggleSection = (section) => {
        setExpandedSections(prev => ({
            ...prev,
            [section]: !prev[section]
        }));
    };

    // Filter data based on checkbox
    const filteredData = showOnlyWithValues
        ? extractedData.filter(item => {
            const value = item.extracted_value;
            if (!value || value.trim() === '') return false;
            // Exclude boolean false values (case insensitive)
            if (value.toLowerCase() === 'false') return false;
            return true;
        })
        : extractedData;

    // Group data by section
    const groupedData = filteredData.reduce((acc, item) => {
        const section = item.section || 'Other';
        if (!acc[section]) acc[section] = [];
        acc[section].push(item);
        return acc;
    }, {});

    const loadSnippet = async (attribute) => {
        if (!attribute) return;

        setSnippetLoading(true);
        setImageError(false);

        try {
            const response = await api.get(`/user/loans/${id}/snippet/${attribute.id}`);
            const base64Image = response.data.image_data;
            const imageSrc = base64Image.startsWith('data:')
                ? base64Image
                : `data:image/png;base64,${base64Image}`;

            setSelectedAttribute(prev => ({
                ...prev, // Keep existing fields
                snippetImage: imageSrc
            }));
        } catch (error) {
            console.error('Error fetching snippet:', error);
            setImageError(true);
        } finally {
            setSnippetLoading(false);
        }
    };

    const viewDocumentSnippet = (item) => {
        // Reset image and show modal
        const itemWithoutImage = { ...item, snippetImage: null };
        setSelectedAttribute(itemWithoutImage);
        setShowDocumentModal(true);
        setImageError(false);

        // Auto-load
        loadSnippet(itemWithoutImage);
    };

    // Full Document Annotation State
    const [fullDocImage, setFullDocImage] = useState(null);
    const [showFullDocModal, setShowFullDocModal] = useState(false);
    const [fullDocLoading, setFullDocLoading] = useState(false);

    const loadFullDocument = async () => {
        setFullDocLoading(true);
        setShowFullDocModal(true);
        try {
            const response = await api.get(`/user/loans/${id}/full_annotation`);
            const base64Image = response.data.image_data;
            setFullDocImage(base64Image.startsWith('data:') ? base64Image : `data:image/png;base64,${base64Image}`);
        } catch (error) {
            console.error('Error fetching annotated doc:', error);
        } finally {
            setFullDocLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-4 bg-red-50 text-red-600 rounded-lg">
                Error loading loan details: {error}
            </div>
        );
    }

    if (!loan) return null;

    return (
        <div className="max-w-7xl mx-auto px-4 py-8">
            <div className="flex items-center gap-4 mb-8">
                <Link
                    to="/user/dashboard"
                    className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-900 transition-colors"
                >
                    <ArrowLeft size={20} />
                </Link>
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">Loan #{loan.loan_number || id}</h1>
                    <p className="text-slate-500 mt-1">{loan.borrower_name}</p>
                </div>
            </div>

            {/* 1008 Form Extraction */}
            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <FileText size={20} className="text-primary-600" />
                        <h2 className="text-lg font-semibold text-slate-900">
                            1008 Form Extraction Analysis
                        </h2>
                        <button
                            onClick={loadFullDocument}
                            className="p-1.5 ml-2 bg-white border border-slate-300 rounded hover:bg-slate-50 text-slate-600 transition-colors shadow-sm"
                            title="View Full Annotated Document"
                        >
                            <Eye size={18} />
                        </button>
                    </div>
                    <div className="flex items-center gap-4">
                        <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={showOnlyWithValues}
                                onChange={(e) => setShowOnlyWithValues(e.target.checked)}
                                className="rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                            />
                            Show only attributes with values
                        </label>
                        <div className="text-sm text-slate-500">
                            {filteredData.length} of {extractedData.length} attributes
                        </div>
                    </div>
                </div>

                <div className="divide-y divide-slate-200">
                    {Object.entries(groupedData).map(([section, items]) => (
                        <div key={section} className="bg-white">
                            <button
                                onClick={() => toggleSection(section)}
                                className="w-full px-6 py-3 bg-slate-50/50 flex items-center justify-between hover:bg-slate-50 transition-colors"
                            >
                                <span className="font-medium text-slate-700">{section}</span>
                                {expandedSections[section] ? (
                                    <ChevronUp size={16} className="text-slate-400" />
                                ) : (
                                    <ChevronDown size={16} className="text-slate-400" />
                                )}
                            </button>

                            {expandedSections[section] && (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left text-sm">
                                        <thead className="bg-slate-50 text-slate-500 font-medium border-y border-slate-200">
                                            <tr>
                                                <th className="px-4 py-2 w-1/3">Attribute</th>
                                                <th className="px-4 py-2 w-1/3">Extracted Value</th>
                                                <th className="px-4 py-2 w-24 text-center">OCR Verified</th>
                                                <th className="px-4 py-2">Evidence Status</th>
                                                <th className="px-4 py-2 text-right">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100">
                                            {items.map((item) => {
                                                const hasEvidence = item.evidence && item.evidence.length > 0;
                                                const isSecured = hasEvidence && item.evidence.some(e => e.is_secured);

                                                return (
                                                    <tr key={item.id} className="hover:bg-slate-50/50 transition-colors">
                                                        <td className="px-4 py-2 font-medium text-slate-700">
                                                            {item.attribute_label}
                                                        </td>
                                                        <td className="px-4 py-2 text-slate-600">
                                                            {item.extracted_value || '-'}
                                                        </td>
                                                        <td className="px-4 py-2 text-center">
                                                            {item.ocr_verified === true ? (
                                                                <CheckCircle2 size={18} className="text-green-600 mx-auto" />
                                                            ) : item.ocr_verified === false ? (
                                                                <XCircle size={18} className="text-red-600 mx-auto" />
                                                            ) : (
                                                                <span className="text-slate-400">-</span>
                                                            )}
                                                        </td>
                                                        <td className="px-4 py-2">
                                                            {hasEvidence ? (
                                                                <div className="flex flex-wrap gap-1">
                                                                    {item.evidence.map((ev, idx) => (
                                                                        <div
                                                                            key={idx}
                                                                            className={clsx(
                                                                                "flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium border",
                                                                                ev.is_secured
                                                                                    ? "bg-green-50 text-green-700 border-green-200"
                                                                                    : "bg-red-50 text-red-700 border-red-200"
                                                                            )}
                                                                        >
                                                                            {ev.is_secured ? (
                                                                                <CheckCircle2 size={14} />
                                                                            ) : (
                                                                                <XCircle size={14} />
                                                                            )}
                                                                            <span className="font-medium truncate max-w-[150px]" title={ev.file_name}>
                                                                                {ev.file_name}
                                                                            </span>
                                                                        </div>
                                                                    ))}
                                                                </div>
                                                            ) : (
                                                                <div className="flex items-center gap-2 text-red-600 text-xs font-medium px-2 py-1 rounded-md bg-red-50 border border-red-100 w-fit">
                                                                    <AlertTriangle size={14} />
                                                                    No Evidence Found
                                                                </div>
                                                            )}
                                                        </td>
                                                        <td className="px-4 py-2 text-right">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button
                                                                    onClick={() => viewDocumentSnippet(item)}
                                                                    className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors"
                                                                    title="View Document Snippet"
                                                                >
                                                                    <Eye size={16} />
                                                                </button>
                                                                {hasEvidence && (
                                                                    <button className="p-1.5 text-slate-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors" title="Download Evidence">
                                                                        <Download size={16} />
                                                                    </button>
                                                                )}
                                                            </div>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div >

            {/* Document Snippet Modal */}
            {
                showDocumentModal && selectedAttribute && (
                    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                        <div className="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col">
                            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
                                <div>
                                    <h3 className="text-lg font-semibold text-slate-900">Document Snippet</h3>
                                    <p className="text-sm text-slate-500 mt-1">
                                        {selectedAttribute.attribute_label}: <span className="font-mono text-slate-700">{selectedAttribute.extracted_value}</span>
                                    </p>
                                </div>
                                <button
                                    onClick={() => setShowDocumentModal(false)}
                                    className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="flex-1 overflow-auto p-6">
                                {snippetLoading ? (
                                    <div className="bg-slate-50 border-2 border-dashed border-slate-300 rounded-lg p-12 text-center h-96 flex flex-col items-center justify-center">
                                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mb-4"></div>
                                        <h4 className="text-lg font-semibold text-slate-700">Loading Snippet...</h4>
                                        <p className="text-slate-500 mt-2">Analyzing document coordinates</p>
                                    </div>
                                ) : selectedAttribute.snippetImage ? (
                                    <div className="space-y-4">
                                        <div className="flex justify-between items-start border-b border-slate-200 pb-4">
                                            <div>
                                                <h3 className="text-lg font-semibold text-slate-900">
                                                    Document Snippet
                                                </h3>
                                                <p className="text-sm text-slate-600 mt-1">
                                                    {selectedAttribute.attribute_label}: {selectedAttribute.extracted_value}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="border-2 border-primary-200 rounded-lg overflow-hidden bg-slate-50 p-4">
                                            {imageError ? (
                                                <p className="text-red-600 text-sm text-center">Failed to load image snippet</p>
                                            ) : (
                                                <div className="flex flex-col items-center">
                                                    <img
                                                        src={selectedAttribute.snippetImage}
                                                        alt="Document snippet"
                                                        className="border border-slate-300 bg-white"
                                                        style={{
                                                            objectFit: 'contain',
                                                            maxWidth: '100%',
                                                            maxHeight: '600px',
                                                            height: 'auto',
                                                            border: '1px solid #e5e7eb',
                                                            borderRadius: '0.5rem',
                                                            boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                                                        }}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                        <p className="text-xs text-slate-400 mt-3 text-center">
                                            Highlighted region shows where this value was found in the document
                                        </p>
                                    </div>
                                ) : (
                                    <div className="bg-slate-50 border-2 border-dashed border-slate-300 rounded-lg p-12 text-center">
                                        <FileText size={48} className="mx-auto text-slate-400 mb-4" />
                                        <h4 className="text-lg font-semibold text-slate-700 mb-2">Document Snippet</h4>
                                        <p className="text-slate-500 mb-4">
                                            {imageError ? "Failed to generate snippet." : "No bounding box data available for this field"}
                                        </p>
                                        <div className="bg-white rounded-lg p-4 max-w-md mx-auto border border-slate-200 mb-4">
                                            <p className="text-sm text-slate-600 mb-2">
                                                <strong>Attribute:</strong> {selectedAttribute.attribute_label}
                                            </p>
                                            <p className="text-sm text-slate-600 mb-2">
                                                <strong>Value:</strong> <span className="font-mono bg-slate-100 px-2 py-1 rounded">{selectedAttribute.extracted_value}</span>
                                            </p>
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200 bg-slate-50">
                                <button
                                    onClick={() => setShowDocumentModal(false)}
                                    className="px-4 py-2 text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 transition-colors"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )
            }

            {/* Full Document Modal */}
            {showFullDocModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl w-full max-w-6xl max-h-[90vh] flex flex-col overflow-hidden">
                        <div className="flex justify-between items-center p-4 border-b border-slate-200">
                            <h3 className="text-lg font-semibold text-slate-900">Full 1008 Form Annotation</h3>
                            <button
                                onClick={() => setShowFullDocModal(false)}
                                className="p-1 hover:bg-slate-100 rounded-full transition-colors"
                            >
                                <X size={24} className="text-slate-400" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-auto p-4 bg-slate-100 flex justify-center">
                            {fullDocLoading ? (
                                <div className="flex flex-col items-center justify-center mt-20">
                                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mb-4"></div>
                                    <p className="text-slate-600">Analyzing full document structure...</p>
                                </div>
                            ) : fullDocImage ? (
                                <img
                                    src={fullDocImage}
                                    alt="Annotated 1008 Form"
                                    className="max-w-full shadow-lg border border-slate-300"
                                />
                            ) : (
                                <div className="flex flex-col items-center justify-center mt-20 text-red-500">
                                    <p>Failed to load annotation.</p>
                                    <button onClick={loadFullDocument} className="mt-2 text-primary-600 hover:underline">Retry</button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div >
    );
};

export default LoanDetails;

