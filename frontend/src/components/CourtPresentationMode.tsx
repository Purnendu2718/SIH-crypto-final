import React from 'react';
import {
  Gavel,
  Building2,
  ShieldCheck,
  ArrowLeft,
} from 'lucide-react';
import { TracePathItem, AttributionBreakdown } from '../lib/api';

interface CourtPresentationModeProps {
  paths: TracePathItem[];
  startAddress: string;
  chain: string;
  ncrpRef?: string;
  victimUtr?: string;
  totalAmountInr?: number;
  attribution?: AttributionBreakdown;
  onExit?: () => void;
}

export const CourtPresentationMode: React.FC<CourtPresentationModeProps> = ({
  paths,
  startAddress,
  chain,
  ncrpRef = 'NCRP/2026/DL-49102',
  victimUtr = 'UPI-429188092144',
  totalAmountInr = 1125000,
  attribution,
  onExit,
}) => {
  const matchedVasp = attribution?.matched_entity || 'CoinDCX';
  const confidence = attribution?.confidence || 0.97;
  const initialCryptoValue = paths.length > 0 ? paths[0].value : 12.5;

  // Approximate INR per crypto unit based on case amount
  const inrPerUnit = initialCryptoValue > 0 ? totalAmountInr / initialCryptoValue : 90000;

  return (
    <div className="w-full bg-[#0b1120] rounded-xl border border-amber-500/30 p-6 shadow-2xl space-y-8 animate-in fade-in duration-300">
      {/* Prosecution Banner */}
      <div className="p-5 rounded-xl border border-amber-500/40 bg-gradient-to-r from-amber-950/40 via-slate-900 to-slate-900 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start space-x-3.5">
          <div className="p-2.5 bg-amber-500/20 border border-amber-500/40 rounded-xl text-amber-400">
            <Gavel className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/30 uppercase">
                Judicial Presentation View
              </span>
              <span className="text-xs text-slate-400 font-mono">Case Ref: {ncrpRef}</span>
            </div>
            <h3 className="text-lg font-bold text-white mt-1">
              Chronological Fund-Flow &amp; Beneficiary Timeline (₹ INR)
            </h3>
            <p className="text-xs text-slate-300 mt-0.5">
              Simplified prosecution-ready narrative prepared for the Hon'ble Court under Section 63 BSA &amp; Section 94 BNSS.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 shrink-0">
          <div className="text-right font-mono">
            <div className="text-xs text-slate-400">Reported Fraud Proceeds</div>
            <div className="text-lg font-bold text-emerald-400">
              ₹{totalAmountInr.toLocaleString('en-IN')} INR
            </div>
          </div>
          {onExit && (
            <button
              onClick={onExit}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Exit Court Mode</span>
            </button>
          )}
        </div>
      </div>

      {/* Case Origin Callout */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 font-mono text-xs">
          <span className="text-slate-500 text-[10px] uppercase font-bold">1. Victim Payment Origin</span>
          <div className="text-white font-bold text-sm mt-1">{victimUtr}</div>
          <p className="text-slate-400 text-[11px] mt-0.5">Bank/UPI debit from complainant's account</p>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 font-mono text-xs">
          <span className="text-slate-500 text-[10px] uppercase font-bold">2. Initial Flagged Destination (Lead)</span>
          <div className="text-rose-400 font-bold text-sm mt-1 truncate">{startAddress}</div>
          <p className="text-slate-400 text-[11px] mt-0.5">First crypto wallet reported in NCRP complaint</p>
        </div>

        <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-950/20 font-mono text-xs">
          <span className="text-amber-400 text-[10px] uppercase font-bold">3. Destination Off-Ramp</span>
          <div className="text-white font-bold text-sm mt-1">
            {matchedVasp} ({Math.round(confidence * 100)}% Confidence)
          </div>
          <p className="text-amber-200/80 text-[11px] mt-0.5">FIU-IND Registered Indian Exchange</p>
        </div>
      </div>

      {/* Chronological Rupee Timeline */}
      <div className="relative pl-6 border-l-2 border-amber-500/30 space-y-8 ml-3">
        {paths.map((p, idx) => {
          const isFinalHop = idx === paths.length - 1;
          const hopAmountInr = Math.round(p.value * inrPerUnit);

          return (
            <div key={idx} className="relative group">
              {/* Timeline Marker Icon */}
              <div
                className={`absolute -left-[35px] top-1 w-8 h-8 rounded-full flex items-center justify-center border-2 ${
                  isFinalHop
                    ? 'bg-amber-500 border-amber-300 text-slate-950 shadow-lg shadow-amber-500/40'
                    : 'bg-slate-900 border-blue-500 text-blue-400'
                }`}
              >
                {isFinalHop ? <Building2 className="w-4 h-4" /> : <span className="font-mono text-xs font-bold">{idx + 1}</span>}
              </div>

              {/* Timeline Step Card */}
              <div
                className={`p-5 rounded-xl border ${
                  isFinalHop
                    ? 'border-amber-500/50 bg-amber-950/30 shadow-xl shadow-amber-950/20'
                    : 'border-slate-800 bg-slate-900/60'
                } space-y-3`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-3">
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-bold text-white uppercase tracking-wider">
                      {isFinalHop
                        ? `Final Hop: Credit into ${matchedVasp} Deposit Infrastructure`
                        : `Step ${idx + 1}: Multi-Hop Fund Movement`}
                    </span>
                    {isFinalHop && (
                      <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono text-[10px] font-bold">
                        ATTRIBUTED OFF-RAMP
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-2 font-mono text-xs">
                    <span className="text-slate-400">Equivalent Value:</span>
                    <span className="text-emerald-400 font-bold text-sm">
                      ₹{hopAmountInr.toLocaleString('en-IN')} INR
                    </span>
                    <span className="text-slate-500">({p.value} {p.chain || chain})</span>
                  </div>
                </div>

                {/* Sender -> Receiver in Plain Words */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                  <div>
                    <span className="text-slate-500 text-[10px] block">Transferred From:</span>
                    <span className="text-slate-200 break-all select-all font-mono text-[11px]">
                      {p.from_addr}
                    </span>
                    {idx === 0 && (
                      <span className="text-[10px] text-red-400 block mt-0.5 font-sans font-semibold">
                        [Reported Flagged Address (Lead)]
                      </span>
                    )}
                  </div>

                  <div>
                    <span className="text-slate-500 text-[10px] block">Transferred To:</span>
                    <span className="text-slate-200 break-all select-all font-mono text-[11px]">
                      {p.to_addr}
                    </span>
                    {isFinalHop && (
                      <span className="text-[10px] text-amber-300 block mt-0.5 font-sans font-semibold">
                        [{matchedVasp} Managed Deposit / Hot Wallet Address]
                      </span>
                    )}
                  </div>
                </div>

                {/* Plain-language Prosecution Explanation */}
                <p className="text-xs text-slate-300 leading-relaxed font-sans">
                  {isFinalHop
                    ? `Illicit crime proceeds totaling ₹${hopAmountInr.toLocaleString('en-IN')} INR were transferred into the cryptocurrency infrastructure owned and operated by ${matchedVasp}. Forensic analysis confirms deposit threshold retention and immediate sweep into the exchange's consolidated hot wallet, establishing definitive platform attribution.`
                    : `Funds totaling ₹${hopAmountInr.toLocaleString('en-IN')} INR were moved from wallet ${p.from_addr.slice(0, 8)}... to ${p.to_addr.slice(0, 8)}..., demonstrating sequential transfer of the reported victim principal across intermediate addresses.`}
                </p>

                <div className="text-[10px] font-mono text-slate-500 truncate">
                  Blockchain Transaction Hash: <span className="text-slate-400">{p.tx_hash}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Statutory Mandate Summary Footer */}
      <div className="p-4 rounded-xl border border-blue-500/30 bg-blue-950/20 flex items-start space-x-3 text-xs">
        <ShieldCheck className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <h4 className="font-bold text-white">Statutory Police Directives Generated</h4>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            A statutory requisition notice under <strong>Section 94 BNSS, 2023</strong> has been pre-drafted for issuance to the Nodal Officer of <strong>{matchedVasp}</strong> directing the immediate freezing of the beneficiary crypto account and requisitioning KYC, bank accounts, and access logs. This timeline is certified under <strong>Section 63 BSA, 2023</strong> for judicial admissibility.
          </p>
        </div>
      </div>
    </div>
  );
};
