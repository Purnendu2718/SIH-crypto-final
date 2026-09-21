import React, { useState, useEffect } from 'react';
import {
  Eye,
  X,
  Plus,
  Trash2,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Radio,
  Send,
  Building2,
} from 'lucide-react';
import { api, WatchlistEntry, WatchlistPollResult } from '../lib/api';

interface WatchlistModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  defaultCaseId?: string;
  defaultAddress?: string;
}

export const WatchlistModal: React.FC<WatchlistModalProps> = ({
  isOpen,
  onClose,
  token,
  defaultCaseId = '',
  defaultAddress = '',
}) => {
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New Watchlist Form
  const [isAdding, setIsAdding] = useState(false);
  const [formAddress, setFormAddress] = useState(defaultAddress);
  const [formChain, setFormChain] = useState('ETH');
  const [formCaseId, setFormCaseId] = useState(defaultCaseId);
  const [formChannel, setFormChannel] = useState('TELEGRAM');
  const [submitting, setSubmitting] = useState(false);

  // Polling State
  const [polling, setPolling] = useState(false);
  const [pollResult, setPollResult] = useState<WatchlistPollResult | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadWatchlist();
      if (defaultAddress) setFormAddress(defaultAddress);
      if (defaultCaseId) setFormCaseId(defaultCaseId);
    }
  }, [isOpen, defaultAddress, defaultCaseId]);

  const loadWatchlist = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listWatchlist(token);
      setEntries(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load Golden Hour watchlist.');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formAddress.trim() || !formCaseId.trim()) {
      setFeedback({ type: 'error', text: 'Address and Case ID are required.' });
      return;
    }

    setSubmitting(true);
    setFeedback(null);
    try {
      await api.createWatchlistEntry(token, {
        address: formAddress.trim(),
        chain: formChain,
        case_id: formCaseId.trim(),
        alert_channel: formChannel,
      });
      setFeedback({ type: 'success', text: 'Address enrolled in Golden Hour monitoring.' });
      setIsAdding(false);
      setFormAddress('');
      await loadWatchlist();
    } catch (err: any) {
      setFeedback({ type: 'error', text: err.message || 'Failed to enroll watchlist address.' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string, addr: string) => {
    if (!window.confirm(`Stop monitoring address ${addr.substring(0, 10)}...?`)) return;
    try {
      await api.deleteWatchlistEntry(token, id);
      setFeedback({ type: 'success', text: 'Watchlist entry removed.' });
      await loadWatchlist();
    } catch (err: any) {
      setFeedback({ type: 'error', text: err.message || 'Failed to remove watchlist entry.' });
    }
  };

  const handlePollNow = async () => {
    setPolling(true);
    setFeedback(null);
    setPollResult(null);
    try {
      const res = await api.pollWatchlistNow(token);
      setPollResult(res);
      setFeedback({
        type: 'success',
        text: `Poll complete: scanned ${res.total_checked} monitored targets. ${res.alerts_fired} active off-ramp movements detected.`,
      });
      await loadWatchlist();
    } catch (err: any) {
      setFeedback({ type: 'error', text: err.message || 'Watchlist poll execution failed.' });
    } finally {
      setPolling(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-4xl bg-slate-900 border border-amber-500/40 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-gradient-to-r from-amber-950/40 via-slate-900 to-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 font-bold">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-white">Golden Hour Target Watchlist</h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  REAL-TIME POLLING
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Automated continuous surveillance of flagged addresses to intercept outbound off-ramp transactions
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="p-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">
              Monitored Targets: <strong className="text-white">{entries.length}</strong>
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handlePollNow}
              disabled={polling}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold shadow-lg shadow-amber-500/20 transition-all disabled:opacity-50"
            >
              <Radio className={`w-3.5 h-3.5 ${polling ? 'animate-pulse text-red-600' : ''}`} />
              <span>{polling ? 'Scanning Nodes...' : 'Poll Off-Ramps Now'}</span>
            </button>
            <button
              onClick={() => setIsAdding(!isAdding)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Watch New Address</span>
            </button>
          </div>
        </div>

        {/* Alerts & Feedback */}
        {feedback && (
          <div
            className={`mx-6 mt-4 p-3 rounded-xl border text-xs flex items-center gap-2 ${
              feedback.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                : 'bg-rose-950/40 border-rose-500/40 text-rose-300'
            }`}
          >
            {feedback.type === 'success' ? (
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{feedback.text}</span>
          </div>
        )}

        {/* Real-Time Live Alert Toast Container */}
        {pollResult && pollResult.alerts_fired > 0 && (
          <div className="mx-6 mt-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 animate-in fade-in">
            <div className="flex items-center gap-2 text-amber-400 font-bold text-xs mb-2">
              <AlertTriangle className="w-4 h-4 animate-pulse" />
              <span>Surveillance Alert Triggered: {pollResult.alerts_fired} Outbound Transfer(s) Detected!</span>
            </div>
            <div className="space-y-2">
              {pollResult.alert_details.map((alert, idx) => (
                <div key={idx} className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs font-mono flex items-center justify-between">
                  <div>
                    <span className="text-slate-400 text-[10px] block">Flagged Target: {alert.address}</span>
                    <span className="text-white font-bold flex items-center gap-1 mt-0.5">
                      <Building2 className="w-3.5 h-3.5 text-amber-400" />
                      Destination VASP: {alert.vasp_name}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-emerald-400 font-bold block">
                      ₹{(alert.tx_value_inr || 0).toLocaleString('en-IN')} INR
                    </span>
                    <span className="text-[10px] text-blue-400">Telegram Webhook Dispatched</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* New Watchlist Entry Form */}
          {isAdding && (
            <form onSubmit={handleCreate} className="p-5 rounded-xl border border-blue-500/40 bg-slate-950/90 shadow-2xl text-xs space-y-4 animate-in fade-in">
              <h4 className="font-bold text-white text-sm flex items-center gap-2">
                <Plus className="w-4 h-4 text-blue-400" />
                <span>Enroll Flagged Wallet for Golden Hour Surveillance</span>
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="md:col-span-2">
                  <label className="block text-slate-300 font-medium mb-1">Flagged Address *</label>
                  <input
                    type="text"
                    required
                    placeholder="0x... or TR7NHq..."
                    value={formAddress}
                    onChange={(e) => setFormAddress(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Associated Case ID *</label>
                  <input
                    type="text"
                    required
                    placeholder="case-..."
                    value={formCaseId}
                    onChange={(e) => setFormCaseId(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Blockchain Network</label>
                  <select
                    value={formChain}
                    onChange={(e) => setFormChain(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="ETH">Ethereum (ETH / ERC-20)</option>
                    <option value="TRON">TRON (TRC-20 / USDT)</option>
                    <option value="BTC">Bitcoin (BTC)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Alert Channel Webhook</label>
                  <select
                    value={formChannel}
                    onChange={(e) => setFormChannel(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  >
                    <option value="TELEGRAM">Telegram Bot Webhook (Real-Time Notification)</option>
                    <option value="REST_WEBHOOK">Custom Cyber Cell HTTP Webhook</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsAdding(false)}
                  className="px-4 py-2 text-slate-400 hover:text-white rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Enrolling...' : 'Start Monitoring'}
                </button>
              </div>
            </form>
          )}

          {/* Watchlist Table */}
          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/60">
            <div className="px-4 py-3 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
              <span className="text-xs font-semibold text-white">Active Watchlist Targets ({entries.length})</span>
              <span className="text-[11px] text-slate-400 font-mono">Surveillance Interval: 60s Demo</span>
            </div>

            {loading ? (
              <div className="p-8 text-center text-xs text-slate-400 font-mono">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-amber-400" />
                Synchronizing watchlist entries...
              </div>
            ) : error ? (
              <div className="p-6 text-center text-xs text-rose-400">{error}</div>
            ) : entries.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">
                No addresses currently under Golden Hour surveillance. Click "Watch New Address" to enroll.
              </div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/60 text-slate-400 uppercase font-mono text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-2.5">Target Address</th>
                    <th className="px-4 py-2.5">Chain</th>
                    <th className="px-4 py-2.5">Alert Channel</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5">Enrolled</th>
                    <th className="px-4 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {entries.map((entry) => (
                    <tr key={entry.id} className="hover:bg-slate-900/40">
                      <td className="px-4 py-3 text-white font-bold truncate max-w-[220px]" title={entry.address}>
                        {entry.address}
                      </td>
                      <td className="px-4 py-3 text-slate-300">{entry.chain}</td>
                      <td className="px-4 py-3 text-blue-400 font-sans flex items-center gap-1">
                        <Send className="w-3 h-3" />
                        <span>{entry.alert_channel}</span>
                      </td>
                      <td className="px-4 py-3 font-sans">
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                          <span>ACTIVE</span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 text-[11px]">
                        {entry.created_at ? new Date(entry.created_at).toLocaleDateString() : 'N/A'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleDelete(entry.id, entry.address)}
                          className="p-1.5 rounded hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 transition-colors"
                          title="Remove from Watchlist"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex items-center justify-between text-xs text-slate-500">
          <span>Golden Hour: Instant off-ramp alerts allow IOs to issue Section 94 BNSS requisition within minutes.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-white font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
