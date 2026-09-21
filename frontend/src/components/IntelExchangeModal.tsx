import React, { useState } from 'react';
import { api, IntelLookupResponse } from '../lib/api';

interface IntelExchangeModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
  defaultAddress?: string;
  officerDistrict?: string;
}

async function computeSha256(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text.trim().toLowerCase());
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export const IntelExchangeModal: React.FC<IntelExchangeModalProps> = ({
  isOpen,
  onClose,
  token,
  defaultAddress = '',
  officerDistrict = 'Cyber Crime Unit',
}) => {
  const [tab, setTab] = useState<'lookup' | 'submit'>('lookup');
  const [addressInput, setAddressInput] = useState(defaultAddress);
  const [tagInput, setTagInput] = useState('DIGITAL_ARREST_MULE');
  const [districtInput, setDistrictInput] = useState(officerDistrict);

  const [loading, setLoading] = useState(false);
  const [calculatedHash, setCalculatedHash] = useState('');
  const [lookupResult, setLookupResult] = useState<IntelLookupResponse | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addressInput.trim()) return;
    setLoading(true);
    setError(null);
    setLookupResult(null);

    try {
      // 1. Compute SHA-256 strictly client-side
      const hash = await computeSha256(addressInput);
      setCalculatedHash(hash);

      // 2. Query exchange with digest only
      const res = await api.lookupIntelHash(token, hash);
      setLookupResult(res);
    } catch (err: any) {
      setError(err.message || 'Failed to query Police Intel Exchange.');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitTag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addressInput.trim()) return;
    setLoading(true);
    setError(null);
    setSubmitSuccess(null);

    try {
      // 1. Compute SHA-256 digest client-side (Raw address NEVER transmitted)
      const hash = await computeSha256(addressInput);
      setCalculatedHash(hash);

      // 2. Submit digest + tag + district
      await api.submitIntelTag(token, {
        address_hash: hash,
        tag: tagInput,
        district: districtInput,
      });

      setSubmitSuccess(`Address digest '${hash.slice(0, 16)}...' successfully indexed under tag '${tagInput}'.`);
    } catch (err: any) {
      setError(err.message || 'Failed to submit intel tag.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-2xl bg-slate-900 border border-blue-500/40 rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-gradient-to-r from-blue-950/40 via-slate-900 to-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-400 font-bold text-lg">
              🛡️
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                Police Intel Exchange
                <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
                  Hash-and-RBAC
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Inter-agency suspect intelligence sharing without raw address or victim PII disclosure
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-xl font-bold p-1"
          >
            ✕
          </button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex border-b border-slate-800 bg-slate-950/50 px-6 pt-3 gap-2">
          <button
            onClick={() => {
              setTab('lookup');
              setError(null);
            }}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition ${
              tab === 'lookup'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            🔍 Intelligence Lookup
          </button>
          <button
            onClick={() => {
              setTab('submit');
              setError(null);
            }}
            className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition ${
              tab === 'submit'
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-slate-400 hover:text-slate-300'
            }`}
          >
            ➕ Contribute Suspect Tag
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {error && (
            <div className="p-3 bg-red-950/40 border border-red-500/50 rounded-lg text-xs text-red-300">
              {error}
            </div>
          )}

          {submitSuccess && (
            <div className="p-3 bg-emerald-950/40 border border-emerald-500/50 rounded-lg text-xs text-emerald-300">
              ✓ {submitSuccess}
            </div>
          )}

          {tab === 'lookup' ? (
            <form onSubmit={handleLookup} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Suspect Wallet Address (Hashed Client-Side Before Search)
                </label>
                <input
                  type="text"
                  value={addressInput}
                  onChange={e => setAddressInput(e.target.value)}
                  placeholder="0x... or TR..."
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
                  required
                />
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50"
                >
                  {loading ? 'Computing Hash & Querying...' : 'Search Intelligence Exchange'}
                </button>
              </div>

              {calculatedHash && (
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg space-y-1">
                  <div className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">
                    Client-Side SHA-256 Digest Transmitted:
                  </div>
                  <div className="font-mono text-xs text-blue-300 break-all">
                    {calculatedHash}
                  </div>
                </div>
              )}

              {lookupResult && (
                <div className="p-4 bg-slate-950/80 border border-slate-800 rounded-lg space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-300">Query Status:</span>
                    <span
                      className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        lookupResult.match_found
                          ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {lookupResult.match_found ? 'MATCH FOUND IN INTER-AGENCY POOL' : 'NO PRIOR INTEL RECORD'}
                    </span>
                  </div>

                  {lookupResult.match_found && (
                    <div className="space-y-2 mt-2">
                      {lookupResult.tags.map((item: any, idx: number) => (
                        <div
                          key={idx}
                          className="p-3 bg-slate-900 border border-slate-800 rounded flex justify-between items-center text-xs"
                        >
                          <div>
                            <span className="font-bold text-amber-300">{item.tag}</span>
                            <div className="text-slate-400 text-[11px]">
                              Submitted by: {item.district}
                            </div>
                          </div>
                          <span className="text-[11px] text-slate-500">
                            {item.submitted_at ? new Date(item.submitted_at).toLocaleDateString() : 'N/A'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  <p className="text-[11px] text-slate-500 italic pt-2 border-t border-slate-800/60">
                    {lookupResult.architecture_notice}
                  </p>
                </div>
              )}
            </form>
          ) : (
            <form onSubmit={handleSubmitTag} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Suspect Wallet Address (Will be SHA-256 Hashed Locally)
                </label>
                <input
                  type="text"
                  value={addressInput}
                  onChange={e => setAddressInput(e.target.value)}
                  placeholder="0x... or TR..."
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500 font-mono"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Typology / Threat Tag
                  </label>
                  <select
                    value={tagInput}
                    onChange={e => setTagInput(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                  >
                    <option value="DIGITAL_ARREST_MULE">Digital Arrest Mule Account</option>
                    <option value="P2P_SCAM_SYNDICATE">P2P Crypto Scam Syndicate</option>
                    <option value="TASK_FRAUD_ACCUMULATOR">Task Fraud Accumulator</option>
                    <option value="RANSOMWARE_OFFRAMP">Ransomware Extraction Off-ramp</option>
                    <option value="ILLEGAL_BETTING_HUB">Illegal Betting Aggregator</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Submitting District / Unit
                  </label>
                  <input
                    type="text"
                    value={districtInput}
                    onChange={e => setDistrictInput(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-blue-500"
                    required
                  />
                </div>
              </div>

              <div className="p-3 bg-blue-950/30 border border-blue-800/40 rounded-lg text-xs text-blue-300 space-y-1">
                <span className="font-semibold block">Privacy Guarantee:</span>
                <span>
                  Your browser will compute the SHA-256 digest of this address. Only the hash, tag, and district are stored. Raw wallet addresses and victim PII are strictly never transmitted.
                </span>
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={loading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50"
                >
                  {loading ? 'Hashing & Submitting...' : 'Submit Anonymized Tag'}
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-900 flex justify-between items-center text-xs text-slate-500">
          <span>Hash-and-RBAC Design • Zero Raw PII Transmitted</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md font-medium text-xs transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
