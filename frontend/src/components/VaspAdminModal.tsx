import React, { useState, useEffect } from 'react';
import {
  Building2,
  X,
  Plus,
  Edit2,
  Trash2,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Clock,
  Mail,
  Wallet,
} from 'lucide-react';
import { api, VASPEntity } from '../lib/api';

interface VaspAdminModalProps {
  isOpen: boolean;
  onClose: () => void;
  token: string;
}

export const VaspAdminModal: React.FC<VaspAdminModalProps> = ({
  isOpen,
  onClose,
  token,
}) => {
  const [vasps, setVasps] = useState<VASPEntity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Editing / Creating State
  const [editingVasp, setEditingVasp] = useState<VASPEntity | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Form State
  const [formName, setFormName] = useState('');
  const [formChain, setFormChain] = useState('ETH');
  const [formHotWallets, setFormHotWallets] = useState('');
  const [formFiuRegistered, setFormFiuRegistered] = useState(true);
  const [formSlaHours, setFormSlaHours] = useState('24');
  const [formNodalContact, setFormNodalContact] = useState('');
  const [saving, setSaving] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadVasps();
    }
  }, [isOpen]);

  const loadVasps = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listVASPs(token);
      setVasps(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load VASP Directory.');
    } finally {
      setLoading(false);
    }
  };

  const startCreate = () => {
    setEditingVasp(null);
    setIsCreating(true);
    setFormName('');
    setFormChain('ETH');
    setFormHotWallets('');
    setFormFiuRegistered(true);
    setFormSlaHours('24');
    setFormNodalContact('');
    setFeedbackMsg(null);
  };

  const startEdit = (vasp: VASPEntity) => {
    setIsCreating(false);
    setEditingVasp(vasp);
    setFormName(vasp.entity_name);
    setFormChain(vasp.chain || 'ETH');
    setFormHotWallets((vasp.hot_wallet_addresses || []).join('\n'));
    setFormFiuRegistered(Boolean(vasp.fiu_ind_registered));
    setFormSlaHours(String(vasp.sla_hours || 24));
    setFormNodalContact(vasp.nodal_contact || '');
    setFeedbackMsg(null);
  };

  const cancelForm = () => {
    setEditingVasp(null);
    setIsCreating(false);
    setFeedbackMsg(null);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFeedbackMsg(null);

    const wallets = formHotWallets
      .split(/[\n,]+/)
      .map((w) => w.trim())
      .filter(Boolean);

    try {
      if (isCreating) {
        await api.createVASP(token, {
          entity_name: formName.trim(),
          chain: formChain,
          hot_wallet_addresses: wallets,
          fiu_ind_registered: formFiuRegistered,
          sla_hours: parseInt(formSlaHours, 10) || 24,
          nodal_contact: formNodalContact.trim(),
        });
        setFeedbackMsg({ type: 'success', text: `VASP "${formName}" created successfully.` });
      } else if (editingVasp) {
        await api.updateVASP(token, editingVasp.entity_name, {
          chain: formChain,
          hot_wallet_addresses: wallets,
          fiu_ind_registered: formFiuRegistered,
          sla_hours: parseInt(formSlaHours, 10) || 24,
          nodal_contact: formNodalContact.trim(),
        });
        setFeedbackMsg({ type: 'success', text: `VASP "${editingVasp.entity_name}" updated successfully.` });
      }

      await loadVasps();
      setIsCreating(false);
      setEditingVasp(null);
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err.message || 'Failed to save VASP.' });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (entityName: string) => {
    if (!window.confirm(`Are you sure you want to remove "${entityName}" from the VASP directory?`)) {
      return;
    }
    try {
      await api.deleteVASP(token, entityName);
      setFeedbackMsg({ type: 'success', text: `VASP "${entityName}" deleted.` });
      await loadVasps();
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: err.message || 'Failed to delete VASP.' });
    }
  };

  if (!isOpen) return null;

  const filteredVasps = vasps.filter((v) =>
    v.entity_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (v.nodal_contact && v.nodal_contact.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-5xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-gradient-to-r from-purple-950/40 via-slate-900 to-slate-900">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-400 font-bold">
              <Building2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-base text-white">VASP Directory Administration</h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
                  ADMIN ONLY
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Curate FIU-IND registered Virtual Asset Service Providers, statutory nodal contacts, and hot wallets
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg border border-slate-800 hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Action / Search Bar */}
        <div className="p-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search VASP by name or contact..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-950 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
            />
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadVasps}
              className="p-2 rounded-lg border border-slate-800 bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-white text-xs transition-colors"
              title="Refresh Directory"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={startCreate}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-lg shadow-purple-600/20 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add VASP</span>
            </button>
          </div>
        </div>

        {/* Feedback Alert */}
        {feedbackMsg && (
          <div
            className={`mx-6 mt-4 p-3 rounded-xl border text-xs flex items-center gap-2 ${
              feedbackMsg.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                : 'bg-rose-950/40 border-rose-500/40 text-rose-300'
            }`}
          >
            {feedbackMsg.type === 'success' ? (
              <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{feedbackMsg.text}</span>
          </div>
        )}

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Create or Edit Form */}
          {(isCreating || editingVasp) && (
            <div className="p-5 rounded-xl border border-purple-500/40 bg-slate-950/90 shadow-2xl animate-in fade-in">
              <h4 className="text-sm font-bold text-white mb-4 flex items-center gap-2">
                {isCreating ? <Plus className="w-4 h-4 text-purple-400" /> : <Edit2 className="w-4 h-4 text-purple-400" />}
                <span>{isCreating ? 'Register New VASP Directory Entry' : `Edit VASP: ${editingVasp?.entity_name}`}</span>
              </h4>

              <form onSubmit={handleSave} className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Entity / Exchange Name *</label>
                  <input
                    type="text"
                    required
                    disabled={!isCreating}
                    placeholder="e.g. CoinDCX, WazirX, Binance"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white disabled:opacity-50 focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Primary Chain</label>
                  <select
                    value={formChain}
                    onChange={(e) => setFormChain(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  >
                    <option value="ETH">Ethereum (ETH / ERC-20)</option>
                    <option value="TRON">TRON (TRC-20 / USDT)</option>
                    <option value="BTC">Bitcoin (BTC)</option>
                    <option value="MULTI">Multi-Chain Infrastructure</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">SLA Response Window (Hours)</label>
                  <input
                    type="number"
                    min="1"
                    max="168"
                    value={formSlaHours}
                    onChange={(e) => setFormSlaHours(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1">Law Enforcement Nodal Contact *</label>
                  <input
                    type="text"
                    required
                    placeholder="nodal.officer@exchange.in, +91-..."
                    value={formNodalContact}
                    onChange={(e) => setFormNodalContact(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-slate-300 font-medium mb-1">
                    Consolidated Hot Wallet Addresses (One per line or comma-separated)
                  </label>
                  <textarea
                    rows={3}
                    placeholder="0x...&#10;0x...&#10;TR7NHq..."
                    value={formHotWallets}
                    onChange={(e) => setFormHotWallets(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-white font-mono text-[11px] focus:outline-none focus:border-purple-500"
                  />
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="fiuReg"
                    checked={formFiuRegistered}
                    onChange={(e) => setFormFiuRegistered(e.target.checked)}
                    className="w-4 h-4 rounded text-purple-600 bg-slate-900 border-slate-700 focus:ring-purple-500"
                  />
                  <label htmlFor="fiuReg" className="text-slate-300 font-medium cursor-pointer">
                    FIU-IND Registered Reporting Entity (Section 63 BSA / PMLA)
                  </label>
                </div>

                <div className="md:col-span-2 flex justify-end gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={cancelForm}
                    className="px-4 py-2 text-slate-400 hover:text-white rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-5 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-semibold transition-colors disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : isCreating ? 'Register VASP' : 'Update VASP'}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* VASP Directory Table */}
          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/60">
            <div className="px-4 py-3 bg-slate-900/80 border-b border-slate-800 flex items-center justify-between">
              <span className="text-xs font-semibold text-white">
                Registered Off-Ramp Entities ({filteredVasps.length})
              </span>
              <span className="text-[11px] text-slate-400 font-mono">FIU-IND Registry Synchronized</span>
            </div>

            {loading ? (
              <div className="p-8 text-center text-xs text-slate-400 font-mono">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-purple-400" />
                Loading VASP directory...
              </div>
            ) : error ? (
              <div className="p-6 text-center text-xs text-rose-400">{error}</div>
            ) : filteredVasps.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">No VASPs match the query.</div>
            ) : (
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/60 text-slate-400 uppercase font-mono text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-2.5">Entity Name</th>
                    <th className="px-4 py-2.5">FIU-IND Status</th>
                    <th className="px-4 py-2.5">SLA Window</th>
                    <th className="px-4 py-2.5">Nodal Contact</th>
                    <th className="px-4 py-2.5">Hot Wallets</th>
                    <th className="px-4 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {filteredVasps.map((vasp) => (
                    <tr key={vasp.entity_name} className="hover:bg-slate-900/40">
                      <td className="px-4 py-3 font-sans font-bold text-white flex items-center gap-2">
                        <Building2 className="w-4 h-4 text-purple-400" />
                        <span>{vasp.entity_name}</span>
                      </td>
                      <td className="px-4 py-3 font-sans">
                        {vasp.fiu_ind_registered ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            <ShieldCheck className="w-3 h-3" />
                            <span>Registered</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                            <span>Unregistered / Foreign</span>
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-300 font-sans">
                        <div className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5 text-slate-500" />
                          <span>{vasp.sla_hours || 24}h SLA</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-400 font-sans truncate max-w-[200px]" title={vasp.nodal_contact || undefined}>
                        <div className="flex items-center gap-1">
                          <Mail className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                          <span className="truncate">{vasp.nodal_contact || 'N/A'}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-400">
                        <div className="flex items-center gap-1">
                          <Wallet className="w-3.5 h-3.5 text-slate-500" />
                          <span>{(vasp.hot_wallet_addresses || []).length} registered</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => startEdit(vasp)}
                            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-purple-300 transition-colors"
                            title="Edit VASP"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleDelete(vasp.entity_name)}
                            className="p-1.5 rounded hover:bg-rose-950/40 text-slate-400 hover:text-rose-400 transition-colors"
                            title="Delete VASP"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex items-center justify-between text-xs text-slate-500">
          <span>Audit Log: Every VASP directory creation/modification appends an immutable hash chain entry.</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 text-white font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
