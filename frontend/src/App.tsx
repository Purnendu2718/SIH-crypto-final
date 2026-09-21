import React, { useState, useEffect } from 'react';
import { AuthProvider } from './lib/authContext';
import { DashboardPage } from './pages/Dashboard';
import { CaseDetailPage } from './pages/CaseDetail';
import { ProtectedRoute } from './components/ProtectedRoute';

const AppContent: React.FC = () => {
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

  return (
    <ProtectedRoute>
      {activeView.view === 'case_detail' && activeView.caseId ? (
        <CaseDetailPage caseId={activeView.caseId} onBack={handleBackToDashboard} onSelectCase={handleSelectCase} />
      ) : (
        <DashboardPage onSelectCase={handleSelectCase} />
      )}
    </ProtectedRoute>
  );
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
