import React from 'react';
import { Loader2, CheckCircle2, RefreshCw, AlertTriangle, Cpu, Sparkles, ShieldCheck } from 'lucide-react';

export default function GenerationProgress({ statusMessage, progress, theme }) {
  const isDark = theme === 'dark';

  const currentSlide = progress?.current_slide || 1;
  const totalSlides = progress?.total_slides || 8;
  const stage = progress?.stage || 'drafting';
  const detail = progress?.detail || statusMessage || 'Initializing curriculum and inline verifier...';

  const verifiedCount = progress?.verified_count || 0;
  const autoHealedCount = progress?.auto_healed_count || 0;
  const needsReviewCount = progress?.needs_review_count || 0;

  // Compute stage badge style
  const getStageBadge = (stg) => {
    const s = (stg || '').toLowerCase();
    if (s.includes('heal')) {
      return {
        label: stg,
        bg: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
        icon: RefreshCw,
        spin: true,
      };
    }
    if (s.includes('running') || s.includes('code')) {
      return {
        label: 'Running Code in Sandbox',
        bg: 'bg-indigo-500/10 text-indigo-400 border-indigo-500/30',
        icon: Cpu,
        spin: false,
      };
    }
    if (s.includes('proving') || s.includes('exercise')) {
      return {
        label: 'Proving Hands-On Exercises',
        bg: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
        icon: Sparkles,
        spin: false,
      };
    }
    if (s.includes('layout') || s.includes('solver')) {
      return {
        label: 'Collision-Free Solver',
        bg: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30',
        icon: ShieldCheck,
        spin: false,
      };
    }
    if (s.includes('completed')) {
      return {
        label: 'Verification Complete',
        bg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
        icon: CheckCircle2,
        spin: false,
      };
    }
    return {
      label: 'Drafting Slide ' + currentSlide,
      bg: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
      icon: Loader2,
      spin: true,
    };
  };

  const badgeInfo = getStageBadge(stage);
  const BadgeIcon = badgeInfo.icon;

  const percent = Math.min(100, Math.max(8, Math.round((currentSlide / Math.max(1, totalSlides)) * 90)));

  return (
    <div
      className={`rounded-2xl p-6 sm:p-8 border shadow-2xl relative overflow-hidden animate-in fade-in transition-colors duration-200 ${
        isDark
          ? 'bg-[#0F172A]/95 border-blue-500/30 text-white'
          : 'bg-white border-blue-200 text-gray-900 shadow-lg'
      }`}
    >
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center space-x-3.5">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-lg shadow-blue-500/20 shrink-0">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-heading font-bold text-lg sm:text-xl tracking-tight">
                Inline Verification & Slide Generation
              </h3>
            </div>
            <p className={`text-xs mt-0.5 font-mono ${isDark ? 'text-blue-400' : 'text-blue-600'}`}>
              {detail}
            </p>
          </div>
        </div>

        {/* Current Stage Badge */}
        <div className="flex items-center space-x-2">
          <span
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold border flex items-center space-x-1.5 shadow-sm ${badgeInfo.bg}`}
          >
            <BadgeIcon className={`w-3.5 h-3.5 ${badgeInfo.spin ? 'animate-spin' : ''}`} />
            <span className="capitalize">{badgeInfo.label}</span>
          </span>
        </div>
      </div>

      {/* Slide Progress Indicator Bar */}
      <div className="space-y-2 mb-6">
        <div className="flex justify-between items-center text-xs">
          <span className={`font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
            Live Per-Slide Generation Pipeline
          </span>
          <span className="font-mono font-semibold text-blue-500">
            Slide {currentSlide} of {totalSlides} ({percent}%)
          </span>
        </div>
        <div
          className={`w-full rounded-full h-2.5 overflow-hidden border ${
            isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-100 border-slate-200'
          }`}
        >
          <div
            className="bg-gradient-to-r from-blue-500 via-indigo-500 to-emerald-500 h-2.5 rounded-full transition-all duration-500 shadow-md shadow-blue-500/20"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Running Counts: Verified, Auto-Healed, Needs-Review */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
        {/* Verified Count */}
        <div
          className={`p-4 rounded-xl border flex items-center space-x-3.5 transition-all ${
            isDark
              ? 'bg-slate-900/70 border-emerald-500/30'
              : 'bg-emerald-50/50 border-emerald-200'
          }`}
        >
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex items-center justify-center shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xl font-bold font-mono text-emerald-500 leading-tight">
              {verifiedCount}
            </div>
            <div className={`text-xs font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              Verified Snippets
            </div>
          </div>
        </div>

        {/* Auto-Healed Count */}
        <div
          className={`p-4 rounded-xl border flex items-center space-x-3.5 transition-all ${
            isDark
              ? 'bg-slate-900/70 border-amber-500/30'
              : 'bg-amber-50/50 border-amber-200'
          }`}
        >
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20 flex items-center justify-center shrink-0">
            <Sparkles className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xl font-bold font-mono text-amber-500 leading-tight">
              {autoHealedCount}
            </div>
            <div className={`text-xs font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              Auto-Healed Items
            </div>
          </div>
        </div>

        {/* Needs-Review Count */}
        <div
          className={`p-4 rounded-xl border flex items-center space-x-3.5 transition-all ${
            isDark
              ? 'bg-slate-900/70 border-rose-500/30'
              : 'bg-rose-50/50 border-rose-200'
          }`}
        >
          <div className="w-10 h-10 rounded-xl bg-rose-500/10 text-rose-500 border border-rose-500/20 flex items-center justify-center shrink-0">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xl font-bold font-mono text-rose-500 leading-tight">
              {needsReviewCount}
            </div>
            <div className={`text-xs font-medium ${isDark ? 'text-slate-400' : 'text-slate-600'}`}>
              Needs Review
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
