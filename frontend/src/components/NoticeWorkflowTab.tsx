import React, { useState, useEffect } from 'react';
import {
  Send,
  FileText,
  Clock,
  CheckCircle2,
  AlertCircle,
  Download,
  Sparkles,
  Building2,
  RefreshCw,
  Plus,
  UserCheck,
} from 'lucide-react';
import {
  api,
  NoticeRecord,
  ExchangeContact,
  NoticeCreatePayload,
} from '../lib/api';
import { useAuth } from '../lib/authContext';

interface NoticeWorkflowTabProps {
  caseId: string;
  ncrpRef?: string;
  submissions?: Array<{ chain: string; address: string }>;
  token: string | null;
}

export const NoticeWorkflowTab: React.FC<NoticeWorkflowTabProps> = ({
  caseId,
  ncrpRef,
  submissions = [],
  token,
}) => {
  const { officer } = useAuth();
  const [notices, setNotices] = useState<NoticeRecord[]>([]);
  const [contacts, setContacts] = useState<ExchangeContact[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Selected notice for detail/edit
  const [selectedNotice, setSelectedNotice] = useState<NoticeRecord | null>(null);
  const [editedSubject, setEditedSubject] = useState<string>('');
  const [editedBody, setEditedBody] = useState<string>('');
  const [polishing, setPolishing] = useState<boolean>(false);


  // New notice modal state
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [newKind, setNewKind] = useState<'preservation' | 'freeze'>('preservation');
  const [selectedExchangeId, setSelectedExchangeId] = useState<string>('');
  const [customName, setCustomName] = useState<string>('');
  const [customEmail, setCustomEmail] = useState<string>('');
  const [firReference, setFirReference] = useState<string>('');
  const [replyDeadlineHours, setReplyDeadlineHours] = useState<number>(48);
  const [legalBasisText, setLegalBasisText] = useState<string>(
    'under the applicable provisions of the Bharatiya Nagarik Suraksha Sanhita, 2023 (section to be confirmed by the investigating officer)'
  );
  const [submittingCreate, setSubmittingCreate] = useState<boolean>(false);

  const isSupervisorOrAdmin =
    officer?.role === 'SUPERVISOR' ||
    officer?.role === 'ADMIN' ||
    (officer?.role as string) === 'APPROVER';

  const fetchNotices = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getCaseNotices(token, caseId);
      setNotices(res.notices);
      setContacts(res.contacts);
      if (res.notices.length > 0 && !selectedNotice) {
        setSelectedNotice(res.notices[0]);
      } else if (selectedNotice) {
        const updated = res.notices.find((n) => n.id === selectedNotice.id);
        if (updated) setSelectedNotice(updated);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch statutory notices.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotices();
  }, [caseId, token]);

  useEffect(() => {
    if (selectedNotice) {
      setEditedSubject(selectedNotice.subject);
      setEditedBody(selectedNotice.body);
    }
  }, [selectedNotice?.id]);

  const handleSelectExchange = (exchId: string) => {
    setSelectedExchangeId(exchId);
    const found = contacts.find((c) => c.id === exchId);
    if (found) {
      setCustomName(found.exchange_name);
      setCustomEmail(found.nodal_email);
    }
  };

  const handleCreateNotice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setSubmittingCreate(true);
    setActionMessage(null);
    try {
      const payload: NoticeCreatePayload = {
        kind: newKind,
        recipient_name: customName || 'Nodal Compliance Officer',
        recipient_email: customEmail,
        fir_reference: firReference || undefined,
        legal_basis_text: legalBasisText,
        reply_deadline_hours: replyDeadlineHours,
        addresses: submissions.map((s) => ({ chain: s.chain, address: s.address })),
      };

      const created = await api.createNoticeDraft(token, caseId, payload);
      setIsCreateOpen(false);
      await fetchNotices();
      setSelectedNotice(created);
      setActionMessage(`Draft for ${created.kind.toUpperCase()} notice successfully prepared.`);
    } catch (err: any) {
      setError(err.message || 'Failed to generate notice draft.');
    } finally {
      setSubmittingCreate(false);
    }
  };

  const handleSaveEdits = async () => {
    if (!token || !selectedNotice) return;
    try {
      const updated = await api.updateNoticeDraft(token, selectedNotice.id, {
        subject: editedSubject,
        body: editedBody,
      });
      setSelectedNotice(updated);
      setActionMessage('Notice draft modifications saved.');
      await fetchNotices();
    } catch (err: any) {
      setError(err.message || 'Failed to save edits.');
    }
  };

  const handlePolishTone = async () => {
    if (!token || !selectedNotice) return;
    setPolishing(true);
    setActionMessage(null);
    try {
      const res = await api.polishNoticeTone(token, selectedNotice.id, editedBody);
      if (res.is_polished) {
        setEditedBody(res.polished_body);
        setActionMessage('Tone successfully polished and cross-verified against cryptographic coordinates.');
        await fetchNotices();
      } else {
        setActionMessage(`AI Polish Note: ${res.note}`);
      }
    } catch (err: any) {
      setError(err.message || 'Tone polish failed.');
    } finally {
      setPolishing(false);
    }
  };

  const handleSubmitForApproval = async () => {
    if (!token || !selectedNotice) return;
    try {
      const res = await api.submitNoticeForApproval(token, selectedNotice.id);
      setActionMessage(res.message);
      await fetchNotices();
    } catch (err: any) {
      setError(err.message || 'Failed to submit notice for approval.');
    }
  };

  const handleApprove = async () => {
    if (!token || !selectedNotice) return;
    try {
      const res = await api.approveNotice(token, selectedNotice.id);
      setActionMessage(res.message);
      await fetchNotices();
    } catch (err: any) {
      setError(err.message || 'Approval rejected.');
    }
  };

  const handleSend = async () => {
    if (!token || !selectedNotice) return;
    try {
      const res = await api.sendNotice(token, selectedNotice.id);
      setActionMessage(res.message);
      await fetchNotices();
    } catch (err: any) {
      setError(err.message || 'Dispatch failed.');
    }
  };

  const getStatusBadge = (st: string) => {
    switch (st) {
      case 'draft':
        return 'bg-slate-800 text-slate-300 border-slate-700';
      case 'pending_approval':
        return 'bg-amber-500/10 text-amber-300 border-amber-500/30 animate-pulse';
      case 'approved':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'sent':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      case 'replied':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/30';
      case 'cancelled':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Action Header */}
      <div className="p-5 rounded-xl border border-slate-800 bg-[#0f172a] flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <Send className="w-5 h-5 text-blue-400" />
            <h3 className="text-base font-bold text-white tracking-wide">
              Exchange Requisitions &amp; Statutory Notices
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-300 border border-blue-500/20">
              BNSS 2023 &bull; Section 94 Requisitions
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1 max-w-2xl">
            Formal preservation directives and debit-freeze notices to Virtual Asset Service Providers (VASPs).
            All notices enforce a mandatory human approval workflow and default to dry-run <code className="text-slate-300 font-mono">.eml</code> outbox mode.
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          <button
            onClick={fetchNotices}
            className="p-2 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            title="Refresh Notices"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="flex-1 md:flex-none flex items-center justify-center space-x-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Draft Statutory Notice</span>
          </button>
        </div>
      </div>

      {actionMessage && (
        <div className="p-3.5 rounded-lg border border-blue-500/30 bg-blue-500/10 text-blue-300 text-xs flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-blue-400 shrink-0" />
          <span>{actionMessage}</span>
        </div>
      )}

      {error && (
        <div className="p-3.5 rounded-lg border border-rose-500/30 bg-rose-500/10 text-rose-300 text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Main Grid: Notices List (Left) & Notice Detail Workspace (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Notice Records List */}
        <div className="lg:col-span-4 space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-400 font-semibold px-1">
            <span>Case Notices ({notices.length})</span>
            <span className="text-[10px] text-slate-500 font-mono">Case: {ncrpRef || caseId.slice(0, 8)}</span>
          </div>

          {notices.length === 0 ? (
            <div className="p-8 rounded-xl border border-dashed border-slate-800 bg-slate-900/30 text-center">
              <FileText className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-xs text-slate-400 font-medium">No statutory notices drafted yet.</p>
              <p className="text-[11px] text-slate-500 mt-1">
                Generate a preservation or freeze request to send to registered exchange nodal contacts.
              </p>
              <button
                onClick={() => setIsCreateOpen(true)}
                className="mt-4 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900 text-blue-400 text-xs font-semibold hover:bg-slate-800"
              >
                + Create First Draft
              </button>
            </div>
          ) : (
            <div className="space-y-2 max-h-[700px] overflow-y-auto pr-1">
              {notices.map((n) => {
                const isSelected = selectedNotice?.id === n.id;
                return (
                  <div
                    key={n.id}
                    onClick={() => setSelectedNotice(n)}
                    className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'border-blue-500/50 bg-blue-950/20 shadow-lg'
                        : 'border-slate-800 bg-slate-900/40 hover:bg-slate-800/40'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                        {n.kind}
                      </span>
                      <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold border ${getStatusBadge(n.status)}`}>
                        {n.status.replace('_', ' ').toUpperCase()}
                      </span>
                    </div>

                    <div className="text-xs text-slate-300 font-medium truncate mb-1">
                      {n.recipient_name}
                    </div>

                    <div className="text-[11px] text-slate-500 truncate font-mono">
                      {n.recipient_email}
                    </div>

                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/60 text-[10px] text-slate-500">
                      <span>By: {n.creator_name || 'Investigator'}</span>
                      <span className="flex items-center space-x-1">
                        <Clock className="w-3 h-3" />
                        <span>{n.due_at ? new Date(n.due_at).toLocaleDateString() : 'No Deadline'}</span>
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Column: Active Notice Workspace */}
        <div className="lg:col-span-8">
          {selectedNotice ? (
            <div className="p-6 rounded-xl border border-slate-800 bg-[#0f172a] shadow-xl space-y-6">
              {/* Notice Metadata Header */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between pb-4 border-b border-slate-800 gap-4">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                      {selectedNotice.kind} REQUISITION
                    </span>
                    <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold border ${getStatusBadge(selectedNotice.status)}`}>
                      {selectedNotice.status.replace('_', ' ').toUpperCase()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 font-mono">
                    ID: {selectedNotice.id} &bull; Created: {selectedNotice.created_at ? new Date(selectedNotice.created_at).toLocaleString() : 'N/A'}
                  </p>
                </div>

                {/* Workflow Actions */}
                <div className="flex flex-wrap items-center gap-2">
                  {/* Investigator Submit */}
                  {selectedNotice.status === 'draft' && (
                    <button
                      onClick={handleSubmitForApproval}
                      className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition-colors"
                    >
                      Submit for Approval
                    </button>
                  )}

                  {/* Supervisor/Admin Approve */}
                  {selectedNotice.status === 'pending_approval' && (
                    <>
                      {isSupervisorOrAdmin ? (
                        <button
                          onClick={handleApprove}
                          className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md transition-colors"
                        >
                          <UserCheck className="w-3.5 h-3.5" />
                          <span>Authorize / Approve</span>
                        </button>
                      ) : (
                        <span className="text-[11px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 rounded-md">
                          Awaiting Supervisor Approval
                        </span>
                      )}
                    </>
                  )}

                  {/* Dispatch (Dry-Run or SMTP) */}
                  {selectedNotice.status === 'approved' && (
                    <button
                      onClick={handleSend}
                      className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition-colors"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>Dispatch Requisition</span>
                    </button>
                  )}

                  {/* Download EML */}
                  <a
                    href={api.getNoticeEmlUrl(selectedNotice.id)}
                    download
                    className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-medium"
                    title="Download RFC-822 EML File"
                  >
                    <Download className="w-3.5 h-3.5 text-blue-400" />
                    <span>.eml</span>
                  </a>

                  {/* Download PDF */}
                  <a
                    href={api.getNoticePdfUrl(selectedNotice.id)}
                    download
                    className="flex items-center space-x-1 px-2.5 py-1.5 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-medium"
                    title="Download Police Requisition PDF"
                  >
                    <Download className="w-3.5 h-3.5 text-rose-400" />
                    <span>PDF</span>
                  </a>
                </div>
              </div>

              {/* Recipient Coordinates Summary */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 text-xs">
                <div>
                  <span className="text-slate-500 block text-[11px]">Recipient / Exchange</span>
                  <span className="text-white font-medium">{selectedNotice.recipient_name}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Nodal Email</span>
                  <span className="text-white font-mono">{selectedNotice.recipient_email}</span>
                </div>
                <div>
                  <span className="text-slate-500 block text-[11px]">Compliance Deadline</span>
                  <span className="text-amber-400 font-mono font-medium">
                    {selectedNotice.due_at ? new Date(selectedNotice.due_at).toLocaleString() : 'Immediate'}
                  </span>
                </div>
              </div>

              {/* Subject Line Field */}
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-400">Notice Subject Line</label>
                {selectedNotice.status === 'draft' ? (
                  <input
                    type="text"
                    value={editedSubject}
                    onChange={(e) => setEditedSubject(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                  />
                ) : (
                  <div className="p-2.5 bg-slate-900/40 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono">
                    {selectedNotice.subject}
                  </div>
                )}
              </div>

              {/* Notice Body Workspace */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-[11px] font-semibold text-slate-400">
                    Statutory Requisition Text (Jinja2 Autoescaped)
                  </label>
                  {selectedNotice.status === 'draft' && (
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={handlePolishTone}
                        disabled={polishing}
                        className="flex items-center space-x-1 text-[11px] text-cyan-400 hover:text-cyan-300 px-2 py-1 rounded border border-cyan-500/30 bg-cyan-500/10 hover:bg-cyan-500/20 font-semibold"
                        title="Guarded LLM Tone Polish (Ensures addresses & hashes remain unaltered)"
                      >
                        <Sparkles className={`w-3 h-3 ${polishing ? 'animate-spin' : ''}`} />
                        <span>{polishing ? 'Verifying...' : 'Polish Tone (AI Guarded)'}</span>
                      </button>

                      <button
                        onClick={handleSaveEdits}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-white text-[11px] font-semibold border border-slate-700"
                      >
                        Save Edits
                      </button>
                    </div>
                  )}
                </div>

                {selectedNotice.status === 'draft' ? (
                  <textarea
                    rows={16}
                    value={editedBody}
                    onChange={(e) => setEditedBody(e.target.value)}
                    className="w-full p-4 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono focus:outline-none focus:border-blue-500 leading-relaxed"
                  />
                ) : (
                  <pre className="w-full p-4 bg-slate-900/60 border border-slate-800 rounded-lg text-xs text-slate-300 font-mono whitespace-pre-wrap leading-relaxed max-h-[500px] overflow-y-auto">
                    {selectedNotice.body}
                  </pre>
                )}
              </div>

              {/* Status Timeline & Audit Trail */}
              {selectedNotice.events && selectedNotice.events.length > 0 && (
                <div className="pt-4 border-t border-slate-800 space-y-3">
                  <h4 className="text-xs font-bold text-white flex items-center space-x-2">
                    <Clock className="w-3.5 h-3.5 text-blue-400" />
                    <span>Audit Event Timeline</span>
                  </h4>
                  <div className="space-y-2">
                    {selectedNotice.events.map((ev) => (
                      <div key={ev.id} className="p-2.5 rounded-lg bg-slate-900/40 border border-slate-800/80 text-xs flex items-start justify-between">
                        <div>
                          <div className="flex items-center space-x-2">
                            <span className="font-bold text-blue-400 font-mono text-[11px]">{ev.event_type}</span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              {ev.from_status ? `${ev.from_status} → ${ev.to_status}` : ev.to_status}
                            </span>
                          </div>
                          {ev.notes && <p className="text-[11px] text-slate-400 mt-0.5">{ev.notes}</p>}
                        </div>
                        <span className="text-[10px] text-slate-500 font-mono shrink-0 ml-4">
                          {new Date(ev.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-12 rounded-xl border border-dashed border-slate-800 bg-[#0f172a]/50 text-center">
              <Building2 className="w-10 h-10 text-slate-600 mx-auto mb-3" />
              <h4 className="text-sm font-bold text-white">Select a Notice</h4>
              <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                Choose a requisition notice from the list on the left to review, polish, approve, or dispatch.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Notice Creation Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#0f172a] border border-blue-500/30 rounded-2xl w-full max-w-2xl shadow-2xl p-6 space-y-5 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <FileText className="w-5 h-5 text-blue-400" />
                <h3 className="text-sm font-bold text-white">Draft Statutory Requisition Notice</h3>
              </div>
              <button
                onClick={() => setIsCreateOpen(false)}
                className="text-slate-400 hover:text-white text-xs font-semibold"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateNotice} className="space-y-4">
              {/* Kind Selector */}
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Requisition Type</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setNewKind('preservation')}
                    className={`p-3 rounded-xl border text-left text-xs transition-colors ${
                      newKind === 'preservation'
                        ? 'border-blue-500 bg-blue-600/10 text-white font-bold'
                        : 'border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <div className="font-semibold text-blue-400">Preservation Request</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">Directs 90-day retention of KYC, IP, and ledger logs.</div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setNewKind('freeze')}
                    className={`p-3 rounded-xl border text-left text-xs transition-colors ${
                      newKind === 'freeze'
                        ? 'border-rose-500 bg-rose-600/10 text-white font-bold'
                        : 'border-slate-800 bg-slate-900 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <div className="font-semibold text-rose-400">Debit-Freeze Request</div>
                    <div className="text-[11px] text-slate-400 mt-0.5">Emergency asset restraint on target deposit/hot wallets.</div>
                  </button>
                </div>
              </div>

              {/* Recipient Directory Dropdown */}
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  Recipient VASP / Exchange
                </label>
                <select
                  value={selectedExchangeId}
                  onChange={(e) => handleSelectExchange(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500 font-mono mb-2"
                >
                  <option value="">-- Choose from FIU-IND Directory or enter custom --</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.exchange_name} ({c.nodal_email})
                    </option>
                  ))}
                </select>

                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="text"
                    placeholder="Recipient Name (e.g. Nodal Officer)"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    required
                    className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500"
                  />
                  <input
                    type="email"
                    placeholder="Nodal Email (e.g. nodal@exchange.example.invalid)"
                    value={customEmail}
                    onChange={(e) => setCustomEmail(e.target.value)}
                    required
                    className="px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                  />
                </div>
              </div>

              {/* FIR Reference & Reply Deadline */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">FIR / DD Reference</label>
                  <input
                    type="text"
                    placeholder="e.g. FIR 142/2026 PS Cyber Cell"
                    value={firReference}
                    onChange={(e) => setFirReference(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-300 block mb-1">Reply Deadline</label>
                  <select
                    value={replyDeadlineHours}
                    onChange={(e) => setReplyDeadlineHours(Number(e.target.value))}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
                  >
                    <option value={12}>12 Hours (Emergency Freeze)</option>
                    <option value={24}>24 Hours (Urgent)</option>
                    <option value={48}>48 Hours (Standard)</option>
                    <option value={72}>72 Hours</option>
                    <option value={168}>7 Days (168 Hours)</option>
                  </select>
                </div>
              </div>

              {/* Legal Basis Placeholder */}
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">
                  Legal Basis Citation (Officer Input Required)
                </label>
                <textarea
                  rows={2}
                  value={legalBasisText}
                  onChange={(e) => setLegalBasisText(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                />
                <p className="text-[10px] text-slate-500 mt-1">
                  Note: Do not auto-cite specific BNSS sections. Legal basis is confirmed directly by the investigating officer.
                </p>
              </div>

              {/* Modal Buttons */}
              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 rounded-lg border border-slate-800 bg-slate-900 text-slate-300 text-xs font-semibold hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingCreate}
                  className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20"
                >
                  {submittingCreate ? 'Rendering...' : 'Generate Requisition Draft'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
