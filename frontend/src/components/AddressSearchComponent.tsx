import React, { useState } from 'react';
import {
  Search,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Copy,
  Check,
  RefreshCw,
  Layers,
  Clock,
  Database,
  ArrowRight,
  ShieldCheck,
  XCircle,
  HelpCircle,
  AlertCircle
} from 'lucide-react';
import { api, MultiChainSearchResponse, ChainSearchResult } from '../lib/api';

interface AddressSearchComponentProps {
  onSelectCase?: (caseId: string) => void;
  className?: string;
}

const SAMPLE_CHIPS = [
  {
    label: 'Satoshi Genesis (BTC)',
    query: '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa',
    chain: 'Bitcoin',
  },
  {
    label: 'EVM Checksummed (ETH)',
    query: '0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed',
    chain: 'Ethereum',
  },
  {
    label: 'Tether Treasury (TRON)',
    query: 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
    chain: 'TRON',
  },
];

export const AddressSearchComponent: React.FC<AddressSearchComponentProps> = ({
  className = '',
}) => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [copiedText, setCopiedText] = useState<string | null>(null);
  const [response, setResponse] = useState<MultiChainSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(text);
    setTimeout(() => setCopiedText(null), 2000);
  };

  const executeSearch = async (searchQuery: string, allCandidates: boolean = false) => {
    const clean = searchQuery.trim();
    if (!clean) return;

    setLoading(true);
    setSearchError(null);

    try {
      const res = await api.searchMultiChain(clean, allCandidates);
      setResponse(res);
      if (res.status === 'error' && res.validation && !res.validation.is_valid) {
        setSearchError(res.validation.error || 'Input validation failed.');
      }
    } catch (err: any) {
      setSearchError(err.message || 'Search failed due to unexpected error.');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    executeSearch(query, false);
  };

  const handleChipClick = (chipQuery: string) => {
    setQuery(chipQuery);
    executeSearch(chipQuery, false);
  };

  const isDemo = response?.demo || response?.results.some((r) => r.demo);

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Demo Mode Banner */}
      {isDemo && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl flex items-center gap-3 text-amber-400 text-xs">
          <AlertTriangle className="w-4 h-4 shrink-0 animate-pulse" />
          <div>
            <span className="font-bold uppercase tracking-wider">DEMO MODE ACTIVE:</span> Displaying simulated on-chain response data. Real API keys not loaded.
          </div>
        </div>
      )}

      {/* Main Search Input Form */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative flex items-center">
            <Search className="w-5 h-5 text-slate-400 absolute left-4 pointer-events-none" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Enter any address or transaction hash (e.g. 1A1zP1..., 0x5aAe..., TR7NH..., Solana, XRPL, Stellar...)"
              aria-label="Multi-chain address or transaction search input"
              className="w-full pl-12 pr-32 py-3.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 font-mono transition-all"
            />
            <div className="absolute right-2 flex items-center gap-2">
              {query && (
                <button
                  type="button"
                  onClick={() => {
                    setQuery('');
                    setResponse(null);
                    setSearchError(null);
                  }}
                  className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded transition-colors"
                >
                  Clear
                </button>
              )}
              <button
                type="submit"
                disabled={loading || !query.trim()}
                className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg shadow-lg shadow-blue-600/20 transition-all"
              >
                {loading ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Searching...</span>
                  </>
                ) : (
                  <>
                    <span>Inspect</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Sample Chips */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-slate-400">Quick Test Samples:</span>
            {SAMPLE_CHIPS.map((chip) => (
              <button
                key={chip.query}
                type="button"
                onClick={() => handleChipClick(chip.query)}
                className="text-xs font-mono px-2.5 py-1 bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 rounded-lg transition-all flex items-center gap-1.5"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                <span>{chip.label}</span>
              </button>
            ))}
          </div>
        </form>
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-4 animate-pulse">
          <div className="h-28 bg-slate-900/60 border border-slate-800 rounded-xl" />
          <div className="h-64 bg-slate-900/60 border border-slate-800 rounded-xl" />
        </div>
      )}

      {/* Validation Error Card (HTTP 422) */}
      {!loading && response && !response.validation.is_valid && (
        <div className="p-5 bg-rose-950/30 border border-rose-800/50 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-rose-400 font-semibold text-sm">
            <XCircle className="w-4 h-4 shrink-0" />
            <span>Cryptographic Validation Failed</span>
          </div>
          <p className="text-sm font-mono text-rose-200 pl-6">
            {response.validation.error || searchError || 'Input failed checksum validation.'}
          </p>
          {response.validation.hint && (
            <div className="flex items-start gap-2 text-xs text-amber-300/90 pl-6 pt-1 bg-amber-500/5 p-2 rounded-lg border border-amber-500/20">
              <HelpCircle className="w-3.5 h-3.5 shrink-0 mt-0.5 text-amber-400" />
              <span>
                <strong>Hint:</strong> {response.validation.hint}
              </span>
            </div>
          )}
        </div>
      )}

      {/* ENS Name Resolution Note */}
      {!loading && response && response.validation.is_valid && response.validation.kind === 'ens_name' && (
        <div className="p-5 bg-blue-950/30 border border-blue-800/50 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-blue-400 font-semibold text-sm">
            <Layers className="w-4 h-4 shrink-0" />
            <span>ENS Name Detected: {response.validation.input}</span>
          </div>
          <p className="text-xs text-slate-300">
            {response.message || 'ENS names require forward resolution via the Ethereum Name Service contract to resolve the target wallet address.'}
          </p>
        </div>
      )}

      {/* Validation Card */}
      {!loading && response && response.validation.is_valid && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Identifier Detected: <span className="text-white capitalize">{response.validation.kind}</span>
              </span>
            </div>

            {/* Certainty Badge */}
            <div>
              {response.validation.certainty === 'verified' ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Checksum verified</span>
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-500/10 text-amber-300 border border-amber-500/30">
                  <AlertTriangle className="w-3 h-3" />
                  <span>Format only: this chain has no checksum, a typo cannot be detected</span>
                </span>
              )}
            </div>
          </div>

          {/* Normalized Value with Copy */}
          <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs text-slate-400 shrink-0">Normalized:</span>
              <span className="text-xs font-mono text-blue-300 truncate select-all">
                {response.validation.normalized}
              </span>
            </div>
            <button
              type="button"
              onClick={() => handleCopy(response.validation.normalized)}
              aria-label="Copy normalized address"
              className="flex items-center gap-1 px-2.5 py-1 text-xs text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded transition-colors shrink-0"
            >
              {copiedText === response.validation.normalized ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span className="text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>Copy</span>
                </>
              )}
            </button>
          </div>

          {/* Candidates Breakdown */}
          <div className="space-y-2">
            <div className="text-xs text-slate-400 font-medium">Valid Chain Candidates:</div>
            <div className="flex flex-wrap gap-2">
              {response.validation.candidates.map((c, idx) => (
                <div
                  key={`${c.chain}-${idx}`}
                  className="px-3 py-1.5 bg-slate-800/60 border border-slate-700/60 rounded-lg text-xs font-mono text-slate-200 flex items-center gap-2"
                >
                  <span className="font-semibold text-white uppercase">{c.chain}</span>
                  <span className="text-slate-400">({c.address_type}, {c.network})</span>
                  {c.checksum_verified && (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" title="Checksum verified" />
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Multi-Candidate / Related EVM Offer */}
          {(response.validation.candidates.length > 1 || (response.validation.related_chains && response.validation.related_chains.length > 0)) && (
            <div className="p-3 bg-blue-950/20 border border-blue-800/40 rounded-lg flex flex-wrap items-center justify-between gap-3 text-xs">
              <div className="text-slate-300">
                Several chains are candidates for this format. Probing primary chain by default.
              </div>
              <button
                type="button"
                onClick={() => executeSearch(query, true)}
                className="px-3 py-1.5 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 hover:text-white border border-blue-500/40 rounded-lg font-medium transition-colors"
              >
                Check other candidate chains
              </button>
            </div>
          )}
        </div>
      )}

      {/* Per-Chain Results Cards */}
      {!loading && response && response.results && response.results.length > 0 && (
        <div className="space-y-6">
          <div className="text-sm font-semibold text-slate-300 flex items-center gap-2">
            <Database className="w-4 h-4 text-blue-400" />
            <span>On-Chain Forensic Inspection Results ({response.results.length} chain{response.results.length > 1 ? 's' : ''})</span>
          </div>

          {response.results.map((res: ChainSearchResult, idx: number) => (
            <div
              key={`${res.chain}-${res.network}-${idx}`}
              className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 space-y-5 shadow-lg"
            >
              {/* Card Header */}
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div className="flex items-center gap-3">
                  <div className="w-3 h-3 rounded-full bg-blue-500" />
                  <div>
                    <h3 className="text-base font-bold text-white uppercase tracking-wide">
                      {res.chain} <span className="text-xs font-normal text-slate-400">({res.network})</span>
                    </h3>
                  </div>
                </div>

                {/* Status Badge */}
                <div>
                  {res.status === 'ok' && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                      Active On-Chain
                    </span>
                  )}
                  {res.status === 'not_found' && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                      Unfunded / No History
                    </span>
                  )}
                  {res.status === 'unavailable' && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/30">
                      Provider Unavailable
                    </span>
                  )}
                  {res.status === 'not_applicable' && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-300 border border-purple-500/30">
                      Privacy Chain
                    </span>
                  )}
                  {res.status === 'unsupported_lookup' && (
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700">
                      Lookup Unsupported
                    </span>
                  )}
                </div>
              </div>

              {/* Matched Entities & Labels */}
              {res.labels && res.labels.length > 0 && (
                <div className="p-3.5 bg-blue-950/30 border border-blue-800/40 rounded-xl space-y-1.5">
                  <div className="text-xs font-semibold text-blue-400 uppercase tracking-wider">
                    Attributed Entity &amp; Intelligence Labels:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {res.labels.map((l, lIdx) => (
                      <div
                        key={lIdx}
                        className="px-2.5 py-1 bg-blue-900/40 border border-blue-500/40 rounded-lg text-xs text-blue-200 flex items-center gap-1.5"
                      >
                        <span className="font-semibold">{l.label}</span>
                        <span className="text-[10px] text-blue-400">({l.source})</span>
                        <span className="text-[9px] px-1.5 py-0.2 bg-blue-500/20 text-blue-300 rounded font-mono">
                          {Math.round(l.confidence * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Summary Metrics */}
              {res.status === 'ok' && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800">
                    <div className="text-xs text-slate-400">On-Chain Balance</div>
                    <div className="text-lg font-bold text-white font-mono mt-1">
                      {res.summary.balance_formatted || `${res.summary.balance || 0} ${res.chain.toUpperCase()}`}
                    </div>
                  </div>

                  <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800">
                    <div className="text-xs text-slate-400">Transactions Count</div>
                    <div className="text-lg font-bold text-white font-mono mt-1">
                      {res.summary.tx_count !== undefined ? res.summary.tx_count : 'N/A'}
                    </div>
                  </div>

                  <div className="p-4 bg-slate-950/60 rounded-xl border border-slate-800">
                    <div className="text-xs text-slate-400">Classification / Type</div>
                    <div className="text-xs font-semibold text-slate-200 mt-2">
                      {res.summary.type || (res.summary.is_contract ? 'Smart Contract' : 'Standard Address')}
                    </div>
                  </div>
                </div>
              )}

              {/* Notice / Error explanation */}
              {res.error && (
                <div className="p-3.5 bg-slate-950/80 border border-slate-800 rounded-xl text-xs text-slate-300 flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold text-slate-200">Provider Notice: </span>
                    <span className="font-mono text-slate-400">{res.error}</span>
                  </div>
                </div>
              )}

              {/* Recent Transactions Table */}
              {res.transactions && res.transactions.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-300">
                    Recent Transactions ({res.transactions.length})
                  </div>
                  <div className="overflow-x-auto rounded-xl border border-slate-800">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 font-mono">
                        <tr>
                          <th className="py-2.5 px-3">Tx Hash</th>
                          <th className="py-2.5 px-3">Timestamp</th>
                          <th className="py-2.5 px-3 text-right">Amount</th>
                          <th className="py-2.5 px-3 text-right">Explorer</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 bg-slate-900/40 font-mono">
                        {res.transactions.map((tx, tIdx) => (
                          <tr key={tIdx} className="hover:bg-slate-800/40 transition-colors">
                            <td className="py-2 px-3 text-slate-300 truncate max-w-[180px]">
                              {tx.hash}
                            </td>
                            <td className="py-2 px-3 text-slate-400 text-[11px]">
                              {tx.time ? new Date(tx.time).toLocaleString() : 'Recent'}
                            </td>
                            <td className="py-2 px-3 text-right text-slate-200 font-semibold">
                              {tx.amount !== undefined && tx.amount !== null ? tx.amount : '—'}
                            </td>
                            <td className="py-2 px-3 text-right">
                              {tx.explorer_url ? (
                                <a
                                  href={tx.explorer_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 transition-colors"
                                >
                                  <span>View</span>
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              ) : (
                                <span className="text-slate-500">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Evidence Footer */}
              <div className="pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-3 text-[11px] text-slate-400 font-mono">
                <div className="flex items-center gap-2">
                  <span>Source:</span>
                  <span className="font-semibold text-slate-300">{res.source}</span>
                  {res.source_url && (
                    <a
                      href={res.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:text-blue-300 inline-flex items-center gap-0.5 ml-1"
                    >
                      <span>Endpoint</span>
                      <ExternalLink className="w-2.5 h-2.5" />
                    </a>
                  )}
                </div>

                <div className="flex items-center gap-1.5 text-slate-400">
                  <Clock className="w-3 h-3 text-slate-400" />
                  <span>Fetched: {new Date(res.fetched_at).toISOString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
