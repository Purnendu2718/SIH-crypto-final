import React, { useEffect, useRef, useState } from 'react';
import cytoscape, { Core, EventObject } from 'cytoscape';
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
} from 'lucide-react';
import { TracePathItem } from '../lib/api';

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

interface SelectedNodeInfo {
  id: string;
  label: string;
  type: 'suspect' | 'intermediary' | 'vasp' | 'bridge';
  entityName?: string;
  inflow?: number;
  outflow?: number;
  txHash?: string;
  hopIndex?: number;
  bridgeDetails?: any;
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
  const [selectedNode, setSelectedNode] = useState<SelectedNodeInfo | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    if (!containerRef.current) return;

    // Collect unique addresses and edges
    const nodesMap = new Map<string, { id: string; label: string; type: 'suspect' | 'intermediary' | 'vasp' | 'bridge'; entityName?: string; bridgeDetails?: any }>();
    const edgesList: any[] = [];

    // Add root address - check if root is a known verified VASP
    const isRootEntity = attributionRule === 'ROOT_ADDRESS_IS_KNOWN_ENTITY' ||
      (paths.length === 0 && Boolean(matchedEntity) && matchedEntity !== 'Insufficient Evidence');

    nodesMap.set(startAddress.toLowerCase(), {
      id: startAddress.toLowerCase(),
      label: isRootEntity
        ? `${matchedEntity}\n(${startAddress.slice(0, 6)}...${startAddress.slice(-4)})\n(Known VASP Root)`
        : `${startAddress.slice(0, 6)}...${startAddress.slice(-4)}\n(Suspect Root)`,
      type: isRootEntity ? 'vasp' : 'suspect',
      entityName: isRootEntity ? matchedEntity : undefined,
    });

    paths.forEach((p, idx) => {
      const fromLower = p.from_addr.toLowerCase();
      const toLower = p.to_addr.toLowerCase();
      const isLastHop = idx === paths.length - 1;

      if (!nodesMap.has(fromLower)) {
        nodesMap.set(fromLower, {
          id: fromLower,
          label: `${p.from_addr.slice(0, 6)}...${p.from_addr.slice(-4)}`,
          type: fromLower === startAddress.toLowerCase() ? 'suspect' : 'intermediary',
        });
      }

      if (!nodesMap.has(toLower)) {
        const isVasp = isLastHop && matchedEntity && matchedEntity !== 'Insufficient Evidence';
        const isBridge = Boolean(p.is_bridge);

        let nodeType: 'suspect' | 'intermediary' | 'vasp' | 'bridge' = 'intermediary';
        let label = `${p.to_addr.slice(0, 6)}...${p.to_addr.slice(-4)}`;
        let entityName = undefined;

        if (isBridge) {
          nodeType = 'bridge';
          const bridgeName = p.bridge_details?.bridge_name || 'Cross-Chain Bridge';
          const destChain = p.bridge_details?.destination_chain || 'Cross-Chain';
          label = `🌉 ${bridgeName}\n(To: ${destChain})`;
          entityName = bridgeName;
        } else if (isVasp) {
          nodeType = 'vasp';
          label = `${matchedEntity}\n(VASP Hot Wallet)`;
          entityName = matchedEntity;
        }

        nodesMap.set(toLower, {
          id: toLower,
          label,
          type: nodeType,
          entityName,
          bridgeDetails: p.bridge_details,
        });
      }

      const isAttributionHop = p.is_attribution_hop || isLastHop;
      const isLowConf = Boolean(p.low_confirmation || (p.confirmations !== undefined && p.confirmations < 3) || p.is_pending);
      const isBridge = Boolean(p.is_bridge);
      const confTag = isLowConf ? ' [⚠️ <3 confs]' : '';
      const bridgeTag = isBridge ? ' [🌉 Bridge]' : '';

      edgesList.push({
        data: {
          id: `edge-${idx}-${fromLower}-${toLower}`,
          source: fromLower,
          target: toLower,
          value: p.value,
          label: isAttributionHop ? `★ ${p.value} ${p.chain || chain}${bridgeTag}${confTag}` : `${p.value} ${p.chain || chain}${bridgeTag}${confTag}`,
          txHash: p.tx_hash,
          hopIndex: p.hop_index,
          isAttributionHop,
          isBridge,
          lowConfirmation: isLowConf,
          confirmations: p.confirmations,
        },
      });
    });

    const elements = [
      ...Array.from(nodesMap.values()).map((n) => ({
        data: {
          id: n.id,
          label: n.label,
          nodeType: n.type,
          entityName: n.entityName,
          bridgeDetails: n.bridgeDetails,
          fullAddress: n.id,
        },
      })),
      ...edgesList,
    ];

    // Initialize Cytoscape
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      boxSelectionEnabled: false,
      autounselectify: false,
      style: [
        {
          selector: 'node',
          style: {
            'background-color': '#1e293b',
            'border-width': 2,
            'border-color': '#38bdf8',
            'label': 'data(label)',
            'color': '#f8fafc',
            'font-family': 'monospace',
            'font-size': '10px',
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'text-wrap': 'wrap',
            'text-max-width': '120px',
            'width': 36,
            'height': 36,
          },
        },
        {
          selector: 'node[nodeType = "suspect"]',
          style: {
            'background-color': '#450a0a',
            'border-color': '#ef4444',
            'border-width': 3,
            'width': 44,
            'height': 44,
            'color': '#fca5a5',
            'font-weight': 'bold',
          },
        },
        {
          selector: 'node[nodeType = "vasp"]',
          style: {
            'background-color': '#451a03',
            'border-color': '#f59e0b',
            'border-width': 4,
            'width': 48,
            'height': 48,
            'color': '#fde68a',
            'font-weight': 'bold',
            'text-outline-color': '#0f172a',
            'text-outline-width': 2,
          },
        },
        {
          selector: 'node[nodeType = "bridge"]',
          style: {
            'background-color': '#3b0764',
            'border-color': '#c084fc',
            'border-width': 3,
            'width': 46,
            'height': 46,
            'color': '#f3e8ff',
            'font-weight': 'bold',
            'text-outline-color': '#0f172a',
            'text-outline-width': 2,
          },
        },
        {
          selector: 'edge',
          style: {
            'width': 2,
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
            'arrow-scale': 1.1,
          },
        },
        {
          selector: 'edge[?isBridge]',
          style: {
            'line-color': '#c084fc',
            'target-arrow-color': '#c084fc',
            'line-style': 'dashed',
            'width': 3.5,
            'color': '#e9d5ff',
            'text-background-color': '#2e1065',
            'text-border-color': '#a855f7',
          },
        },
        {
          selector: 'edge[?lowConfirmation]',
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            'line-style': 'dotted',
            'width': 2.5,
          },
        },
        {
          selector: 'edge[?isAttributionHop]',
          style: {
            'width': 4,
            'line-color': '#f59e0b',
            'line-style': 'dashed',
            'target-arrow-color': '#f59e0b',
            'color': '#fbbf24',
            'font-weight': 'bold',
            'arrow-scale': 1.4,
            'text-background-color': '#451a03',
            'text-border-color': '#f59e0b',
            'text-background-opacity': 0.95,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 5,
            'border-color': '#60a5fa',
          },
        },
      ],
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 50,
        spacingFactor: 1.8,
        animate: true,
        animationDuration: 500,
      },
    });

    cy.on('tap', 'node', (evt: EventObject) => {
      const node = evt.target;
      const data = node.data();
      setSelectedNode({
        id: data.fullAddress,
        label: data.label,
        type: data.nodeType,
        entityName: data.entityName,
        bridgeDetails: data.bridgeDetails,
      });
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [paths, startAddress, chain, matchedEntity]);

  const handleZoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.25);
  const handleZoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() * 0.8);
  const handleFit = () => cyRef.current?.fit(undefined, 40);
  const handleReset = () => {
    cyRef.current?.layout({
      name: 'breadthfirst',
      directed: true,
      padding: 50,
      spacingFactor: 1.8,
      animate: true,
      animationDuration: 400,
    }).run();
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative w-full h-[520px] bg-[#0b1120] rounded-xl border border-slate-800 overflow-hidden shadow-2xl flex flex-col">
      {/* Canvas Top Bar / Legend */}
      <div className="px-4 py-2.5 bg-[#0f172a]/90 backdrop-blur border-b border-slate-800 flex items-center justify-between z-10">
        <div className="flex items-center space-x-4 text-xs font-mono">
          <span className="text-slate-400 font-semibold flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Interactive Multi-Hop Graph</span>
          </span>

          {isStreaming && (
            <div className="flex items-center space-x-1.5 px-2 py-0.5 rounded bg-purple-950/60 border border-purple-500/40 text-purple-300 font-mono text-[11px] animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
              <span>WebSocket Stream Active (Hop {streamingHopIndex || paths.length})</span>
            </div>
          )}

          <div className="hidden sm:flex items-center space-x-3 text-[11px]">
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-600 border border-red-400"></span>
              <span className="text-slate-300">Suspect Source</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-600 border border-blue-400"></span>
              <span className="text-slate-300">Intermediary Hop</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-600 border border-purple-400"></span>
              <span className="text-purple-300">Cross-Chain Bridge</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 border border-amber-300"></span>
              <span className="text-slate-300">Target VASP Hot Wallet</span>
            </span>
            <span className="flex items-center space-x-1.5">
              <span className="w-4 h-0.5 bg-amber-400 border-b border-dashed border-amber-300"></span>
              <span className="text-amber-400 font-bold">Attribution Match Hop</span>
            </span>
          </div>
        </div>

        {/* Toolbar Controls */}
        <div className="flex items-center space-x-1 bg-slate-900 border border-slate-800 rounded-lg p-1">
          {onReplayTrace && (
            <button
              onClick={onReplayTrace}
              title="Replay WebSocket Live Trace Stream"
              className="px-2 py-1 text-xs font-mono bg-purple-900/40 hover:bg-purple-800/60 text-purple-300 border border-purple-500/40 rounded flex items-center space-x-1 transition-colors mr-1"
            >
              <span>⚡ Replay Stream</span>
            </button>
          )}
          <button
            onClick={handleZoomIn}
            title="Zoom In"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleZoomOut}
            title="Zoom Out"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleFit}
            title="Fit to Screen"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleReset}
            title="Rearrange Layout"
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Cytoscape Viewport */}
      <div ref={containerRef} className="flex-1 w-full h-full cursor-grab active:cursor-grabbing" />

      {/* Node Inspector Overlay */}
      {selectedNode && (
        <div className="absolute bottom-4 left-4 max-w-sm w-full bg-[#0f172a]/95 backdrop-blur border border-slate-700 rounded-xl p-4 shadow-2xl z-20 animate-in fade-in slide-in-from-bottom-2">
          <div className="flex items-start justify-between mb-2">
            <div className="flex items-center space-x-2">
              {selectedNode.type === 'suspect' ? (
                <div className="p-1.5 bg-red-950/60 border border-red-500/40 rounded text-red-400">
                  <AlertTriangle className="w-4 h-4" />
                </div>
              ) : selectedNode.type === 'vasp' ? (
                <div className="p-1.5 bg-amber-950/60 border border-amber-500/40 rounded text-amber-400">
                  <Building2 className="w-4 h-4" />
                </div>
              ) : selectedNode.type === 'bridge' ? (
                <div className="p-1.5 bg-purple-950/60 border border-purple-500/40 rounded text-purple-400">
                  <span className="text-sm">🌉</span>
                </div>
              ) : (
                <div className="p-1.5 bg-blue-950/60 border border-blue-500/40 rounded text-blue-400">
                  <Info className="w-4 h-4" />
                </div>
              )}
              <div>
                <h4 className="text-xs font-bold text-white uppercase tracking-wider">
                  {selectedNode.type === 'suspect'
                    ? 'Reported Suspect Source'
                    : selectedNode.type === 'vasp'
                    ? `Identified VASP: ${selectedNode.entityName}`
                    : selectedNode.type === 'bridge'
                    ? `Cross-Chain Bridge: ${selectedNode.entityName}`
                    : 'Intermediary Layering Node'}
                </h4>
                <p className="text-[10px] text-slate-400 font-mono">Chain: {chain}</p>
              </div>
            </div>

            <button
              onClick={() => setSelectedNode(null)}
              className="text-slate-400 hover:text-white text-xs font-bold px-1"
            >
              &times;
            </button>
          </div>

          <div className="bg-slate-950/80 rounded-lg p-2.5 border border-slate-800/80 my-2">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-300 break-all">
              <span>{selectedNode.id}</span>
              <button
                onClick={() => copyToClipboard(selectedNode.id)}
                className="ml-2 p-1 text-slate-400 hover:text-blue-400 transition-colors"
                title="Copy Address"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {selectedNode.type === 'vasp' && (
            <div className="mt-2 text-[11px] text-amber-300/90 bg-amber-950/30 border border-amber-500/20 rounded p-2">
              Attribution Match: <strong>{matchedEntity}</strong> ({Math.round((confidence || 0) * 100)}% Confidence)
              <div className="text-[10px] text-slate-400 font-mono mt-0.5">Rule: {attributionRule}</div>
            </div>
          )}

          {selectedNode.type === 'bridge' && (
            <div className="mt-2 text-[11px] text-purple-300/90 bg-purple-950/40 border border-purple-500/30 rounded p-2.5">
              <div className="font-bold flex items-center space-x-1 text-purple-200">
                <span>🌉 {selectedNode.entityName || 'Cross-Chain Bridge Gateway'}</span>
              </div>
              {selectedNode.bridgeDetails && (
                <div className="text-[10px] text-slate-300 font-mono mt-1 space-y-0.5">
                  <div>Destination Chain: <span className="text-purple-400 font-bold">{selectedNode.bridgeDetails.destination_chain}</span></div>
                  <div>Decoding Rule: <span className="text-slate-400">{selectedNode.bridgeDetails.decoding_rule}</span></div>
                  {selectedNode.bridgeDetails.recipient && (
                    <div>Forward Recipient: <span className="text-purple-300 break-all">{selectedNode.bridgeDetails.recipient}</span></div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
