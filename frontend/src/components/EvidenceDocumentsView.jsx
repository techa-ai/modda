import React, { useState, useEffect } from 'react';
import { FileText, Search, Filter } from 'lucide-react';
import EvidenceDocumentModal from '../components/EvidenceDocumentModal';

const EvidenceDocumentsView = ({ loanId }) => {
    const [documents, setDocuments] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [selectedDoc, setSelectedDoc] = useState(null);
    const [modalOpen, setModalOpen] = useState(false);

    useEffect(() => {
        fetchEvidenceDocuments();
    }, [loanId]);

    const fetchEvidenceDocuments = async () => {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`http://localhost:8006/api/admin/loans/${loanId}/evidence-documents`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            
            if (response.ok) {
                const data = await response.json();
                setDocuments(data.documents || []);
            }
        } catch (error) {
            console.error('Error fetching evidence documents:', error);
        } finally {
            setLoading(false);
        }
    };

    const filteredDocs = documents.filter(doc =>
        doc.file_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        doc.doc_type?.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const handleOpenModal = (doc) => {
        setSelectedDoc(doc);
        setModalOpen(true);
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-gray-500">Loading evidence documents...</div>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header & Search */}
            <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-4">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Evidence Documents</h2>
                        <p className="text-sm text-slate-500 mt-1">
                            Documents used for verifying 1008 form attributes
                        </p>
                    </div>
                    <div className="text-2xl font-bold text-primary-600">
                        {documents.length}
                    </div>
                </div>

                {/* Search */}
                <div className="relative">
                    <Search size={18} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
                    <input
                        type="text"
                        placeholder="Search documents..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500 text-sm"
                    />
                </div>
            </div>

            {/* Documents Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredDocs.map((doc, idx) => (
                    <button
                        key={idx}
                        onClick={() => handleOpenModal(doc)}
                        className="bg-white rounded-lg shadow-sm border border-slate-200 p-4 hover:shadow-md hover:border-primary-300 transition-all text-left"
                    >
                        <div className="flex items-start gap-3">
                            <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary-100 flex items-center justify-center">
                                <FileText size={20} className="text-primary-600" />
                            </div>
                            <div className="flex-1 min-w-0">
                                <h3 className="text-sm font-semibold text-slate-900 truncate">
                                    {doc.file_name}
                                </h3>
                                <p className="text-xs text-slate-500 mt-1">
                                    {doc.doc_type || 'Evidence Document'}
                                </p>
                                {doc.usage && doc.usage.length > 0 && (
                                    <div className="mt-2 flex items-center gap-2">
                                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                            {doc.usage.length} {doc.usage.length === 1 ? 'attribute' : 'attributes'}
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </button>
                ))}
            </div>

            {filteredDocs.length === 0 && (
                <div className="bg-white rounded-lg shadow-sm border border-slate-200 p-12 text-center">
                    <FileText size={48} className="text-gray-300 mx-auto mb-3" />
                    <p className="text-gray-500">No evidence documents found</p>
                </div>
            )}

            {/* Modal */}
            <EvidenceDocumentModal
                isOpen={modalOpen}
                onClose={() => setModalOpen(false)}
                document={selectedDoc}
                loanId={loanId}
            />
        </div>
    );
};

export default EvidenceDocumentsView;








