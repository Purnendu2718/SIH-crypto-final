import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderToString } from 'react-dom/server';
import { ProtectedRoute } from '../components/ProtectedRoute';
import * as authModule from '../lib/authContext';

vi.mock('../lib/authContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../pages/Login', () => ({
  LoginPage: () => <div data-testid="mock-login-page">Officer Authentication Required</div>,
}));

describe('ProtectedRoute Route Guard Tests', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders loading state when session is being verified', () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      officer: null,
      token: null,
      isLoading: true,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });

    const html = renderToString(
      <ProtectedRoute>
        <div>Officer Workspace Content</div>
      </ProtectedRoute>
    );

    expect(html).toContain('Verifying Officer Security Session');
    expect(html).not.toContain('Officer Workspace Content');
  });

  it('renders login page when officer is not authenticated and no fallback provided', () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      officer: null,
      token: null,
      isLoading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });

    const html = renderToString(
      <ProtectedRoute>
        <div>Officer Workspace Content</div>
      </ProtectedRoute>
    );

    expect(html).toContain('Officer Authentication Required');
    expect(html).not.toContain('Officer Workspace Content');
  });

  it('renders fallback component when officer is not authenticated and fallback is given', () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      officer: null,
      token: null,
      isLoading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });

    const html = renderToString(
      <ProtectedRoute fallback={<div id="custom-denied">Please log in to continue</div>}>
        <div>Officer Workspace Content</div>
      </ProtectedRoute>
    );

    expect(html).toContain('Please log in to continue');
    expect(html).not.toContain('Officer Workspace Content');
  });

  it('renders children when authenticated with valid role', () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      officer: {
        id: 'off-1',
        full_name: 'Inspector Vijay',
        role: 'INVESTIGATOR',
      },
      token: 'jwt-xyz',
      isLoading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });

    const html = renderToString(
      <ProtectedRoute>
        <div id="case-workspace">Active Cases Caseload List</div>
      </ProtectedRoute>
    );

    expect(html).toContain('Active Cases Caseload List');
  });

  it('denies access when officer role is below required clearance', () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      officer: {
        id: 'off-2',
        full_name: 'Sub-Inspector Ankit',
        role: 'INVESTIGATOR',
      },
      token: 'jwt-abc',
      isLoading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });

    const html = renderToString(
      <ProtectedRoute requiredRole="SUPERVISOR">
        <div>Supervisor Audit Logs</div>
      </ProtectedRoute>
    );

    expect(html).toContain('Access Clearance Denied');
    expect(html).toContain('requires <strong>SUPERVISOR</strong> clearance');
    expect(html).not.toContain('Supervisor Audit Logs');
  });

  it('allows access when officer role exceeds required clearance', () => {
    vi.spyOn(authModule, 'useAuth').mockReturnValue({
      officer: {
        id: 'off-admin',
        full_name: 'Director Sharma',
        role: 'ADMIN',
      },
      token: 'jwt-admin',
      isLoading: false,
      login: vi.fn(),
      signup: vi.fn(),
      logout: vi.fn(),
      refreshProfile: vi.fn(),
    });

    const html = renderToString(
      <ProtectedRoute requiredRole="SUPERVISOR">
        <div>Supervisor Audit Logs</div>
      </ProtectedRoute>
    );

    expect(html).toContain('Supervisor Audit Logs');
  });
});
