import React from 'react';
import { useAuth } from '../lib/authContext';
import { Shield } from 'lucide-react';
import { LoginPage } from '../pages/Login';

export interface ProtectedRouteProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  requiredRole?: 'INVESTIGATOR' | 'SUPERVISOR' | 'ADMIN';
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  fallback,
  requiredRole,
}) => {
  const { officer, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div
        data-testid="loading-state"
        className="min-h-screen bg-[#0b1120] text-slate-100 flex flex-col items-center justify-center font-mono text-xs"
      >
        <div className="p-3 bg-blue-600/10 border border-blue-500/30 rounded-xl mb-3 text-blue-400 animate-pulse">
          <Shield className="w-8 h-8" />
        </div>
        <p className="text-slate-400">Verifying Officer Security Session...</p>
      </div>
    );
  }

  if (!officer) {
    return fallback ? <>{fallback}</> : <LoginPage />;
  }

  // Role check if required
  if (requiredRole) {
    const roleLevels: Record<string, number> = {
      INVESTIGATOR: 1,
      SUPERVISOR: 2,
      ADMIN: 3,
    };
    const officerLevel = roleLevels[officer.role] || 1;
    const requiredLevel = roleLevels[requiredRole] || 1;

    if (officerLevel < requiredLevel) {
      return (
        <div
          data-testid="unauthorized-role"
          className="min-h-screen bg-[#0b1120] text-slate-100 flex flex-col items-center justify-center font-mono text-xs p-4"
        >
          <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl max-w-md text-center">
            <h3 className="text-rose-400 font-bold text-sm mb-2">Access Clearance Denied</h3>
            <p className="text-slate-400 mb-2">
              This section requires <strong>{requiredRole}</strong> clearance. Your current active role is{' '}
              <strong>{officer.role}</strong>.
            </p>
            <p className="text-slate-500 text-[10px]">
              Refer to MHA / I4C Role Clearance Policy. Contact a Supervisor or Admin for privilege elevation.
            </p>
          </div>
        </div>
      );
    }
  }

  return <>{children}</>;
};
