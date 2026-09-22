import React, { useState } from 'react';
import {
  FileText,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Copy,
  Check,
  Play,
  ArrowRight,
  ArrowLeft,
  BookOpen,
  Lock,
} from 'lucide-react';
import { useAuth } from '../lib/authContext';
import {
  api,
  IntakeResponse,
} from '../lib/api';


interface IntakePageProps {
  onCaseCreated?: (caseId: string) => void;
  onBack?: () => void;
}

const SAMPLE_COMPLAINT_EN = `On 15 May 2024, I was contacted on Telegram by a scammer offering guaranteed crypto returns.
They instructed me to deposit 50,000 INR via UPI to their representative (Mobile: +91 9876543210, Aadhaar: 3456 7890 1234, Account: 5010023456789).
After receiving fiat, they claimed to purchase USDT on Binance and asked me to transfer crypto to suspect wallet:
0x71C837775f0a514d3493722a4D6Bf49b1a1E4f9b
They also gave a secondary Bitcoin deposit address:
1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
Later they provided an address with a typo: 0x71C837775f0a514d3493722a4D6Bf49b1a1E4f9z
Total loss is 50,000 INR. Please freeze the funds.`;

const SAMPLE_COMPLAINT_HI = `मुझे 12 जून 2024 को व्हाट्सएप पर मैसेज आया कि क्रिप्टो ट्रेडिंग में भारी मुनाफा होगा। 
ठग ने मेरा फोन 9811223344 और पैन ABCDE1234F लेकर मुझसे 85000 रुपये ठग लिए।
उसने मुझे अपने WazirX अकाउंट से इस ट्रॉन वॉलेट पर USDT भेजने को कहा:
TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t
इसके बाद पैसे वापस नहीं मिले और उसने ब्लॉक कर दिया।`;

export const IntakePage: React.FC<IntakePageProps> = ({ onCaseCreated, onBack }) => {
  const { token } = useAuth();
  const [complaintText, setComplaintText] = useState<string>('');
  const [language, setLanguage] = useState<string>('auto');
  const [loading, setLoading] = useState<boolean>(false);
  const [creatingCase, setCreatingCase] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [intakeData, setIntakeData] = useState<IntakeResponse | null>(null);

  // Selected addresses for case creation
  const [selectedAddresses, setSelectedAddresses] = useState<Set<string>>(new Set());
  const [customNcrpRef, setCustomNcrpRef] = useState<string>('');
  const [copiedToken, setCopiedToken] = useState<string | null>(null);

  const handleExtract = async () => {
    if (!token || !complaintText.trim()) return;
    setLoading(true);
    setError(null);
    setSuccessMessage(null);
    try {
      const resp = await api.processIntake(
        token,
        complaintText,
        language === 'auto' ? undefined : language
      );
      setIntakeData(resp);
      // Select all accepted addresses by default
      const addrs = new Set(resp.accepted_addresses.map((a) => a.address));
      setSelectedAddresses(addrs);
    } catch (err: any) {
      setError(err.message || 'Failed to process complaint intake.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleAddress = (addr: string) => {
    setSelectedAddresses((prev) => {
      const next = new Set(prev);
      if (next.has(addr)) {
        next.delete(addr);
      } else {
        next.add(addr);
      }
      return next;
    });
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(text);
    setTimeout(() => setCopiedToken(null), 2000);
  };

  const handleCreateCase = async () => {
    if (!token || !intakeData) return;
    if (selectedAddresses.size === 0) {
      alert('Please select at least one accepted address to create a case.');
      return;
    }
    setCreatingCase(true);
    setError(null);
    try {
      const resp = await api.createCaseFromIntake(
        token,
        intakeData.id,
        Array.from(selectedAddresses),
        undefined,
        customNcrpRef.trim() || undefined
      );
      setSuccessMessage(resp.message);
      if (onCaseCreated) {
        setTimeout(() => {
          onCaseCreated(resp.case_id);
        }, 1200);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to create case from intake.');
    } finally {
      setCreatingCase(false);
    }
  };

  return (
    <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div className="flex items-center space-x-3">
          {onBack && (
            <button
              type="button"
              onClick={onBack}
              title="Back to Dashboard"
              className="p-2 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-blue-600/20 border border-blue-500/30 text-blue-400">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight">
                Complaint Intake &amp; Guarded Extraction
              </h1>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                MHA / I4C Multilingual Ingestion &bull; DPDP 2023 PII Masking &bull; Substring Containment Guard
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2">

          <button
            type="button"
            onClick={() => setComplaintText(SAMPLE_COMPLAINT_EN)}
            className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-800 text-slate-300 text-xs font-mono transition-colors"
          >
            Sample (English)
          </button>
          <button
            type="button"
            onClick={() => setComplaintText(SAMPLE_COMPLAINT_HI)}
            className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-800 text-slate-300 text-xs font-mono transition-colors"
          >
            Sample (Hindi)
          </button>
        </div>
      </div>

      {/* DPDP Compliance & Operational Banner */}
      <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-950/20 text-xs flex items-start gap-3 text-indigo-200 leading-relaxed">
        <Lock className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold text-indigo-100">
            DPDP Act 2023 Data Minimization &amp; Evidence Repository Compliance
          </p>
          <p className="mt-0.5 text-indigo-300/90 font-mono text-[11px]">
            Victim phone numbers, Aadhaar sequences, PAN, and bank accounts are automatically masked prior to log recording or external AI inference. Original complaint text is stored solely in the encrypted forensic database per Section 8(4).
          </p>
        </div>
      </div>

      {/* Input Form Card */}
      <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <label className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
            <span>Victim Cybercrime Complaint Statement</span>
            <span className="text-[10px] text-slate-500 font-normal">
              (Paste raw email, FIR excerpt, NCRP narrative, or chat statement)
            </span>
          </label>
          <div className="flex items-center space-x-2">
            <span className="text-xs text-slate-400 font-mono">Language:</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
            >
              <option value="auto">Auto-Detect</option>
              <option value="en">English</option>
              <option value="hi">Hindi (हिन्दी)</option>
              <option value="hinglish">Hinglish</option>
            </select>
          </div>
        </div>

        <textarea
          rows={7}
          value={complaintText}
          onChange={(e) => setComplaintText(e.target.value)}
          placeholder="Paste unformatted victim complaint here... e.g. 'I was cheated of 1,50,000 INR and told to send crypto to 0x71C837775f0a514d3493722a4D6Bf49b1a1E4f9b on Binance...'"
          className="w-full bg-slate-950 border border-slate-700 rounded-xl p-4 text-xs font-mono text-white placeholder-slate-600 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
        />

        <div className="flex items-center justify-between pt-2">
          <span className="text-xs text-slate-500 font-mono">
            {complaintText.length} characters &bull; {complaintText.split(/\s+/).filter(Boolean).length} words
          </span>
          <div className="flex items-center space-x-3">
            {complaintText && (
              <button
                type="button"
                onClick={() => {
                  setComplaintText('');
                  setIntakeData(null);
                }}
                className="px-3 py-2 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-400 text-xs font-mono transition-colors"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={handleExtract}
              disabled={loading || !complaintText.trim()}
              className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold flex items-center space-x-2 transition-all shadow-md disabled:opacity-50"
            >
              <Play className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>{loading ? 'Analyzing & Validating...' : 'Extract Structured Evidence'}</span>
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-500/40 text-rose-300 text-xs flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="p-4 rounded-xl bg-emerald-950/50 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Results Section */}
      {intakeData && (
        <div className="space-y-6">
          {/* Mode Banner */}
          <div
            className={`p-4 rounded-xl border flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs ${
              intakeData.is_deterministic
                ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
                : 'bg-blue-950/30 border-blue-500/40 text-blue-200'
            }`}
          >
            <div className="flex items-center space-x-3">
              <ShieldCheck className="w-5 h-5 text-amber-400 shrink-0" />
              <div>
                <span className="font-bold text-white text-sm block">
                  {intakeData.is_deterministic ? 'Deterministic Extraction Mode' : 'Guarded AI Extraction Mode'}
                </span>
                <span className="text-xs opacity-90">{intakeData.mode_banner}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-slate-300 font-mono text-[11px]">
                PII Masked: {intakeData.pii_redacted_count} entities
              </span>
              <span className="px-2.5 py-1 rounded bg-slate-900 border border-slate-700 text-slate-300 font-mono text-[11px]">
                Provider: {intakeData.provider}
              </span>
            </div>
          </div>

          {/* Group 1: Accepted Addresses */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <h3 className="font-bold text-sm text-white">
                  1. Accepted Cryptocurrency Addresses ({intakeData.accepted_addresses.length})
                </h3>
              </div>
              <span className="text-xs text-slate-400 font-mono">
                Cryptographically validated checksums
              </span>
            </div>

            {intakeData.accepted_addresses.length === 0 ? (
              <p className="text-xs text-slate-500 font-mono italic">
                No valid cryptocurrency wallet addresses detected in the complaint text.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 text-[11px]">
                    <tr>
                      <th className="py-2.5 px-3 w-10">Select</th>
                      <th className="py-2.5 px-3">Validated Address</th>
                      <th className="py-2.5 px-3">Primary Chain</th>
                      <th className="py-2.5 px-3">Certainty</th>
                      <th className="py-2.5 px-3">Candidate Chains</th>
                      <th className="py-2.5 px-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-900/30">
                    {intakeData.accepted_addresses.map((item) => {
                      const isSelected = selectedAddresses.has(item.address);
                      return (
                        <tr key={item.address} className="hover:bg-slate-800/40 transition-colors">
                          <td className="py-2.5 px-3">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleToggleAddress(item.address)}
                              className="rounded border-slate-700 bg-slate-950 text-blue-600 focus:ring-blue-500"
                            />
                          </td>
                          <td className="py-2.5 px-3 font-semibold text-white break-all select-all">
                            {item.address}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-300 text-[11px]">
                              {item.primary_chain}
                            </span>
                          </td>
                          <td className="py-2.5 px-3">
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                item.certainty === 'verified'
                                  ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                                  : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                              }`}
                            >
                              {item.certainty}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-slate-400 text-[11px]">
                            {item.candidates.map((c) => c.chain).join(', ')}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              type="button"
                              onClick={() => handleCopy(item.address)}
                              className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] flex items-center gap-1 ml-auto"
                            >
                              {copiedToken === item.address ? (
                                <Check className="w-3 h-3 text-emerald-400" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                              <span>{copiedToken === item.address ? 'Copied' : 'Copy'}</span>
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Group 2: Near Misses with Actionable Hints */}
          {intakeData.near_misses.length > 0 && (
            <div className="p-6 rounded-2xl border border-amber-500/30 bg-amber-950/10 shadow-xl space-y-4">
              <div className="flex items-center justify-between border-b border-amber-500/20 pb-3">
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <h3 className="font-bold text-sm text-white">
                    2. Near Misses &amp; Formatting Warnings ({intakeData.near_misses.length})
                  </h3>
                </div>
                <span className="text-xs text-amber-300/80 font-mono">
                  Review typos or character corruptions with complainant
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3">
                {intakeData.near_misses.map((item, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl border border-amber-500/30 bg-slate-950/80 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-slate-400 text-[11px]">Candidate Token:</span>
                        <span className="font-bold text-amber-300 break-all select-all">
                          {item.token}
                        </span>
                      </div>
                      <div className="text-rose-300/90 text-[11px]">
                        <strong>Error:</strong> {item.error}
                      </div>
                      <div className="text-blue-300 text-[11px] bg-blue-500/10 px-2 py-0.5 rounded border border-blue-500/20 inline-block">
                        <strong>Investigator Hint:</strong> {item.hint}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleCopy(item.token)}
                      className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] shrink-0 self-start md:self-center"
                    >
                      Copy Token
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Group 3: Extracted Facts with Highlighted Evidence Quotes */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-2">
                <BookOpen className="w-4 h-4 text-blue-400" />
                <h3 className="font-bold text-sm text-white">
                  3. Verified Extracted Facts ({intakeData.extracted_facts.length})
                </h3>
              </div>
              <span className="text-xs text-slate-400 font-mono">
                Every claim verified by exact source substring
              </span>
            </div>

            {/* Summary & Translation Strip */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-1 text-xs">
                <span className="text-slate-400 font-mono font-bold uppercase text-[10px]">
                  Neutral Case Summary
                </span>
                <p className="text-slate-200 leading-relaxed font-sans">{intakeData.summary}</p>
              </div>

              {intakeData.translation_en ? (
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-1 text-xs">
                  <span className="text-slate-400 font-mono font-bold uppercase text-[10px]">
                    English Translation (From Source Language)
                  </span>
                  <p className="text-slate-200 leading-relaxed font-sans">
                    {intakeData.translation_en}
                  </p>
                </div>
              ) : (
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 space-y-1 text-xs">
                  <span className="text-slate-400 font-mono font-bold uppercase text-[10px]">
                    Containment Guard Guarantee
                  </span>
                  <p className="text-slate-400 leading-relaxed font-mono text-[11px]">
                    No generative hallucination: all claims are mapped directly from original text substrings.
                  </p>
                </div>
              )}
            </div>

            {/* Verified Facts List */}
            {intakeData.extracted_facts.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {intakeData.extracted_facts.map((fact, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl border border-slate-800 bg-slate-950/80 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400 font-mono uppercase text-[10px] font-bold">
                        {fact.label || fact.fact_type}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                        Verified Quote
                      </span>
                    </div>

                    <div className="text-white font-bold text-sm">
                      {String(fact.value)}
                    </div>

                    <div className="text-[11px] text-slate-400 pt-1 border-t border-slate-800/80">
                      <span className="text-slate-500 font-mono">Evidence Quote: </span>
                      <span className="bg-blue-500/15 text-blue-200 px-1.5 py-0.5 rounded font-mono text-[10px] border border-blue-500/30 select-all">
                        "{fact.evidence_quote}"
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Rejected Claims Alert (Hallucination Containment) */}
            {intakeData.rejected_facts.length > 0 && (
              <div className="mt-4 p-4 rounded-xl border border-rose-500/40 bg-rose-950/20 space-y-2 text-xs">
                <div className="flex items-center space-x-2 text-rose-400 font-bold">
                  <XCircle className="w-4 h-4" />
                  <span>Unverifiable / Rejected Claims ({intakeData.rejected_facts.length})</span>
                </div>
                <p className="text-rose-300/80 text-[11px] font-mono">
                  The following claims generated by the AI were automatically rejected because their evidence quote could not be proven as an exact substring in the original complaint text:
                </p>
                <div className="space-y-1.5 pt-1">
                  {intakeData.rejected_facts.map((rf, idx) => (
                    <div
                      key={idx}
                      className="p-2 rounded bg-rose-950/40 border border-rose-500/30 text-[11px] font-mono flex items-center justify-between"
                    >
                      <span className="text-rose-200">
                        <strong>{rf.fact_type}:</strong> {String(rf.claimed_value)}
                      </span>
                      <span className="text-rose-400 text-[10px]">{rf.rejection_reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Action Strip: Create Case CTA */}
          <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/90 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <h4 className="font-bold text-white text-sm">Provision Investigation Case</h4>
              <p className="text-xs text-slate-400 font-mono">
                Attaches {selectedAddresses.size} selected cryptocurrency wallet lead(s) and initializes automated multi-hop trace.
              </p>
            </div>

            <div className="flex items-center space-x-3">
              <input
                type="text"
                value={customNcrpRef}
                onChange={(e) => setCustomNcrpRef(e.target.value)}
                placeholder="NCRP Ref (Optional)"
                className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder-slate-600 focus:outline-none focus:border-blue-500"
              />
              <button
                type="button"
                onClick={handleCreateCase}
                disabled={creatingCase || selectedAddresses.size === 0}
                className="px-5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center space-x-2 transition-all shadow-md disabled:opacity-50"
              >
                <span>
                  {creatingCase ? 'Creating Case...' : `Create Case (${selectedAddresses.size} Addresses)`}
                </span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
