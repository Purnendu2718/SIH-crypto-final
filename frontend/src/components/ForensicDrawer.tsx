import React from 'react';
import {
  Layers,
  Scale,
  Percent,
  CheckCircle2,
  AlertTriangle,
  Flame,
  TrendingDown,
} from 'lucide-react';
import { AttributionBreakdown, TypologyHit, TaintResult, RiskAssessment } from '../lib/api';

interface ForensicDrawerProps {
  attribution?: AttributionBreakdown;
  typologies?: TypologyHit[];
  taint?: TaintResult;
  risk?: RiskAssessment;
  isOpen: boolean;
  onClose: () => void;
}

const ATTRIBUTION_FACTOR_META: Record<string, { label: string; weight: number; desc: string }> = {
  sweep_label_match: {
    label: 'Sweep / Label Match',
    weight: 0.35,
    desc: 'Direct consolidation into verified VASP hot wallet address infrastructure.',
  },
  path_proximity: {
    label: 'Path Proximity',
    weight: 0.20,
    desc: 'Inverse hop distance to recipient entity (degrades monotonically over hops).',
  },
  deposit_pattern_similarity: {
    label: 'Deposit Pattern Match',
    weight: 0.15,
    desc: 'Transfer value retention, single-deposit thresholds, and gas-sweep signatures.',
  },
  temporal_correlation: {
    label: 'Temporal Correlation',
    weight: 0.15,
    desc: 'Execution latency between theft event and exchange deposit (rapid sweep correlation).',
  },
  co_spend_cluster: {
    label: 'Co-Spend / Cluster Match',
    weight: 0.10,
    desc: 'Common-input ownership clustering and shared deposit forwarders.',
  },
  behavioral: {
    label: 'Behavioral Heuristics',
    weight: 0.05,
    desc: 'Automated script routing vs manual transfer behavioral indicators.',
  },
};

export const ForensicDrawer: React.FC<ForensicDrawerProps> = ({
  attribution,
  typologies = [],
  taint,
  risk,
  isOpen,
  onClose,
}) => {
  if (!isOpen) return null;

  const confidence = attribution?.confidence ?? 0;
  const band = attribution?.confidence_band ?? 'INSUFFICIENT_EVIDENCE';
  const breakdown = attribution?.score_breakdown || {};

  const getBandBadge = (b: string) => {
    switch (b) {
      case 'VERY_HIGH':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
      case 'HIGH':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/30';
      case 'MEDIUM':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
      case 'INSUFFICIENT_EVIDENCE':
      default:
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
    }
  };

  const getRiskColor = (level?: string) => {
    switch (level) {
      case 'CRITICAL':
        return 'text-rose-400 bg-rose-500/10 border-rose-500/30';
      case 'HIGH':
        return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
      case 'MEDIUM':
        return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30';
      case 'LOW':
      default:
        return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-xl bg-[#0f172a] border-l border-slate-800 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-300">
      {/* Header */}
      <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/80 backdrop-blur">
        <div className="flex items-center space-x-2.5">
          <div className="p-2 bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-400">
            <Scale className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white tracking-wide">
              Forensic Attribution &amp; Evidence Engine
            </h3>
            <p className="text-[11px] text-slate-400 font-mono">
              Explainable Decision Support Matrix (SIH26183)
            </p>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors text-sm font-bold"
        >
          &times;
        </button>
      </div>

      {/* Content Scrollable */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6 text-xs">
        {/* Attribution Overview Card */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg">
          <div className="flex items-center justify-between mb-3">
            <span className="text-slate-400 uppercase tracking-wider text-[10px] font-semibold">
              Attributed Destination Off-Ramp
            </span>
            <span className={`px-2 py-0.5 rounded-full border text-[10px] font-mono font-bold ${getBandBadge(band)}`}>
              {band.replace('_', ' ')} &bull; {Math.round(confidence * 100)}%
            </span>
          </div>

          <div className="flex items-baseline space-x-3 mb-2">
            <div className="text-xl font-bold text-white tracking-tight">
              {attribution?.matched_entity || 'Insufficient Evidence'}
            </div>
            {attribution?.rule_fired && (
              <span className="text-[10px] font-mono text-blue-400 bg-blue-950/40 px-2 py-0.5 rounded border border-blue-800/40">
                Rule: {attribution.rule_fired}
              </span>
            )}
          </div>

          {attribution?.rule_fired === 'ROOT_ADDRESS_IS_KNOWN_ENTITY' && (
            <div className="mt-2 p-3 rounded-lg bg-emerald-950/40 border border-emerald-500/50 text-emerald-300 text-[11px] flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
              <span>
                <strong>Root-Entity Direct Match:</strong> This address belongs directly to verified entity <strong>{attribution.matched_entity}</strong> (0 hops required). Outward tracing was bypassed.
              </span>
            </div>
          )}

          {band === 'INSUFFICIENT_EVIDENCE' && attribution?.rule_fired !== 'ROOT_ADDRESS_IS_KNOWN_ENTITY' && (
            <div className="mt-2 p-2.5 rounded-lg bg-rose-950/30 border border-rose-800/40 text-rose-300 text-[11px] flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>
                <strong>Non-Negotiable Principle:</strong> Confidence is below threshold (0.40). The system strictly returns "Insufficient Evidence" rather than forcing an ungrounded guess.
              </span>
            </div>
          )}
        </div>

        {/* Explainable 6-Factor Weighted Scoring Table */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-1.5">
              <Percent className="w-3.5 h-3.5 text-blue-400" />
              <span>Explainable 6-Factor Weight Breakdown</span>
            </h4>
            <span className="text-[10px] text-slate-500 font-mono">Sum = Weighted Confidence</span>
          </div>

          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/50">
            <table className="w-full text-left font-mono">
              <thead className="bg-slate-900/90 text-slate-400 text-[10px] border-b border-slate-800 uppercase">
                <tr>
                  <th className="px-3 py-2">Forensic Criterion</th>
                  <th className="px-2 py-2 text-center">Weight</th>
                  <th className="px-2 py-2 text-center">Score</th>
                  <th className="px-3 py-2 text-right">Contribution</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-[11px]">
                {Object.entries(ATTRIBUTION_FACTOR_META).map(([key, meta]) => {
                  const score = typeof breakdown[key] === 'number' ? breakdown[key] : (key === 'sweep_label_match' ? (confidence >= 0.65 ? 1.0 : 0.0) : 0.5);
                  const contribution = score * meta.weight;
                  return (
                    <tr key={key} className="hover:bg-slate-900/40 transition-colors">
                      <td className="px-3 py-2 font-sans">
                        <div className="font-medium text-slate-200">{meta.label}</div>
                        <div className="text-[10px] text-slate-500">{meta.desc}</div>
                      </td>
                      <td className="px-2 py-2 text-center text-slate-400 font-mono">
                        {Math.round(meta.weight * 100)}%
                      </td>
                      <td className="px-2 py-2 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] ${score >= 0.8 ? 'bg-emerald-500/10 text-emerald-400' : score >= 0.4 ? 'bg-blue-500/10 text-blue-400' : 'bg-slate-800 text-slate-400'}`}>
                          {(score * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-bold text-white">
                        +{(contribution * 100).toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Laundering Typologies */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-1.5">
              <Layers className="w-3.5 h-3.5 text-purple-400" />
              <span>Detected Money Laundering Typologies ({typologies.length})</span>
            </h4>
          </div>

          {typologies.length === 0 ? (
            <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-900/30 text-slate-400 flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>No obfuscation patterns detected. Direct fund flow path observed.</span>
            </div>
          ) : (
            <div className="space-y-2">
              {typologies.map((t, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl border border-slate-800 bg-slate-900/40 flex items-start justify-between"
                >
                  <div className="flex items-start space-x-2.5">
                    <div className="p-1.5 rounded-lg bg-purple-950/60 border border-purple-500/30 text-purple-400 mt-0.5">
                      <Flame className="w-3.5 h-3.5" />
                    </div>
                    <div>
                      <div className="font-bold text-white font-mono">{t.typology}</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {t.description || `Structural laundering pattern detected between hops ${t.hop_start ?? 0} and ${t.hop_end ?? 'end'}.`}
                      </div>
                    </div>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 border border-purple-500/20">
                    Hops {t.hop_start ?? 0} &rarr; {t.hop_end ?? '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* FIFO Taint Accounting */}
        {taint && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-1.5">
                <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
                <span>FIFO Taint Contamination Accounting</span>
              </h4>
              <span className="text-[10px] font-mono text-rose-400 font-bold">
                {taint.final_taint_percentage.toFixed(1)}% Contaminated
              </span>
            </div>

            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
              <div className="w-full bg-slate-800 rounded-full h-2 mb-3 overflow-hidden">
                <div
                  className="bg-rose-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, taint.final_taint_percentage))}%` }}
                />
              </div>

              <div className="grid grid-cols-2 gap-3 text-mono text-[11px]">
                <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800">
                  <div className="text-slate-400 text-[10px]">Tainted Value</div>
                  <div className="font-bold text-rose-400 mt-0.5">
                    {taint.final_tainted_value.toLocaleString()}
                  </div>
                </div>
                <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800">
                  <div className="text-slate-400 text-[10px]">Clean Co-mingled</div>
                  <div className="font-bold text-emerald-400 mt-0.5">
                    {taint.clean_value.toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Composite Risk Score */}
        {risk && (
          <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                Composite Forensic Risk Score
              </span>
              <span className={`px-2 py-0.5 rounded-full border text-[10px] font-mono font-bold ${getRiskColor(risk.risk_level)}`}>
                {risk.risk_level} &bull; {risk.composite_score}/100
              </span>
            </div>

            <p className="text-[11px] text-slate-300 mt-2 leading-relaxed">
              {risk.explanation}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
