// API client.
//
// Talks to the FastAPI backend under /api/v1 (same origin in production, where
// FastAPI serves this SPA; overridable via VITE_API_BASE). Attaches a Clerk
// bearer token when available and generates idempotency keys for mutations.

import axios from 'axios';
import type {
  AccountConnectPayload,
  ActivityItem,
  Agent,
  BrandVoiceSummary,
  Campaign,
  CampaignCreate,
  ConnectedAccount,
  Dashboard,
  GenerateResult,
  ICP,
  ICPPayload,
  PaginatedResponse,
  ScorePreview,
  Suggestion,
  SuggestionPage,
  PreflightReport,
  Target,
  TargetImportItem,
  WarmupProgram,
  WarmupStatus,
  WarmupToday,
} from '@/types';

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1';

export const http = axios.create({ baseURL: API_BASE });

// The Clerk provider registers a token getter here so the interceptor can attach
// the session token. Left null in demo mode (no Clerk configured).
type TokenGetter = () => Promise<string | null>;
let tokenGetter: TokenGetter | null = null;

export function setAuthTokenGetter(getter: TokenGetter | null): void {
  tokenGetter = getter;
}

http.interceptors.request.use(async (config) => {
  if (tokenGetter) {
    try {
      const token = await tokenGetter();
      if (token) {
        config.headers = config.headers ?? {};
        config.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // No token available; proceed unauthenticated (demo mode).
    }
  }
  return config;
});

function idempotencyKey(): Record<string, string> {
  const uuid =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return { 'X-Idempotency-Key': uuid };
}

// The backend returns a raw CampaignResponse; normalize it to the frontend
// Campaign shape (which carries share/follow + a flat progress object).
function normalizeCampaign(raw: any): Campaign {
  const actions = raw.actions ?? {};
  const progress = raw.progress ?? {};
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description ?? '',
    status: raw.status,
    target_urls: raw.target_urls ?? [],
    account_ids: raw.account_ids ?? [],
    actions: {
      like: !!actions.like,
      comment: !!actions.comment,
      share: !!actions.share,
      follow: !!actions.follow,
    },
    priority: raw.priority ?? 1,
    progress: {
      total_tasks: progress.total_tasks ?? 0,
      completed_tasks: progress.completed_tasks ?? 0,
      failed_tasks: progress.failed_tasks ?? 0,
    },
    created_at: raw.created_at,
    updated_at: raw.updated_at,
    scheduled_start: raw.scheduled_start_at ?? raw.scheduled_start,
  };
}

export const campaignApi = {
  async list(
    page = 1,
    pageSize = 50,
    status?: string,
  ): Promise<PaginatedResponse<Campaign>> {
    const { data } = await http.get('/campaigns', {
      params: { page, page_size: pageSize, status },
    });
    const items = (data.campaigns ?? []).map(normalizeCampaign);
    const total = data.total ?? items.length;
    const size = data.page_size ?? pageSize;
    return {
      items,
      total,
      page: data.page ?? page,
      page_size: size,
      total_pages: size ? Math.ceil(total / size) : 1,
    };
  },

  async get(id: string): Promise<Campaign> {
    const { data } = await http.get(`/campaigns/${id}`);
    return normalizeCampaign(data);
  },

  async create(payload: CampaignCreate): Promise<Campaign> {
    const { data } = await http.post('/campaigns', payload, {
      headers: idempotencyKey(),
    });
    return normalizeCampaign(data);
  },

  async start(id: string): Promise<void> {
    await http.post(`/campaigns/${id}/start`, null, { headers: idempotencyKey() });
  },

  async pause(id: string): Promise<void> {
    await http.post(`/campaigns/${id}/pause`, null, { headers: idempotencyKey() });
  },
};

export const agentApi = {
  async list(): Promise<Agent[]> {
    const { data } = await http.get('/agents');
    return data as Agent[];
  },
};

// ---------------------------------------------------------------------------
// Outreach API: accounts, targeting, and the approval queue
// ---------------------------------------------------------------------------

export const accountApi = {
  async list(): Promise<ConnectedAccount[]> {
    const { data } = await http.get('/accounts');
    return data.accounts ?? [];
  },

  async connect(payload: AccountConnectPayload): Promise<ConnectedAccount> {
    const { data } = await http.post('/accounts', payload, {
      headers: idempotencyKey(),
    });
    return data as ConnectedAccount;
  },

  async update(
    id: string,
    payload: Partial<{
      mode: string;
      status: string;
      active_icp_id: string;
      daily_caps: Record<string, unknown>;
      display_name: string;
    }>,
  ): Promise<ConnectedAccount> {
    const { data } = await http.patch(`/accounts/${id}`, payload);
    return data as ConnectedAccount;
  },

  async rotateCredentials(
    id: string,
    payload: { li_at: string; jsessionid?: string },
  ): Promise<ConnectedAccount> {
    const { data } = await http.post(`/accounts/${id}/credentials`, payload);
    return data as ConnectedAccount;
  },

  async verify(id: string): Promise<{ ok: boolean; status: string; error?: string }> {
    const { data } = await http.post(`/accounts/${id}/verify`);
    return data;
  },

  async disconnect(id: string): Promise<void> {
    await http.delete(`/accounts/${id}`);
  },
};

export const targetingApi = {
  async listIcps(): Promise<ICP[]> {
    const { data } = await http.get('/targeting/icps');
    return data as ICP[];
  },

  async listBrandVoices(): Promise<BrandVoiceSummary[]> {
    const { data } = await http.get('/targeting/brand-voices');
    return data as BrandVoiceSummary[];
  },

  async createIcp(payload: Partial<ICPPayload> & { name: string }): Promise<ICP> {
    const { data } = await http.post('/targeting/icps', payload, {
      headers: idempotencyKey(),
    });
    return data as ICP;
  },

  async updateIcp(id: string, payload: Partial<ICPPayload>): Promise<ICP> {
    const { data } = await http.patch(`/targeting/icps/${id}`, payload);
    return data as ICP;
  },

  async deleteIcp(id: string): Promise<void> {
    await http.delete(`/targeting/icps/${id}`);
  },

  // Score a hypothetical person against a draft ICP without saving anything.
  async preview(
    icp: Partial<ICPPayload>,
    target: TargetImportItem,
  ): Promise<ScorePreview> {
    const { data } = await http.post('/targeting/preview', { icp, target });
    return data as ScorePreview;
  },

  async listTargets(accountId?: string, status?: string): Promise<Target[]> {
    const { data } = await http.get('/targeting/targets', {
      params: { account_id: accountId, status },
    });
    return data.targets ?? [];
  },

  async importTargets(payload: {
    account_id: string;
    icp_id?: string;
    targets: TargetImportItem[];
  }): Promise<{ imported: number; duplicates: number; targets: Target[] }> {
    const { data } = await http.post('/targeting/targets', payload, {
      headers: idempotencyKey(),
    });
    return data;
  },

  async suppress(targetId: string): Promise<Target> {
    const { data } = await http.post(`/targeting/targets/${targetId}/suppress`);
    return data as Target;
  },
};

export const outreachApi = {
  async generate(
    accountId: string,
    icpId?: string,
    limit?: number,
  ): Promise<GenerateResult> {
    const { data } = await http.post(
      '/outreach/suggestions',
      { account_id: accountId, icp_id: icpId, limit },
      { headers: idempotencyKey() },
    );
    return data as GenerateResult;
  },

  /** One page of the queue. Asking for 200 and hoping was the stopgap here
   *  until 2026-09-04; at 400 pending, the rest were invisible and `total`
   *  reported the page size, so nothing could even say how many were missing. */
  async list(
    accountId?: string,
    status = 'pending',
    { limit = 50, offset = 0 }: { limit?: number; offset?: number } = {},
  ): Promise<SuggestionPage> {
    const { data } = await http.get('/outreach/suggestions', {
      params: { account_id: accountId, status, limit, offset },
    });
    return {
      suggestions: data.suggestions ?? [],
      total: data.total ?? 0,
      offset: data.offset ?? offset,
      has_more: data.has_more ?? false,
    };
  },

  /** Just the count for a status, for the queue's tab labels. */
  async count(accountId: string | undefined, status: string): Promise<number> {
    const { data } = await http.get('/outreach/suggestions', {
      params: { account_id: accountId, status, limit: 1 },
    });
    return data.total ?? 0;
  },

  async approve(id: string, editedText?: string, sendAt?: string): Promise<Suggestion> {
    const { data } = await http.post(`/outreach/suggestions/${id}/approve`, {
      edited_text: editedText,
      send_at: sendAt,
    });
    return data as Suggestion;
  },

  async reject(id: string, reason: string, suppressTarget = false): Promise<Suggestion> {
    // reason is required by the backend now (RejectRequest.reason) -- it's
    // the data that improves the prompt later, not optional metadata.
    const { data } = await http.post(`/outreach/suggestions/${id}/reject`, {
      reason,
      suppress_target: suppressTarget,
    });
    return data as Suggestion;
  },

  async send(id: string): Promise<Suggestion> {
    const { data } = await http.post(`/outreach/suggestions/${id}/send`);
    return data as Suggestion;
  },

  async runDue(
    accountId: string,
  ): Promise<{ sent: string[]; blocked: Record<string, string> }> {
    const { data } = await http.post(`/outreach/accounts/${accountId}/run`);
    return data;
  },

  async activity(accountId?: string): Promise<ActivityItem[]> {
    const { data } = await http.get('/outreach/activity', {
      params: { account_id: accountId },
    });
    return data.items ?? [];
  },

  async dashboard(): Promise<Dashboard> {
    const { data } = await http.get('/outreach/dashboard');
    return data as Dashboard;
  },
};

export const warmupApi = {
  async program(): Promise<WarmupProgram> {
    const { data } = await http.get('/warmup/program');
    return data as WarmupProgram;
  },

  async status(accountId: string): Promise<WarmupStatus> {
    const { data } = await http.get(`/warmup/accounts/${accountId}`);
    return data as WarmupStatus;
  },

  async today(accountId: string): Promise<WarmupToday> {
    const { data } = await http.get(`/warmup/accounts/${accountId}/today`);
    return data as WarmupToday;
  },

  async pause(accountId: string, paused: boolean, reason = ''): Promise<void> {
    await http.post(`/warmup/accounts/${accountId}/pause`, { paused, reason });
  },

  async setStage(accountId: string, stage: string): Promise<{ warning?: string }> {
    const { data } = await http.post(`/warmup/accounts/${accountId}/stage`, { stage });
    return data;
  },
};

// Read-only validation of a live account. Sends nothing.
export async function preflight(accountId: string): Promise<PreflightReport> {
  const { data } = await http.post(`/accounts/${accountId}/preflight`);
  return data as PreflightReport;
}

export async function syncAccount(
  accountId: string,
): Promise<{ accepted: number; replied: number; errors: string[] }> {
  const { data } = await http.post(`/outreach/accounts/${accountId}/sync`);
  return data;
}

export async function recordOutcome(
  targetId: string,
  outcome: 'interested' | 'booked' | 'not_interested',
): Promise<{ status: string }> {
  const { data } = await http.post(`/outreach/targets/${targetId}/outcome`, { outcome });
  return data;
}
