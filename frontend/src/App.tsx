import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './lib/authContext';
import { LoginPage } from './pages/Login';
import { DashboardPage } from './pages/Dashboard';
import { CaseDetailPage } from './pages/CaseDetail';
import { Shield } from 'lucide-react';

const AppContent: React.FC = () => {
  const { officer, isLoading } = useAuth();
  const [activeView, setActiveView] = useState<{ view: 'dashboard' | 'case_detail'; caseId?: string }>(() => {
    const hash = window.location.hash;
    if (hash.startsWith('#case/')) {
      return { view: 'case_detail', caseId: hash.replace('#case/', '') };
    }
    return { view: 'dashboard' };
  });

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      if (hash.startsWith('#case/')) {
        const id = hash.replace('#case/', '');
        setActiveView({ view: 'case_detail', caseId: id });
      } else {
        setActiveView({ view: 'dashboard' });
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const handleSelectCase = (caseId: string) => {
    window.location.hash = `#case/${caseId}`;
    setActiveView({ view: 'case_detail', caseId });
  };

  const handleBackToDashboard = () => {
    window.location.hash = '';
    setActiveView({ view: 'dashboard' });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#0b1120] text-slate-100 flex flex-col items-center justify-center font-mono text-xs">
        <div className="p-3 bg-blue-600/10 border border-blue-500/30 rounded-xl mb-3 text-blue-400 animate-pulse">
          <Shield className="w-8 h-8" />
        </div>
        <p className="text-slate-400">Verifying Officer Security Session...</p>
      </div>
    );
  }

  if (!officer) {
    return <LoginPage />;
  }

  if (activeView.view === 'case_detail' && activeView.caseId) {
    return <CaseDetailPage caseId={activeView.caseId} onBack={handleBackToDashboard} onSelectCase={handleSelectCase} />;
  }

  return <DashboardPage onSelectCase={handleSelectCase} />;
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
