import React, { useState, useRef } from 'react';
import { Play, Square, Zap, AlertCircle } from 'lucide-react';
import { api, TracePathItem } from '../lib/api';

interface TraceFormComponentProps {
  initialSeedAddress: string;
  initialChain?: string;
  caseId?: string;
  onTraceStarted: (data: any) => void;
  onHopDiscovered: (hop: TracePathItem) => void;
  onTraceCompleted: (data: any) => void;
  onError: (err: any) => void;
  isStreaming: boolean;
  setIsStreaming: (streaming: boolean) => void;
  streamingHopCount: number;
  streamingStatus: string;
  setStreamingStatus: (status: string) => void;
}

export const TraceFormComponent: React.FC<TraceFormComponentProps> = ({
  initialSeedAddress,
  initialChain = 'ETH',
  caseId,
  onTraceStarted,
  onHopDiscovered,
  onTraceCompleted,
  onError,
  isStreaming,
  setIsStreaming,
  streamingHopCount,
  streamingStatus,
  setStreamingStatus,
}) => {
  const [seedAddress, setSeedAddress] = useState<string>(initialSeedAddress || '');
  const [chain, setChain] = useState<string>(initialChain || 'ETH');
  const [maxHops, setMaxHops] = useState<number>(3);
  const [minAmount, setMinAmount] = useState<string>('0.0');
  const [taintModel, setTaintModel] = useState<string>('FIFO');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [formError, setFormError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);

  const handleStartSSETrace = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const cleanSeed = seedAddress.trim();
    if (!cleanSeed) {
      setFormError('Seed flagged address is required to execute trace.');
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    setIsStreaming(true);
    setStreamingStatus(`Connecting to forensic SSE stream for ${cleanSeed.slice(0, 10)}...`);

    try {
      await api.streamTraceSSE(
        {
          seedAddress: cleanSeed,
          chain,
          maxHops,
          minAmount: parseFloat(minAmount) || 0,
          taintModel,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          caseId,
        },
        {
          onStarted: (data) => {
            setStreamingStatus(`Trace initiated: ${data.max_hops || maxHops} max hops configured`);
            onTraceStarted(data);
          },
          onHop: (hop) => {
            setStreamingStatus(`Discovered Hop ${hop.hop_index}: ${hop.value} ${hop.chain || chain}`);
            onHopDiscovered(hop);
          },
          onCompleted: (data) => {
            setStreamingStatus(
              `Trace completed: ${data.total_hops} hops analyzed. Matched entity: ${data.matched_vasp || 'None'}`
            );
            setIsStreaming(false);
            onTraceCompleted(data);
          },
          onError: (err) => {
            setStreamingStatus(`Trace error: ${err.message || String(err)}`);
            setIsStreaming(false);
            onError(err);
          },
        },
        abortCtrl.signal
      );
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setFormError(err.message || 'SSE trace stream encountered an error.');
        setStreamingStatus(`Disconnected: ${err.message || 'Error'}`);
      }
      setIsStreaming(false);
    }
  };

  const handleStopTrace = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    setStreamingStatus('SSE trace stopped by investigator.');
  };

  return (
    <div
      role="region"
      aria-label="Forensic Trace Parameters Form"
      className="p-4 rounded-xl border border-slate-800 bg-slate-900/80 shadow-lg space-y-4 font-mono text-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div className="flex items-center space-x-2">
          <div className="p-1.5 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/30">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              Forensic Multi-Hop Trace Engine
            </h3>
            <p className="text-slate-400 text-[11px]">
              Live server-sent events stream with taint accounting &amp; heuristics
            </p>
          </div>
        </div>

        {/* Streaming Status Pill */}
        {isStreaming && (
          <div className="flex items-center space-x-2 px-3 py-1 rounded-full bg-purple-950/60 border border-purple-500/50 text-purple-300 text-xs animate-pulse">
            <span className="w-2 h-2 rounded-full bg-purple-400 animate-ping"></span>
            <span>SSE Streaming &bull; Hop {streamingHopCount}</span>
          </div>
        )}
      </div>

      {formError && (
        <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{formError}</span>
        </div>
      )}

      <form onSubmit={handleStartSSETrace} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Seed Flagged Address */}
          <div className="sm:col-span-2">
            <label className="block text-slate-300 font-bold mb-1">
              Seed Flagged Address (Origin Lead) <span className="text-rose-400">*</span>
            </label>
            <input
              type="text"
              value={seedAddress}
              onChange={(e) => setSeedAddress(e.target.value)}
              placeholder="0x... or 1... or TR..."
              aria-label="Seed Flagged Address"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          {/* Blockchain Selection */}
          <div>
            <label className="block text-slate-300 font-bold mb-1">Blockchain</label>
            <select
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              aria-label="Blockchain"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500"
            >
              <option value="ETH">Ethereum (ETH)</option>
              <option value="BTC">Bitcoin (BTC)</option>
              <option value="TRON">TRON (TRX / USDT)</option>
              <option value="SOL">Solana (SOL)</option>
              <option value="XRP">XRPL (XRP)</option>
              <option value="POLYGON">Polygon (MATIC)</option>
            </select>
          </div>

          {/* Hop Budget */}
          <div>
            <label className="block text-slate-300 font-bold mb-1">
              Hop Budget (1 - 10)
            </label>
            <input
              type="number"
              min="1"
              max="10"
              value={maxHops}
              onChange={(e) => setMaxHops(parseInt(e.target.value) || 3)}
              aria-label="Max Hops Budget"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Dust Threshold (Min Amount) */}
          <div>
            <label className="block text-slate-300 font-bold mb-1">
              Min Amount (Dust Filter)
            </label>
            <input
              type="number"
              step="0.001"
              min="0"
              value={minAmount}
              onChange={(e) => setMinAmount(e.target.value)}
              placeholder="0.0"
              aria-label="Dust Filter Min Amount"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* Taint Accounting Model */}
          <div>
            <label className="block text-slate-300 font-bold mb-1">Taint Model</label>
            <select
              value={taintModel}
              onChange={(e) => setTaintModel(e.target.value)}
              aria-label="Taint Accounting Model"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500"
            >
              <option value="FIFO">FIFO (First-In-First-Out)</option>
              <option value="PRO_RATA">Pro-Rata / Haircut</option>
              <option value="POISON_PILL">Poison Pill (Full Contamination)</option>
            </select>
          </div>

          {/* Start Date */}
          <div>
            <label className="block text-slate-300 font-bold mb-1">Start Date (Optional)</label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              aria-label="Trace Start Date"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500"
            />
          </div>

          {/* End Date */}
          <div>
            <label className="block text-slate-300 font-bold mb-1">End Date (Optional)</label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              aria-label="Trace End Date"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Action Controls & Live Progress Message */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800">
          <div className="flex items-center space-x-2 text-[11px] text-slate-400">
            {isStreaming ? (
              <span className="text-purple-300 font-semibold">{streamingStatus}</span>
            ) : streamingStatus ? (
              <span className="text-slate-300">{streamingStatus}</span>
            ) : (
              <span>Ready to stream live graph hops over authorized SSE channel.</span>
            )}
          </div>

          <div className="flex items-center space-x-2">
            {isStreaming ? (
              <button
                type="button"
                onClick={handleStopTrace}
                aria-label="Stop Live SSE Trace"
                className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-sans text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-lg shadow-rose-900/30"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Stop Trace</span>
              </button>
            ) : (
              <button
                type="submit"
                aria-label="Execute Live SSE Trace"
                className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-sans text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-lg shadow-blue-900/30"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Execute Graph Trace (SSE)</span>
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
};
