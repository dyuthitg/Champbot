// Campaign Types
export type CampaignStatus =
  | 'draft'
  | 'scheduled'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type TaskStatus =
  | 'pending'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'rate_limited';

export type AgentStatus =
  | 'idle'
  | 'processing'
  | 'waiting'
  | 'error';

export interface CampaignProgress {
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
}

export interface Campaign {
  id: string;
  name: string;
  description: string;
  status: CampaignStatus;
  target_urls: string[];
  account_ids: string[];
  actions: {
    like: boolean;
    comment: boolean;
    share: boolean;
    follow: boolean;
  };
  priority: number;
  progress: CampaignProgress;
  created_at: string;
  updated_at: string;
  scheduled_start?: string;
}

export interface CampaignTask {
  id: string;
  campaign_id: string;
  orchestrator_task_id?: string;
  target_url: string;
  status: TaskStatus;
  result?: {
    likes?: number;
    comments?: number;
    shares?: number;
    error?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface CampaignCreate {
  name: string;
  description: string;
  target_urls: string[];
  account_ids: string[];
  actions: {
    like: boolean;
    comment: boolean;
    share: boolean;
    follow: boolean;
  };
  priority?: number;
  scheduled_start?: string;
}

export interface CampaignUpdate {
  name?: string;
  description?: string;
  status?: CampaignStatus;
  target_urls?: string[];
  account_ids?: string[];
  actions?: {
    like?: boolean;
    comment?: boolean;
    share?: boolean;
    follow?: boolean;
  };
  priority?: number;
  scheduled_start?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Agent Types
export interface Agent {
  id: string;
  name: string;
  type: 'account_manager' | 'content_analysis' | 'interaction' | 'conversation' | 'safety';
  status: AgentStatus;
  current_task?: string;
  tasks_completed: number;
  tasks_failed: number;
  last_activity: string;
}

export interface AgentMessage {
  id: string;
  agent_id: string;
  type: 'COMMAND' | 'QUERY' | 'RESPONSE' | 'EVENT' | 'ERROR' | 'HEALTH_CHECK' | 'STATE_UPDATE';
  priority: 'LOW' | 'NORMAL' | 'HIGH' | 'CRITICAL';
  content: any;
  timestamp: string;
}

// WebSocket Message Types
export interface WSMessage {
  type: 'CAMPAIGN_UPDATE' | 'TASK_COMPLETED' | 'TASK_FAILED' | 'AGENT_STATUS' | 'PROGRESS_UPDATE';
  campaign_id?: string;
  task_id?: string;
  agent_id?: string;
  data: any;
  timestamp: string;
}

// Auth Types
export interface User {
  id: string;
  email: string;
  name?: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

// ---------------------------------------------------------------------------
// Outreach: connected accounts, ICP targeting, and the approval queue
// ---------------------------------------------------------------------------

export type AccountStatus =
  | 'active'
  | 'inactive'
  | 'suspended'
  | 'rate_limited'
  | 'auth_required'
  | 'error';

export type EngagementMode = 'outreach' | 'account_based_engagement';

export interface ActionCaps {
  per_hour: number;
  per_day: number;
  cooldown_seconds: number;
}

export interface AccountPolicy {
  actions: Record<string, ActionCaps>;
  suggestion_budget: number;
  active_hours: [number, number];
  warmup: boolean;
}

export interface ConnectedAccount {
  id: string;
  org_id: string;
  user_id: string;
  status: AccountStatus;
  mode?: EngagementMode;
  display_name?: string;
  headline?: string;
  profile_url?: string;
  linkedin_member_urn?: string;
  active_icp_id?: string;
  policy: AccountPolicy;
  has_credentials: boolean;
  transport?: string;
  last_post_at?: string;
  last_active_at?: string;
  created_at?: string;
}

export interface AccountConnectPayload {
  li_at: string;
  jsessionid?: string;
  label?: string;
  mode?: EngagementMode;
  proxy_url?: string;
  timezone?: string;
}

export interface ICP {
  id: string;
  org_id: string;
  account_id?: string;
  name: string;
  titles: string[];
  seniorities: string[];
  industries: string[];
  keywords: string[];
  excluded_keywords: string[];
  excluded_titles: string[];
  locations: string[];
  company_sizes: string[];
  value_proposition?: string;
  instructions?: string;
  relevance_floor: number;
  is_active: boolean;
  created_at?: string;
}

export type ICPPayload = Omit<ICP, 'id' | 'org_id' | 'is_active' | 'created_at'>;

export type TargetStatus =
  | 'new'
  | 'scored'
  | 'suggested'
  | 'approved'
  | 'contacted'
  | 'connected'
  | 'replied'
  | 'skipped'
  | 'suppressed';

export interface Target {
  id: string;
  account_id: string;
  member_urn: string;
  public_id?: string;
  profile_url?: string;
  full_name?: string;
  first_name?: string;
  headline?: string;
  title?: string;
  company?: string;
  industry?: string;
  location?: string;
  source?: string;
  relevance_score: number;
  relevance_reasons: string[];
  status: TargetStatus;
  last_touched_at?: string;
  created_at?: string;
}

export interface TargetImportItem {
  profile_url?: string;
  member_urn?: string;
  full_name?: string;
  first_name?: string;
  headline?: string;
  title?: string;
  company?: string;
  industry?: string;
  location?: string;
  source?: string;
  context?: Record<string, unknown>;
}

export type SuggestionAction = 'connect' | 'message' | 'comment' | 'like' | 'follow';

export type SuggestionStatus =
  | 'pending'
  | 'approved'
  | 'scheduled'
  | 'sent'
  | 'failed'
  | 'rejected'
  | 'expired'
  | 'blocked';

export interface TargetSummary {
  id: string;
  full_name?: string;
  first_name?: string;
  headline?: string;
  title?: string;
  company?: string;
  location?: string;
  profile_url?: string;
  status?: string;
}

export interface Suggestion {
  id: string;
  account_id: string;
  target_id: string;
  action: SuggestionAction;
  status: SuggestionStatus;
  draft_text?: string;
  final_text?: string;
  rationale?: string;
  relevance_score: number;
  relevance_reasons: string[];
  quality_score?: number;
  quality_warnings: string[];
  generated_by?: string;
  subject_urn?: string;
  scheduled_for?: string;
  sent_at?: string;
  error?: string;
  created_at?: string;
  target?: TargetSummary;
  /** Names of other pending suggestions this draft reads like — see
   * src/outreach/similarity.py. Empty when nothing queued is close enough
   * to flag. */
  similar_to?: string[];
}

export interface GenerateResult {
  created: Suggestion[];
  considered: number;
  skipped: Record<string, number>;
  message: string;
}

export interface ActivityItem {
  id: string;
  account_id: string;
  action: string;
  status: string;
  target_name?: string;
  target_headline?: string;
  text?: string;
  relevance_score: number;
  occurred_at?: string;
  error?: string;
}

export interface AccountStats {
  account_id: string;
  display_name?: string;
  status: AccountStatus;
  mode?: EngagementMode;
  pending_review: number;
  scheduled: number;
  sent_today: number;
  sent_total: number;
  failed: number;
  connects_sent: number;
  messages_sent: number;
  remaining_today: Record<string, number>;
  warmup_stage?: string;
  warmup_stage_name?: string;
  warmup_paused: boolean;
  health_verdict: 'healthy' | 'caution' | 'danger' | 'unknown';
  health_headline: string;
  throttle: number;
  funnel: Partial<Funnel>;
}

export interface Dashboard {
  accounts: AccountStats[];
  totals: Record<string, number>;
}

export interface ScorePreview {
  score: number;
  reasons: string[];
  excluded: boolean;
  exclusion_reason?: string;
  passes_floor: boolean;
}

// ---------------------------------------------------------------------------
// Warm-up programme
// ---------------------------------------------------------------------------

export type WarmupStageKey =
  | 'observe'
  | 'react'
  | 'converse'
  | 'publish'
  | 'connect'
  | 'full';

export type HealthVerdict = 'healthy' | 'caution' | 'danger' | 'unknown';

export interface WarmupStageSpec {
  key: WarmupStageKey;
  name: string;
  intent: string;
  min_days: number;
  allowed: string[];
  daily: Record<string, { low: number; high: number; probability: number }>;
  requires: Record<string, number>;
  min_acceptance_rate: number | null;
}

export interface SequenceStepSpec {
  key: string;
  action: string;
  wait_days: number;
  objective: string;
  requires_status: string[];
  manual_only: boolean;
  allow_scheduler_link: boolean;
}

export interface WarmupProgram {
  stages: WarmupStageSpec[];
  minimum_days_to_outreach: number;
  sequence: SequenceStepSpec[];
  acceptance_thresholds: { caution_below: number; danger_below: number };
  principles: string[];
}

export interface Funnel {
  invites_sent: number;
  invites_accepted: number;
  messages_sent: number;
  replies: number;
  interested: number;
  booked: number;
  acceptance_rate: number | null;
  reply_rate: number | null;
  booking_rate: number | null;
}

export interface AccountHealthReport {
  verdict: HealthVerdict;
  throttle: number;
  suspended_actions: string[];
  headline: string;
  advice: string[];
  had_challenge: boolean;
  funnel: Funnel;
}

export interface WarmupStatus {
  account_id: string;
  stage: WarmupStageKey;
  stage_name: string;
  intent: string;
  days_in_stage: number;
  min_days: number;
  allowed_actions: string[];
  totals: Record<string, number>;
  changed: { from: string; to: string; direction: string } | null;
  ready_to_advance: boolean;
  next_stage: string | null;
  progress: string[];
  blockers: string[];
  paused: boolean;
  health: AccountHealthReport;
}

export interface PlannedAction {
  action: string;
  at: string;
  reason: string;
}

export interface WarmupToday extends WarmupStatus {
  plan: {
    day?: string;
    actions: PlannedAction[];
    counts: Record<string, number>;
    completed_today?: Record<string, number>;
    notes: string[];
  };
}

export interface PreflightCheck {
  name: string;
  label: string;
  ok: boolean;
  critical: boolean;
  detail: Record<string, unknown> | null;
  error: string | null;
  impact: string;
}

export interface PreflightReport {
  ok: boolean;
  identity: Record<string, string>;
  summary: string;
  next_steps: string[];
  checks: PreflightCheck[];
}
