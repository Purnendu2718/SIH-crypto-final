/**
 * CryptoTrace Sentinel — Typed API Client
 * Reference: SIH26183, MHA / I4C
 */

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
}

export interface OfficerProfile {
  id: string;
  email?: string;
  full_name: string;
  badge_no?: string;
  role: 'INVESTIGATOR' | 'SUPERVISOR' | 'ADMIN';
  district?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  officer: OfficerProfile;
}

export interface AttributionItem {
  id: string;
  matched_entity: string;
  rule_fired: string;
  confidence: number;
  score_breakdown?: Record<string, any>;
}

export interface AnalysisRunItem {
  run_id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  attributions: AttributionItem[];
}

export interface WalletSubmissionItem {
  submission_id: string;
  chain: string;
  address: string;
  submitted_at: string;
  analysis_runs: AnalysisRunItem[];
}

export interface CaseRecord {
  case_id: string;
  ncrp_ref?: string;
  victim_utr?: string;
  victim_utr_timestamp?: string;
  amount_inr?: number;
  assigned_officer_id?: string;
  assigned_officer_name?: string;
  status: string;
  created_at: string;
  submissions: WalletSubmissionItem[];
  latest_entity?: string;
  latest_confidence?: number;
}

export interface TracePathItem {
  hop_index: number;
  from_addr: string;
  to_addr: string;
  value: number;
  tx_hash: string;
  timestamp?: string;
  chain?: string;
  confirmations?: number;
  low_confirmation?: boolean;
  is_pending?: boolean;
  is_attribution_hop?: boolean;
  is_bridge?: boolean;
  bridge_details?: {
    bridge_name: string;
    source_chain: string;
    destination_chain: string;
    contract_address: string;
    recipient?: string;
    decoding_rule?: string;
  };
}

export interface AttributionBreakdown {
  matched_entity: string;
  confidence: number;
  confidence_band: 'VERY_HIGH' | 'HIGH' | 'MEDIUM' | 'INSUFFICIENT_EVIDENCE';
  rule_fired: string;
  score_breakdown: {
    sweep_label_match?: number;
    path_proximity?: number;
    deposit_pattern_similarity?: number;
    temporal_correlation?: number;
    co_spend_cluster?: number;
    behavioral?: number;
    [key: string]: any;
  };
}

export interface TypologyHit {
  typology: 'FAN_OUT' | 'MIXER' | 'PEELING_CHAIN' | 'LAYERING';
  hop_start?: number;
  hop_end?: number;
  description?: string;
}

export interface TaintHop {
  hop_index: number;
  from_addr: string;
  to_addr: string;
  total_value: number;
  tainted_value: number;
  clean_value: number;
  taint_percentage: number;
}

export interface TaintResult {
  initial_stolen_principal: number;
  final_taint_percentage: number;
  final_tainted_value: number;
  clean_value: number;
  hops: TaintHop[];
}

export interface RiskAssessment {
  composite_score: number;
  risk_level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  factor_breakdown: {
    attribution_confidence_pts?: number;
    typology_severity_pts?: number;
    taint_exposure_pts?: number;
    [key: string]: any;
  };
  explanation: string;
}

export interface ForensicResult {
  status: string;
  is_root_entity?: boolean;
  attribution_source?: string;
  trace: {
    start_address: string;
    chain: string;
    total_hops: number;
    reached_vasp: boolean;
    vasp_name?: string | null;
    paths: TracePathItem[];
  };
  attribution: AttributionBreakdown;
  typologies: TypologyHit[];
  taint: TaintResult;
  risk: RiskAssessment;
}

export interface EvidencePackageItem {
  package_id: string;
  run_id: string;
  sha256_hash: string;
  merkle_root: string;
  generated_at: string;
  files: Record<string, string>;
}

export interface EvidenceGenerationResponse {
  package: EvidencePackageItem;
  legal_notice: string;
  forensic_summary: ForensicResult;
}

export interface AuditVerificationResponse {
  is_valid: boolean;
  total_entries?: number;
  status: string;
  message: string;
  corrupted_entry_index?: number;
  corrupted_entry_id?: string;
  latest_hash?: string;
}

export interface UTRCandidateMatch {
  tx_hash: string;
  from_address: string;
  to_address: string;
  chain: string;
  crypto_amount: number;
  fiat_amount_inr: number;
  tx_timestamp: string;
  time_diff_minutes: number;
  amount_diff_inr: number;
  amount_diff_percent: number;
  correlation_score: number;
  is_correlated: boolean;
  explanation: string;
}

export interface UTRCorrelationResult {
  victim_utr: string;
  reported_amount_inr: number;
  utr_timestamp: string;
  time_tolerance_minutes: number;
  amount_tolerance_percent: number;
  total_candidates_evaluated: number;
  matched_candidates: UTRCandidateMatch[];
  best_candidate?: UTRCandidateMatch | null;
  correlation_status: string;
}

export interface WatchlistEntry {
  id: string;
  address: string;
  chain: string;
  case_id: string;
  alert_channel?: string | null;
  created_at?: string;
  last_checked_at?: string | null;
  status: 'ACTIVE' | 'TRIGGERED' | 'PAUSED';
  last_alert_at?: string | null;
  last_seen_tx_hash?: string | null;
}

export interface WatchlistPollResult {
  total_checked: number;
  alerts_fired: number;
  alert_details: Array<Record<string, any>>;
}

export interface VASPEntity {
  entity_name: string;
  chain?: string;
  hot_wallet_addresses?: string[];
  fiu_ind_registered?: boolean;
  sla_hours?: number;
  nodal_contact?: string | null;
}

export interface IntelTag {
  address_hash: string;
  tag: string;
  district: string;
  submitted_by?: string;
  submitted_at?: string;
}

export interface IntelLookupResponse {
  match_found: boolean;
  address_hash: string;
  tags: IntelTag[];
  architecture_notice: string;
}

export interface ArjunaSummaryResponse {
  case_id: string;
  ncrp_ref?: string;
  summary_en: string;
  summary_hi: string;
  factual_verification: Record<string, any>;
  strict_containment_passed: boolean;
}

export interface LegalProvisionItem {
  id: string;
  act: string;
  section: string;
  title: string;
  primary_display: string;
  secondary_display: string;
  ipc_equivalent?: string | null;
  verified: boolean;
  badge: 'Cross-checked' | 'Unverified';
  verify_at: string;
  notes?: string | null;
}

export interface LegalChecklistItem {
  ingredient: string;
  source: 'complaint' | 'on_chain' | 'officer';
  signal?: string | null;
  status: 'present' | 'missing' | 'needs_officer_input';
  details: string;
}

export interface LegalSuggestionsResponse {
  rules_version: string;
  disclaimer: string;
  typology: string;
  typology_title: string;
  offence_date?: string | null;
  scheme: 'IPC' | 'BNS' | 'BOTH';
  scheme_note: string;
  provisions: LegalProvisionItem[];
  ingredients_checklist: LegalChecklistItem[];
}

export interface LegalSuggestionsParams {
  typology: string;
  offence_date?: string | null;
  trace_result?: Record<string, any> | null;
}


export interface CandidateInfo {
  chain: string;
  address_type: string;
  network: string;
  checksum_verified: boolean;
  note?: string | null;
}

export interface ValidationData {
  input: string;
  normalized: string;
  is_valid: boolean;
  kind: 'address' | 'transaction_hash' | 'ens_name' | 'unknown';
  certainty: 'verified' | 'format_only' | 'none';
  candidates: CandidateInfo[];
  primary?: CandidateInfo | null;
  related_chains: string[];
  error?: string | null;
  hint?: string | null;
}

export interface ChainSearchResult {
  chain: string;
  network: string;
  status: 'ok' | 'not_found' | 'unavailable' | 'not_applicable' | 'unsupported_lookup';
  summary: {
    balance?: number;
    balance_satoshis?: number;
    balance_sun?: number;
    balance_formatted?: string;
    tx_count?: number;
    first_seen?: string | null;
    last_seen?: string | null;
    is_contract?: boolean;
    type?: string;
    note?: string;
    [key: string]: any;
  };
  transactions: Array<{
    hash: string;
    time?: string | null;
    amount?: number | null;
    from_address?: string;
    to_address?: string;
    fee?: number | null;
    confirmed?: boolean;
    explorer_url?: string;
    [key: string]: any;
  }>;
  labels: Array<{
    label: string;
    source: string;
    confidence: number;
  }>;
  source: string;
  source_url: string;
  fetched_at: string;
  error?: string | null;
  demo?: boolean;
}

export interface MultiChainSearchResponse {
  run_id: string;
  query: string;
  validation: ValidationData;
  results: ChainSearchResult[];
  status?: string;
  message?: string;
  demo?: boolean;
}

import { fetchEventSource } from '@microsoft/fetch-event-source';

const API_BASE = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || '/api';
export const TOKEN_STORAGE_KEY = 'cryptotrace_sentinel_token';

export class ApiClient {
  private base: string;
  private token: string | null = null;

  constructor(base: string = API_BASE) {
    this.base = base;
    // In-memory token with sessionStorage restore
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        this.token = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
      }
    } catch {
      this.token = null;
    }
  }

  setToken(token: string | null): void {
    this.token = token;
    try {
      if (typeof window !== 'undefined' && window.sessionStorage) {
        if (token) {
          window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
        } else {
          window.sessionStorage.removeItem(TOKEN_STORAGE_KEY);
        }
      }
    } catch {}
  }

  getToken(): string | null {
    if (!this.token) {
      try {
        if (typeof window !== 'undefined' && window.sessionStorage) {
          this.token = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
        }
      } catch {}
    }
    return this.token;
  }

  getBaseUrl(): string {
    return this.base;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.base}${endpoint}`;
    const currentToken = this.getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(currentToken ? { Authorization: `Bearer ${currentToken}` } : {}),
      ...(options.headers as Record<string, string> || {}),
    };

    const response = await fetch(url, { ...options, headers });
    if (!response.ok) {
      let errorMsg = response.statusText;
      try {
        const errorJson = await response.json();
        errorMsg = errorJson.detail || JSON.stringify(errorJson);
      } catch {
        const errorText = await response.text();
        if (errorText) errorMsg = errorText;
      }
      throw new Error(`API error (${response.status}): ${errorMsg}`);
    }
    return response.json();
  }

  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health');
  }

  async login(email: string, password: string): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async signup(
    email: string,
    password: string,
    full_name: string,
    badge_no?: string,
    district?: string,
  ): Promise<AuthResponse> {
    return this.request<AuthResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name, badge_no, district }),
    });
  }

  async getMe(token: string): Promise<OfficerProfile> {
    return this.request<OfficerProfile>('/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async getCases(token: string): Promise<CaseRecord[]> {
    return this.request<CaseRecord[]>('/cases', {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async getCase(token: string, caseId: string): Promise<CaseRecord> {
    return this.request<CaseRecord>(`/cases/${caseId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async createCase(
    token: string,
    data: {
      ncrp_ref?: string;
      victim_utr?: string;
      victim_utr_timestamp?: string;
      amount_inr?: number;
      chain?: string;
      suspect_address?: string;
      flagged_address?: string;
    },
  ): Promise<CaseRecord> {
    const payload = {
      ...data,
      suspect_address: data.suspect_address || data.flagged_address,
    };
    return this.request<CaseRecord>('/cases', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    });
  }

  async runAnalysis(token: string, submissionId: string): Promise<ForensicResult> {
    return this.request<ForensicResult>(`/analysis/run/${submissionId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async getRunAnalysis(token: string, runId: string): Promise<ForensicResult> {
    return this.request<ForensicResult>(`/analysis/run/${runId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async generateEvidence(token: string, runId: string): Promise<EvidenceGenerationResponse> {
    return this.request<EvidenceGenerationResponse>(`/evidence/generate/${runId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async verifyAuditChain(token: string): Promise<AuditVerificationResponse> {
    return this.request<AuditVerificationResponse>('/audit/verify', {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  getEvidencePdfUrl(runId: string): string {
    return `${this.base}/evidence/pdf/${runId}`;
  }

  getEvidencePackageUrl(caseId: string): string {
    return `${this.base}/v1/cases/${caseId}/evidence-package`;
  }

  async downloadEvidencePackage(token: string, caseId: string): Promise<Blob> {
    const url = `${this.base}/v1/cases/${caseId}/evidence-package`;
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) {
      throw new Error(`Failed to download evidence package (${response.status})`);
    }
    return response.blob();
  }

  async seedDemo(): Promise<any> {
    return this.request<any>('/cases/seed-demo', {
      method: 'POST',
    });
  }

  // Phase 7 Innovation Endpoints
  async correlateCaseUTR(
    token: string,
    caseId: string,
    params?: { time_tolerance_minutes?: number; amount_tolerance_percent?: number },
  ): Promise<UTRCorrelationResult> {
    const qs = new URLSearchParams();
    if (params?.time_tolerance_minutes) qs.append('time_tolerance_minutes', String(params.time_tolerance_minutes));
    if (params?.amount_tolerance_percent) qs.append('amount_tolerance_percent', String(params.amount_tolerance_percent));
    return this.request<UTRCorrelationResult>(`/correlator/case/${caseId}?${qs.toString()}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async listWatchlist(token: string, caseId?: string): Promise<WatchlistEntry[]> {
    const url = caseId ? `/watchlist?case_id=${caseId}` : '/watchlist';
    return this.request<WatchlistEntry[]>(url, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async createWatchlistEntry(
    token: string,
    data: { address: string; chain?: string; case_id: string; alert_channel?: string },
  ): Promise<WatchlistEntry> {
    return this.request<WatchlistEntry>('/watchlist', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(data),
    });
  }

  async deleteWatchlistEntry(token: string, id: string): Promise<any> {
    return this.request<any>(`/watchlist/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async pollWatchlistNow(token: string): Promise<WatchlistPollResult> {
    return this.request<WatchlistPollResult>('/watchlist/poll-now', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async listVASPs(token: string): Promise<VASPEntity[]> {
    return this.request<VASPEntity[]>('/admin/vasps', {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async createVASP(
    token: string,
    data: {
      entity_name: string;
      chain?: string;
      hot_wallet_addresses?: string[];
      fiu_ind_registered?: boolean;
      sla_hours?: number;
      nodal_contact?: string;
    },
  ): Promise<VASPEntity> {
    return this.request<VASPEntity>('/admin/vasps', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(data),
    });
  }

  async updateVASP(
    token: string,
    entityName: string,
    data: {
      chain?: string;
      hot_wallet_addresses?: string[];
      fiu_ind_registered?: boolean;
      sla_hours?: number;
      nodal_contact?: string;
    },
  ): Promise<VASPEntity> {
    return this.request<VASPEntity>(`/admin/vasps/${encodeURIComponent(entityName)}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(data),
    });
  }

  async deleteVASP(token: string, entityName: string): Promise<any> {
    return this.request<any>(`/admin/vasps/${encodeURIComponent(entityName)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async submitIntelTag(
    token: string,
    data: { address_hash: string; tag: string; district: string },
  ): Promise<any> {
    return this.request<any>('/intel/submit', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(data),
    });
  }

  async lookupIntelHash(token: string, addressHash: string): Promise<IntelLookupResponse> {
    return this.request<IntelLookupResponse>('/intel/lookup', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ address_hash: addressHash }),
    });
  }

  async getArjunaSummary(
    token: string,
    caseId: string,
    language: string = 'both',
  ): Promise<ArjunaSummaryResponse> {
    return this.request<ArjunaSummaryResponse>(`/analysis/${caseId}/arjuna-summary?language=${language}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  async validate(query: string): Promise<ValidationData> {
    const res = await fetch(`${this.base}/v1/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    return res.json();
  }

  async searchMultiChain(
    query: string,
    allCandidates: boolean = false,
    caseId?: string,
    token?: string
  ): Promise<MultiChainSearchResponse> {
    const url = `${this.base}/v1/search`;
    const authToken = token || this.getToken();
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    };
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query, all_candidates: allCandidates, case_id: caseId }),
    });

    if (response.status === 422) {
      const errorJson = await response.json();
      return {
        run_id: '',
        query,
        validation: errorJson.validation || {
          input: query,
          normalized: query,
          is_valid: false,
          kind: 'unknown',
          certainty: 'none',
          candidates: [],
          related_chains: [],
          error: errorJson.detail || 'Invalid address or transaction hash format.',
          hint: null,
        },
        results: [],
        status: 'error',
        message: errorJson.detail,
      };
    }

    if (!response.ok) {
      let errorMsg = response.statusText;
      try {
        const errorJson = await response.json();
        errorMsg = errorJson.detail || JSON.stringify(errorJson);
      } catch {}
      throw new Error(`Search error (${response.status}): ${errorMsg}`);
    }

    return response.json();
  }

  async streamTraceSSE(
    params: {
      seedAddress: string;
      chain?: string;
      maxHops?: number;
      minAmount?: number;
      taintModel?: string;
      dateFrom?: string;
      dateTo?: string;
      caseId?: string;
    },
    callbacks: {
      onStarted?: (data: any) => void;
      onHop?: (hop: TracePathItem) => void;
      onCompleted?: (data: any) => void;
      onError?: (err: any) => void;
    },
    signal?: AbortSignal
  ): Promise<void> {
    const authToken = this.getToken();
    const url = `${this.base}/trace/sse`;

    await fetchEventSource(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: JSON.stringify({
        seed_address: params.seedAddress,
        chain: params.chain || 'ETH',
        max_hops: params.maxHops || 3,
        min_amount: params.minAmount || 0,
        taint_model: params.taintModel || 'FIFO',
        date_from: params.dateFrom,
        date_to: params.dateTo,
        case_id: params.caseId,
      }),
      signal,
      async onopen(response) {
        if (!response.ok) {
          throw new Error(`SSE stream connection failed (${response.status})`);
        }
      },
      onmessage(msg) {
        try {
          const data = msg.data ? JSON.parse(msg.data) : {};
          if (msg.event === 'trace_started') {
            callbacks.onStarted?.(data);
          } else if (msg.event === 'hop_discovered') {
            callbacks.onHop?.(data);
          } else if (msg.event === 'trace_completed') {
            callbacks.onCompleted?.(data);
          } else if (msg.event === 'error') {
            callbacks.onError?.(new Error(data.message || 'Stream error'));
          }
        } catch (e) {
          callbacks.onError?.(e);
        }
      },
      onerror(err) {
        callbacks.onError?.(err);
        throw err;
      },
    });
  }

  async unifiedSearch(
    token: string,
    query: string,
  ): Promise<SearchResponse> {
    return this.request<SearchResponse>('/search', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ query }),
    });
  }

  async getLegalSuggestions(
    token: string,
    caseId: string,
    params: LegalSuggestionsParams,
  ): Promise<LegalSuggestionsResponse> {
    return this.request<LegalSuggestionsResponse>(`/cases/${caseId}/legal-suggestions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(params),
    });
  }
}


export interface SearchResponse {
  query: string;
  query_type: string;
  detected_chain: string;
  resolved_address: string;
  case_id?: string;
  ncrp_ref?: string;
  run_id?: string;
  status: string;
  is_root_entity: boolean;
  attribution_source?: string;
  matched_entity?: string;
  confidence: number;
  confidence_band: string;
  total_hops: number;
  confirmations?: number;
  is_pending?: boolean;
  low_confirmation?: boolean;
  has_low_confirmation_hops?: boolean;
  candidate_addresses?: string[];
  error?: string;
  forensic_payload: Record<string, any>;
}


export const api = new ApiClient();
