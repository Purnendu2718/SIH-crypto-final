/**
 * Graph Data Transform Module for Cytoscape.js
 * Reference: SIH26183, Phase 6 Specification
 *
 * Computes:
 * - Node size by cumulative transfer value
 * - Node color/category: exchange, mixer, sanctioned, unlabelled, lead, bridge
 * - Edge width by taint percentage
 * - Edge heuristic badges (SWEEP, FAN_OUT, MIXER, BRIDGE, LOW_CONF, etc.)
 * - Cycle detection and highlighting
 * - Endpoint identification and outlines
 * - Performance guard: collapses low-value leaf nodes if total nodes > 1,500
 * - Text alternative summary for accessibility
 */

import { TracePathItem } from './api';
export type { TracePathItem };

export type NodeCategory = 'lead' | 'exchange' | 'mixer' | 'sanctioned' | 'unlabelled' | 'bridge';

export interface GraphNodeData {
  id: string;
  label: string;
  category: NodeCategory;
  value: number;
  size: number;
  isEndpoint: boolean;
  inCycle: boolean;
  fullAddress: string;
  entityName?: string;
  labels?: Array<{ label: string; source: string; confidence: number }>;
  firstSeen?: string;
  lastSeen?: string;
  inflow: number;
  outflow: number;
  bridgeDetails?: any;
  isCollapsedGroup?: boolean;
  collapsedCount?: number;
}

export interface GraphEdgeData {
  id: string;
  source: string;
  target: string;
  value: number;
  width: number;
  taintPercentage: number;
  heuristicBadge?: string;
  label: string;
  txHash: string;
  chain: string;
  inCycle: boolean;
  isBridge: boolean;
  lowConfirmation: boolean;
  timestamp?: string;
}

export interface TransformedGraph {
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
  cyclesDetected: string[][];
  endpoints: string[];
  isCollapsed: boolean;
  totalNodeCount: number;
  summary: {
    totalNodes: number;
    totalEdges: number;
    exchangeNodes: number;
    mixerNodes: number;
    sanctionedNodes: number;
    unlabelledNodes: number;
    cycleCount: number;
    endpointsCount: number;
    cyclesSummary: string;
    endpointAddresses: string[];
  };
}

export interface TransformOptions {
  paths: TracePathItem[];
  startAddress: string;
  chain?: string;
  matchedEntity?: string;
  attributionRule?: string;
  confidence?: number;
  timeCutoff?: string; // Optional time filter
  maxNodesThreshold?: number; // Defaults to 1500
}

/**
 * Detect cycles in directed graph using Tarjan's / DFS approach.
 */
export function detectCycles(adjacency: Map<string, string[]>): string[][] {
  const visited = new Set<string>();
  const recursionStack = new Set<string>();
  const currentPath: string[] = [];
  const cycles: string[][] = [];

  function dfs(node: string) {
    visited.add(node);
    recursionStack.add(node);
    currentPath.push(node);

    const neighbors = adjacency.get(node) || [];
    for (const neighbor of neighbors) {
      if (!visited.has(neighbor)) {
        dfs(neighbor);
      } else if (recursionStack.has(neighbor)) {
        // Cycle detected
        const cycleStartIndex = currentPath.indexOf(neighbor);
        if (cycleStartIndex !== -1) {
          cycles.push(currentPath.slice(cycleStartIndex).concat(neighbor));
        }
      }
    }

    currentPath.pop();
    recursionStack.delete(node);
  }

  for (const node of adjacency.keys()) {
    if (!visited.has(node)) {
      dfs(node);
    }
  }

  return cycles;
}

/**
 * Categorize address into entity category.
 */
export function determineCategory(
  _address: string,
  isStart: boolean,
  isVasp: boolean,
  isBridge: boolean,
  labels?: Array<{ label: string; source: string }>,
  entityName?: string
): NodeCategory {
  if (isStart) return 'lead';
  if (isBridge) return 'bridge';
  if (isVasp) return 'exchange';

  const lowerEntity = (entityName || '').toLowerCase();
  if (lowerEntity.includes('mixer') || lowerEntity.includes('tornado') || lowerEntity.includes('coinjoin')) {
    return 'mixer';
  }
  if (lowerEntity.includes('sanction') || lowerEntity.includes('ofac') || lowerEntity.includes('illicit')) {
    return 'sanctioned';
  }
  if (lowerEntity.includes('binance') || lowerEntity.includes('wazirx') || lowerEntity.includes('coinbase') || lowerEntity.includes('exchange')) {
    return 'exchange';
  }

  if (labels && labels.length > 0) {
    for (const l of labels) {
      const lowerL = l.label.toLowerCase();
      if (lowerL.includes('mixer') || lowerL.includes('tumbler')) return 'mixer';
      if (lowerL.includes('sanction') || lowerL.includes('scam') || lowerL.includes('phishing')) return 'sanctioned';
      if (lowerL.includes('exchange') || lowerL.includes('deposit') || lowerL.includes('hot wallet')) return 'exchange';
    }
  }

  return 'unlabelled';
}

/**
 * Calculate node size based on value (between 32px and 76px).
 */
export function calculateNodeSize(value: number, maxValue: number): number {
  if (maxValue <= 0 || value <= 0) return 36;
  const scaled = Math.log10(value + 1) / Math.log10(maxValue + 1);
  return Math.round(36 + Math.min(40, scaled * 40));
}

/**
 * Calculate edge width based on taint percentage (between 2px and 8px).
 */
export function calculateEdgeWidth(taintPercentage: number): number {
  const clamped = Math.max(0, Math.min(100, taintPercentage));
  return Number((2 + (clamped / 100) * 6).toFixed(1));
}

/**
 * Main Pure Graph Transformer
 */
export function transformTraceToGraph(options: TransformOptions): TransformedGraph {
  const {
    paths,
    startAddress,
    chain = 'ETH',
    matchedEntity,
    attributionRule,
    confidence = 0,
    timeCutoff,
    maxNodesThreshold = 1500,
  } = options;

  const startLower = (startAddress || '').trim().toLowerCase();

  // Filter paths by time if timeCutoff provided
  let filteredPaths = paths;
  if (timeCutoff) {
    const cutoffDate = new Date(timeCutoff).getTime();
    filteredPaths = paths.filter((p) => {
      if (!p.timestamp) return true;
      return new Date(p.timestamp).getTime() <= cutoffDate;
    });
  }

  // Build adjacency list for cycle detection
  const adjacency = new Map<string, string[]>();
  const inDegree = new Map<string, number>();
  const outDegree = new Map<string, number>();
  const nodeValues = new Map<string, number>();
  const nodeInflow = new Map<string, number>();
  const nodeOutflow = new Map<string, number>();
  const nodeTimestamps = new Map<string, { first?: string; last?: string }>();

  // Ensure start node exists in tracking
  if (startLower) {
    adjacency.set(startLower, []);
    inDegree.set(startLower, 0);
    outDegree.set(startLower, 0);
    nodeValues.set(startLower, 0);
  }

  filteredPaths.forEach((p) => {
    const fromLower = (p.from_addr || '').trim().toLowerCase();
    const toLower = (p.to_addr || '').trim().toLowerCase();
    const val = Number(p.value) || 0;

    if (!adjacency.has(fromLower)) adjacency.set(fromLower, []);
    if (!adjacency.has(toLower)) adjacency.set(toLower, []);
    adjacency.get(fromLower)!.push(toLower);

    if (!outDegree.has(fromLower)) outDegree.set(fromLower, 0);
    if (!outDegree.has(toLower)) outDegree.set(toLower, 0);
    if (!inDegree.has(fromLower)) inDegree.set(fromLower, 0);
    if (!inDegree.has(toLower)) inDegree.set(toLower, 0);

    outDegree.set(fromLower, (outDegree.get(fromLower) || 0) + 1);
    inDegree.set(toLower, (inDegree.get(toLower) || 0) + 1);

    nodeValues.set(fromLower, (nodeValues.get(fromLower) || 0) + val);
    nodeValues.set(toLower, (nodeValues.get(toLower) || 0) + val);

    nodeOutflow.set(fromLower, (nodeOutflow.get(fromLower) || 0) + val);
    nodeInflow.set(toLower, (nodeInflow.get(toLower) || 0) + val);

    if (p.timestamp) {
      const fromTs = nodeTimestamps.get(fromLower) || {};
      if (!fromTs.first || p.timestamp < fromTs.first) fromTs.first = p.timestamp;
      if (!fromTs.last || p.timestamp > fromTs.last) fromTs.last = p.timestamp;
      nodeTimestamps.set(fromLower, fromTs);

      const toTs = nodeTimestamps.get(toLower) || {};
      if (!toTs.first || p.timestamp < toTs.first) toTs.first = p.timestamp;
      if (!toTs.last || p.timestamp > toTs.last) toTs.last = p.timestamp;
      nodeTimestamps.set(toLower, toTs);
    }
  });

  // Cycle detection
  const cycles = detectCycles(adjacency);
  const cycleNodes = new Set<string>();
  const cycleEdges = new Set<string>();

  cycles.forEach((cycle) => {
    for (let i = 0; i < cycle.length; i++) {
      cycleNodes.add(cycle[i]);
      if (i < cycle.length - 1) {
        cycleEdges.add(`${cycle[i]}->${cycle[i + 1]}`);
      }
    }
  });

  // Max value calculation for node scaling
  const maxValue = Math.max(...Array.from(nodeValues.values()), 1);

  // Performance Guard: Collapse low-value leaves if > maxNodesThreshold
  const totalUniqueNodes = adjacency.size;
  const isCollapsed = totalUniqueNodes > maxNodesThreshold;
  const collapsedLeafNodes = new Set<string>();

  if (isCollapsed) {
    for (const [addr, outCount] of outDegree.entries()) {
      if (outCount === 0 && addr !== startLower) {
        const val = nodeValues.get(addr) || 0;
        // Low-value leaf (under 5% of max value)
        if (val < maxValue * 0.05) {
          collapsedLeafNodes.add(addr);
        }
      }
    }
  }

  // Endpoints: Out-degree = 0 and in-degree > 0
  const endpoints: string[] = [];
  for (const [addr, outCount] of outDegree.entries()) {
    if (outCount === 0 && (inDegree.get(addr) || 0) > 0) {
      endpoints.push(addr);
    }
  }

  // Build nodes
  const nodes: GraphNodeData[] = [];
  const processedNodes = new Set<string>();

  // Add start node first
  if (startLower) {
    const isRootEntity =
      attributionRule === 'ROOT_ADDRESS_IS_KNOWN_ENTITY' ||
      (filteredPaths.length === 0 && Boolean(matchedEntity) && matchedEntity !== 'Insufficient Evidence');

    const cat = isRootEntity ? 'exchange' : 'lead';
    const val = nodeValues.get(startLower) || 0;

    nodes.push({
      id: startLower,
      label: isRootEntity
        ? `${matchedEntity}\n(${startLower.slice(0, 6)}...${startLower.slice(-4)})\n(Known VASP)`
        : `${startLower.slice(0, 6)}...${startLower.slice(-4)}\n(Flagged Lead)`,
      category: cat,
      value: val,
      size: calculateNodeSize(val, maxValue),
      isEndpoint: endpoints.includes(startLower),
      inCycle: cycleNodes.has(startLower),
      fullAddress: startLower,
      entityName: isRootEntity ? matchedEntity : undefined,
      labels: isRootEntity && matchedEntity
        ? [{ label: matchedEntity, source: 'VASP Directory', confidence: confidence || 0.95 }]
        : undefined,
      inflow: nodeInflow.get(startLower) || 0,
      outflow: nodeOutflow.get(startLower) || 0,
      firstSeen: nodeTimestamps.get(startLower)?.first,
      lastSeen: nodeTimestamps.get(startLower)?.last,
    });
    processedNodes.add(startLower);
  }

  // Build other nodes and edges
  const edges: GraphEdgeData[] = [];

  filteredPaths.forEach((p, idx) => {
    const fromLower = (p.from_addr || '').trim().toLowerCase();
    const toLower = (p.to_addr || '').trim().toLowerCase();
    const val = Number(p.value) || 0;
    const isLastHop = idx === filteredPaths.length - 1;
    const isAttributionHop = Boolean(p.is_attribution_hop || isLastHop);
    const isBridge = Boolean(p.is_bridge);
    const isLowConf = Boolean(p.low_confirmation || (p.confirmations !== undefined && p.confirmations < 3) || p.is_pending);

    // Skip creating individual leaf if collapsed
    if (isCollapsed && collapsedLeafNodes.has(toLower)) {
      return;
    }

    if (!processedNodes.has(fromLower)) {
      const fromVal = nodeValues.get(fromLower) || 0;
      const cat = determineCategory(fromLower, fromLower === startLower, false, false);
      nodes.push({
        id: fromLower,
        label: `${fromLower.slice(0, 6)}...${fromLower.slice(-4)}`,
        category: cat,
        value: fromVal,
        size: calculateNodeSize(fromVal, maxValue),
        isEndpoint: endpoints.includes(fromLower),
        inCycle: cycleNodes.has(fromLower),
        fullAddress: fromLower,
        inflow: nodeInflow.get(fromLower) || 0,
        outflow: nodeOutflow.get(fromLower) || 0,
        firstSeen: nodeTimestamps.get(fromLower)?.first,
        lastSeen: nodeTimestamps.get(fromLower)?.last,
      });
      processedNodes.add(fromLower);
    }

    if (!processedNodes.has(toLower)) {
      const toVal = nodeValues.get(toLower) || 0;
      const isVasp = isLastHop && Boolean(matchedEntity) && matchedEntity !== 'Insufficient Evidence';
      const entity = isBridge ? p.bridge_details?.bridge_name : isVasp ? matchedEntity : undefined;
      const cat = determineCategory(toLower, false, isVasp, isBridge, undefined, entity);

      let label = `${toLower.slice(0, 6)}...${toLower.slice(-4)}`;
      if (isBridge) {
        label = `🌉 ${entity || 'Bridge'}\n(To: ${p.bridge_details?.destination_chain || 'Cross-Chain'})`;
      } else if (isVasp) {
        label = `${matchedEntity}\n(Attributed VASP)`;
      }

      nodes.push({
        id: toLower,
        label,
        category: cat,
        value: toVal,
        size: calculateNodeSize(toVal, maxValue),
        isEndpoint: endpoints.includes(toLower),
        inCycle: cycleNodes.has(toLower),
        fullAddress: toLower,
        entityName: entity,
        bridgeDetails: p.bridge_details,
        labels: isVasp && matchedEntity
          ? [{ label: matchedEntity, source: 'Attribution Engine', confidence: confidence || 0.85 }]
          : undefined,
        inflow: nodeInflow.get(toLower) || 0,
        outflow: nodeOutflow.get(toLower) || 0,
        firstSeen: nodeTimestamps.get(toLower)?.first,
        lastSeen: nodeTimestamps.get(toLower)?.last,
      });
      processedNodes.add(toLower);
    }

    // Heuristic tag badge
    let heuristicBadge: string | undefined = undefined;
    if (isBridge) heuristicBadge = 'BRIDGE';
    else if (isAttributionHop) heuristicBadge = 'SWEEP';
    else if (isLowConf) heuristicBadge = 'LOW_CONF';

    // Taint percentage (default to 100% on first hop decaying across hops if not given)
    const taintPercentage = (p as any).taint_percentage !== undefined
      ? Number((p as any).taint_percentage)
      : Math.max(20, Math.round(100 - (p.hop_index || idx + 1) * 15));

    const edgeCycle = cycleEdges.has(`${fromLower}->${toLower}`);

    edges.push({
      id: `edge-${idx}-${fromLower}-${toLower}`,
      source: fromLower,
      target: toLower,
      value: val,
      width: calculateEdgeWidth(taintPercentage),
      taintPercentage,
      heuristicBadge,
      label: heuristicBadge ? `[${heuristicBadge}] ${val} ${p.chain || chain}` : `${val} ${p.chain || chain}`,
      txHash: p.tx_hash,
      chain: p.chain || chain,
      inCycle: edgeCycle,
      isBridge,
      lowConfirmation: isLowConf,
      timestamp: p.timestamp,
    });
  });

  // If collapsed leaves exist, add cluster node
  if (isCollapsed && collapsedLeafNodes.size > 0) {
    const clusterId = 'cluster_collapsed_leaves';
    nodes.push({
      id: clusterId,
      label: `Collapsed Leaves\n(${collapsedLeafNodes.size} low-value addresses)`,
      category: 'unlabelled',
      value: 0,
      size: 44,
      isEndpoint: true,
      inCycle: false,
      fullAddress: clusterId,
      isCollapsedGroup: true,
      collapsedCount: collapsedLeafNodes.size,
      inflow: 0,
      outflow: 0,
    });
  }

  // Summary counts for accessibility
  const exchangeCount = nodes.filter((n) => n.category === 'exchange').length;
  const mixerCount = nodes.filter((n) => n.category === 'mixer').length;
  const sanctionedCount = nodes.filter((n) => n.category === 'sanctioned').length;
  const unlabelledCount = nodes.filter((n) => n.category === 'unlabelled').length;

  return {
    nodes,
    edges,
    cyclesDetected: cycles,
    endpoints,
    isCollapsed,
    totalNodeCount: totalUniqueNodes,
    summary: {
      totalNodes: nodes.length,
      totalEdges: edges.length,
      exchangeNodes: exchangeCount,
      mixerNodes: mixerCount,
      sanctionedNodes: sanctionedCount,
      unlabelledNodes: unlabelledCount,
      cycleCount: cycles.length,
      endpointsCount: endpoints.length,
      cyclesSummary: cycles.length > 0 ? `${cycles.length} circular flow cycle(s) detected` : 'No circular cycles detected',
      endpointAddresses: endpoints,
    },
  };
}
