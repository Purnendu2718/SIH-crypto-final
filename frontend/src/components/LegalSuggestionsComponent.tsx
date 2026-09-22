import React, { useState, useEffect } from 'react';
import {
  Scale,
  Calendar,
  AlertCircle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ExternalLink,
  Copy,
  Check,
  BookOpen,
  ShieldAlert,
} from 'lucide-react';
import {
  api,
  LegalSuggestionsResponse,
  LegalChecklistItem,
} from '../lib/api';


interface LegalSuggestionsProps {
  caseId: string;
  initialOffenceDate?: string;
  traceResult?: Record<string, any> | null;
  token: string | null;
}

const TYPOLOGY_OPTIONS = [
  { value: 'investment_scam', label: 'Investment & Ponzi Fraud Scheme' },
  { value: 'phishing_impersonation', label: 'Phishing & Fake Authority Impersonation' },
  { value: 'hack_theft', label: 'Unauthorized Computer Access & Asset Theft' },
  { value: 'ransomware_extortion', label: 'Ransomware & Digital Extortion' },
  { value: 'sextortion', label: 'Sextortion & Cyber Blackmail' },
  { value: 'insider_misappropriation', label: 'Insider Misappropriation & Key Theft' },
  { value: 'layering_laundering', label: 'Professional Layering & Syndicate Laundering' },
];

export const LegalSuggestionsComponent: React.FC<LegalSuggestionsProps> = ({
  caseId,
  initialOffenceDate = '',
  traceResult = null,
  token,
}) => {
  const [typology, setTypology] = useState<string>('investment_scam');
  const [offenceDate, setOffenceDate] = useState<string>(initialOffenceDate);
  const [data, setData] = useState<LegalSuggestionsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const fetchSuggestions = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.getLegalSuggestions(token, caseId, {
        typology,
        offence_date: offenceDate.trim() || undefined,
        trace_result: traceResult || undefined,
      });
      setData(response);
    } catch (err: any) {
      setError(err.message || 'Failed to generate legal statutory suggestions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSuggestions();
  }, [typology, offenceDate, caseId, token]);

  const handleCopyToClipboard = () => {
    if (!data) return;

    const lines: string[] = [
      `================================================================================`,
      `CRYPTOTRACE SENTINEL — LEGAL STATUTORY SUGGESTION SUMMARY`,
      `Rules Engine Version: ${data.rules_version}`,
      `Generated for Case ID: ${caseId}`,
      `Typology: ${data.typology_title} (${data.typology})`,
      `Offence Date: ${data.offence_date || 'Not specified (Requires confirmation)'}`,
      `Substantive Legal Scheme: ${data.scheme} (${data.scheme_note})`,
      `================================================================================`,
      ``,
      `[STATUTORY PROVISIONS RECOMMENDED FOR REVIEW]`,
    ];

    data.provisions.forEach((p, idx) => {
      lines.push(`${idx + 1}. [${p.badge}] ${p.primary_display}`);
      lines.push(`   Secondary Ref: ${p.secondary_display}`);
      if (p.notes) {
        lines.push(`   Officer Note: ${p.notes}`);
      }
      lines.push(`   Verify text at: ${p.verify_at}`);
      lines.push(``);
    });

    lines.push(`[INGREDIENTS CHECKLIST & EVIDENTIARY SIGNALS]`);
    data.ingredients_checklist.forEach((item, idx) => {
      const statusSymbol = item.status === 'present' ? '[PRESENT]' : item.status === 'missing' ? '[MISSING]' : '[NEEDS OFFICER INPUT]';
      lines.push(`${idx + 1}. ${statusSymbol} ${item.ingredient}`);
      lines.push(`   Source: ${item.source.toUpperCase()}${item.signal ? ` | Signal: ${item.signal}` : ''}`);
      lines.push(`   Status Detail: ${item.details}`);
      lines.push(``);
    });

    lines.push(`--------------------------------------------------------------------------------`);
    lines.push(`MANDATORY STATUTORY DISCLAIMER:`);
    lines.push(data.disclaimer);
    lines.push(`Note on Verification: "Cross-checked" indicates cross-checked against published`);
    lines.push(`IPC-to-BNS comparison tables; it is NOT confirmation against the official text.`);
    lines.push(`This is a decision-support suggestion tool for investigating officers, not legal advice.`);
    lines.push(`================================================================================`);

    navigator.clipboard.writeText(lines.join('\n'));
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  };

  const renderStatusBadge = (status: LegalChecklistItem['status']) => {
    switch (status) {
      case 'present':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            present
          </span>
        );
      case 'missing':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-rose-500/15 text-rose-300 border border-rose-500/30">
            <XCircle className="w-3 h-3 text-rose-400" />
            missing
          </span>
        );
      case 'needs_officer_input':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30">
            <HelpCircle className="w-3 h-3 text-amber-400" />
            needs_officer_input
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 text-slate-200">
      {/* Top Disclaimer Banner */}
      <div className="p-3.5 rounded-xl border border-amber-500/40 bg-amber-950/30 text-amber-200 flex items-start gap-3 text-xs leading-relaxed">
        <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold text-amber-100">
            Decision Support Tool — Not Legal Advice
          </p>
          <p className="mt-0.5 text-amber-300/90 font-mono text-[11px]">
            {data?.disclaimer ||
              'Suggestions for review by the investigating officer and legal counsel; verify each section on indiacode.nic.in.'}
          </p>
          <p className="mt-1 text-[10px] text-amber-400/80">
            The Indian Penal Code was replaced by the Bharatiya Nyaya Sanhita (BNS) from 1 July 2024; the offence date decides which applies (IPC up to 30 June 2024, BNS from 1 July 2024).
          </p>
        </div>
        {data?.rules_version && (
          <span className="shrink-0 font-mono text-[10px] px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
            v{data.rules_version}
          </span>
        )}
      </div>

      {/* Control Strip: Typology Selector & Offence Date Switch */}
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 grid grid-cols-1 md:grid-cols-12 gap-4 items-center">
        {/* Typology Selector */}
        <div className="md:col-span-6 space-y-1.5">
          <label className="block text-xs font-mono font-bold text-slate-400 uppercase tracking-wider">
            Cybercrime Typology
          </label>
          <select
            value={typology}
            onChange={(e) => setTypology(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 font-medium"
          >
            {TYPOLOGY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Offence Date Picker / Input */}
        <div className="md:col-span-4 space-y-1.5">
          <label className="block text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Date of Offence</span>
            <span className="text-[10px] text-slate-500 font-normal">Switch: 2024-07-01</span>
          </label>
          <div className="relative">
            <input
              type="date"
              value={offenceDate}
              onChange={(e) => setOffenceDate(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 font-mono"
            />
            {offenceDate && (
              <button
                type="button"
                onClick={() => setOffenceDate('')}
                title="Clear date (review both codes)"
                className="absolute right-8 top-2 text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Copy to Clipboard CTA */}
        <div className="md:col-span-2 flex items-end">
          <button
            type="button"
            onClick={handleCopyToClipboard}
            disabled={!data || loading}
            className={`w-full py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all shadow-sm ${
              copied
                ? 'bg-emerald-600 text-white'
                : 'bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50'
            }`}
          >
            {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            <span>{copied ? 'Copied' : 'Copy Diary'}</span>
          </button>
        </div>
      </div>

      {/* Date Switch Indicator Banner */}
      {data && (
        <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-900/40 text-xs flex items-center justify-between gap-3">
          <div className="flex items-center space-x-2.5">
            <Calendar className="w-4 h-4 text-blue-400 shrink-0" />
            <div>
              <span className="font-bold text-white uppercase text-[11px] font-mono mr-2">
                Primary Regime: {data.scheme}
              </span>
              <span className="text-slate-300 text-xs">{data.scheme_note}</span>
            </div>
          </div>
          <div className="shrink-0 flex items-center space-x-1.5">
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                data.scheme === 'BNS'
                  ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                  : data.scheme === 'IPC'
                  ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40'
                  : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
              }`}
            >
              {data.scheme === 'BNS'
                ? 'BNS >= 01-07-2024'
                : data.scheme === 'IPC'
                ? 'IPC < 01-07-2024'
                : 'DATE MISSING (BOTH CODES SHOWN)'}
            </span>
          </div>
        </div>
      )}

      {error && (
        <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 text-rose-300 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Recommended Provisions Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Scale className="w-4 h-4 text-blue-400" />
            <h3 className="font-bold text-sm text-white">
              Applicable Statutory Provisions ({data?.provisions.length || 0})
            </h3>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            Verification: indiacode.nic.in
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {data?.provisions.map((prov) => {
            const isCrossChecked = prov.badge === 'Cross-checked';
            return (
              <div
                key={prov.id}
                className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 hover:bg-slate-900/80 transition-colors flex flex-col justify-between space-y-2.5"
              >
                <div>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                      {prov.act}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span
                        title={
                          isCrossChecked
                            ? 'Cross-checked against published IPC-to-BNS comparison tables; NOT official confirmation.'
                            : 'Unverified against comparison tables. Officer review mandatory.'
                        }
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                          isCrossChecked
                            ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                            : 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}
                      >
                        {prov.badge}
                      </span>
                    </div>
                  </div>

                  <h4 className="text-white font-bold text-sm mt-1 leading-snug">
                    {prov.primary_display}
                  </h4>
                  <p className="text-slate-400 text-xs mt-0.5 font-mono">
                    {prov.secondary_display}
                  </p>

                  {prov.notes && (
                    <div className="mt-2 text-[11px] text-amber-300/90 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 rounded">
                      <strong>Note:</strong> {prov.notes}
                    </div>
                  )}
                </div>

                <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
                  <span className="text-slate-500 text-[10px]">
                    Status: {isCrossChecked ? 'Cross-checked table match' : 'Unverified mapping'}
                  </span>
                  <a
                    href={prov.verify_at}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300 font-mono hover:underline"
                  >
                    <span>indiacode.nic.in</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Ingredients Checklist Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <BookOpen className="w-4 h-4 text-emerald-400" />
            <h3 className="font-bold text-sm text-white">
              Ingredients &amp; Evidentiary Signals Checklist
            </h3>
          </div>
          <span className="text-[11px] text-slate-400 font-mono">
            Derived from stored trace analysis &amp; officer input
          </span>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden divide-y divide-slate-800">
          {data?.ingredients_checklist.map((item, idx) => (
            <div
              key={idx}
              className="p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
            >
              <div className="space-y-1 max-w-2xl">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-xs">
                    {idx + 1}. {item.ingredient}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
                  <span>Source: <strong className="text-slate-300 uppercase">{item.source}</strong></span>
                  {item.signal && (
                    <>
                      <span>&bull;</span>
                      <span>Signal: <strong className="text-blue-300">{item.signal}</strong></span>
                    </>
                  )}
                  <span>&bull;</span>
                  <span className="text-slate-300">{item.details}</span>
                </div>
              </div>

              <div className="shrink-0 flex items-center space-x-2">
                {renderStatusBadge(item.status)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom Information Callout */}
      <div className="p-3 rounded-lg bg-slate-900/40 border border-slate-800 text-slate-400 text-[11px] font-mono flex items-center justify-between">
        <span>
          Verification Definition: "Cross-checked" means the entry was checked against published IPC-to-BNS comparison tables; it is NOT confirmation against the official text.
        </span>
        <a
          href="https://indiacode.nic.in"
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 flex items-center gap-1 shrink-0 ml-4 hover:underline"
        >
          <span>India Code Repository</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
};
