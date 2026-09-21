import React from 'react';
import { X, Search } from 'lucide-react';
import { AddressSearchComponent } from './AddressSearchComponent';

interface AddressSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectCase?: (caseId: string) => void;
  initialQuery?: string;
}

export const AddressSearchModal: React.FC<AddressSearchModalProps> = ({
  isOpen,
  onClose,
  onSelectCase,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-400">
              <Search className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-wide">
                  Universal Multi-Chain Forensic Inspector
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  Phase 9 Ready
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Checksum-level cryptographic validation &amp; live on-chain data inspection across BTC, EVM, TRON, Solana, XRPL, Stellar, and UTXO forks.
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            title="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <AddressSearchComponent onSelectCase={onSelectCase} />
        </div>
      </div>
    </div>
  );
};
