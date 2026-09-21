import { describe, it, expect } from 'vitest';
import {
  calculateNodeSize,
  calculateEdgeWidth,
  determineCategory,
  detectCycles,
  transformTraceToGraph,
  TracePathItem,
} from '../lib/graphTransform';

describe('Graph Transform Unit Tests', () => {
  describe('calculateNodeSize', () => {
    it('returns minimum size 36 for zero or negative values', () => {
      expect(calculateNodeSize(0, 100)).toBe(36);
      expect(calculateNodeSize(-5, 100)).toBe(36);
    });

    it('scales logarithmically up to maximum size 76', () => {
      const minSize = calculateNodeSize(1, 1000);
      const maxSize = calculateNodeSize(1000, 1000);
      expect(minSize).toBeGreaterThanOrEqual(36);
      expect(maxSize).toBe(76);
      expect(maxSize).toBeGreaterThan(minSize);
    });
  });

  describe('calculateEdgeWidth', () => {
    it('scales edge width from 2px at 0% taint to 8px at 100% taint', () => {
      expect(calculateEdgeWidth(0)).toBe(2);
      expect(calculateEdgeWidth(50)).toBe(5);
      expect(calculateEdgeWidth(100)).toBe(8);
    });

    it('clamps values below 0 and above 100', () => {
      expect(calculateEdgeWidth(-10)).toBe(2);
      expect(calculateEdgeWidth(150)).toBe(8);
    });
  });

  describe('determineCategory', () => {
    it('identifies lead address', () => {
      expect(determineCategory('0x123', true, false, false)).toBe('lead');
    });

    it('identifies bridge contract', () => {
      expect(determineCategory('0xbridge', false, false, true)).toBe('bridge');
    });

    it('identifies exchange from VASP flag or entity name', () => {
      expect(determineCategory('0xvasp', false, true, false)).toBe('exchange');
      expect(determineCategory('0xbinance', false, false, false, [], 'Binance Hot Wallet')).toBe('exchange');
    });

    it('identifies mixer from keywords', () => {
      expect(determineCategory('0xmixer', false, false, false, [], 'Tornado Cash Proxy')).toBe('mixer');
      expect(
        determineCategory('0xmixer2', false, false, false, [{ label: 'Tornado.Cash: Mixer', source: 'Etherscan' }])
      ).toBe('mixer');
    });

    it('identifies sanctioned from labels', () => {
      expect(
        determineCategory('0xsanction', false, false, false, [{ label: 'OFAC Sanctioned Entity', source: 'Chainalysis' }])
      ).toBe('sanctioned');
    });

    it('defaults to unlabelled', () => {
      expect(determineCategory('0xplain', false, false, false)).toBe('unlabelled');
    });
  });

  describe('detectCycles', () => {
    it('detects simple cycles in directed adjacency graph', () => {
      const adj = new Map<string, string[]>([
        ['A', ['B']],
        ['B', ['C']],
        ['C', ['A']],
      ]);
      const cycles = detectCycles(adj);
      expect(cycles.length).toBeGreaterThan(0);
      expect(cycles[0]).toEqual(['A', 'B', 'C', 'A']);
    });

    it('returns empty array when no cycles exist', () => {
      const adj = new Map<string, string[]>([
        ['A', ['B']],
        ['B', ['C']],
        ['C', []],
      ]);
      const cycles = detectCycles(adj);
      expect(cycles).toEqual([]);
    });
  });

  describe('transformTraceToGraph', () => {
    const mockPaths: TracePathItem[] = [
      {
        hop_index: 1,
        from_addr: '0xseed1111',
        to_addr: '0xinter2222',
        value: 10.5,
        tx_hash: '0xtx1',
        timestamp: '2026-03-01T10:00:00Z',
      },
      {
        hop_index: 2,
        from_addr: '0xinter2222',
        to_addr: '0xvasp3333',
        value: 10.2,
        tx_hash: '0xtx2',
        timestamp: '2026-03-01T10:30:00Z',
        is_attribution_hop: true,
      },
    ];

    it('transforms paths into nodes and edges with endpoints identified', () => {
      const result = transformTraceToGraph({
        paths: mockPaths,
        startAddress: '0xseed1111',
        matchedEntity: 'WazirX India',
      });

      expect(result.nodes.length).toBe(3);
      expect(result.edges.length).toBe(2);

      // Start node
      const seedNode = result.nodes.find((n) => n.id === '0xseed1111');
      expect(seedNode).toBeDefined();
      expect(seedNode?.category).toBe('lead');
      expect(seedNode?.isEndpoint).toBe(false);

      // Endpoint node (0xvasp3333 has outDegree 0)
      const endpointNode = result.nodes.find((n) => n.id === '0xvasp3333');
      expect(endpointNode).toBeDefined();
      expect(endpointNode?.isEndpoint).toBe(true);
      expect(result.endpoints).toContain('0xvasp3333');

      // Summary
      expect(result.summary.totalNodes).toBe(3);
      expect(result.summary.totalEdges).toBe(2);
      expect(result.summary.endpointsCount).toBe(1);
    });

    it('identifies cycle nodes and flags them', () => {
      const cyclicPaths: TracePathItem[] = [
        {
          hop_index: 1,
          from_addr: '0xa',
          to_addr: '0xb',
          value: 5,
          tx_hash: '0xtx1',
        },
        {
          hop_index: 2,
          from_addr: '0xb',
          to_addr: '0xc',
          value: 4.8,
          tx_hash: '0xtx2',
        },
        {
          hop_index: 3,
          from_addr: '0xc',
          to_addr: '0xa',
          value: 4.5,
          tx_hash: '0xtx3',
        },
      ];

      const result = transformTraceToGraph({
        paths: cyclicPaths,
        startAddress: '0xa',
      });

      expect(result.summary.cycleCount).toBeGreaterThan(0);
      const nodeA = result.nodes.find((n) => n.id === '0xa');
      expect(nodeA?.inCycle).toBe(true);
      const edgeCA = result.edges.find((e) => e.source === '0xc' && e.target === '0xa');
      expect(edgeCA?.inCycle).toBe(true);
    });

    it('activates performance collapse guard when total nodes exceed maxNodesThreshold', () => {
      // Create 15 leaf nodes connected to a central node, with threshold = 10
      const generatedPaths: TracePathItem[] = [];
      for (let i = 0; i < 15; i++) {
        generatedPaths.push({
          hop_index: 1,
          from_addr: '0xseed',
          to_addr: `0xleaf_${i}`,
          value: 0.001, // low value
          tx_hash: `0xtx_${i}`,
        });
      }

      // Add one high value hop to establish high max value
      generatedPaths.push({
        hop_index: 1,
        from_addr: '0xseed',
        to_addr: '0xmain_hub',
        value: 500,
        tx_hash: '0xtx_main',
      });

      const result = transformTraceToGraph({
        paths: generatedPaths,
        startAddress: '0xseed',
        maxNodesThreshold: 10,
      });

      expect(result.isCollapsed).toBe(true);
      // Low value leaves collapsed into a group
      const collapsedNode = result.nodes.find((n) => n.isCollapsedGroup);
      expect(collapsedNode).toBeDefined();
      expect(collapsedNode?.collapsedCount).toBeGreaterThan(0);
    });
  });
});
