import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Play,
  RotateCw,
  Scale,
  FileCheck,
  AlertTriangle,
  Gavel,
  Network,
  Sparkles,
  Eye,
  Shield,
  CheckCircle2,
  ShieldAlert,
} from 'lucide-react';
import { useAuth } from '../lib/authContext';
import {
  api,
  CaseRecord,
  ForensicResult,
  EvidencePackageItem,
  UTRCorrelationResult,
  TracePathItem,
} from '../lib/api';
import { GraphCanvas } from '../components/GraphCanvas';
import { ForensicDrawer } from '../components/ForensicDrawer';
import { EvidenceView } from '../components/EvidenceView';
import { CourtPresentationMode } from '../components/CourtPresentationMode';
import { ArjunaCopilotModal } from '../components/ArjunaCopilotModal';
import { IntelExchangeModal } from '../components/IntelExchangeModal';
import { WatchlistModal } from '../components/WatchlistModal';
import { HeaderSearchBar } from '../components/HeaderSearchBar';

interface CaseDetailPageProps {
  caseId: string;
  onBack: () => void;
  onSelectCase?: (caseId: string) => void;
}

export const CaseDetailPage: React.FC<CaseDetailPageProps> = ({ caseId, onBack, onSelectCase }) => {
  const { token } = useAuth();
  const [caseRecord, setCaseRecord] = useState<CaseRecord | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Forensic Analysis State
  const [forensicData, setForensicData] = useState<ForensicResult | null>(null);
  const [runningAnalysis, setRunningAnalysis] = useState<boolean>(false);

  // View States
  const [isCourtMode, setIsCourtMode] = useState<boolean>(false);
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  const [isEvidenceOpen, setIsEvidenceOpen] = useState<boolean>(false);

  // Phase 7 Innovation States
  const [isArjunaOpen, setIsArjunaOpen] = useState<boolean>(false);
  const [isIntelOpen, setIsIntelOpen] = useState<boolean>(false);
  const [isWatchlistOpen, setIsWatchlistOpen] = useState<boolean>(false);
  const [utrCorrelationResult, setUtrCorrelationResult] = useState<UTRCorrelationResult | null>(null);
  const [correlatingUtr, setCorrelatingUtr] = useState<boolean>(false);

  // Evidence Package State
  const [evidencePackage, setEvidencePackage] = useState<EvidencePackageItem | undefined>(undefined);
  const [legalNotice, setLegalNotice] = useState<string | undefined>(undefined);

  // Phase 8B Streaming Graph States
  const [isWsStreaming, setIsWsStreaming] = useState<boolean>(false);
  const [streamedHops, setStreamedHops] = useState<TracePathItem[]>([]);
  const [streamingHopIndex, setStreamingHopIndex] = useState<number>(0);
  const [streamingStatus, setStreamingStatus] = useState<string>('');
  const [detectedBridge, setDetectedBridge] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const handleStartWebSocketStream = () => {
    if (!caseRecord) return;
    const sub = caseRecord.submissions && caseRecord.submissions[0];
    if (!sub) {
      alert('No suspect wallet address submitted for this case.');
      return;
    }

    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {}
    }

    setIsWsStreaming(true);
    setStreamedHops([]);
    setStreamingHopIndex(0);
    setDetectedBridge(null);
    setStreamingStatus('Connecting to forensic WebSocket stream...');

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const port = window.location.port ? `:${window.location.port}` : '';
    // In local Vite dev (port 5173), direct WS to backend 8000; in production behind Nginx, use origin
    const wsBase = window.location.port === '5173' ? `${protocol}//${host}:8000` : `${protocol}//${host}${port}`;
    const token = localStorage.getItem('sentinel_token') || sessionStorage.getItem('sentinel_token');
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : '';
    const wsUrl = `${wsBase}/api/ws/trace/${sub.submission_id}${tokenQuery}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStreamingStatus(`Streaming trace for ${sub.address.slice(0, 8)}...`);
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'TRACE_STARTED') {
          setStreamingStatus(`Trace initialized: ${msg.total_hops} hops queued`);
        } else if (msg.type === 'HOP_DISCOVERED') {
          const hopItem: TracePathItem = {
            hop_index: msg.hop_index,
            from_addr: msg.from_addr,
            to_addr: msg.to_addr,
            value: msg.value,
            tx_hash: msg.tx_hash,
            chain: msg.chain,
            confirmations: msg.confirmations,
            low_confirmation: msg.low_confirmation,
            is_pending: msg.is_pending,
            is_bridge: msg.is_bridge,
            bridge_details: msg.bridge_details,
          };
          setStreamedHops((prev) => [...prev, hopItem]);
          setStreamingHopIndex(msg.hop_index);
          setStreamingStatus(`Discovered Hop ${msg.hop_index}: ${msg.from_addr.slice(0, 6)}... -> ${msg.to_addr.slice(0, 6)}... (${msg.value} ${msg.chain || 'ETH'})`);
          if (msg.is_bridge) {
            setDetectedBridge(msg.bridge_details);
          }
        } else if (msg.type === 'TRACE_COMPLETED') {
          setStreamingStatus(`Trace streaming complete: ${msg.matched_vasp || 'Off-ramp detected'}`);
          setIsWsStreaming(false);
          fetchCaseDetails();
        } else if (msg.type === 'ERROR') {
          setStreamingStatus(`Streaming error: ${msg.message}`);
          setIsWsStreaming(false);
        }
      } catch (err) {
        console.error('Error parsing WS trace frame:', err);
      }
    };

    ws.onerror = () => {
      setStreamingStatus('WebSocket streaming disconnected. Swapped to REST cache.');
      setIsWsStreaming(false);
    };

    ws.onclose = () => {
      setIsWsStreaming(false);
    };
  };

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {}
      }
    };
  }, []);

  const handleCorrelateUtr = async () => {
    if (!token || !caseId) return;
    setCorrelatingUtr(true);
    try {
      const res = await api.correlateCaseUTR(token, caseId, {
        time_tolerance_minutes: 120,
        amount_tolerance_percent: 5,
      });
      setUtrCorrelationResult(res);
    } catch (err: any) {
      alert(err.message || 'UPI-UTR correlation failed.');
    } finally {
      setCorrelatingUtr(false);
    }
  };

  const fetchCaseDetails = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getCase(token, caseId);
      setCaseRecord(data);

      // Check if submission already has an analysis run
      const sub = data.submissions && data.submissions[0];
      if (sub && sub.analysis_runs && sub.analysis_runs.length > 0) {
        const latestRun = sub.analysis_runs[0];
        if (
          latestRun.status === 'COMPLETED' ||
          latestRun.status === 'ANALYZED' ||
          latestRun.status?.startsWith('ANALYSIS_') ||
          latestRun.status === 'NO_CONFIDENT_OFF_RAMP'
        ) {
          // Fetch existing run details
          try {
            const fData = await api.getRunAnalysis(token, latestRun.run_id);
            setForensicData(fData);
          } catch {
            // Run analysis if full report wasn't cached
          }
        }
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load case details.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCaseDetails();
  }, [caseId, token]);

  const handleExecuteForensics = async () => {
    if (!token || !caseRecord) return;
    const sub = caseRecord.submissions && caseRecord.submissions[0];
    if (!sub) {
      alert('No suspect wallet address submitted for this case.');
      return;
    }

    setRunningAnalysis(true);
    try {
      const result = await api.runAnalysis(token, sub.submission_id);
      setForensicData(result);
      // Refresh case record so status updates
      await fetchCaseDetails();
    } catch (err: any) {
      alert(err.message || 'Forensic trace execution failed.');
    } finally {
      setRunningAnalysis(false);
    }
  };

  const handleOpenEvidence = async () => {
    if (!token || !caseRecord) return;
    const sub = caseRecord.submissions && caseRecord.submissions[0];
    const run = sub?.analysis_runs && sub.analysis_runs[0];

    if (!run || !forensicData) {
      alert('Please run forensic analysis first before generating evidence.');
      return;
    }

    try {
      const genRes = await api.generateEvidence(token, run.run_id);
      setEvidencePackage(genRes.package);
      setLegalNotice(genRes.legal_notice);
      setIsEvidenceOpen(true);
    } catch (err: any) {
      alert(err.message || 'Failed to compile evidence package.');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0b1120] text-slate-100 flex items-center justify-center font-mono text-xs">
        <RotateCw className="w-6 h-6 animate-spin text-blue-500 mr-2" />
        <span>Loading Case File {caseId}...</span>
      </div>
    );
  }

  if (error || !caseRecord) {
    return (
      <div className="min-h-screen bg-[#0b1120] text-slate-100 p-8">
        <button
          onClick={onBack}
          className="flex items-center space-x-2 text-blue-400 hover:text-white text-xs mb-6 font-mono"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Caseload</span>
        </button>
        <div className="p-6 rounded-xl border border-rose-800 bg-rose-950/20 text-rose-300 text-xs">
          <AlertTriangle className="w-5 h-5 text-rose-400 mb-2" />
          <h4 className="font-bold text-sm text-white mb-1">Unable to Load Case</h4>
          <p>{error || 'Case record not found.'}</p>
        </div>
      </div>
    );
  }

  const primarySubmission = caseRecord.submissions && caseRecord.submissions[0];
  const activeRun = primarySubmission?.analysis_runs && primarySubmission.analysis_runs[0];
  const runId = activeRun?.run_id || 'run-placeholder';

  const attr = forensicData?.attribution;
  const matchedEntity = attr?.matched_entity || caseRecord.latest_entity;
  const confidence = attr?.confidence ?? caseRecord.latest_confidence ?? 0;
  const band = attr?.confidence_band || (confidence >= 0.85 ? 'VERY_HIGH' : confidence >= 0.65 ? 'HIGH' : confidence >= 0.40 ? 'MEDIUM' : 'INSUFFICIENT_EVIDENCE');
  const hasLowConfirmation = Boolean(
    forensicData?.trace?.paths?.some(
      (p) => p.low_confirmation || (p.confirmations !== undefined && p.confirmations < 3) || p.is_pending
    )
  );

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case 'ANALYSIS_COMPLETE_ATTRIBUTED':
      case 'COMPLETED':
        return {
          label: 'Attributed to Off-Ramp',
          style: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
        };
      case 'ANALYSIS_COMPLETE_NO_PATH_FOUND':
      case 'NO_CONFIDENT_OFF_RAMP':
        return {
          label: 'No Off-Ramp Path Found',
          style: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
        };
      case 'ANALYSIS_FAILED_ADAPTER_ERROR':
        return {
          label: 'Adapter / Provider Error',
          style: 'bg-red-500/10 text-red-400 border-red-500/30',
        };
      case 'ANALYSIS_FAILED_INVALID_ADDRESS':
        return {
          label: 'Invalid Address Format',
          style: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
        };
      default:
        return {
          label: status || 'PENDING TRACE',
          style: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
        };
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#0a0e17] text-slate-100 font-sans overflow-hidden">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-[#0f172a]/90 backdrop-blur z-20">
        <div className="px-6 py-3 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button
              onClick={onBack}
              className="p-2 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
              title="Return to Caseload"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>

            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-white text-base">
                  {caseRecord.ncrp_ref || 'Case Investigation File'}
                </span>
                {(() => {
                  const badge = getStatusBadge(forensicData?.status || caseRecord.submissions?.[0]?.analysis_runs?.[0]?.status || caseRecord.status);
                  return (
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider border ${badge.style}`}>
                      {badge.label}
                    </span>
                  );
                })()}
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                Victim UTR: {caseRecord.victim_utr || '—'} &bull; Fraud: ₹{(caseRecord.amount_inr || 0).toLocaleString('en-IN')} INR
              </p>
            </div>

            {/* Universal One-Box Search Bar */}
            <div className="hidden xl:block ml-4">
              <HeaderSearchBar token={token || undefined} onSelectCase={onSelectCase} />
            </div>
          </div>

          {/* Action Toolbar */}
          <div className="flex flex-wrap items-center gap-2">
            {/* Arjuna AI Prosecution Summary Co-pilot */}
            {forensicData && (
              <button
                onClick={() => setIsArjunaOpen(true)}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-semibold shadow-lg shadow-amber-500/10 transition-colors"
                title="Generate Judicial Prosecution Summary via Arjuna AI"
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                <span>Arjuna AI</span>
              </button>
            )}

            {/* Police Intel Exchange */}
            <button
              onClick={() => setIsIntelOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition-colors"
              title="Query or Submit to Privacy-Preserving Police Intel Exchange"
            >
              <Shield className="w-3.5 h-3.5 text-blue-400" />
              <span>Intel Exchange</span>
            </button>

            {/* Watchlist */}
            <button
              onClick={() => setIsWatchlistOpen(true)}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 text-xs font-semibold transition-colors"
              title="Golden Hour Surveillance Watchlist"
            >
              <Eye className="w-3.5 h-3.5 text-amber-400" />
              <span>Watchlist</span>
            </button>

            {/* Court Presentation Mode Toggle */}
            <button
              onClick={() => setIsCourtMode(!isCourtMode)}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all ${
                isCourtMode
                  ? 'bg-amber-500 text-slate-950 border-amber-400 shadow-lg shadow-amber-500/30'
                  : 'bg-slate-900 border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800'
              }`}
            >
              <Gavel className="w-3.5 h-3.5" />
              <span>{isCourtMode ? 'Court Mode (Active)' : 'Court Presentation'}</span>
            </button>

            {/* Explainable Forensics Button */}
            {forensicData && (
              <button
                onClick={() => setIsDrawerOpen(true)}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white text-xs font-semibold transition-colors"
              >
                <Scale className="w-3.5 h-3.5 text-blue-400" />
                <span>Forensic Matrix</span>
              </button>
            )}

            {/* Evidence & Statutory Notice Button */}
            {forensicData && (
              <button
                onClick={handleOpenEvidence}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-colors"
              >
                <FileCheck className="w-3.5 h-3.5" />
                <span>Court Evidence &amp; Notice</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Root-Address Direct Attribution Banner */}
      {forensicData?.is_root_entity && (
        <div className="bg-emerald-950/50 border-b border-emerald-500/40 px-6 py-2.5 flex items-center justify-between text-xs text-emerald-300">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>
              <strong>Root-Address Direct Attribution:</strong> Suspect address belongs directly to verified entity{' '}
              <strong>{forensicData.attribution?.matched_entity}</strong> (0 hops required by design). Outward tracing was bypassed.
            </span>
          </div>
          <span className="font-mono text-[10px] font-bold bg-emerald-500/20 px-2.5 py-0.5 rounded border border-emerald-500/30 text-emerald-200">
            100% CONFIDENCE &bull; 0 HOPS
          </span>
        </div>
      )}

      {/* Invalid Address Format Failure Banner */}
      {forensicData?.status === 'ANALYSIS_FAILED_INVALID_ADDRESS' && (
        <div className="bg-rose-950/60 border-b border-rose-500/50 px-6 py-2.5 flex items-center justify-between text-xs text-rose-200 animate-in fade-in">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>
              <strong>Cryptographic Validation Failure:</strong> The submitted address failed mathematical checksum verification across EVM (EIP-55), Bitcoin (Base58Check/Bech32), and TRON standards. Outward tracing was aborted.
            </span>
          </div>
          <span className="font-mono text-[10px] font-bold bg-rose-500/20 px-2.5 py-0.5 rounded border border-rose-500/40 text-rose-300 shrink-0">
            INVALID ADDRESS FORMAT
          </span>
        </div>
      )}

      {/* Adapter / Provider Failure Banner */}
      {forensicData?.status === 'ANALYSIS_FAILED_ADAPTER_ERROR' && (
        <div className="bg-red-950/60 border-b border-red-500/50 px-6 py-2.5 flex items-center justify-between text-xs text-red-200 animate-in fade-in">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <span>
              <strong>Adapter / Provider Network Failure:</strong> Live blockchain provider request timed out or encountered an RPC error.
            </span>
          </div>
          <span className="font-mono text-[10px] font-bold bg-red-500/20 px-2.5 py-0.5 rounded border border-red-500/40 text-red-300 shrink-0">
            ADAPTER ERROR
          </span>
        </div>
      )}

      {/* Low-Confirmation Reorg Honesty Warning Banner */}
      {hasLowConfirmation && (
        <div className="bg-amber-950/60 border-b border-amber-500/50 px-6 py-2.5 flex items-center justify-between text-xs text-amber-200 animate-in fade-in">
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 animate-pulse" />
            <span>
              <strong>Forensic Freshness Notice:</strong> One or more transaction hops in this path have fewer than 3 block confirmations (or remain unconfirmed in the mempool). This path is <em>low-confirmation, subject to potential chain reorganization</em>.
            </span>
          </div>
          <span className="font-mono text-[10px] font-bold bg-amber-500/20 px-2.5 py-0.5 rounded border border-amber-500/40 text-amber-300 shrink-0">
            &lt; 3 CONFIRMATIONS &bull; REORG RISK
          </span>
        </div>
      )}

      {/* Main Workspace Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Case Metadata & Suspect Header Strip */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 font-mono text-xs">
            <span className="text-slate-500 text-[10px] uppercase font-bold">Suspect Wallet Address</span>
            <div className="text-white font-bold truncate mt-1 select-all">
              {primarySubmission?.address || 'No wallet registered'}
            </div>
            <p className="text-slate-400 text-[10px] mt-0.5">Network: {primarySubmission?.chain || 'ETH'}</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 font-mono text-xs">
            <span className="text-slate-500 text-[10px] uppercase font-bold">Attributed Off-Ramp</span>
            <div className="text-white font-bold text-sm mt-1 flex items-center space-x-2">
              <span>{matchedEntity || 'Pending'}</span>
              {confidence > 0 && (
                <span className="px-1.5 py-0.2 rounded text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  {Math.round(confidence * 100)}%
                </span>
              )}
            </div>
            <p className="text-slate-400 text-[10px] mt-0.5">Band: {band}</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 font-mono text-xs">
            <span className="text-slate-500 text-[10px] uppercase font-bold">Investigating Officer</span>
            <div className="text-white font-bold text-sm mt-1">{caseRecord.assigned_officer_name}</div>
            <p className="text-slate-400 text-[10px] mt-0.5">Cyber Crime Division</p>
          </div>

          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 font-mono text-xs">
            <span className="text-slate-500 text-[10px] uppercase font-bold">Forensic Pipeline Status</span>
            <div className="mt-1 flex items-center justify-between">
              <span className={`font-bold ${
                forensicData?.status === 'ANALYSIS_COMPLETE_ATTRIBUTED' || forensicData?.status === 'COMPLETED'
                  ? 'text-emerald-400'
                  : forensicData?.status === 'ANALYSIS_COMPLETE_NO_PATH_FOUND' || forensicData?.status === 'NO_CONFIDENT_OFF_RAMP'
                  ? 'text-amber-400'
                  : forensicData?.status === 'ANALYSIS_FAILED_ADAPTER_ERROR' || forensicData?.status === 'ANALYSIS_FAILED_INVALID_ADDRESS'
                  ? 'text-rose-400'
                  : 'text-slate-200'
              }`}>
                {forensicData ? getStatusBadge(forensicData.status).label : 'Awaiting Execution'}
              </span>
              {!forensicData && (
                <button
                  onClick={handleExecuteForensics}
                  disabled={runningAnalysis}
                  className="flex items-center space-x-1 px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white font-sans text-xs font-semibold transition-colors disabled:opacity-50"
                >
                  <Play className={`w-3 h-3 ${runningAnalysis ? 'animate-spin' : ''}`} />
                  <span>{runningAnalysis ? 'Tracing...' : 'Run Trace'}</span>
                </button>
              )}
            </div>
            <p className="text-slate-400 text-[10px] mt-0.5">
              {forensicData
                ? forensicData.status === 'ANALYSIS_FAILED_INVALID_ADDRESS'
                  ? 'Checksum validation failed'
                  : forensicData.status === 'ANALYSIS_FAILED_ADAPTER_ERROR'
                  ? 'Provider connection failed'
                  : `${forensicData.trace.total_hops} Hops Analyzed`
                : 'Dominant flow BFS'}
            </p>
          </div>
        </div>

        {/* UPI-UTR Correlator Heuristic Card */}
        {caseRecord.victim_utr && (
          <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-950/20 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 text-xs">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
                <CheckCircle2 className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <h4 className="font-bold text-white text-sm">UPI-UTR Banking Correlator</h4>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                    MHA / I4C HEURISTIC
                  </span>
                </div>
                <p className="text-slate-400 text-[11px] mt-0.5 font-mono">
                  Victim UTR: <strong className="text-indigo-300">{caseRecord.victim_utr}</strong> &bull; Reported Fraud: <strong className="text-emerald-400">₹{(caseRecord.amount_inr || 0).toLocaleString('en-IN')} INR</strong>
                </p>
                {utrCorrelationResult?.best_candidate && (
                  <p className="text-emerald-400 text-[11px] mt-1 font-mono">
                    Candidate Matched: {utrCorrelationResult.best_candidate.explanation} (Δ {utrCorrelationResult.best_candidate.amount_diff_percent.toFixed(1)}% INR, Δ {Math.round(utrCorrelationResult.best_candidate.time_diff_minutes)}m)
                  </p>
                )}
                {utrCorrelationResult && !utrCorrelationResult.best_candidate && (
                  <p className="text-amber-400 text-[11px] mt-1 font-mono">
                    No on-chain deposit found within 120min / ±5% tolerance window.
                  </p>
                )}
              </div>
            </div>

            <button
              onClick={handleCorrelateUtr}
              disabled={correlatingUtr}
              className="px-3.5 py-1.5 rounded-lg border border-indigo-500/40 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 hover:text-white font-semibold text-xs transition-colors shrink-0 disabled:opacity-50"
            >
              {correlatingUtr ? 'Evaluating Tolerance Window...' : utrCorrelationResult ? 'Re-Correlate UTR' : 'Correlate On-Chain Deposits'}
            </button>
          </div>
        )}

        {/* Viewport: Either Court Presentation Mode OR Cytoscape Technical Graph */}
        {isCourtMode ? (
          <CourtPresentationMode
            paths={forensicData?.trace?.paths || streamedHops}
            startAddress={primarySubmission?.address || ''}
            chain={primarySubmission?.chain || 'ETH'}
            ncrpRef={caseRecord.ncrp_ref}
            victimUtr={caseRecord.victim_utr}
            totalAmountInr={caseRecord.amount_inr || 1125000}
            attribution={forensicData?.attribution}
            onExit={() => setIsCourtMode(false)}
          />
        ) : forensicData || isWsStreaming || streamedHops.length > 0 ? (
          <div className="space-y-4">
            {/* Live Streaming Active Status Banner */}
            {isWsStreaming && (
              <div className="p-3 rounded-xl bg-purple-950/40 border border-purple-500/40 flex items-center justify-between text-xs text-purple-200 animate-pulse">
                <div className="flex items-center space-x-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-400"></span>
                  <span className="font-mono">{streamingStatus}</span>
                </div>
                <span className="text-[11px] font-mono text-purple-300">
                  WebSocket Streaming &bull; Hop {streamingHopIndex}
                </span>
              </div>
            )}

            {/* Detected Bridge Notification Banner */}
            {detectedBridge && (
              <div className="p-3 rounded-xl bg-purple-950/60 border border-purple-500/60 flex items-center justify-between text-xs text-purple-200">
                <div className="flex items-center space-x-2">
                  <span className="text-base">🌉</span>
                  <div>
                    <span className="font-bold">Cross-Chain Bridge Identified:</span> {detectedBridge.bridge_name}
                    <span className="ml-2 text-purple-300 font-mono text-[11px]">(Target Chain: {detectedBridge.destination_chain} &bull; Rule: {detectedBridge.decoding_rule})</span>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded bg-purple-900/80 border border-purple-400/40 text-[10px] font-mono text-purple-200">
                  Receipt Log Decoder Verified
                </span>
              </div>
            )}

            {/* Quick Forensic Summary Header */}
            <div className="p-4 rounded-xl border border-blue-500/20 bg-blue-950/20 flex flex-wrap items-center justify-between gap-4 text-xs">
              <div className="flex items-center space-x-3">
                <div className="p-2 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-400">
                  <Network className="w-5 h-5" />
                </div>
                <div>
                  <h4 className="font-bold text-white text-sm">
                    Multi-Hop Fund Flow &bull; Off-Ramp: {matchedEntity || (isWsStreaming ? 'Streaming...' : 'Pending')}
                  </h4>
                  <p className="text-slate-400 text-[11px]">
                    Trace reached verified deposit infrastructure within {(isWsStreaming || (streamedHops.length > 0 && (!forensicData || forensicData.trace.paths.length === 0)) ? streamedHops : (forensicData?.trace?.paths || [])).length} hops.
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-4 font-mono text-xs">
                <div className="text-right">
                  <span className="text-slate-400 text-[10px] block">Confidence Band</span>
                  <span className="text-emerald-400 font-bold">{band} ({Math.round(confidence * 100)}%)</span>
                </div>
                <div className="text-right">
                  <span className="text-slate-400 text-[10px] block">Composite Risk</span>
                  <span className="text-amber-400 font-bold">{forensicData?.risk?.composite_score ?? 59}/100</span>
                </div>
                <div className="text-right">
                  <span className="text-slate-400 text-[10px] block">FIFO Taint</span>
                  <span className="text-rose-400 font-bold">{(forensicData?.taint?.final_taint_percentage ?? 100).toFixed(1)}%</span>
                </div>
              </div>
            </div>

            {/* Cytoscape.js Canvas */}
            <GraphCanvas
              paths={isWsStreaming || (streamedHops.length > 0 && (!forensicData || forensicData.trace.paths.length === 0)) ? streamedHops : (forensicData?.trace?.paths || [])}
              startAddress={primarySubmission?.address || ''}
              chain={primarySubmission?.chain || 'ETH'}
              matchedEntity={matchedEntity || undefined}
              attributionRule={forensicData?.attribution?.rule_fired}
              confidence={confidence}
              isStreaming={isWsStreaming}
              streamingHopIndex={streamingHopIndex}
              onReplayTrace={handleStartWebSocketStream}
            />
          </div>
        ) : (
          /* Empty / Trigger State */
          <div className="p-16 text-center border border-dashed border-slate-800 rounded-2xl bg-slate-900/30">
            <div className="w-12 h-12 rounded-2xl bg-blue-600/10 border border-blue-500/30 text-blue-400 flex items-center justify-center mx-auto mb-4">
              <Network className="w-6 h-6" />
            </div>
            <h3 className="text-base font-bold text-white mb-2">Automated Forensic Analytics Pending</h3>
            <p className="text-xs text-slate-400 max-w-md mx-auto mb-6">
              Initialize bounded breadth-first search across blockchain nodes to identify multi-hop dissipation paths and attribute the receiving exchange.
            </p>
            <div className="flex items-center justify-center space-x-3">
              <button
                onClick={handleStartWebSocketStream}
                disabled={runningAnalysis || isWsStreaming}
                className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-xl shadow-purple-600/30 transition-all disabled:opacity-50"
              >
                <Play className={`w-4 h-4 ${isWsStreaming ? 'animate-spin' : ''}`} />
                <span>{isWsStreaming ? 'Streaming Live Trace...' : '⚡ Stream Live Trace (WebSocket)'}</span>
              </button>
              <button
                onClick={handleExecuteForensics}
                disabled={runningAnalysis || isWsStreaming}
                className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-xl shadow-blue-600/30 transition-all disabled:opacity-50"
              >
                <Play className={`w-4 h-4 ${runningAnalysis ? 'animate-spin' : ''}`} />
                <span>{runningAnalysis ? 'Tracing Multi-Hop Paths...' : 'Standard Forensic Trace'}</span>
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Slide-out Explainable Forensic Drawer */}
      <ForensicDrawer
        attribution={forensicData?.attribution}
        typologies={forensicData?.typologies}
        taint={forensicData?.taint}
        risk={forensicData?.risk}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />

      {/* Court Evidence & Notice Modal */}
      <EvidenceView
        runId={runId}
        evidencePackage={evidencePackage}
        legalNotice={legalNotice}
        forensicData={forensicData || undefined}
        isOpen={isEvidenceOpen}
        onClose={() => setIsEvidenceOpen(false)}
        token={token || undefined}
      />

      {/* Arjuna AI Prosecution Co-pilot Modal */}
      {token && (
        <ArjunaCopilotModal
          isOpen={isArjunaOpen}
          onClose={() => setIsArjunaOpen(false)}
          token={token}
          caseId={caseId}
          ncrpRef={caseRecord.ncrp_ref}
        />
      )}

      {/* Police Intel Exchange Modal */}
      {token && (
        <IntelExchangeModal
          isOpen={isIntelOpen}
          onClose={() => setIsIntelOpen(false)}
          token={token}
          defaultAddress={primarySubmission?.address || ''}
          officerDistrict={caseRecord.assigned_officer_name || 'Cyber Crime Unit'}
        />
      )}

      {/* Golden Hour Watchlist Modal */}
      {token && (
        <WatchlistModal
          isOpen={isWatchlistOpen}
          onClose={() => setIsWatchlistOpen(false)}
          token={token}
          defaultCaseId={caseId}
          defaultAddress={primarySubmission?.address || ''}
        />
      )}
    </div>
  );
};
