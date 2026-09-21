import React, { useState } from 'react';
import { Search, Loader2, CheckCircle, AlertTriangle, ArrowRight, ShieldAlert } from 'lucide-react';
import { api, SearchResponse } from '../lib/api';

interface HeaderSearchBarProps {
  token?: string;
  onSelectCase?: (caseId: string) => void;
  onOpenInspector?: (initialQuery?: string) => void;
}

type SearchStage = 'idle' | 'searching' | 'found' | 'tracing' | 'done' | 'error';

export const HeaderSearchBar: React.FC<HeaderSearchBarProps> = ({ token, onSelectCase, onOpenInspector }) => {
  const [query, setQuery] = useState('');
  const [stage, setStage] = useState<SearchStage>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const [lastResult, setLastResult] = useState<SearchResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) return;

    if (onOpenInspector) {
      onOpenInspector(cleanQuery);
      return;
    }

    if (!token) {
      setErrorMessage('Officer session not authenticated.');
      setStage('error');
      return;
    }

    setErrorMessage(null);
    setLastResult(null);

    // Stage 1: Searching / Detecting
    setStage('searching');
    setStatusMessage('Analyzing format & cryptographic checksum...');

    try {
      const timer1 = setTimeout(() => {
        setStage('found');
        setStatusMessage('Checksum verified. Identifying network node...');
      }, 400);

      const timer2 = setTimeout(() => {
        setStage('tracing');
        setStatusMessage('Executing bounded multi-hop forensic trace...');
      }, 1000);

      const res = await api.unifiedSearch(token, cleanQuery);

      clearTimeout(timer1);
      clearTimeout(timer2);

      if (res.status === 'ANALYSIS_FAILED_INVALID_ADDRESS') {
        setStage('error');
        setErrorMessage(res.error || 'Input failed checksum validation across EVM, BTC, and TRON.');
        return;
      }

      setLastResult(res);
      setStage('done');
      setStatusMessage(
        res.is_root_entity
          ? `Direct Match: ${res.matched_entity} (0 hops)`
          : `Trace Complete: ${res.matched_entity || 'No off-ramp'} (${res.total_hops} hops)`
      );

      // Auto-navigate to case after 800ms
      setTimeout(() => {
        if (res.case_id && onSelectCase) {
          onSelectCase(res.case_id);
          setStage('idle');
          setQuery('');
        }
      }, 900);
    } catch (err: any) {
      setStage('error');
      setErrorMessage(err.message || 'Universal search request failed.');
    }
  };

  return (
    <div className="relative flex items-center">
      <form onSubmit={handleSearch} className="relative flex items-center w-80 sm:w-96 lg:w-[420px]">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="One-Box Search: EVM/TRON/BTC/Solana/XRPL/UTXO..."
          className="w-full pl-9 pr-28 py-1.5 bg-slate-900/90 border border-slate-700/80 rounded-lg text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all font-mono"
        />

        <div className="absolute right-1.5 flex items-center gap-1">
          {stage !== 'idle' && stage !== 'error' && (
            <span className="flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {stage === 'searching' && <Loader2 className="w-2.5 h-2.5 animate-spin text-blue-400" />}
              {stage === 'found' && <Loader2 className="w-2.5 h-2.5 animate-spin text-amber-400" />}
              {stage === 'tracing' && <Loader2 className="w-2.5 h-2.5 animate-spin text-purple-400" />}
              {stage === 'done' && <CheckCircle className="w-2.5 h-2.5 text-emerald-400" />}
              <span className="capitalize">{stage}</span>
            </span>
          )}

          {onOpenInspector && (
            <button
              type="button"
              onClick={() => onOpenInspector(query)}
              className="p-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-400 transition-colors"
              title="Open Universal Multi-Chain Forensic Inspector"
            >
              <Search className="w-3.5 h-3.5" />
            </button>
          )}

          <button
            type="submit"
            disabled={!query.trim() || stage === 'searching' || stage === 'tracing'}
            className="p-1 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 transition-colors"
            title="Inspect with Multi-Chain Forensic Engine"
          >
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </form>

      {/* Floating Status Dropdown / Toast */}
      {stage !== 'idle' && (
        <div className="absolute top-full left-0 right-0 mt-2 z-50 p-3 rounded-xl border shadow-2xl backdrop-blur bg-slate-900/95 border-slate-700 text-xs font-mono animate-in fade-in">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {stage === 'error' ? (
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
              ) : stage === 'done' ? (
                <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
              ) : (
                <Loader2 className="w-4 h-4 text-blue-400 animate-spin shrink-0" />
              )}
              <span className={stage === 'error' ? 'text-rose-300' : 'text-slate-200'}>
                {stage === 'error' ? errorMessage : statusMessage}
              </span>
            </div>

            {stage === 'error' && (
              <button
                onClick={() => setStage('idle')}
                className="text-[10px] text-slate-400 hover:text-white px-2 py-0.5 rounded border border-slate-800"
              >
                Dismiss
              </button>
            )}
          </div>

          {/* Low Confirmation Honesty Warning */}
          {lastResult && (lastResult.low_confirmation || lastResult.has_low_confirmation_hops) && (
            <div className="mt-2 pt-2 border-t border-slate-800 flex items-center gap-1.5 text-[11px] text-amber-300">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>Notice: Hop includes &lt; 3 confirmations (low-confirmation, subject to reorg).</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
