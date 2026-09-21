import React, { useState } from 'react';
import {
  FileText,
  Download,
  Copy,
  Check,
  ShieldCheck,
  FileCode,
  Lock,
} from 'lucide-react';
import { EvidencePackageItem, ForensicResult, api } from '../lib/api';

interface EvidenceViewProps {
  runId: string;
  evidencePackage?: EvidencePackageItem;
  legalNotice?: string;
  forensicData?: ForensicResult;
  isOpen: boolean;
  onClose: () => void;
  token?: string;
}

export const EvidenceView: React.FC<EvidenceViewProps> = ({
  runId,
  evidencePackage,
  legalNotice,
  forensicData,
  isOpen,
  onClose,
  token,
}) => {
  if (!isOpen) return null;

  const [activeTab, setActiveTab] = useState<'pdf' | 'json' | 'notice'>('pdf');
  const [copiedHash, setCopiedHash] = useState<boolean>(false);
  const [copiedRoot, setCopiedRoot] = useState<boolean>(false);
  const [copiedNotice, setCopiedNotice] = useState<boolean>(false);
  const [copiedJson, setCopiedJson] = useState<boolean>(false);
  const [downloading, setDownloading] = useState<boolean>(false);

  const sha256Hash = evidencePackage?.sha256_hash || 'SHA256_COMPUTED_ON_EXPORT';
  const merkleRoot = evidencePackage?.merkle_root || 'MERKLE_ROOT_COMPUTED_ON_EXPORT';

  const rawJsonString = JSON.stringify(
    {
      evidence_package_id: evidencePackage?.package_id || 'pkg-demo',
      run_id: runId,
      sha256_hash: sha256Hash,
      merkle_root: merkleRoot,
      forensics: forensicData,
    },
    null,
    2
  );

  const handleDownloadPdf = async () => {
    setDownloading(true);
    try {
      const url = api.getEvidencePdfUrl(runId);
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error('Failed to download PDF report');
      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `Forensic_Evidence_Report_${runId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err: any) {
      alert(err.message || 'Download failed.');
    } finally {
      setDownloading(false);
    }
  };

  const copyToClipboard = (text: string, type: 'hash' | 'root' | 'notice' | 'json') => {
    navigator.clipboard.writeText(text);
    if (type === 'hash') {
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2000);
    } else if (type === 'root') {
      setCopiedRoot(true);
      setTimeout(() => setCopiedRoot(false), 2000);
    } else if (type === 'notice') {
      setCopiedNotice(true);
      setTimeout(() => setCopiedNotice(false), 2000);
    } else if (type === 'json') {
      setCopiedJson(true);
      setTimeout(() => setCopiedJson(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[#0f172a] border border-slate-700 w-full max-w-4xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Top Bar */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/90">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-blue-600/20 border border-blue-500/30 rounded-lg text-blue-400">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-white tracking-wide">
                Court Evidence Package &amp; Section 63 BSA Certificate
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Admissible Electronic Record under Bharatiya Sakshya Adhiniyam, 2023
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors text-base font-bold"
          >
            &times;
          </button>
        </div>

        {/* Cryptographic Hash Bar */}
        <div className="bg-slate-950/80 px-6 py-3 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center space-x-2 text-slate-300 overflow-hidden">
            <span className="text-slate-500 font-bold shrink-0">SHA-256:</span>
            <span className="truncate text-blue-400 select-all font-mono text-[11px]">{sha256Hash}</span>
            <button
              onClick={() => copyToClipboard(sha256Hash, 'hash')}
              title="Copy SHA-256 Hash"
              className="p-1 text-slate-400 hover:text-white transition-colors shrink-0"
            >
              {copiedHash ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>

          <div className="flex items-center space-x-2 text-slate-300 overflow-hidden">
            <span className="text-slate-500 font-bold shrink-0">Merkle Root:</span>
            <span className="truncate text-purple-400 select-all font-mono text-[11px]">{merkleRoot}</span>
            <button
              onClick={() => copyToClipboard(merkleRoot, 'root')}
              title="Copy Merkle Root"
              className="p-1 text-slate-400 hover:text-white transition-colors shrink-0"
            >
              {copiedRoot ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 border-b border-slate-800 bg-slate-900/40 flex items-center justify-between">
          <div className="flex space-x-4">
            <button
              onClick={() => setActiveTab('pdf')}
              className={`py-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-colors ${
                activeTab === 'pdf'
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Court PDF Report</span>
            </button>

            <button
              onClick={() => setActiveTab('notice')}
              className={`py-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-colors ${
                activeTab === 'notice'
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Lock className="w-4 h-4" />
              <span>Section 94 BNSS Statutory Notice</span>
            </button>

            <button
              onClick={() => setActiveTab('json')}
              className={`py-3 text-xs font-semibold flex items-center space-x-2 border-b-2 transition-colors ${
                activeTab === 'json'
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileCode className="w-4 h-4" />
              <span>Raw Evidence JSON</span>
            </button>
          </div>

          <button
            onClick={handleDownloadPdf}
            disabled={downloading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/20 transition-colors disabled:opacity-50"
          >
            <Download className="w-3.5 h-3.5" />
            <span>{downloading ? 'Downloading...' : 'Download PDF'}</span>
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-6 flex-1 overflow-y-auto">
          {activeTab === 'pdf' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl border border-blue-500/20 bg-blue-950/20 text-blue-300 text-xs flex items-center justify-between">
                <div>
                  <h4 className="font-bold text-white text-sm mb-1">
                    ReportLab Court Evidence Report (Ready for Adjudication)
                  </h4>
                  <p className="text-[11px] text-slate-300">
                    Includes official Police Header, Multi-Hop Audit Trail, Explainable Attribution Matrix, Laundering Typologies, FIFO Taint Accounting, and Section 63 BSA Certificate.
                  </p>
                </div>
                <button
                  onClick={handleDownloadPdf}
                  disabled={downloading}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg text-xs shrink-0 shadow-lg shadow-blue-600/30"
                >
                  {downloading ? 'Generating...' : 'Download Signed PDF'}
                </button>
              </div>

              {/* PDF Preview Summary Card */}
              <div className="border border-slate-800 rounded-xl p-6 bg-slate-900/60 font-mono text-xs space-y-4">
                <div className="border-b border-slate-800 pb-3 flex justify-between items-center text-slate-400">
                  <span>DOCUMENT TYPE: FORENSIC EVIDENCE REPORT</span>
                  <span>FORMAT: ISO 32000-1 (PDF)</span>
                </div>

                <div className="grid grid-cols-2 gap-4 text-[11px]">
                  <div>
                    <span className="text-slate-500">Producing Software:</span>
                    <p className="text-white">CryptoTrace Sentinel (SIH26183)</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Legal Authority:</span>
                    <p className="text-white">Sec 94 BNSS, 2023 &amp; Sec 63 BSA, 2023</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Cryptographic Integrity:</span>
                    <p className="text-emerald-400 font-bold">Tamper-Evident Hash Chained</p>
                  </div>
                  <div>
                    <span className="text-slate-500">Attributed Off-Ramp:</span>
                    <p className="text-amber-400 font-bold">
                      {forensicData?.attribution?.matched_entity || 'CoinDCX'} (
                      {Math.round((forensicData?.attribution?.confidence || 0) * 100)}%)
                    </p>
                  </div>
                </div>

                <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-lg text-slate-300 text-[11px] font-sans">
                  <strong>Section 63 BSA Attestation Statement:</strong> Certified electronic record generated through automated computational procedures operating in the ordinary course of official duties. System integrity verified via cryptographic SHA-256 and hash chain pointers.
                </div>
              </div>
            </div>
          )}

          {activeTab === 'notice' && (
            <div className="relative">
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-mono text-slate-400">
                  Pre-filled Statutory Notice under Section 94 BNSS, 2023
                </span>
                <button
                  onClick={() => copyToClipboard(legalNotice || '', 'notice')}
                  className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono transition-colors"
                >
                  {copiedNotice ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedNotice ? 'Copied' : 'Copy Notice Text'}</span>
                </button>
              </div>

              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-slate-300 font-mono text-xs whitespace-pre-wrap leading-relaxed max-h-[420px] overflow-y-auto">
                {legalNotice || 'Notice text generating...'}
              </pre>
            </div>
          )}

          {activeTab === 'json' && (
            <div className="relative">
              <div className="flex justify-between items-center mb-2">
                <span className="text-xs font-mono text-slate-400">
                  Raw Serialized Forensic Trace &amp; Evidence Payload
                </span>
                <button
                  onClick={() => copyToClipboard(rawJsonString, 'json')}
                  className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono transition-colors"
                >
                  {copiedJson ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedJson ? 'Copied' : 'Copy JSON'}</span>
                </button>
              </div>

              <pre className="p-4 bg-slate-950 border border-slate-800 rounded-xl text-blue-300 font-mono text-[11px] overflow-x-auto max-h-[420px] overflow-y-auto">
                {rawJsonString}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
