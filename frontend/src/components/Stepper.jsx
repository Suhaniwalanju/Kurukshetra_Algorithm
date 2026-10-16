import React from 'react';
import {
  FileText,
  Layout,
  Presentation,
  ShieldCheck,
  CheckCircle,
  BookOpen,
  Download,
} from 'lucide-react';

export default function Stepper({ currentStep, onSelectStep, theme, deckState = {} }) {
  const isDark = theme === 'dark';

  const steps = [
    { id: 1, label: 'Inputs', icon: FileText, desc: 'Topic & Tech' },
    { id: 2, label: 'Template', icon: Layout, desc: 'Branded Zone' },
    { id: 3, label: 'Deck Preview', icon: Presentation, desc: 'Minimal Slides' },
    { id: 4, label: 'Verification', icon: ShieldCheck, desc: 'Sandbox QA' },
    { id: 5, label: 'Approval', icon: CheckCircle, desc: 'Professor Signoff' },
    { id: 6, label: 'Materials', icon: BookOpen, desc: 'Notes, Quiz, Sheet' },
    { id: 7, label: 'Export', icon: Download, desc: 'PDF / PPTX / ZIP' },
  ];

  const isStepAccessible = (stepId) => {
    if (stepId <= 1) return true;
    if (stepId <= 3 && deckState?.hasDeck) return true;
    if (stepId === 4 && deckState?.hasDeck) return true;
    if (stepId === 5 && deckState?.verified) return true;
    if (stepId === 6 && deckState?.approved) return true;
    if (stepId === 7 && deckState?.materialsReady) return true;
    return false;
  };

  return (
    <div
      className={`rounded-2xl p-4 border transition-colors shadow-sm ${
        isDark ? 'bg-[#0F172A]/90 border-slate-800' : 'bg-white border-slate-200'
      }`}
    >
      <div className="flex items-center justify-between overflow-x-auto pb-1 gap-2">
        {steps.map((step, idx) => {
          const Icon = step.icon;
          const isActive = currentStep === step.id;
          const accessible = isStepAccessible(step.id);
          const isCompleted = currentStep > step.id;

          return (
            <div key={step.id} className="flex items-center flex-1 min-w-[120px]">
              <button
                onClick={() => accessible && onSelectStep && onSelectStep(step.id)}
                disabled={!accessible}
                className={`w-full flex items-center space-x-2.5 p-2 rounded-xl text-left transition-all ${
                  isActive
                    ? 'bg-gradient-to-r from-blue-600/20 to-indigo-600/20 border border-blue-500/40 text-blue-400'
                    : isCompleted
                    ? isDark
                      ? 'text-emerald-400 hover:bg-slate-800/60'
                      : 'text-emerald-600 hover:bg-slate-100'
                    : accessible
                    ? isDark
                      ? 'text-slate-300 hover:bg-slate-800/50'
                      : 'text-slate-700 hover:bg-slate-100'
                    : 'opacity-40 cursor-not-allowed text-slate-500'
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold ${
                    isActive
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-500/30'
                      : isCompleted
                      ? 'bg-emerald-600/20 text-emerald-400 border border-emerald-500/30'
                      : isDark
                      ? 'bg-slate-800 text-slate-400'
                      : 'bg-slate-200 text-slate-600'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold truncate leading-tight flex items-center space-x-1">
                    <span>{step.label}</span>
                    {isCompleted && <span className="text-[10px] text-emerald-400">✓</span>}
                  </div>
                  <div
                    className={`text-[10px] truncate ${
                      isActive
                        ? 'text-blue-300'
                        : isDark
                        ? 'text-slate-400'
                        : 'text-slate-500'
                    }`}
                  >
                    {step.desc}
                  </div>
                </div>
              </button>
              {idx < steps.length - 1 && (
                <div
                  className={`hidden sm:block w-3 h-[2px] mx-1 shrink-0 ${
                    currentStep > step.id
                      ? 'bg-emerald-500/40'
                      : isDark
                      ? 'bg-slate-800'
                      : 'bg-slate-200'
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
