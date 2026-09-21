import { describe, it, expect, beforeEach, vi } from 'vitest';
import { ApiClient, TOKEN_STORAGE_KEY } from '../lib/api';

describe('ApiClient Unit Tests', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('initializes with null token if sessionStorage is empty', () => {
    const client = new ApiClient('http://localhost:8000/api');
    expect(client.getToken()).toBeNull();
  });

  it('restores token from sessionStorage on initialization', () => {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, 'test-jwt-token-123');
    const client = new ApiClient('http://localhost:8000/api');
    expect(client.getToken()).toBe('test-jwt-token-123');
  });

  it('sets in-memory token and persists to sessionStorage', () => {
    const client = new ApiClient('http://localhost:8000/api');
    client.setToken('session-jwt-token-456');
    expect(client.getToken()).toBe('session-jwt-token-456');
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBe('session-jwt-token-456');
  });

  it('clears token from memory and sessionStorage when set to null', () => {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, 'initial-token');
    const client = new ApiClient('http://localhost:8000/api');
    expect(client.getToken()).toBe('initial-token');

    client.setToken(null);
    expect(client.getToken()).toBeNull();
    expect(window.sessionStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull();
  });

  it('attaches Authorization: Bearer header when token is present', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'healthy', app: 'CryptoTrace' }),
    });
    globalThis.fetch = mockFetch;

    const client = new ApiClient('http://localhost:8000/api');
    client.setToken('officer-secret-bearer-jwt');

    await client.getHealth();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [calledUrl, calledOptions] = mockFetch.mock.calls[0];
    expect(calledUrl).toBe('http://localhost:8000/api/health');
    expect(calledOptions.headers['Authorization']).toBe('Bearer officer-secret-bearer-jwt');
    expect(calledOptions.headers['Content-Type']).toBe('application/json');
  });

  it('does not include Authorization header when token is null', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'healthy', app: 'CryptoTrace' }),
    });
    globalThis.fetch = mockFetch;

    const client = new ApiClient('http://localhost:8000/api');
    client.setToken(null);

    await client.getHealth();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [, calledOptions] = mockFetch.mock.calls[0];
    expect(calledOptions.headers['Authorization']).toBeUndefined();
  });

  it('throws descriptive error on non-200 responses', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Invalid officer token' }),
    });
    globalThis.fetch = mockFetch;

    const client = new ApiClient('http://localhost:8000/api');
    client.setToken('expired-jwt');

    await expect(client.getHealth()).rejects.toThrow('API error (401): Invalid officer token');
  });
});
