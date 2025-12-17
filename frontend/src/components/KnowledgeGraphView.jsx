import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import ForceGraph2D from 'react-force-graph-2d';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { JSONTree } from 'react-json-tree';
import { RefreshCw, Maximize2, Minimize2, Download, FileText, Sparkles } from 'lucide-react';

const KnowledgeGraphView = () => {
    const { loanId } = useParams();
    const [knowledgeGraph, setKnowledgeGraph] = useState(null);
    const [kgSummary, setKgSummary] = useState(null);
    const [loading, setLoading] = useState(true);
    const [generatingSummary, setGeneratingSummary] = useState(false);
    const [view, setView] = useState('query'); // 'query', 'json', 'split', 'graph', 'summary'
    const [query, setQuery] = useState('');
    const [queryResult, setQueryResult] = useState(null);
    const [querying, setQuerying] = useState(false);
    const [selectedNode, setSelectedNode] = useState(null);
    const [graphData, setGraphData] = useState({ nodes: [], links: [] });
    const graphRef = useRef();

    useEffect(() => {
        fetchKnowledgeGraph();
    }, [loanId]);

    const fetchKnowledgeGraph = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('token');
            const response = await axios.get(
                `http://localhost:8006/api/admin/loans/${loanId}/knowledge-graph`,
                { headers: { Authorization: `Bearer ${token}` } }
            );
            
            if (response.data.knowledge_graph) {
                setKnowledgeGraph(response.data.knowledge_graph);
                setKgSummary(response.data.kg_summary);
                
                // Convert to format for react-force-graph
                const kg = response.data.knowledge_graph;
                const nodes = kg.nodes?.map(node => ({
                    id: node.id,
                    name: node.properties?.name || node.id,
                    type: node.type,
                    ...node.properties
                })) || [];
                
                const links = kg.edges?.map(edge => ({
                    source: edge.from,
                    target: edge.to,
                    type: edge.type,
                    ...edge.properties
                })) || [];
                
                setGraphData({ nodes, links });
            }
        } catch (error) {
            console.error('Error fetching knowledge graph:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleGenerateKG = async () => {
        setLoading(true);
        try {
            const token = localStorage.getItem('token');
            const response = await axios.post(
                `http://localhost:8006/api/admin/loans/${loanId}/generate-knowledge-graph`,
                {},
                { headers: { Authorization: `Bearer ${token}` } }
            );
            
            if (response.data.success) {
                alert(`Knowledge Graph generation started!\nCheck back in a few minutes.\nLog file: ${response.data.log_file}`);
                // Poll for completion
                setTimeout(() => fetchKnowledgeGraph(), 10000);
            }
        } catch (error) {
            console.error('Error generating knowledge graph:', error);
            alert('Failed to start knowledge graph generation');
        } finally {
            setLoading(false);
        }
    };

    const handleQuery = async () => {
        if (!query.trim()) return;
        
        setQuerying(true);
        try {
            const token = localStorage.getItem('token');
            const response = await axios.post(
                `http://localhost:8006/api/admin/loans/${loanId}/query-knowledge-graph`,
                { query: query },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            
            if (response.data.answer) {
                setQueryResult({
                    query: query,
                    answer: response.data.answer,
                    nodes: response.data.relevant_nodes || [],
                    edges: response.data.relevant_edges || []
                });
            }
        } catch (error) {
            console.error('Error querying knowledge graph:', error);
            setQueryResult({
                query: query,
                answer: 'Error: Could not query knowledge graph. Please try again.',
                nodes: [],
                edges: []
            });
        } finally {
            setQuerying(false);
        }
    };

    const handleGenerateSummary = async () => {
        setGeneratingSummary(true);
        try {
            const token = localStorage.getItem('token');
            const response = await axios.post(
                `http://localhost:8006/api/admin/loans/${loanId}/generate-kg-summary`,
                {},
                { headers: { Authorization: `Bearer ${token}` } }
            );
            if (response.data.summary) {
                setKgSummary(response.data.summary);
            }
        } catch (error) {
            console.error('Error generating summary:', error);
            alert('Failed to generate summary');
        } finally {
            setGeneratingSummary(false);
        }
    };

    const getNodeColor = (node) => {
        const colors = {
            'Loan': '#3b82f6',
            'Document': '#10b981',
            'Person': '#f59e0b',
            'Property': '#8b5cf6',
            'Company': '#ec4899',
            'Value': '#06b6d4',
            'Rule': '#f97316',
            'Adjustment': '#ef4444',
            'Source': '#6b7280',
            'Version': '#14b8a6'
        };
        return colors[node.type] || '#9ca3af';
    };

    const handleNodeClick = (node) => {
        setSelectedNode(node);
    };

    const downloadGraph = () => {
        const dataStr = JSON.stringify(knowledgeGraph, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `knowledge_graph_loan_${loanId}.json`;
        link.click();
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-96">
                <RefreshCw className="w-8 h-8 animate-spin text-blue-600" />
                <span className="ml-3 text-gray-600">Loading knowledge graph...</span>
            </div>
        );
    }

    if (!knowledgeGraph) {
        return (
            <div className="bg-white rounded-lg shadow p-8 text-center">
                <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No Knowledge Graph</h3>
                <p className="text-sm text-gray-600 mb-4">
                    Knowledge graph has not been generated for this loan yet.
                </p>
                <button
                    className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 flex items-center gap-2"
                    onClick={handleGenerateKG}
                    disabled={loading}
                >
                    {loading ? (
                        <>
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            Generating...
                        </>
                    ) : (
                        <>
                            <Sparkles className="w-4 h-4" />
                            Generate Knowledge Graph
                        </>
                    )}
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header Controls */}
            <div className="bg-white rounded-lg shadow p-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <h2 className="text-lg font-semibold text-gray-900">Knowledge Graph</h2>
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                        <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded">
                            {graphData.nodes.length} Nodes
                        </span>
                        <span className="px-2 py-1 bg-green-100 text-green-700 rounded">
                            {graphData.links.length} Edges
                        </span>
                    </div>
                </div>
                
                <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1 bg-gray-100 rounded-md p-1">
                        <button
                            onClick={() => setView('query')}
                            className={`px-3 py-1 text-xs font-medium rounded ${
                                view === 'query' ? 'bg-white shadow-sm text-blue-600' : 'text-gray-600 hover:text-gray-900'
                            }`}
                        >
                            Query
                        </button>
                        <button
                            onClick={() => setView('json')}
                            className={`px-3 py-1 text-xs font-medium rounded ${
                                view === 'json' ? 'bg-white shadow-sm text-blue-600' : 'text-gray-600 hover:text-gray-900'
                            }`}
                        >
                            JSON
                        </button>
                        <button
                            onClick={() => setView('split')}
                            className={`px-3 py-1 text-xs font-medium rounded ${
                                view === 'split' ? 'bg-white shadow-sm text-blue-600' : 'text-gray-600 hover:text-gray-900'
                            }`}
                        >
                            Graph
                        </button>
                    </div>
                    <button
                        onClick={downloadGraph}
                        className="p-2 hover:bg-gray-100 rounded"
                        title="Download Graph JSON"
                    >
                        <Download className="w-4 h-4" />
                    </button>
                    <button
                        onClick={fetchKnowledgeGraph}
                        className="p-2 hover:bg-gray-100 rounded"
                        title="Refresh"
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Main Content */}
            <div className="space-y-4">
                {/* Query View */}
                {view === 'query' && (
                    <div className="bg-white rounded-lg shadow p-6">
                        <h3 className="text-base font-semibold text-gray-900 mb-4">Ask Questions About This Loan</h3>
                        
                        {/* Quick Examples */}
                        <div className="mb-4 flex flex-wrap gap-2">
                            <span className="text-xs text-gray-500">Examples:</span>
                            {[
                                'What information is in the 1008 form?',
                                'How is monthly income of $30,721.67 calculated?',
                                'Who is the borrower?',
                                'What is the property address?',
                                'What documents do we have?',
                                'What is the loan amount and interest rate?'
                            ].map((example, idx) => (
                                <button
                                    key={idx}
                                    onClick={() => setQuery(example)}
                                    className="text-xs px-2 py-1 bg-blue-50 text-blue-700 rounded hover:bg-blue-100"
                                >
                                    {example}
                                </button>
                            ))}
                        </div>
                        
                        {/* Query Input */}
                        <div className="flex gap-2 mb-6">
                            <input
                                type="text"
                                value={query}
                                onChange={(e) => setQuery(e.target.value)}
                                onKeyPress={(e) => e.key === 'Enter' && handleQuery()}
                                placeholder="Ask a question about this loan..."
                                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            />
                            <button
                                onClick={handleQuery}
                                disabled={querying || !query.trim()}
                                className={`px-6 py-2 rounded-lg text-sm font-medium transition-colors ${
                                    querying || !query.trim()
                                        ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                        : 'bg-blue-600 text-white hover:bg-blue-700'
                                }`}
                            >
                                {querying ? (
                                    <><RefreshCw className="w-4 h-4 animate-spin inline mr-1" /> Thinking...</>
                                ) : (
                                    'Ask'
                                )}
                            </button>
                        </div>
                        
                        {/* Query Result */}
                        {queryResult && (
                            <div className="space-y-4">
                                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                    <div className="text-xs font-medium text-blue-900 mb-2">Question:</div>
                                    <div className="text-sm text-blue-700">{queryResult.query}</div>
                                </div>
                                
                                <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                                    <div className="text-xs font-medium text-green-900 mb-2">Answer:</div>
                                    <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
                                        {queryResult.answer}
                                    </div>
                                </div>
                                
                                {queryResult.nodes && queryResult.nodes.length > 0 && (
                                    <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                                        <div className="text-xs font-medium text-gray-900 mb-3">
                                            Relevant Entities ({queryResult.nodes.length})
                                        </div>
                                        <div className="space-y-2">
                                            {queryResult.nodes.map((node, idx) => (
                                                <div key={idx} className="text-xs p-2 bg-white rounded border border-gray-200">
                                                    <div className="font-medium text-blue-600">{node.id}</div>
                                                    <div className="text-gray-500 text-xs mt-1">{node.type}</div>
                                                    <pre className="mt-2 text-xs text-gray-700 overflow-x-auto">
                                                        {JSON.stringify(node.properties, null, 2)}
                                                    </pre>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* JSON View */}
                {view === 'json' && (
                    <div className="bg-white rounded-lg shadow p-4">
                        <div className="mb-4 flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-gray-900">Knowledge Graph JSON</h3>
                            <div className="flex items-center gap-2 text-xs text-gray-600">
                                <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded">
                                    {graphData.nodes.length} Nodes
                                </span>
                                <span className="px-2 py-1 bg-green-100 text-green-700 rounded">
                                    {graphData.links.length} Edges
                                </span>
                            </div>
                        </div>
                        
                        <div className="border border-gray-200 rounded-lg overflow-hidden">
                            <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex items-center justify-between">
                                <span className="text-xs font-medium text-gray-700">Raw JSON Structure</span>
                                <button
                                    onClick={downloadGraph}
                                    className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
                                >
                                    <Download className="w-3 h-3" />
                                    Download
                                </button>
                            </div>
                            <div className="overflow-auto" style={{ maxHeight: '800px' }}>
                                <div className="p-4">
                                    <JSONTree 
                                        data={knowledgeGraph}
                                        theme={{
                                            scheme: 'bright',
                                            base00: '#ffffff',
                                            base0B: '#10b981',
                                            base09: '#f59e0b',
                                            base08: '#ef4444',
                                            base0D: '#3b82f6',
                                        }}
                                        invertTheme={false}
                                        hideRoot={false}
                                        shouldExpandNodeInitially={(keyPath, data, level) => level < 2}
                                    />
                                </div>
                            </div>
                        </div>
                        
                        {/* Quick Stats */}
                        <div className="mt-4 grid grid-cols-2 gap-4">
                            <div className="bg-blue-50 p-3 rounded-lg">
                                <div className="text-xs text-blue-600 font-medium mb-1">Node Types</div>
                                <div className="space-y-1">
                                    {Object.entries(
                                        graphData.nodes.reduce((acc, node) => {
                                            acc[node.type] = (acc[node.type] || 0) + 1;
                                            return acc;
                                        }, {})
                                    ).map(([type, count]) => (
                                        <div key={type} className="text-xs text-gray-700 flex justify-between">
                                            <span>{type}:</span>
                                            <span className="font-semibold">{count}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            
                            <div className="bg-green-50 p-3 rounded-lg">
                                <div className="text-xs text-green-600 font-medium mb-1">Edge Types</div>
                                <div className="space-y-1">
                                    {Object.entries(
                                        graphData.links.reduce((acc, link) => {
                                            acc[link.type] = (acc[link.type] || 0) + 1;
                                            return acc;
                                        }, {})
                                    ).map(([type, count]) => (
                                        <div key={type} className="text-xs text-gray-700 flex justify-between">
                                            <span>{type}:</span>
                                            <span className="font-semibold">{count}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Graph Visualization */}
                {(view === 'split' || view === 'graph') && (
                    <div className="bg-white rounded-lg shadow p-4">
                        <div className="mb-4">
                            <h3 className="text-sm font-semibold text-gray-900 mb-2">Interactive Graph</h3>
                            <div className="flex flex-wrap gap-2 text-xs">
                                {Object.entries({
                                    'Loan': '#3b82f6',
                                    'Document': '#10b981',
                                    'Person': '#f59e0b',
                                    'Property': '#8b5cf6',
                                    'Company': '#ec4899',
                                    'Value': '#06b6d4'
                                }).map(([type, color]) => (
                                    <span key={type} className="flex items-center gap-1">
                                        <span
                                            className="w-3 h-3 rounded-full"
                                            style={{ backgroundColor: color }}
                                        />
                                        <span className="text-gray-600">{type}</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                        
                        <div className="border border-gray-200 rounded-lg" style={{ height: view === 'split' ? '600px' : '800px' }}>
                            <ForceGraph2D
                                ref={graphRef}
                                graphData={graphData}
                                nodeLabel="name"
                                nodeAutoColorBy="type"
                                nodeColor={getNodeColor}
                                nodeRelSize={6}
                                nodeCanvasObject={(node, ctx, globalScale) => {
                                    const label = node.name || node.id;
                                    const fontSize = 12/globalScale;
                                    ctx.font = `${fontSize}px Sans-Serif`;
                                    ctx.textAlign = 'center';
                                    ctx.textBaseline = 'middle';
                                    ctx.fillStyle = getNodeColor(node);
                                    ctx.fillText(label, node.x, node.y);
                                }}
                                linkLabel="type"
                                linkDirectionalArrowLength={6}
                                linkDirectionalArrowRelPos={1}
                                linkCurvature={0.2}
                                onNodeClick={handleNodeClick}
                                enableNodeDrag={true}
                                enableZoomPanInteraction={true}
                                d3VelocityDecay={0.3}
                            />
                        </div>

                        {/* Selected Node Details */}
                        {selectedNode && (
                            <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                                <div className="flex items-center justify-between mb-2">
                                    <h4 className="text-sm font-semibold text-gray-900">{selectedNode.type}</h4>
                                    <button
                                        onClick={() => setSelectedNode(null)}
                                        className="text-gray-400 hover:text-gray-600"
                                    >
                                        ×
                                    </button>
                                </div>
                                <div className="space-y-1 text-xs">
                                    <div><span className="font-medium">ID:</span> {selectedNode.id}</div>
                                    {Object.entries(selectedNode).filter(([k, v]) => !['id', 'type', 'x', 'y', 'vx', 'vy', 'index'].includes(k)).map(([key, value]) => (
                                        <div key={key}>
                                            <span className="font-medium capitalize">{key.replace(/_/g, ' ')}:</span>{' '}
                                            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Summary Panel */}
                {(view === 'split' || view === 'summary') && (
                    <div className="bg-white rounded-lg shadow overflow-hidden">
                        <div className="p-4 border-b border-gray-200 bg-gradient-to-r from-purple-50 to-indigo-50">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Sparkles className="w-5 h-5 text-purple-600" />
                                    <h3 className="text-sm font-semibold text-gray-900">KG-Based Summary</h3>
                                </div>
                                <button
                                    onClick={handleGenerateSummary}
                                    disabled={generatingSummary}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                        generatingSummary
                                            ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                                            : 'bg-purple-600 text-white hover:bg-purple-700'
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
                                            {kgSummary ? 'Regenerate' : 'Generate'}
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                        
                        <div className="p-4 overflow-y-auto" style={{ height: view === 'split' ? '650px' : '800px' }}>
                            {kgSummary ? (
                                <div className="prose prose-sm max-w-none">
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            h1: ({node, ...props}) => <h1 className="text-lg font-bold text-gray-900 border-b pb-2 mb-4" {...props} />,
                                            h2: ({node, ...props}) => <h2 className="text-base font-semibold text-gray-900 mt-6 mb-3" {...props} />,
                                            h3: ({node, ...props}) => <h3 className="text-sm font-medium text-gray-800 mt-4 mb-2" {...props} />,
                                            p: ({node, ...props}) => <p className="text-xs text-gray-700 mb-2 leading-relaxed" {...props} />,
                                            table: ({node, ...props}) => (
                                                <div className="overflow-x-auto my-4 border border-gray-200 rounded-lg">
                                                    <table className="min-w-full divide-y divide-gray-200" {...props} />
                                                </div>
                                            ),
                                            thead: ({node, ...props}) => <thead className="bg-gray-50" {...props} />,
                                            th: ({node, ...props}) => <th className="px-4 py-2 text-left text-xs font-semibold text-gray-700" {...props} />,
                                            td: ({node, ...props}) => <td className="px-4 py-2 text-xs text-gray-600" {...props} />,
                                        }}
                                    >
                                        {kgSummary}
                                    </ReactMarkdown>
                                </div>
                            ) : (
                                <div className="text-center py-12">
                                    <Sparkles className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                                    <p className="text-sm text-gray-500 mb-1">No summary generated yet</p>
                                    <p className="text-xs text-gray-400 mb-4">Click "Generate" to create summary from knowledge graph</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default KnowledgeGraphView;

