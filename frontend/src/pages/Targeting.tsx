// Define who's worth talking to, and load candidate people.
//
// The live preview is the important part of this screen. Getting the ICP wrong
// is what turns outreach into spam, and it should take seconds — not a live
// send — to find out that your criteria would have contacted the wrong people.

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Check, Loader2, Plus, Target as TargetIcon, Upload, X } from 'lucide-react';
import { clsx } from 'clsx';
import { accountApi, targetingApi } from '@/lib/api';
import type { BrandVoiceSummary, ICP, ScorePreview, TargetImportItem } from '@/types';

const BLANK = {
  name: '',
  titles: [] as string[],
  seniorities: [] as string[],
  industries: [] as string[],
  keywords: [] as string[],
  excluded_keywords: [] as string[],
  excluded_titles: [] as string[],
  locations: [] as string[],
  company_sizes: [] as string[],
  value_proposition: '',
  instructions: '',
  brand_voice_id: null as string | null,
  relevance_floor: 60,
};

export function Targeting() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<typeof BLANK | null>(null);
  const [importFor, setImportFor] = useState<string | null>(null);

  const { data: icps = [], isLoading } = useQuery({
    queryKey: ['icps'],
    queryFn: targetingApi.listIcps,
  });
  const { data: accounts = [] } = useQuery({
    queryKey: ['accounts'],
    queryFn: accountApi.list,
  });
  // The brand voice picker: files under config/brand_voices/, not database
  // rows — a marketer adding one shows up here on next load, no deploy.
  const { data: brandVoices = [] } = useQuery({
    queryKey: ['brand-voices'],
    queryFn: targetingApi.listBrandVoices,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['icps'] });

  const save = useMutation({
    mutationFn: (payload: typeof BLANK) => targetingApi.createIcp(payload),
    onSuccess: () => {
      setEditing(null);
      refresh();
    },
  });

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <header className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Targeting</h1>
          <p className="text-slate-400 mt-1">
            Who is worth talking to — and just as importantly, who isn't.
          </p>
        </div>
        <button onClick={() => setEditing(BLANK)} className="btn-primary shrink-0">
          <Plus size={16} />
          New target profile
        </button>
      </header>

      {editing && (
        <ICPEditor
          value={editing}
          onChange={setEditing}
          onSave={() => save.mutate(editing)}
          onCancel={() => setEditing(null)}
          saving={save.isPending}
          brandVoices={brandVoices}
        />
      )}

      {isLoading ? (
        <div className="flex justify-center py-16 text-slate-400">
          <Loader2 className="animate-spin" />
        </div>
      ) : icps.length === 0 && !editing ? (
        <div className="text-center py-16">
          <TargetIcon className="mx-auto text-slate-600 mb-4" size={40} />
          <h2 className="text-lg font-semibold text-slate-200">No target profile yet</h2>
          <p className="text-slate-400 mt-2 max-w-md mx-auto">
            A target profile decides who gets contacted. Without one, nobody does —
            that's deliberate.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {icps.map((icp) => (
            <ICPRow
              key={icp.id}
              icp={icp}
              onImport={() => setImportFor(icp.id)}
              onDeleted={refresh}
            />
          ))}
        </div>
      )}

      {importFor && (
        <ImportPanel
          icpId={importFor}
          accounts={accounts}
          onClose={() => setImportFor(null)}
        />
      )}
    </div>
  );
}

function ICPEditor({
  value,
  onChange,
  onSave,
  onCancel,
  saving,
  brandVoices,
}: {
  value: typeof BLANK;
  onChange: (next: typeof BLANK) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  brandVoices: BrandVoiceSummary[];
}) {
  const set = (patch: Partial<typeof BLANK>) => onChange({ ...value, ...patch });

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-6 rounded-xl bg-slate-800/60 border border-slate-700 p-5"
    >
      <h2 className="text-slate-100 font-semibold mb-4">Define the right person</h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">Name this profile</span>
          <input
            value={value.name}
            onChange={(e) => set({ name: e.target.value })}
            placeholder="e.g. SaaS growth leaders in the UK"
            className="input"
          />
        </label>

        <TagInput
          label="Job titles"
          hint="Matched against title and headline"
          values={value.titles}
          onChange={(titles) => set({ titles })}
        />
        <TagInput
          label="Industries"
          values={value.industries}
          onChange={(industries) => set({ industries })}
        />
        <TagInput
          label="Keywords"
          hint="Any of these anywhere on the profile"
          values={value.keywords}
          onChange={(keywords) => set({ keywords })}
        />
        <TagInput
          label="Locations"
          values={value.locations}
          onChange={(locations) => set({ locations })}
        />
        <TagInput
          label="Never contact if title includes"
          tone="danger"
          values={value.excluded_titles}
          onChange={(excluded_titles) => set({ excluded_titles })}
        />
        <TagInput
          label="Never contact if profile mentions"
          tone="danger"
          hint="One match here rules the person out entirely"
          values={value.excluded_keywords}
          onChange={(excluded_keywords) => set({ excluded_keywords })}
        />

        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">
            What do you help these people with? (in your own words)
          </span>
          <textarea
            value={value.value_proposition}
            onChange={(e) => set({ value_proposition: e.target.value })}
            rows={2}
            placeholder="I help B2B SaaS teams find and fix activation drop-off."
            className="input"
          />
        </label>

        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">
            Standing instructions for the writer
          </span>
          <textarea
            value={value.instructions}
            onChange={(e) => set({ instructions: e.target.value })}
            rows={2}
            placeholder="Never pitch in a first message. Mention the RevOps community if they're in it. Keep it under three sentences."
            className="input"
          />
        </label>

        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">Brand voice</span>
          <select
            value={value.brand_voice_id ?? ''}
            onChange={(e) => set({ brand_voice_id: e.target.value || null })}
            className="select"
          >
            <option value="">Default — plain, brand-neutral voice</option>
            {brandVoices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {voice.brand_name} ({voice.formality})
              </option>
            ))}
          </select>
          <span className="text-xs text-slate-500">
            Defined in config/brand_voices/ — a marketer adds a new one there, no
            engineer needed. It shapes tone only; the safety rules above always apply.
          </span>
        </label>

        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs text-slate-400">
            Only suggest people scoring at least{' '}
            <span className="text-slate-200 font-medium">{value.relevance_floor}</span>
            /100
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={value.relevance_floor}
            onChange={(e) => set({ relevance_floor: Number(e.target.value) })}
            className="accent-accent"
          />
          <span className="text-xs text-slate-500">
            Higher means fewer, better-fitting people.
          </span>
        </label>
      </div>

      <PreviewPanel icp={value} />

      <div className="flex items-center gap-3 mt-5">
        <button
          onClick={onSave}
          disabled={saving || !value.name.trim()}
          className="btn-primary"
        >
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
          Save target profile
        </button>
        <button onClick={onCancel} className="btn-ghost">
          Cancel
        </button>
      </div>
    </motion.div>
  );
}

// Score a made-up person against the draft criteria, live.
function PreviewPanel({ icp }: { icp: typeof BLANK }) {
  const [person, setPerson] = useState<TargetImportItem>({
    full_name: 'Dana Whitfield',
    title: 'Head of Growth',
    company: 'Northwind',
    industry: 'SaaS',
    location: 'London',
    headline: 'Head of Growth at Northwind | B2B activation',
  });
  const [result, setResult] = useState<ScorePreview | null>(null);

  const run = useMutation({
    mutationFn: () => targetingApi.preview(icp, person),
    onSuccess: setResult,
  });

  return (
    <div className="mt-5 pt-5 border-t border-slate-700">
      <h3 className="text-sm font-medium text-slate-200 mb-1">Test it</h3>
      <p className="text-xs text-slate-500 mb-3">
        Score an example person against these criteria. Nothing is saved.
      </p>

      <div className="grid gap-2 sm:grid-cols-4">
        {(['title', 'company', 'industry', 'location'] as const).map((field) => (
          <input
            key={field}
            value={(person[field] as string) ?? ''}
            onChange={(e) => setPerson({ ...person, [field]: e.target.value })}
            placeholder={field}
            className="input text-sm"
          />
        ))}
      </div>

      <button
        onClick={() => run.mutate()}
        disabled={run.isPending}
        className="btn-ghost mt-2"
      >
        {run.isPending ? <Loader2 size={15} className="animate-spin" /> : null}
        Score this person
      </button>

      {result && (
        <div
          className={clsx(
            'mt-3 rounded-lg border p-3 text-sm',
            result.excluded
              ? 'bg-red-500/10 border-red-500/40 text-red-200'
              : result.passes_floor
                ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-200'
                : 'bg-amber-500/10 border-amber-500/40 text-amber-200',
          )}
        >
          <div className="font-medium">
            {result.excluded
              ? `Excluded — ${result.exclusion_reason}`
              : result.passes_floor
                ? `${result.score}/100 — would be contacted`
                : `${result.score}/100 — below your floor, would be skipped`}
          </div>
          <ul className="mt-1.5 space-y-0.5 text-xs opacity-90">
            {result.reasons.map((reason) => (
              <li key={reason}>· {reason}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function TagInput({
  label,
  hint,
  values,
  onChange,
  tone = 'normal',
}: {
  label: string;
  hint?: string;
  values: string[];
  onChange: (next: string[]) => void;
  tone?: 'normal' | 'danger';
}) {
  const [draft, setDraft] = useState('');

  const add = () => {
    const value = draft.trim().toLowerCase();
    if (value && !values.includes(value)) onChange([...values, value]);
    setDraft('');
  };

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <div className="flex flex-wrap gap-1.5 mb-1">
        {values.map((value) => (
          <span
            key={value}
            className={clsx(
              'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs',
              tone === 'danger'
                ? 'bg-red-500/15 text-red-300'
                : 'bg-purple-500/15 text-purple-300',
            )}
          >
            {value}
            <button onClick={() => onChange(values.filter((v) => v !== value))}>
              <X size={11} />
            </button>
          </span>
        ))}
      </div>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
        placeholder="type and press enter"
        className="input text-sm"
      />
      {hint && <span className="text-[11px] text-slate-500">{hint}</span>}
    </div>
  );
}

function ICPRow({
  icp,
  onImport,
  onDeleted,
}: {
  icp: ICP;
  onImport: () => void;
  onDeleted: () => void;
}) {
  const remove = useMutation({
    mutationFn: () => targetingApi.deleteIcp(icp.id),
    onSuccess: onDeleted,
  });

  return (
    <div className="rounded-xl bg-slate-800/60 border border-slate-700 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-slate-100 font-semibold">{icp.name}</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Only contacts people scoring {icp.relevance_floor}+
          </p>
        </div>
        <div className="flex gap-1 shrink-0">
          <button onClick={onImport} className="btn-ghost">
            <Upload size={15} />
            Add people
          </button>
          <button
            onClick={() => remove.mutate()}
            className="btn-ghost text-red-400 hover:bg-red-500/10"
          >
            <X size={15} />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 mt-3">
        {icp.titles.map((title) => (
          <span key={title} className="px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 text-xs">
            {title}
          </span>
        ))}
        {icp.excluded_keywords.map((keyword) => (
          <span key={keyword} className="px-2 py-0.5 rounded bg-red-500/15 text-red-300 text-xs">
            not: {keyword}
          </span>
        ))}
      </div>
    </div>
  );
}

// Paste profile URLs to add candidate people for an account.
function ImportPanel({
  icpId,
  accounts,
  onClose,
}: {
  icpId: string;
  accounts: { id: string; display_name?: string }[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? '');
  const [raw, setRaw] = useState('');
  const [result, setResult] = useState<string | null>(null);

  const parsed: TargetImportItem[] = raw
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.includes('linkedin.com/in/'))
    .map((line) => {
      // Accept "url, Name, Title, Company" so a quick paste carries the context
      // that makes personalized copy possible.
      const [url, name, title, company] = line.split(',').map((part) => part?.trim());
      return {
        profile_url: url,
        full_name: name || undefined,
        title: title || undefined,
        company: company || undefined,
        source: 'manual',
      };
    });

  const submit = useMutation({
    mutationFn: () =>
      targetingApi.importTargets({
        account_id: accountId,
        icp_id: icpId,
        targets: parsed,
      }),
    onSuccess: (data) => {
      setResult(
        `Added ${data.imported} ${data.imported === 1 ? 'person' : 'people'}` +
          (data.duplicates ? `, skipped ${data.duplicates} already on file.` : '.'),
      );
      setRaw('');
      queryClient.invalidateQueries({ queryKey: ['targets'] });
    },
  });

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center p-4 z-50">
      <motion.div
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        className="w-full max-w-xl rounded-xl bg-slate-800 border border-slate-700 p-5"
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-slate-100 font-semibold">Add people</h2>
            <p className="text-sm text-slate-400 mt-1">
              One LinkedIn profile URL per line. Optionally add name, title and
              company after commas — more detail means less generic messages.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X size={18} />
          </button>
        </div>

        <label className="flex flex-col gap-1 mb-3">
          <span className="text-xs text-slate-400">For account</span>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="select"
          >
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.display_name ?? 'Unnamed account'}
              </option>
            ))}
          </select>
        </label>

        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          rows={7}
          placeholder={
            'https://www.linkedin.com/in/dana-whitfield, Dana Whitfield, Head of Growth, Northwind'
          }
          className="input font-mono text-xs w-full"
        />
        <div className="text-xs text-slate-500 mt-1">
          {parsed.length} valid {parsed.length === 1 ? 'profile' : 'profiles'} detected
        </div>

        {result && <div className="mt-3 text-sm text-emerald-300">{result}</div>}

        <div className="flex gap-3 mt-4">
          <button
            onClick={() => submit.mutate()}
            disabled={submit.isPending || !parsed.length || !accountId}
            className="btn-primary"
          >
            {submit.isPending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Upload size={16} />
            )}
            Add {parsed.length || ''} {parsed.length === 1 ? 'person' : 'people'}
          </button>
          <button onClick={onClose} className="btn-ghost">
            Done
          </button>
        </div>
      </motion.div>
    </div>
  );
}
