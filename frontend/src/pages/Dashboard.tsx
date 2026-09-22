import React, { useState, useEffect } from 'react';
import {
  Shield,
  User,
  LogOut,
  FolderLock,
  Search,
  Plus,
  ArrowUpRight,
  TrendingUp,
  AlertCircle,
  Building2,
  RefreshCw,
  Eye,
  FileText,
} from 'lucide-react';
import { useAuth } from '../lib/authContext';
import { api, CaseRecord } from '../lib/api';
import { IntelExchangeModal } from '../components/IntelExchangeModal';
import { WatchlistModal } from '../components/WatchlistModal';
import { VaspAdminModal } from '../components/VaspAdminModal';
import { HeaderSearchBar } from '../components/HeaderSearchBar';
import { AddressSearchModal } from '../components/AddressSearchModal';
import { AddressSearchComponent } from '../components/AddressSearchComponent';
import { LanguageSwitcher } from '../components/LanguageSwitcher';

interface DashboardPageProps {
  onSelectCase?: (caseId: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({ onSelectCase }) => {
  const { officer, token, logout } = useAuth();
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [isSubmittingNew, setIsSubmittingNew] = useState<boolean>(false);

  // Phase 7 Innovation Modals State
  const [isIntelOpen, setIsIntelOpen] = useState<boolean>(false);
  const [isWatchlistOpen, setIsWatchlistOpen] = useState<boolean>(false);
  const [isVaspAdminOpen, setIsVaspAdminOpen] = useState<boolean>(false);
  const [isSearchModalOpen, setIsSearchModalOpen] = useState<boolean>(false);
  const [searchModalInitialQuery, setSearchModalInitialQuery] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'cases' | 'inspector'>('cases');

  // New Case Form state
  const [ncrpRef, setNcrpRef] = useState<string>('');
  const [victimUtr, setVictimUtr] = useState<string>('');
  const [amountInr, setAmountInr] = useState<string>('');
  const [flaggedAddress, setFlaggedAddress] = useState<string>('');
  const [chain, setChain] = useState<string>('ETH');
  const [submitting, setSubmitting] = useState<boolean>(false);

  const fetchCaseload = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getCases(token);
      setCases(data);
    } catch (err: any) {
      setError(err.message || 'Failed to preload officer caseload.');
    } finally {
      setLoading(false);
    }
  };

  // Immediate work-history preload on mount (Mandatory requirement)
  useEffect(() => {
    fetchCaseload();
  }, [token]);

  const handleCreateCase = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setSubmitting(true);
    try {
      const created = await api.createCase(token, {
        ncrp_ref: ncrpRef || undefined,
        victim_utr: victimUtr || undefined,
        amount_inr: amountInr ? parseFloat(amountInr) : undefined,
        flagged_address: flaggedAddress || undefined,
        chain,
      });
      // Clear form and refresh
      setNcrpRef('');
      setVictimUtr('');
      setAmountInr('');
      setFlaggedAddress('');
      setIsSubmittingNew(false);
      await fetchCaseload();
      if (onSelectCase && created.case_id) {
        onSelectCase(created.case_id);
      }
    } catch (err: any) {
      alert(err.message || 'Failed to create case');
    } finally {
      setSubmitting(false);
    }
  };

  const filteredCases = cases.filter((c) => {
    const q = searchQuery.toLowerCase();
    return (
      (c.ncrp_ref && c.ncrp_ref.toLowerCase().includes(q)) ||
      (c.victim_utr && c.victim_utr.toLowerCase().includes(q)) ||
      (c.assigned_officer_name && c.assigned_officer_name.toLowerCase().includes(q)) ||
      (c.latest_entity && c.latest_entity.toLowerCase().includes(q))
    );
  });

  const totalAmountInr = cases.reduce((sum, c) => sum + (c.amount_inr || 0), 0);
  const attributedCount = cases.filter((c) => c.latest_entity).length;

  const getCaseloadStatusBadge = (c: CaseRecord) => {
    const runStatus = c.submissions?.[0]?.analysis_runs?.[0]?.status || c.status;
    switch (runStatus) {
      case 'ANALYSIS_COMPLETE_ATTRIBUTED':
      case 'COMPLETED':
        return {
          label: 'Attributed',
          style: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
        };
      case 'ANALYSIS_COMPLETE_NO_PATH_FOUND':
      case 'NO_CONFIDENT_OFF_RAMP':
        return {
          label: 'No Path Found',
          style: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
        };
      case 'ANALYSIS_FAILED_ADAPTER_ERROR':
        return {
          label: 'Adapter Error',
          style: 'bg-red-500/10 text-red-400 border-red-500/30',
        };
      case 'ANALYSIS_FAILED_INVALID_ADDRESS':
        return {
          label: 'Invalid Address',
          style: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
        };
      default:
        return {
          label: runStatus === 'ANALYZED' ? 'Analyzed' : 'Pending Trace',
          style: runStatus === 'ANALYZED'
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            : 'bg-blue-500/10 text-blue-400 border-blue-500/30',
        };
    }
  };

  return (
    <div className="min-h-screen bg-[#0b1120] text-slate-100 flex flex-col">
      {/* Top Officer Header */}
      <header className="border-b border-slate-800 bg-[#0f172a]/95 backdrop-blur sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-400">
              <Shield className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold tracking-tight text-white text-base">CryptoTrace Sentinel</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
                  SIH26183
                </span>
              </div>
              <p className="text-[11px] text-slate-400">Forensics &amp; VASP Attribution System</p>
            </div>
          </div>

          {/* Universal One-Box Search Bar */}
          <div className="hidden md:block">
            <HeaderSearchBar
              token={token || undefined}
              onSelectCase={onSelectCase}
              onOpenInspector={(q) => {
                setSearchModalInitialQuery(q || '');
                setIsSearchModalOpen(true);
              }}
            />
          </div>

          {/* Officer Identity & Logout */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-3 bg-slate-900/80 border border-slate-800 rounded-lg px-3 py-1.5">
              <div className="w-7 h-7 rounded-full bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400 text-xs font-bold">
                {officer?.full_name?.charAt(0) || 'O'}
              </div>
              <div className="text-left">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-semibold text-white">{officer?.full_name}</span>
                  <span
                    className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase font-semibold ${
                      officer?.role === 'SUPERVISOR'
                        ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                        : officer?.role === 'ADMIN'
                        ? 'bg-purple-500/10 text-purple-400 border-purple-500/20'
                        : 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                    }`}
                  >
                    {officer?.role}
                  </span>
                </div>
                <p className="text-[10px] text-slate-400 font-mono">
                  {officer?.district || 'Central'} &bull; Badge: {officer?.badge_no || 'N/A'}
                </p>
              </div>
            </div>

            <LanguageSwitcher />

            <button
              onClick={logout}
              title="Sign Out"
              className="p-2 rounded-lg border border-slate-800 bg-slate-900 hover:bg-rose-950/40 hover:border-rose-800/60 text-slate-400 hover:text-rose-300 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Caseload Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* RLS Policy Banner */}
        <div className="mb-6 p-4 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="p-2 rounded-lg bg-blue-600/10 text-blue-400 border border-blue-500/20">
              <FolderLock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">
                Row-Level Security (RLS) Active &bull; Work History Preloaded
              </h3>
              <p className="text-xs text-slate-400">
                {officer?.role === 'INVESTIGATOR'
                  ? `Filtering strictly at the database query level: Showing only cases assigned to Officer ID ${officer.id}.`
                  : `Supervisory Clearance: Viewing all multi-district cases logged across the department.`}
              </p>
            </div>
          </div>
          <button
            onClick={fetchCaseload}
            className="flex items-center space-x-1 text-xs text-slate-400 hover:text-blue-400 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Authorized Caseload</span>
              <FolderLock className="w-4 h-4 text-blue-400" />
            </div>
            <div className="text-2xl font-bold text-white font-mono">{cases.length}</div>
            <p className="text-[11px] text-slate-500 mt-1">Preloaded on session initialization</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Reported Fraud (INR)</span>
              <TrendingUp className="w-4 h-4 text-emerald-400" />
            </div>
            <div className="text-2xl font-bold text-emerald-400 font-mono">
              ₹{totalAmountInr.toLocaleString('en-IN')}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Across assigned victim complaints</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Attributed Off-Ramps</span>
              <Building2 className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-2xl font-bold text-white font-mono">{attributedCount}</div>
            <p className="text-[11px] text-slate-500 mt-1">Matched Indian / Global VASPs</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Access Scope</span>
              <User className="w-4 h-4 text-purple-400" />
            </div>
            <div className="text-sm font-bold text-purple-400 font-mono mt-1">
              {officer?.role === 'INVESTIGATOR' ? 'OWN ASSIGNED CASES' : 'SUPERVISORY BROAD'}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Badge: {officer?.badge_no}</p>
          </div>
        </div>

        {/* Action & Search Bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mb-6">
          <div className="relative w-full sm:w-80">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search NCRP ref, UTR, VASP..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-2 bg-slate-900/80 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2.5 w-full sm:w-auto">
            {/* Multi-Chain Inspector Button */}
            <button
              onClick={() => {
                setSearchModalInitialQuery('');
                setIsSearchModalOpen(true);
              }}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-lg border border-cyan-500/30 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 text-xs font-semibold transition-colors"
              title="Universal Multi-Chain Checksum Validation & Live On-Chain Inspector"
            >
              <Search className="w-3.5 h-3.5 text-cyan-400" />
              <span>Multi-Chain Inspector</span>
            </button>

            {/* Complaint Intake Button */}
            <a
              href="#intake"
              className="flex items-center space-x-1.5 px-3 py-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 text-xs font-semibold transition-colors"
              title="Victim Complaint Intake with Guarded Extraction"
            >
              <FileText className="w-3.5 h-3.5 text-emerald-400" />
              <span>Complaint Intake</span>
            </a>

            {/* Police Intel Exchange Button */}
            <button
              onClick={() => setIsIntelOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-lg border border-slate-800 bg-slate-900/80 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition-colors"
              title="Query or Submit Anonymized Address Hashes to Police Intel Exchange"
            >
              <Shield className="w-3.5 h-3.5 text-blue-400" />
              <span>Intel Exchange</span>
            </button>

            {/* Golden Hour Watchlist Button */}
            <button
              onClick={() => setIsWatchlistOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-semibold transition-colors"
              title="Real-Time Golden Hour Off-Ramp Monitoring"
            >
              <Eye className="w-3.5 h-3.5 text-amber-400" />
              <span>Watchlist</span>
            </button>

            {/* VASP Directory Admin Button (ADMIN only) */}
            {officer?.role === 'ADMIN' && (
              <button
                onClick={() => setIsVaspAdminOpen(true)}
                className="flex items-center space-x-1.5 px-3 py-2 rounded-lg border border-purple-500/30 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 text-xs font-semibold transition-colors"
                title="Manage FIU-IND Registered VASPs and Hot Wallets"
              >
                <Building2 className="w-3.5 h-3.5 text-purple-400" />
                <span>VASP Directory</span>
              </button>
            )}

            {/* New Investigation Button */}
            <button
              onClick={() => setIsSubmittingNew(!isSubmittingNew)}
              className="flex items-center justify-center space-x-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>New Wallet Investigation</span>
            </button>
          </div>
        </div>

        {/* Quick New Case Submission Drawer/Form */}
        {isSubmittingNew && (
          <div className="mb-8 p-6 rounded-xl border border-blue-500/30 bg-[#0f172a] shadow-2xl animate-in fade-in">
            <h4 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
              <Plus className="w-4 h-4 text-blue-400" />
              <span>Register Victim-Reported Flagged Wallet (Lead)</span>
            </h4>
            <form onSubmit={handleCreateCase} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  NCRP Reference No
                </label>
                <input
                  type="text"
                  placeholder="e.g. NCRP/2026/DL-99120"
                  value={ncrpRef}
                  onChange={(e) => setNcrpRef(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Victim Bank / UPI UTR
                </label>
                <input
                  type="text"
                  placeholder="UPI-992182019283"
                  value={victimUtr}
                  onChange={(e) => setVictimUtr(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Fraud Amount (INR)
                </label>
                <input
                  type="number"
                  placeholder="500000"
                  value={amountInr}
                  onChange={(e) => setAmountInr(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Flagged Wallet Address (Lead)
                </label>
                <input
                  type="text"
                  required
                  placeholder="0x... or TR7NHq..."
                  value={flaggedAddress}
                  onChange={(e) => setFlaggedAddress(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white font-mono focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Chain
                </label>
                <select
                  value={chain}
                  onChange={(e) => setChain(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="ETH">Ethereum (ETH / ERC-20)</option>
                  <option value="TRON">Tron (TRC-20 / USDT)</option>
                  <option value="BTC">Bitcoin (BTC)</option>
                </select>
              </div>

              <div className="sm:col-span-3 flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setIsSubmittingNew(false)}
                  className="px-4 py-2 text-xs text-slate-400 hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition-colors disabled:opacity-50"
                >
                  {submitting ? 'Creating Case...' : 'Submit & Register'}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* View Selection Tabs */}
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3 mb-6">
          <button
            type="button"
            onClick={() => setActiveTab('cases')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'cases'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <FolderLock className="w-3.5 h-3.5" />
            <span>Assigned Caseload ({cases.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('inspector')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors flex items-center gap-1.5 ${
              activeTab === 'inspector'
                ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            <Search className="w-3.5 h-3.5" />
            <span>Multi-Chain Forensic Inspector</span>
          </button>
        </div>

        {activeTab === 'inspector' ? (
          <AddressSearchComponent onSelectCase={onSelectCase} />
        ) : (
          /* Caseload Table */
          <div className="bg-[#0f172a] rounded-xl border border-slate-800 shadow-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">
              Assigned Investigation Files ({filteredCases.length})
            </h3>
            <span className="text-xs text-slate-400 font-mono">
              Preloaded via /api/cases
            </span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-slate-400 font-mono text-xs">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-blue-500" />
              Preloading case history from database...
            </div>
          ) : error ? (
            <div className="p-8 text-center text-rose-400 text-xs">
              <AlertCircle className="w-6 h-6 mx-auto mb-2 text-rose-500" />
              {error}
            </div>
          ) : filteredCases.length === 0 ? (
            <div className="p-12 text-center text-slate-500 text-xs">
              No cases found in current clearance scope. Submit a flagged wallet to start.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/60 text-slate-400 uppercase font-mono text-[10px] tracking-wider border-b border-slate-800">
                  <tr>
                    <th className="px-6 py-3">NCRP Reference</th>
                    <th className="px-6 py-3">Victim UTR</th>
                    <th className="px-6 py-3">Amount (INR)</th>
                    <th className="px-6 py-3">Assigned Officer</th>
                    <th className="px-6 py-3">Attributed VASP</th>
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {filteredCases.map((c) => (
                    <tr
                      key={c.case_id}
                      onClick={() => onSelectCase && onSelectCase(c.case_id)}
                      className="hover:bg-slate-800/40 cursor-pointer transition-colors"
                    >
                      <td className="px-6 py-4 font-semibold text-white">
                        {c.ncrp_ref || 'N/A'}
                      </td>
                      <td className="px-6 py-4 text-slate-400">
                        {c.victim_utr || '—'}
                      </td>
                      <td className="px-6 py-4 text-emerald-400 font-semibold">
                        {c.amount_inr ? `₹${c.amount_inr.toLocaleString('en-IN')}` : '—'}
                      </td>
                      <td className="px-6 py-4 text-slate-300">
                        {c.assigned_officer_name || 'Unassigned'}
                      </td>
                      <td className="px-6 py-4">
                        {c.latest_entity ? (
                          <div className="flex items-center space-x-2">
                            <span className="text-white font-sans font-medium">{c.latest_entity}</span>
                            <span
                              className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                (c.latest_confidence || 0) >= 0.85
                                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                  : (c.latest_confidence || 0) >= 0.65
                                  ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                              }`}
                            >
                              {Math.round((c.latest_confidence || 0) * 100)}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-slate-500 italic">Pending Trace</span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {(() => {
                          const badge = getCaseloadStatusBadge(c);
                          return (
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] uppercase font-bold tracking-wider border ${badge.style}`}
                            >
                              {badge.label}
                            </span>
                          );
                        })()}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectCase && onSelectCase(c.case_id);
                          }}
                          className="inline-flex items-center space-x-1 text-blue-400 hover:text-blue-300 font-sans font-medium"
                        >
                          <span>Forensics</span>
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        )}
      </main>

      {/* Multi-Chain Forensic Address & Tx Inspector Modal */}
      <AddressSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
        onSelectCase={onSelectCase}
        initialQuery={searchModalInitialQuery}
      />

      {/* Police Intel Exchange Modal */}
      {token && (
        <IntelExchangeModal
          isOpen={isIntelOpen}
          onClose={() => setIsIntelOpen(false)}
          token={token}
          officerDistrict={officer?.district || 'Cyber Crime Unit'}
        />
      )}

      {/* Golden Hour Watchlist Modal */}
      {token && (
        <WatchlistModal
          isOpen={isWatchlistOpen}
          onClose={() => setIsWatchlistOpen(false)}
          token={token}
        />
      )}

      {/* VASP Directory Admin Modal (ADMIN only) */}
      {token && officer?.role === 'ADMIN' && (
        <VaspAdminModal
          isOpen={isVaspAdminOpen}
          onClose={() => setIsVaspAdminOpen(false)}
          token={token}
        />
      )}
    </div>
  );
};
