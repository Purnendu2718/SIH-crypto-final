import React, { useEffect, useRef, useState, useMemo } from 'react';
import cytoscape, { Core, EventObject } from 'cytoscape';
// @ts-ignore
import dagre from 'cytoscape-dagre';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  Copy,
  Check,
  Building2,
  AlertTriangle,
  Info,
  Download,
  FileCode,
  FileText,
  Sliders,
  X,
  ExternalLink,
  Flame,
  RefreshCw,
} from 'lucide-react';
import { TracePathItem } from '../lib/api';
import {
  transformTraceToGraph,
  GraphNodeData,
  TransformedGraph,
} from '../lib/graphTransform';

// Register dagre layout plugin once
try {
  cytoscape.use(dagre);
} catch {}

interface GraphCanvasProps {
  paths: TracePathItem[];
  startAddress: string;
  chain: string;
  matchedEntity?: string;
  attributionRule?: string;
  confidence?: number;
  isStreaming?: boolean;
  streamingHopIndex?: number;
  onReplayTrace?: () => void;
}

export const GraphCanvas: React.FC<GraphCanvasProps> = ({
  paths,
  startAddress,
  chain,
  matchedEntity,
  attributionRule,
  confidence,
  isStreaming,
  streamingHopIndex,
  onReplayTrace,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [showSummaryModal, setShowSummaryModal] = useState<boolean>(false);
  const [timeCutoffIndex, setTimeCutoffIndex] = useState<number>(100);

  // Derive unique sorted timestamps from paths
  const timestamps = useMemo(() => {
    const list = paths
      .map((p) => p.timestamp)
      .filter((ts): ts is string => Boolean(ts))
      .sort();
    return Array.from(new Set(list));
  }, [paths]);

  const activeCutoffTime = useMemo(() => {
    if (timestamps.length === 0 || timeCutoffIndex >= 100) return undefined;
    const idx = Math.min(
      timestamps.length - 1,
      Math.floor((timeCutoffIndex / 100) * timestamps.length)
    );
    return timestamps[idx];
  }, [timestamps, timeCutoffIndex]);

  // Pure graph transform
  const graphData: TransformedGraph = useMemo(() => {
    return transformTraceToGraph({
      paths,
      startAddress,
      chain,
      matchedEntity,
      attributionRule,
      confidence,
      timeCutoff: activeCutoffTime,
    });
  }, [paths, startAddress, chain, matchedEntity, attributionRule, confidence, activeCutoffTime]);

  // Keyboard navigation: Escape key closes side panel and summary modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedNode(null);
        setShowSummaryModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Initialize and update Cytoscape instance
  useEffect(() => {
    if (!containerRef.current) return;

    const elements: any[] = [
      ...graphData.nodes.map((n) => ({
        data: {
          id: n.id,
          label: n.label,
          category: n.category,
          size: n.size,
          isEndpoint: n.isEndpoint,
          inCycle: n.inCycle,
          fullAddress: n.fullAddress,
          entityName: n.entityName,
          bridgeDetails: n.bridgeDetails,
          labels: n.labels,
          firstSeen: n.firstSeen,
          lastSeen: n.lastSeen,
          inflow: n.inflow,
          outflow: n.outflow,
          isCollapsedGroup: n.isCollapsedGroup,
          collapsedCount: n.collapsedCount,
        },
      })),
      ...graphData.edges.map((e) => ({
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
          value: e.value,
          width: e.width,
          inCycle: e.inCycle,
          isBridge: e.isBridge,
          lowConfirmation: e.lowConfirmation,
          txHash: e.txHash,
          chain: e.chain,
        },
      })),
    ];

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      boxSelectionEnabled: false,
      autounselectify: false,
      style: [
        // Base Node Style
        {
          selector: 'node',
          style: {
            'background-color': '#0f172a',
            'border-width': 2,
            'border-color': '#38bdf8',
            'label': 'data(label)',
            'color': '#f8fafc',
            'font-family': 'monospace',
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'text-wrap': 'wrap',
            'text-max-width': '130px',
            'width': 'data(size)',
            'height': 'data(size)',
          },
        },
        // Lead / Origin Flagged Address (Never use 'suspect')
        {
          selector: 'node[category = "lead"]',
          style: {
            'background-color': '#451a03',
            'border-color': '#f59e0b',
            'border-width': 3.5,
            'color': '#fde68a',
            'font-weight': 'bold',
          },
        },
        // Exchange / VASP Category (Emerald)
        {
          selector: 'node[category = "exchange"]',
          style: {
            'background-color': '#064e3b',
            'border-color': '#10b981',
            'border-width': 4,
            'color': '#a7f3d0',
            'font-weight': 'bold',
            'text-outline-color': '#0f172a',
            'text-outline-width': 2,
          },
        },
        // Mixer Category (Purple)
        {
          selector: 'node[category = "mixer"]',
          style: {
            'background-color': '#4c1d95',
            'border-color': '#a855f7',
            'border-width': 3.5,
            'color': '#f3e8ff',
            'font-weight': 'bold',
          },
        },
        // Sanctioned Category (Crimson)
        {
          selector: 'node[category = "sanctioned"]',
          style: {
            'background-color': '#7f1d1d',
            'border-color': '#ef4444',
            'border-width': 4,
            'color': '#fecaca',
            'font-weight': 'bold',
          },
        },
        // Bridge Category (Violet)
        {
          selector: 'node[category = "bridge"]',
          style: {
            'background-color': '#3b0764',
            'border-color': '#c084fc',
            'border-width': 3,
            'color': '#e9d5ff',
          },
        },
        // Unlabelled Intermediary (Slate/Sky)
        {
          selector: 'node[category = "unlabelled"]',
          style: {
            'background-color': '#1e293b',
            'border-color': '#64748b',
            'border-width': 2,
            'color': '#cbd5e1',
          },
        },
        // Terminal Endpoints Outlined (Double border, distinct outline)
        {
          selector: 'node[?isEndpoint]',
          style: {
            'border-width': 5,
            'border-style': 'double',
            'border-color': '#10b981',
          },
        },
        // Cycle Nodes Highlighted
        {
          selector: 'node[?inCycle]',
          style: {
            'border-color': '#f59e0b',
            'border-width': 4,
            'border-style': 'dashed',
          },
        },
        // Selected Node Highlight
        {
          selector: 'node:selected',
          style: {
            'border-color': '#60a5fa',
            'border-width': 6,
          },
        },
        // Base Edge Style (Width scaled by taint)
        {
          selector: 'edge',
          style: {
            'width': 'data(width)',
            'line-color': '#475569',
            'target-arrow-color': '#475569',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-family': 'monospace',
            'font-size': '9px',
            'color': '#94a3b8',
            'text-background-color': '#0b1120',
            'text-background-opacity': 0.85,
            'text-background-padding': '3px',
            'text-border-color': '#1e293b',
            'text-border-width': 1,
            'text-border-opacity': 0.8,
            'arrow-scale': 1.15,
          },
        },
        // Cycle Edges Highlighted (Amber Dashed)
        {
          selector: 'edge[?inCycle]',
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            'line-style': 'dashed',
            'color': '#fbbf24',
            'font-weight': 'bold',
            'arrow-scale': 1.3,
          },
        },
        // Bridge Edge
        {
          selector: 'edge[?isBridge]',
          style: {
            'line-color': '#c084fc',
            'target-arrow-color': '#c084fc',
            'line-style': 'dashed',
            'color': '#e9d5ff',
          },
        },
        // Low Confirmation Edge
        {
          selector: 'edge[?lowConfirmation]',
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            'line-style': 'dotted',
          },
        },
      ],
      layout: {
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 60,
        rankSep: 110,
        padding: 40,
        animate: true,
        animationDuration: 400,
      } as any,
    });

    cy.on('tap', 'node', (evt: EventObject) => {
      const node = evt.target;
      const data = node.data();
      setSelectedNode({
        id: data.id,
        label: data.label,
        category: data.category,
        value: data.value,
        size: data.size,
        isEndpoint: data.isEndpoint,
        inCycle: data.inCycle,
        fullAddress: data.fullAddress,
        entityName: data.entityName,
        bridgeDetails: data.bridgeDetails,
        labels: data.labels,
        firstSeen: data.firstSeen,
        lastSeen: data.lastSeen,
        inflow: data.inflow,
        outflow: data.outflow,
        isCollapsedGroup: data.isCollapsedGroup,
        collapsedCount: data.collapsedCount,
      });
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [graphData]);

  // Controls Handlers
  const handleZoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.25);
  const handleZoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() * 0.8);
  const handleFit = () => cyRef.current?.fit(undefined, 40);
  const handleResetLayout = () => {
    cyRef.current
      ?.layout({
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 60,
        rankSep: 110,
        padding: 40,
        animate: true,
        animationDuration: 300,
      } as any)
      .run();
  };

  // Export graph as PNG
  const handleExportPng = () => {
    if (!cyRef.current) return;
    const pngData = cyRef.current.png({ full: true, bg: '#0b1120', scale: 2 });
    const link = document.createElement('a');
    link.href = pngData;
    link.download = `cryptotrace_sentinel_graph_${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Export graph as JSON
  const handleExportJson = () => {
    if (!cyRef.current) return;
    const jsonStr = JSON.stringify(cyRef.current.json(), null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `cryptotrace_sentinel_graph_${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Public explorer link generator
  const getExplorerUrl = (address: string, networkChain: string) => {
    const c = (networkChain || chain).toUpperCase();
    if (c === 'ETH' || c === 'ETHEREUM') return `https://etherscan.io/address/${address}`;
    if (c === 'BTC' || c === 'BITCOIN') return `https://mempool.space/address/${address}`;
    if (c === 'TRON' || c === 'TRX') return `https://tronscan.org/#/address/${address}`;
    if (c === 'SOL' || c === 'SOLANA') return `https://solscan.io/account/${address}`;
    if (c === 'XRP' || c === 'XRPL') return `https://xrpscan.com/account/${address}`;
    if (c === 'POLYGON' || c === 'MATIC') return `https://polygonscan.com/address/${address}`;
    return `https://blockchair.com/search?q=${address}`;
  };

  return (
    <div
      role="region"
      aria-label="Blockchain Forensics Trace Graph"
      className="relative w-full h-[540px] bg-[#0b1120] rounded-xl border border-slate-800 overflow-hidden shadow-2xl flex flex-col"
    >
      {/* Top Bar: Legend, Stream Status, Performance Guard, and Toolbar Controls */}
      <div className="px-4 py-2.5 bg-[#0f172a]/95 backdrop-blur border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 z-10">
        {/* Left: Title & Stream Indicator */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          <span className="text-slate-300 font-semibold flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Forensic Trace Graph</span>
          </span>

          {isStreaming && (
            <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded bg-purple-950/60 border border-purple-500/40 text-purple-300 font-mono text-[11px] animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
              <span>SSE Trace Active (Hop {streamingHopIndex || paths.length})</span>
            </div>
          )}

          {/* Performance Guard Banner (Triggered above 1,500 nodes) */}
          {graphData.isCollapsed && (
            <div
              data-testid="performance-guard-banner"
              className="px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/40 text-amber-300 text-[10px] font-mono flex items-center gap-1 animate-pulse"
            >
              <AlertTriangle className="w-3 h-3" />
              <span>High density (&gt;1,500 nodes): collapsed low-value leaves for performance.</span>
            </div>
          )}
        </div>

        {/* Center: Legend Chips */}
        <div
          role="group"
          aria-label="Graph Legend"
          className="hidden lg:flex items-center space-x-3 text-[11px] font-mono"
        >
          <span className="flex items-center space-x-1.5" title="Origin flagged address (lead)">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 border border-amber-300"></span>
            <span className="text-amber-200">Origin Lead</span>
          </span>
          <span className="flex items-center space-x-1.5" title="Attributed Exchange / VASP">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 border border-emerald-300"></span>
            <span className="text-emerald-300">Exchange / VASP</span>
          </span>
          <span className="flex items-center space-x-1.5" title="Privacy mixer entity">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-500 border border-purple-300"></span>
            <span className="text-purple-300">Mixer</span>
          </span>
          <span className="flex items-center space-x-1.5" title="Sanctioned / illicit entity">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 border border-red-300"></span>
            <span className="text-red-300">Sanctioned</span>
          </span>
          <span className="flex items-center space-x-1.5" title="Unlabelled intermediary wallet">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-600 border border-slate-400"></span>
            <span className="text-slate-400">Unlabelled</span>
          </span>
          <span className="flex items-center space-x-1.5" title="Terminal off-ramp endpoint">
            <span className="w-3 h-3 rounded-full border-2 border-double border-emerald-400"></span>
            <span className="text-slate-300">Endpoint</span>
          </span>
          {graphData.cyclesDetected.length > 0 && (
            <span className="flex items-center space-x-1.5" title="Cycle loop detected">
              <span className="w-3 h-1 border-t-2 border-dashed border-amber-400"></span>
              <span className="text-amber-400 font-bold">Cycle Loop</span>
            </span>
          )}
        </div>

        {/* Right Toolbar: Replay, Zoom, Export, Text Summary */}
        <div
          role="toolbar"
          aria-label="Graph Canvas Controls"
          className="flex items-center space-x-1 bg-slate-900 border border-slate-800 rounded-lg p-1"
        >
          {onReplayTrace && (
            <button
              onClick={onReplayTrace}
              aria-label="Replay Live SSE Trace Stream"
              title="Replay SSE Live Trace Stream"
              className="px-2 py-1 text-xs font-mono bg-purple-900/40 hover:bg-purple-800/60 text-purple-300 border border-purple-500/40 rounded flex items-center space-x-1 transition-colors mr-1"
            >
              <RefreshCw className="w-3 h-3 animate-spin" />
              <span>Replay</span>
            </button>
          )}

          {/* Text Summary Accessible Button */}
          <button
            onClick={() => setShowSummaryModal(true)}
            aria-label="View Text Alternative Summary"
            title="Text Alternative Summary (Accessibility)"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <FileText className="w-3.5 h-3.5" />
          </button>

          {/* Export PNG */}
          <button
            onClick={handleExportPng}
            aria-label="Export Graph as PNG"
            title="Export Graph as PNG"
            className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-slate-800 rounded transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
          </button>

          {/* Export JSON */}
          <button
            onClick={handleExportJson}
            aria-label="Export Graph as JSON"
            title="Export Graph as JSON"
            className="p-1.5 text-slate-400 hover:text-blue-400 hover:bg-slate-800 rounded transition-colors"
          >
            <FileCode className="w-3.5 h-3.5" />
          </button>

          <div className="w-px h-4 bg-slate-800 mx-1"></div>

          <button
            onClick={handleZoomIn}
            aria-label="Zoom In"
            title="Zoom In"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleZoomOut}
            aria-label="Zoom Out"
            title="Zoom Out"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleFit}
            aria-label="Fit Graph to Screen"
            title="Fit to Screen"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleResetLayout}
            aria-label="Reset Dagre Layout"
            title="Reset Layout"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Time Filter Slider Strip */}
      {timestamps.length > 1 && (
        <div className="px-4 py-1.5 bg-slate-950/80 border-b border-slate-800/80 flex items-center justify-between gap-4 text-xs font-mono z-10">
          <div className="flex items-center space-x-2 text-slate-400 text-[11px]">
            <Sliders className="w-3 h-3 text-blue-400" />
            <span>Time Slider:</span>
            <span className="text-slate-200">
              {activeCutoffTime ? new Date(activeCutoffTime).toLocaleString() : 'Showing All Hops'}
            </span>
          </div>
          <div className="flex items-center space-x-3 flex-1 max-w-xs">
            <input
              type="range"
              min="10"
              max="100"
              value={timeCutoffIndex}
              onChange={(e) => setTimeCutoffIndex(Number(e.target.value))}
              aria-label="Time Cutoff Filter"
              className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
            />
            <span className="text-[10px] text-slate-500">{timeCutoffIndex}%</span>
          </div>
        </div>
      )}

      {/* Main Cytoscape Graph Canvas */}
      <div
        ref={containerRef}
        tabIndex={0}
        aria-label="Interactive multi-hop node canvas. Use mouse or touch to pan and zoom. Click a node to view forensic dossier."
        className="flex-1 w-full h-full cursor-grab active:cursor-grabbing focus:outline-none focus:ring-1 focus:ring-blue-500/40"
      />

      {/* Node Inspector Side Panel (Accessible with keyboard, ARIA attributes) */}
      {selectedNode && (
        <aside
          role="region"
          aria-label="Flagged Address Dossier"
          className="absolute top-14 right-4 bottom-4 w-80 md:w-96 bg-[#0f172a]/95 backdrop-blur border border-slate-700 rounded-xl p-4 shadow-2xl z-20 flex flex-col justify-between overflow-y-auto animate-in fade-in slide-in-from-right-2"
        >
          <div className="space-y-3">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-800 pb-2">
              <div className="flex items-center space-x-2">
                {selectedNode.category === 'lead' ? (
                  <div className="p-1.5 bg-amber-950/60 border border-amber-500/40 rounded text-amber-400">
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                ) : selectedNode.category === 'exchange' ? (
                  <div className="p-1.5 bg-emerald-950/60 border border-emerald-500/40 rounded text-emerald-400">
                    <Building2 className="w-4 h-4" />
                  </div>
                ) : selectedNode.category === 'mixer' ? (
                  <div className="p-1.5 bg-purple-950/60 border border-purple-500/40 rounded text-purple-400">
                    <Flame className="w-4 h-4" />
                  </div>
                ) : selectedNode.category === 'sanctioned' ? (
                  <div className="p-1.5 bg-red-950/60 border border-red-500/40 rounded text-red-400">
                    <AlertTriangle className="w-4 h-4" />
                  </div>
                ) : (
                  <div className="p-1.5 bg-blue-950/60 border border-blue-500/40 rounded text-blue-400">
                    <Info className="w-4 h-4" />
                  </div>
                )}
                <div>
                  <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                    {selectedNode.category === 'lead'
                      ? 'Flagged Origin Lead'
                      : selectedNode.category === 'exchange'
                      ? `VASP: ${selectedNode.entityName || 'Exchange Hot Wallet'}`
                      : selectedNode.category === 'mixer'
                      ? `Privacy Mixer: ${selectedNode.entityName || 'Anonymizing Pool'}`
                      : selectedNode.category === 'sanctioned'
                      ? 'Sanctioned / High Risk Entity'
                      : 'Intermediary Wallet'}
                  </h4>
                  <p className="text-[10px] text-slate-400 font-mono">Chain: {chain.toUpperCase()}</p>
                </div>
              </div>

              <button
                onClick={() => setSelectedNode(null)}
                aria-label="Close Flagged Address Dossier"
                className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Address Identifier with Copy Button */}
            <div className="bg-slate-950/80 rounded-lg p-2.5 border border-slate-800 font-mono text-[11px]">
              <div className="text-[10px] text-slate-500 uppercase font-bold mb-1">Address Identifier</div>
              <div className="flex items-center justify-between text-slate-300 break-all">
                <span>{selectedNode.fullAddress}</span>
                <button
                  onClick={() => copyToClipboard(selectedNode.fullAddress)}
                  aria-label="Copy Address"
                  title="Copy Address"
                  className="ml-2 p-1 text-slate-400 hover:text-blue-400 transition-colors shrink-0"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                </button>
              </div>
            </div>

            {/* Attribution Notice & Labels (MANDATORY: Attribution is not proof) */}
            <div className="p-2.5 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase font-bold text-slate-400">Intelligence &amp; Attribution</span>
                <span
                  data-testid="attribution-not-proof-notice"
                  className="text-[10px] font-mono text-amber-300 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/30"
                >
                  Attribution is not proof
                </span>
              </div>

              {selectedNode.labels && selectedNode.labels.length > 0 ? (
                <div className="space-y-1.5">
                  {selectedNode.labels.map((l, lIdx) => (
                    <div
                      key={lIdx}
                      className="p-1.5 rounded bg-blue-950/30 border border-blue-500/30 text-xs flex items-center justify-between"
                    >
                      <span className="font-semibold text-blue-300">{l.label}</span>
                      <span className="text-[10px] text-slate-400">
                        {l.source} ({Math.round(l.confidence * 100)}%)
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-slate-400 font-mono">
                  No public intelligence tag registered. Entity categorized via path topology and clustering heuristics.
                </p>
              )}
            </div>

            {/* Metrics: Inflow, Outflow, Seen Times */}
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="p-2 rounded bg-slate-950/60 border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Total Inflow</div>
                <div className="text-white font-bold mt-0.5">{selectedNode.inflow.toFixed(4)} {chain}</div>
              </div>
              <div className="p-2 rounded bg-slate-950/60 border border-slate-800">
                <div className="text-[10px] text-slate-500 uppercase">Total Outflow</div>
                <div className="text-white font-bold mt-0.5">{selectedNode.outflow.toFixed(4)} {chain}</div>
              </div>
            </div>

            {/* First & Last Seen */}
            {(selectedNode.firstSeen || selectedNode.lastSeen) && (
              <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800 font-mono text-[11px] space-y-1">
                {selectedNode.firstSeen && (
                  <div className="flex justify-between text-slate-400">
                    <span>First Seen:</span>
                    <span className="text-slate-200">{new Date(selectedNode.firstSeen).toLocaleDateString()}</span>
                  </div>
                )}
                {selectedNode.lastSeen && (
                  <div className="flex justify-between text-slate-400">
                    <span>Last Seen:</span>
                    <span className="text-slate-200">{new Date(selectedNode.lastSeen).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer Actions: Public Explorer Link */}
          <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
            <a
              href={getExplorerUrl(selectedNode.fullAddress, chain)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 font-mono transition-colors"
            >
              <span>View on Public Explorer</span>
              <ExternalLink className="w-3 h-3" />
            </a>

            <button
              onClick={() => setSelectedNode(null)}
              className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-mono transition-colors"
            >
              Close
            </button>
          </div>
        </aside>
      )}

      {/* Text Alternative Summary Modal (Mandatory for Accessibility) */}
      {showSummaryModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="summary-modal-title"
          className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm z-30 flex items-center justify-center p-4"
        >
          <div className="bg-[#0f172a] border border-slate-700 rounded-2xl max-w-lg w-full p-6 shadow-2xl space-y-4 font-mono text-xs">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-blue-400" />
                <h3 id="summary-modal-title" className="text-sm font-bold text-white uppercase tracking-wider">
                  Text Alternative Graph Summary
                </h3>
              </div>
              <button
                onClick={() => setShowSummaryModal(false)}
                aria-label="Close Summary Modal"
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2 text-slate-300">
              <div className="p-3 bg-slate-950/70 rounded-xl border border-slate-800 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-slate-400">Total Forensic Nodes:</span>
                  <span className="text-white font-bold">{graphData.summary.totalNodes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Total Transaction Edges:</span>
                  <span className="text-white font-bold">{graphData.summary.totalEdges}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Exchange / VASP Destinations:</span>
                  <span className="text-emerald-400 font-bold">{graphData.summary.exchangeNodes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Mixer Pools Detected:</span>
                  <span className="text-purple-400 font-bold">{graphData.summary.mixerNodes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Sanctioned / High Risk Nodes:</span>
                  <span className="text-red-400 font-bold">{graphData.summary.sanctionedNodes}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Terminal Endpoints (Outflow 0):</span>
                  <span className="text-white font-bold">{graphData.summary.endpointsCount}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Circular Fund Loops (Cycles):</span>
                  <span className={graphData.summary.cycleCount > 0 ? 'text-amber-400 font-bold' : 'text-slate-400'}>
                    {graphData.summary.cycleCount} detected
                  </span>
                </div>
              </div>

              {graphData.summary.endpointAddresses.length > 0 && (
                <div>
                  <div className="text-[11px] text-slate-400 font-bold mb-1">Terminal Off-Ramp Endpoints:</div>
                  <div className="max-h-24 overflow-y-auto space-y-1">
                    {graphData.summary.endpointAddresses.map((ep, idx) => (
                      <div key={idx} className="p-1 rounded bg-slate-900 border border-slate-800 text-[10px] break-all">
                        {ep}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowSummaryModal(false)}
                className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded font-sans text-xs font-semibold"
              >
                Close Summary
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
