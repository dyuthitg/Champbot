import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Target,
  Settings,
  Calendar,
  Plus,
  X,
  ThumbsUp,
  MessageSquare,
  Share2,
  UserPlus,
} from 'lucide-react';
import { campaignApi } from '@/lib/api';
import type { CampaignCreate } from '@/types';
import { clsx } from 'clsx';

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

interface FormData {
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
  priority: number;
  scheduled_start?: string;
}

const steps = [
  {
    id: 1,
    title: 'Basic Info',
    subtitle: 'Campaign name and description',
    icon: FileText,
  },
  {
    id: 2,
    title: 'Target URLs',
    subtitle: 'LinkedIn profiles or posts',
    icon: Target,
  },
  {
    id: 3,
    title: 'Actions',
    subtitle: 'Choose automation actions',
    icon: Settings,
  },
  {
    id: 4,
    title: 'Schedule',
    subtitle: 'Set priority and timing',
    icon: Calendar,
  },
];

export function CreateCampaign() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [currentStep, setCurrentStep] = useState(1);
  const [direction, setDirection] = useState(1);
  const reduced = prefersReducedMotion();

  const [formData, setFormData] = useState<FormData>({
    name: '',
    description: '',
    target_urls: [],
    account_ids: ['default-account'], // TODO: Fetch actual accounts
    actions: {
      like: true,
      comment: false,
      share: false,
      follow: false,
    },
    priority: 2,
  });

  const createMutation = useMutation({
    mutationFn: (data: CampaignCreate) => campaignApi.create(data),
    onSuccess: (campaign) => {
      queryClient.invalidateQueries({ queryKey: ['campaigns'] });
      navigate(`/campaigns/${campaign.id}`);
    },
  });

  const nextStep = () => {
    if (currentStep < steps.length) {
      setDirection(1);
      setCurrentStep(currentStep + 1);
    }
  };

  const prevStep = () => {
    if (currentStep > 1) {
      setDirection(-1);
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = () => {
    createMutation.mutate(formData);
  };

  const isStepValid = () => {
    switch (currentStep) {
      case 1:
        return formData.name.trim() !== '' && formData.description.trim() !== '';
      case 2:
        return formData.target_urls.length > 0;
      case 3:
        return Object.values(formData.actions).some((v) => v);
      case 4:
        return true;
      default:
        return false;
    }
  };

  const slideVariants = {
    enter: (dir: number) => ({ x: reduced ? 0 : dir > 0 ? 300 : -300, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: reduced ? 0 : dir > 0 ? -300 : 300, opacity: 0 }),
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <button
          onClick={() => navigate('/campaigns')}
          className="flex items-center gap-2 text-muted hover:text-foreground mb-4 min-h-[44px] sm:min-h-0"
        >
          <ArrowLeft size={20} />
          Back to Campaigns
        </button>

        <h1 className="text-2xl font-semibold text-slate-100 mb-2">
          Create New Campaign
        </h1>
        <p className="text-muted">
          Set up your LinkedIn automation campaign in a few steps
        </p>
      </div>

      {/* Progress Indicator */}
      <div className="mb-8">
        <div className="flex justify-between">
          {steps.map((step, index) => {
            const isActive = currentStep === step.id;
            const isCompleted = currentStep > step.id;
            const Icon = step.icon;

            return (
              <div key={step.id} className="flex-1">
                <div className="flex items-center">
                  {/* Line */}
                  {index > 0 && (
                    <div className="flex-1 h-1 mx-1 sm:mx-2">
                      <motion.div
                        className="h-full bg-slate-800 rounded-full overflow-hidden"
                        initial={false}
                      >
                        <motion.div
                          className="h-full bg-accent"
                          initial={reduced ? { width: isCompleted ? '100%' : '0%' } : { width: 0 }}
                          animate={{ width: isCompleted ? '100%' : '0%' }}
                          transition={{ duration: reduced ? 0 : 0.3 }}
                        />
                      </motion.div>
                    </div>
                  )}

                  {/* Step Indicator */}
                  <div className="flex flex-col items-center">
                    <motion.div
                      className={clsx(
                        'w-10 h-10 sm:w-12 sm:h-12 rounded-full flex items-center justify-center',
                        'border-2 transition-colors duration-300',
                        isActive || isCompleted
                          ? 'bg-accent border-accent text-white'
                          : 'bg-surface border-border text-muted'
                      )}
                      whileHover={reduced ? undefined : { scale: 1.1 }}
                    >
                      {isCompleted ? <Check size={22} /> : <Icon size={22} />}
                    </motion.div>

                    <div className="mt-2 text-center">
                      <p
                        className={clsx(
                          'text-xs sm:text-sm font-medium',
                          isActive || isCompleted ? 'text-foreground' : 'text-muted'
                        )}
                      >
                        {step.title}
                      </p>
                      <p className="text-xs text-muted hidden md:block">
                        {step.subtitle}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Form Content */}
      <div className="bg-surface border border-border rounded-xl p-4 sm:p-8 mb-6">
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={currentStep}
            custom={direction}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ type: 'tween', duration: reduced ? 0 : 0.3 }}
          >
            {currentStep === 1 && (
              <Step1BasicInfo formData={formData} setFormData={setFormData} />
            )}
            {currentStep === 2 && (
              <Step2TargetURLs formData={formData} setFormData={setFormData} reduced={reduced} />
            )}
            {currentStep === 3 && (
              <Step3Actions formData={formData} setFormData={setFormData} reduced={reduced} />
            )}
            {currentStep === 4 && (
              <Step4Schedule formData={formData} setFormData={setFormData} reduced={reduced} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Navigation Buttons */}
      <div className="flex justify-between gap-3">
        {currentStep > 1 ? (
          <motion.button
            whileHover={reduced ? undefined : { scale: 1.05 }}
            whileTap={reduced ? undefined : { scale: 0.95 }}
            onClick={prevStep}
            className="flex items-center gap-2 px-6 py-3 min-h-[44px] border border-border rounded-lg font-medium text-muted hover:bg-surface"
          >
            <ArrowLeft size={20} />
            Previous
          </motion.button>
        ) : (
          <div />
        )}

        {currentStep < steps.length ? (
          <motion.button
            whileHover={reduced || !isStepValid() ? undefined : { scale: 1.05 }}
            whileTap={reduced || !isStepValid() ? undefined : { scale: 0.95 }}
            onClick={nextStep}
            disabled={!isStepValid()}
            className={clsx(
              'flex items-center gap-2 px-6 py-3 min-h-[44px] rounded-lg font-medium',
              isStepValid()
                ? 'bg-accent text-white hover:bg-accent/85'
                : 'bg-slate-700/60 text-muted cursor-not-allowed'
            )}
          >
            Next
            <ArrowRight size={20} />
          </motion.button>
        ) : (
          <motion.button
            whileHover={reduced || !isStepValid() ? undefined : { scale: 1.05 }}
            whileTap={reduced || !isStepValid() ? undefined : { scale: 0.95 }}
            onClick={handleSubmit}
            disabled={!isStepValid() || createMutation.isPending}
            className={clsx(
              'flex items-center gap-2 px-6 py-3 min-h-[44px] rounded-lg font-medium',
              isStepValid() && !createMutation.isPending
                ? 'bg-success text-white hover:bg-success/85'
                : 'bg-slate-700/60 text-muted cursor-not-allowed'
            )}
          >
            {createMutation.isPending ? (
              <>
                <motion.div
                  animate={reduced ? undefined : { rotate: 360 }}
                  transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  className="w-5 h-5 border-2 border-white border-t-transparent rounded-full"
                />
                Creating...
              </>
            ) : (
              <>
                <Check size={20} />
                Create Campaign
              </>
            )}
          </motion.button>
        )}
      </div>
    </div>
  );
}

// Step 1: Basic Info
function Step1BasicInfo({
  formData,
  setFormData,
}: {
  formData: FormData;
  setFormData: (data: FormData) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-muted mb-2">
          Campaign Name *
        </label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="e.g., Tech Industry Outreach Q1 2024"
          className="input w-full py-3"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-muted mb-2">
          Description *
        </label>
        <textarea
          value={formData.description}
          onChange={(e) =>
            setFormData({ ...formData, description: e.target.value })
          }
          placeholder="Describe your campaign goals and target audience..."
          rows={6}
          className="input w-full py-3 resize-none"
        />
      </div>
    </div>
  );
}

// Step 2: Target URLs
function Step2TargetURLs({
  formData,
  setFormData,
  reduced,
}: {
  formData: FormData;
  setFormData: (data: FormData) => void;
  reduced: boolean;
}) {
  const [newUrl, setNewUrl] = useState('');

  const addUrl = () => {
    if (newUrl.trim() && !formData.target_urls.includes(newUrl.trim())) {
      setFormData({
        ...formData,
        target_urls: [...formData.target_urls, newUrl.trim()],
      });
      setNewUrl('');
    }
  };

  const removeUrl = (url: string) => {
    setFormData({
      ...formData,
      target_urls: formData.target_urls.filter((u) => u !== url),
    });
  };

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-muted mb-2">
          Add Target URL
        </label>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="url"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addUrl())}
            placeholder="https://linkedin.com/in/username"
            className="input flex-1 py-3"
          />
          <motion.button
            whileHover={reduced ? undefined : { scale: 1.05 }}
            whileTap={reduced ? undefined : { scale: 0.95 }}
            onClick={addUrl}
            className="btn-primary min-h-[44px] px-6 py-3 justify-center"
          >
            <Plus size={20} />
            Add
          </motion.button>
        </div>
      </div>

      {formData.target_urls.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-muted mb-2">
            Target URLs ({formData.target_urls.length})
          </label>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            <AnimatePresence mode="popLayout">
              {formData.target_urls.map((url) => (
                <motion.div
                  key={url}
                  layout
                  initial={reduced ? undefined : { opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={reduced ? undefined : { opacity: 0, x: 20 }}
                  className="flex items-center justify-between gap-2 p-4 bg-slate-900/50 rounded-lg border border-border"
                >
                  <span className="text-sm text-slate-300 truncate">{url}</span>
                  <motion.button
                    whileHover={reduced ? undefined : { scale: 1.1 }}
                    whileTap={reduced ? undefined : { scale: 0.9 }}
                    onClick={() => removeUrl(url)}
                    className="text-danger-fg hover:text-danger min-h-[44px] min-w-[44px] flex items-center justify-center shrink-0"
                    aria-label={`Remove ${url}`}
                  >
                    <X size={20} />
                  </motion.button>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}
    </div>
  );
}

// Step 3: Actions
function Step3Actions({
  formData,
  setFormData,
  reduced,
}: {
  formData: FormData;
  setFormData: (data: FormData) => void;
  reduced: boolean;
}) {
  const actions = [
    {
      key: 'like' as const,
      icon: ThumbsUp,
      label: 'Like Posts',
      description: 'Automatically like target posts',
      color: 'bg-blue-500',
    },
    {
      key: 'comment' as const,
      icon: MessageSquare,
      label: 'Comment',
      description: 'Leave AI-generated comments',
      color: 'bg-success',
    },
    {
      key: 'share' as const,
      icon: Share2,
      label: 'Share',
      description: 'Share posts to your network',
      color: 'bg-purple-500',
    },
    {
      key: 'follow' as const,
      icon: UserPlus,
      label: 'Follow',
      description: 'Follow target profiles',
      color: 'bg-orange-500',
    },
  ];

  const toggleAction = (key: keyof FormData['actions']) => {
    setFormData({
      ...formData,
      actions: {
        ...formData.actions,
        [key]: !formData.actions[key],
      },
    });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted mb-4">
        Select the actions you want to automate
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {actions.map((action) => {
          const Icon = action.icon;
          const isActive = formData.actions[action.key];

          return (
            <motion.button
              key={action.key}
              onClick={() => toggleAction(action.key)}
              whileHover={reduced ? undefined : { scale: 1.02 }}
              whileTap={reduced ? undefined : { scale: 0.98 }}
              className={clsx(
                'p-6 rounded-xl border-2 text-left transition-all',
                isActive
                  ? 'border-accent bg-accent/10'
                  : 'border-border bg-slate-900/40 hover:border-slate-600'
              )}
            >
              <div className="flex items-start gap-4">
                <div
                  className={clsx(
                    'w-12 h-12 rounded-lg flex items-center justify-center text-white shrink-0',
                    action.color
                  )}
                >
                  <Icon size={24} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-semibold text-foreground">
                      {action.label}
                    </h3>
                    {isActive && (
                      <motion.div
                        initial={reduced ? undefined : { scale: 0 }}
                        animate={{ scale: 1 }}
                        className="w-6 h-6 bg-accent rounded-full flex items-center justify-center shrink-0"
                      >
                        <Check size={16} className="text-white" />
                      </motion.div>
                    )}
                  </div>
                  <p className="text-sm text-muted">{action.description}</p>
                </div>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}

// Step 4: Schedule
function Step4Schedule({
  formData,
  setFormData,
  reduced,
}: {
  formData: FormData;
  setFormData: (data: FormData) => void;
  reduced: boolean;
}) {
  const priorities = [
    { value: 1, label: 'Low', description: 'Run when resources available' },
    { value: 2, label: 'Normal', description: 'Standard priority' },
    { value: 3, label: 'High', description: 'Execute as soon as possible' },
  ];

  return (
    <div className="space-y-6">
      {/* Priority */}
      <div>
        <label className="block text-sm font-medium text-muted mb-4">
          Campaign Priority
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {priorities.map((priority) => (
            <motion.button
              key={priority.value}
              onClick={() =>
                setFormData({ ...formData, priority: priority.value })
              }
              whileHover={reduced ? undefined : { scale: 1.02 }}
              whileTap={reduced ? undefined : { scale: 0.98 }}
              className={clsx(
                'p-4 rounded-lg border-2 text-center transition-all',
                formData.priority === priority.value
                  ? 'border-accent bg-accent/10'
                  : 'border-border bg-slate-900/40 hover:border-slate-600'
              )}
            >
              <h4 className="font-semibold text-foreground mb-1">
                {priority.label}
              </h4>
              <p className="text-xs text-muted">{priority.description}</p>
            </motion.button>
          ))}
        </div>
      </div>

      {/* Schedule Start (Optional) */}
      <div>
        <label className="block text-sm font-medium text-muted mb-2">
          Scheduled Start (Optional)
        </label>
        <input
          type="datetime-local"
          value={formData.scheduled_start || ''}
          onChange={(e) =>
            setFormData({ ...formData, scheduled_start: e.target.value })
          }
          className="input w-full py-3"
        />
        <p className="text-sm text-muted mt-2">
          Leave empty to start immediately when campaign is activated
        </p>
      </div>

      {/* Summary */}
      <div className="mt-8 p-6 bg-slate-900/40 rounded-lg border border-border">
        <h3 className="font-semibold text-foreground mb-4">Campaign Summary</h3>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between gap-3">
            <span className="text-muted">Name:</span>
            <span className="font-medium text-foreground truncate">{formData.name || '-'}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-muted">Target URLs:</span>
            <span className="font-medium text-foreground">{formData.target_urls.length}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-muted">Actions:</span>
            <span className="font-medium text-foreground">
              {Object.values(formData.actions).filter(Boolean).length}
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-muted">Priority:</span>
            <span className="font-medium text-foreground">
              {priorities.find((p) => p.value === formData.priority)?.label}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
