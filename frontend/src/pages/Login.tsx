import React, { useState } from 'react';
import { Shield, Lock, Mail, User, Award, MapPin, AlertCircle, ArrowRight } from 'lucide-react';
import { useAuth } from '../lib/authContext';
import { api } from '../lib/api';

export const LoginPage: React.FC = () => {
  const { login, signup } = useAuth();
  const [isRegistering, setIsRegistering] = useState<boolean>(false);
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [fullName, setFullName] = useState<string>('');
  const [badgeNo, setBadgeNo] = useState<string>('');
  const [district, setDistrict] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      if (isRegistering) {
        await signup(email, password, fullName, badgeNo, district);
      } else {
        await login(email, password);
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = async (officerEmail: string, officerPass: string) => {
    setError(null);
    setLoading(true);
    try {
      // Auto seed demo if needed
      await api.seedDemo().catch(() => {});
      await login(officerEmail, officerPass);
    } catch (err: any) {
      setError(err.message || 'Quick login failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0b1120] text-slate-100 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        {/* Emblem & Portal Title */}
        <div className="inline-flex items-center justify-center p-3 bg-blue-600/10 border border-blue-500/30 rounded-2xl mb-4 text-blue-400 shadow-lg shadow-blue-900/20">
          <Shield className="w-10 h-10" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-white">
          CryptoTrace Sentinel
        </h2>
        <p className="mt-1 text-xs font-mono text-blue-400 uppercase tracking-wider">
          MHA / I4C &bull; SIH26183 &bull; Officer Access Portal
        </p>
        <p className="mt-2 text-xs text-slate-400">
          Authorized Law Enforcement Personnel Only &bull; RBAC &amp; Audit Log Enforced
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-[#0f172a] py-8 px-6 shadow-2xl rounded-xl sm:px-10 border border-slate-800">
          {/* Tab Switcher */}
          <div className="flex border-b border-slate-800 mb-6">
            <button
              type="button"
              onClick={() => { setIsRegistering(false); setError(null); }}
              className={`flex-1 pb-3 text-sm font-medium text-center transition-colors ${
                !isRegistering
                  ? 'text-blue-400 border-b-2 border-blue-500 font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Officer Login
            </button>
            <button
              type="button"
              onClick={() => { setIsRegistering(true); setError(null); }}
              className={`flex-1 pb-3 text-sm font-medium text-center transition-colors ${
                isRegistering
                  ? 'text-blue-400 border-b-2 border-blue-500 font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Register Officer
            </button>
          </div>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            {isRegistering && (
              <>
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1">
                    Officer Full Name &amp; Rank
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                    <input
                      type="text"
                      required
                      placeholder="e.g. Sub-Inspector R. Sharma"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="w-full pl-9 pr-3 py-2 bg-slate-900/80 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder-slate-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Badge No
                    </label>
                    <div className="relative">
                      <Award className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        placeholder="DEL-8842"
                        value={badgeNo}
                        onChange={(e) => setBadgeNo(e.target.value)}
                        className="w-full pl-9 pr-3 py-2 bg-slate-900/80 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500 placeholder-slate-500"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      District / Unit
                    </label>
                    <div className="relative">
                      <MapPin className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        placeholder="Cyber Cell"
                        value={district}
                        onChange={(e) => setDistrict(e.target.value)}
                        className="w-full pl-9 pr-3 py-2 bg-slate-900/80 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500 placeholder-slate-500"
                      />
                    </div>
                  </div>
                </div>
              </>
            )}

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Official Police Email (.gov.in or authorized)
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                <input
                  type="email"
                  required
                  placeholder="officer@sentinel.gov.in"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-900/80 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder-slate-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-2.5" />
                <input
                  type="password"
                  required
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 bg-slate-900/80 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 placeholder-slate-500"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 flex items-center justify-center py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-colors shadow-lg shadow-blue-600/20 disabled:opacity-50"
            >
              {loading ? (
                <span>Authenticating...</span>
              ) : (
                <span className="flex items-center space-x-2">
                  <span>{isRegistering ? 'Register as Investigator' : 'Sign In to Portal'}</span>
                  <ArrowRight className="w-4 h-4" />
                </span>
              )}
            </button>
          </form>

          {/* Quick-Fill Demo Profiles Section */}
          <div className="mt-8 pt-6 border-t border-slate-800">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 text-center">
              Phase 1 Verification &bull; Quick Test Accounts
            </p>
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => handleQuickLogin('sharma@sentinel.gov.in', 'SentinelPass123!')}
                className="w-full p-2.5 rounded-lg border border-slate-800 bg-slate-900 hover:border-blue-500/50 hover:bg-slate-800/80 text-left transition-all flex items-center justify-between group"
              >
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-medium text-white group-hover:text-blue-400">SI Vikram Sharma</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
                      INVESTIGATOR
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">Delhi Cyber Cell &bull; Owns DL-49102</p>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-blue-400 transition-colors" />
              </button>

              <button
                type="button"
                onClick={() => handleQuickLogin('patel@sentinel.gov.in', 'SentinelPass123!')}
                className="w-full p-2.5 rounded-lg border border-slate-800 bg-slate-900 hover:border-emerald-500/50 hover:bg-slate-800/80 text-left transition-all flex items-center justify-between group"
              >
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-medium text-white group-hover:text-emerald-400">Insp. Ananya Patel</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
                      INVESTIGATOR
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">Mumbai Cyber Unit &bull; Owns MH-82190</p>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-emerald-400 transition-colors" />
              </button>

              <button
                type="button"
                onClick={() => handleQuickLogin('verma@sentinel.gov.in', 'SentinelPass123!')}
                className="w-full p-2.5 rounded-lg border border-slate-800 bg-slate-900 hover:border-amber-500/50 hover:bg-slate-800/80 text-left transition-all flex items-center justify-between group"
              >
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-medium text-white group-hover:text-amber-400">ACP Rajesh Verma</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono">
                      SUPERVISOR
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">I4C HQ &bull; Sees All Multi-District Cases</p>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-slate-500 group-hover:text-amber-400 transition-colors" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
