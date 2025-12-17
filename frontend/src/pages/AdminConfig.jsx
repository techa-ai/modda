import React, { useState, useEffect, useMemo } from 'react';
import api from '../utils/api';
import {
    FileJson,
    Eye,
    X,
    ChevronDown,
    ChevronRight,
    FileText
} from 'lucide-react';

// Helper to flatten the schema into a list for rendering
const flattenSchema = (schema, level = 0, parentPath = '') => {
    let nodes = [];
    if (!schema || !schema.properties) return nodes;

    Object.entries(schema.properties).forEach(([key, value]) => {
        const currentPath = parentPath ? `${parentPath}.${key}` : key;
        const isObject = value.type === 'object' && value.properties;

        nodes.push({
            key: currentPath,
            name: key,
            data: value,
            level,
            hasChildren: isObject,
            parentPath
        });

        if (isObject) {
            nodes = nodes.concat(flattenSchema(value, level + 1, currentPath));
        }
    });
    return nodes;
};

const AdminConfig = () => {
    // Schemas
    const [schemas, setSchemas] = useState([]);
    const [selectedSchema, setSelectedSchema] = useState(null);
    const [schemaContent, setSchemaContent] = useState(null);

    // Expansion state for schema viewer
    const [expandedRows, setExpandedRows] = useState({});

    useEffect(() => {
        fetchSchemas();
    }, []);

    const fetchSchemas = async () => {
        try {
            const response = await api.get('/config/schemas');
            setSchemas(response.data.schemas);
        } catch (error) {
            console.error('Error fetching schemas:', error);
        }
    };

    const handleViewSchema = async (filename) => {
        try {
            const response = await api.get(`/config/schemas/${filename}`);
            setSchemaContent(response.data);
            setSelectedSchema(filename);
            setExpandedRows({}); // Reset expansion state
        } catch (error) {
            console.error('Error fetching schema content:', error);
        }
    };

    const toggleRow = (key) => {
        setExpandedRows(prev => ({
            ...prev,
            [key]: prev[key] === undefined ? false : !prev[key] // Default to expanded (undefined = true), so toggle makes it false
        }));
    };

    // Memoize flattened nodes
    const flatNodes = useMemo(() => {
        if (!schemaContent) return [];
        return flattenSchema(schemaContent);
    }, [schemaContent]);

    // Calculate visible nodes based on expansion state
    const visibleNodes = useMemo(() => {
        const visible = [];
        let skipUntilLevel = null;

        for (const node of flatNodes) {
            if (skipUntilLevel !== null) {
                if (node.level > skipUntilLevel) {
                    continue;
                } else {
                    skipUntilLevel = null;
                }
            }

            visible.push(node);

            // Check if collapsed. Default is expanded (undefined).
            // If expandedRows[key] is false, it is collapsed.
            // If expandedRows[key] is true or undefined, it is expanded.
            const isExpanded = expandedRows[node.key] !== false;

            if (node.hasChildren && !isExpanded) {
                skipUntilLevel = node.level;
            }
        }
        return visible;
    }, [flatNodes, expandedRows]);

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900">System Configuration</h1>
                    <p className="text-slate-500 mt-1">Manage document definitions and schemas</p>
                </div>
            </div>

            <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50">
                    <h2 className="font-semibold text-slate-900">Document Definitions</h2>
                </div>
                <div className="divide-y divide-slate-100">
                    {schemas.map((schema) => (
                        <div key={schema} className="px-6 py-4 flex items-center justify-between hover:bg-slate-50">
                            <div className="flex items-center gap-4">
                                <div className="w-8 h-8 rounded bg-indigo-50 flex items-center justify-center text-indigo-500">
                                    <FileJson size={16} />
                                </div>
                                <div>
                                    <h3 className="font-medium text-slate-900">
                                        {schema.replace('.json', '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                    </h3>
                                    <p className="text-xs text-slate-500">{schema}</p>
                                </div>
                            </div>
                            <button
                                onClick={() => handleViewSchema(schema)}
                                className="btn btn-secondary text-xs flex items-center gap-2"
                            >
                                <Eye size={14} /> View Schema
                            </button>
                        </div>
                    ))}
                    {schemas.length === 0 && (
                        <div className="px-6 py-8 text-center text-slate-500">
                            No schemas found.
                        </div>
                    )}
                </div>
            </div>

            {/* Schema Viewer Modal */}
            {selectedSchema && schemaContent && (
                <div className="fixed inset-0 bg-slate-900/50 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                    <div className="bg-white rounded-xl shadow-xl w-[95vw] h-[90vh] flex flex-col animate-in fade-in zoom-in-95 duration-200">
                        <div className="flex items-center justify-between p-4 border-b border-slate-200">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900">{schemaContent.title || selectedSchema}</h2>
                                <p className="text-xs text-slate-500 mt-0.5">{schemaContent.description}</p>
                            </div>
                            <button onClick={() => setSelectedSchema(null)} className="text-slate-400 hover:text-slate-600">
                                <X size={20} />
                            </button>
                        </div>
                        <div className="flex-1 overflow-auto p-4 bg-white">
                            <div className="border border-slate-200 rounded-lg overflow-hidden">
                                <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex items-center text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                                    <div className="w-1/4">Field</div>
                                    <div className="flex-1 px-4">Definition</div>
                                    <div className="w-20 text-center">Type</div>
                                    <div className="w-1/4 pl-4">Evidence</div>
                                </div>
                                <div className="divide-y divide-slate-50">
                                    {visibleNodes.map((node) => (
                                        <div key={node.key} className="flex items-start hover:bg-slate-50 py-2 px-4">
                                            {/* Field Column */}
                                            <div className="w-1/4 min-w-0 flex items-start gap-2" style={{ paddingLeft: `${node.level * 1.5}rem` }}>
                                                {node.hasChildren ? (
                                                    <button
                                                        onClick={() => toggleRow(node.key)}
                                                        className="p-0.5 mt-0.5 hover:bg-slate-200 rounded text-slate-400 shrink-0"
                                                    >
                                                        {expandedRows[node.key] !== false ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                                                    </button>
                                                ) : (
                                                    <div className="w-4 shrink-0" />
                                                )}

                                                <div className="min-w-0 flex-1">
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-medium text-slate-700 text-xs truncate" title={node.data.title || node.name}>
                                                            {node.data.title || node.name}
                                                        </span>
                                                    </div>
                                                    <span className="text-[10px] text-slate-400 bg-slate-100 px-1 rounded truncate block mt-0.5" title={node.name}>
                                                        {node.name}
                                                    </span>
                                                </div>
                                            </div>

                                            {/* Definition Column */}
                                            <div className="flex-1 min-w-0 px-4">
                                                <p className="text-[10px] text-slate-600 leading-normal">
                                                    {node.data.definition || node.data.description || '-'}
                                                </p>
                                            </div>

                                            {/* Type Column */}
                                            <div className="w-20 shrink-0 flex justify-center">
                                                {node.data.type && (
                                                    <span className={`text-[9px] uppercase font-bold px-1.5 py-0.5 rounded-full ${node.data.type === 'number' || node.data.type === 'integer' ? 'bg-blue-100 text-blue-700' :
                                                        node.data.type === 'boolean' ? 'bg-purple-100 text-purple-700' :
                                                            node.data.type === 'object' ? 'bg-slate-200 text-slate-600' :
                                                                'bg-slate-100 text-slate-700'
                                                        }`}>
                                                        {node.data.type}
                                                    </span>
                                                )}
                                            </div>

                                            {/* Evidence Column */}
                                            <div className="w-1/4 shrink-0 pl-4">
                                                {node.data.evidence && (
                                                    <div className="text-[10px]">
                                                        {node.data.evidence.document_types && node.data.evidence.document_types.length > 0 ? (
                                                            <div className="flex flex-wrap gap-1">
                                                                {node.data.evidence.document_types.map((doc, i) => (
                                                                    <span key={i} className="bg-green-50 text-green-700 border border-green-100 px-1 py-0.5 rounded text-[9px]">
                                                                        {doc}
                                                                    </span>
                                                                ))}
                                                            </div>
                                                        ) : (
                                                            <span className="text-slate-400 italic">No specific evidence required</span>
                                                            /* node.data.evidence.notes shows optional notes if needed */
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default AdminConfig;
