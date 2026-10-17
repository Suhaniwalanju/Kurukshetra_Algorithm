import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  Download,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Terminal,
  Cpu,
  Sparkles,
  Eye,
  FileText,
} from 'lucide-react';

export default function VerificationReportPanel({
  deckId,
  theme,
  isApproved,
  onApprove,
}) {
  const isDark = theme === 'dark';
  const [isOpen, setIsOpen] = useState(true);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [reverifying, setReverifying] = useState(false);
  const [reverifyMessage, setReverifyMessage] = useState('');
  const [selectedDiffId, setSelectedDiffId] = useState(null);

  const fetchReport = async () => {
    try {
      setLoading(true);
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/report`);
      if (res.ok) {
        const data = await res.json();
        setReport(data);
      }
    } catch (err) {
      console.error('Error fetching verification report:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (deckId) {
      fetchReport();
    }
  }, [deckId]);

  const handleReverify = async () => {
    try {
      setReverifying(true);
      setReverifyMessage('');
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/reverify`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setReverifyMessage(
          `Re-verified ${data.stale_checked || 0} snippet(s): ${data.reverified_count || 0} passed, ${data.healed_count || 0} healed.`
        );
        fetchReport();
      } else {
        const err = await res.json();
        alert(`Re-verify error: ${err.detail || 'Failed'}`);
      }
    } catch (err) {
      console.error('Re-verify failed:', err);
      alert('Network error during re-verification');
    } finally {
      setReverifying(false);
    }
  };

  const handleDownloadReport = () => {
    window.open(`http://localhost:8000/api/decks/${deckId}/report/html`, '_blank');
  };

  const summary = report?.summary || {};
  const snippets = report?.snippets || [];
  const healingLogs = report?.healing_logs || [];

  // Map healing logs by snippet_id
  const healingLogsBySnippet = {};
  healingLogs.forEach((log) => {
    if (!healingLogsBySnippet[log.snippet_id]) {
      healingLogsBySnippet[log.snippet_id] = [];
    }
    healingLogsBySnippet[log.snippet_id].push(log);
  });

  return (
    <div
      className={`rounded-2xl border transition-all duration-200 overflow-hidden shadow-xl ${
        isDark ? 'bg-[#0F172A]/95 border-slate-800' : 'bg-white border-slate-200 shadow-md'
      }`}
    >
      {/* Collapsible Panel Header */}
      <div className="p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-slate-200 dark:border-slate-800/80">
        <div className="flex items-center space-x-3.5">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-600 text-white flex items-center justify-center shadow-md shadow-emerald-500/20 shrink-0">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-heading font-bold text-base sm:text-lg tracking-tight">
                Verification Report
              </h3>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                Final Result
              </span>
            </div>
            <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              Inline sandbox execution and self-healing report across all lecture snippets
            </p>
          </div>
        </div>

        {/* Action Buttons & Expand Toggle */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Re-verify Button */}
          <button
            onClick={handleReverify}
            disabled={reverifying}
            className={`px-3 py-2 rounded-xl text-xs font-semibold flex items-center space-x-1.5 border transition-all ${
              reverifying
                ? 'opacity-60 cursor-not-allowed bg-slate-800 border-slate-700 text-slate-300'
                : isDark
                ? 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'
                : 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-800'
            }`}
            title="Re-run only stale or changed snippets"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-blue-400 ${reverifying ? 'animate-spin' : ''}`} />
            <span>{reverifying ? 'Re-verifying...' : 'Re-verify'}</span>
          </button>

          {/* Download Verification Report Button */}
          <button
            onClick={handleDownloadReport}
            className="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs flex items-center space-x-1.5 shadow-md shadow-blue-500/20 transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download verification report</span>
          </button>

          {/* Approve Deck Button */}
          {!isApproved && onApprove ? (
            <button
              onClick={onApprove}
              className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-md shadow-emerald-500/20 transition-all"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Approve Deck</span>
            </button>
          ) : (
            <span className="px-3 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-semibold text-xs flex items-center space-x-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Approved</span>
            </span>
          )}

          {/* Collapse/Expand Toggle */}
          <button
            onClick={() => setIsOpen(!isOpen)}
            className={`p-2 rounded-xl border transition-colors ${
              isDark
                ? 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-300'
                : 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-700'
            }`}
            aria-label="Toggle verification report"
          >
            {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Reverify feedback notice */}
      {reverifyMessage && (
        <div className="px-5 py-2 bg-blue-500/10 border-b border-blue-500/20 text-blue-400 text-xs flex items-center space-x-2">
          <CheckCircle2 className="w-3.5 h-3.5 text-blue-400 shrink-0" />
          <span>{reverifyMessage}</span>
        </div>
      )}

      {/* Summary Stat Badges (Always Visible) */}
      <div
        className={`px-5 py-3 border-b flex flex-wrap items-center gap-4 text-xs font-mono ${
          isDark ? 'bg-slate-900/60 border-slate-800 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-700'
        }`}
      >
        <div className="flex items-center space-x-1.5">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          <span>Total Snippets: <strong className="font-bold">{summary.total_snippets || snippets.length}</strong></span>
        </div>
        <div className="flex items-center space-x-1.5 text-emerald-500">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span>Verified: <strong>{summary.verified_snippets || 0}</strong></span>
        </div>
        <div className="flex items-center space-x-1.5 text-amber-500">
          <span className="w-2 h-2 rounded-full bg-amber-500" />
          <span>Auto-Healed: <strong>{summary.auto_healed_snippets || 0}</strong></span>
        </div>
        <div className="flex items-center space-x-1.5 text-rose-500">
          <span className="w-2 h-2 rounded-full bg-rose-500" />
          <span>Needs Review: <strong>{summary.needs_review_snippets || 0}</strong></span>
        </div>
        {report?.tech && (
          <div className="ml-auto flex items-center space-x-1 text-slate-400">
            <Cpu className="w-3 h-3 text-indigo-400" />
            <span>Target: {report.tech}</span>
          </div>
        )}
      </div>

      {/* Collapsible Content */}
      {isOpen && (
        <div className="p-5 space-y-4">
          {loading ? (
            <div className="py-8 text-center text-xs text-slate-400 flex items-center justify-center space-x-2">
              <RefreshCw className="w-4 h-4 animate-spin text-blue-500" />
              <span>Loading verification report details...</span>
            </div>
          ) : snippets.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-400">
              No code snippets extracted or verified for this deck.
            </div>
          ) : (
            <div className="space-y-4">
              {snippets.map((snip, idx) => {
                const snipLogs = healingLogsBySnippet[snip.id] || [];
                const lastLog = snipLogs.length > 0 ? snipLogs[snipLogs.length - 1] : null;
                const isAutoHealed = snip.status === 'auto_healed' || snip.status === 'healed';
                const isNeedsReview = snip.status === 'needs_review' || snip.status === 'failed';
                const modelUsed = lastLog?.model_name || 'qwen2.5:3b';
                const repairDiff = lastLog?.diff || '';

                const showDiff = selectedDiffId === snip.id;

                return (
                  <div
                    key={snip.id || idx}
                    className={`rounded-xl border p-4 transition-colors ${
                      isDark ? 'bg-slate-900/70 border-slate-800' : 'bg-slate-50 border-slate-200'
                    }`}
                  >
                    {/* Snippet Header Row */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-slate-200 dark:border-slate-800">
                      <div className="flex items-center space-x-2.5">
                        <span className="px-2 py-0.5 rounded-lg text-xs font-bold font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20">
                          {snip.source_location === 'trainer_notes'
                            ? `Notes Slide ${snip.slide_id}`
                            : snip.source_location === 'quiz_item'
                            ? 'Quiz Code'
                            : snip.source_location === 'exercise_starter'
                            ? 'Exercise Code'
                            : `Slide ${snip.slide_id}`}
                        </span>

                        <span className="text-xs font-semibold capitalize">
                          {snip.language}
                        </span>

                        <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
                          isDark ? 'bg-slate-800 border-slate-700 text-slate-300' : 'bg-slate-200 border-slate-300 text-slate-700'
                        }`}>
                          v{snip.real_runtime_version || snip.version || 'pinned'}
                        </span>

                        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                          backend: {snip.sandbox_backend || 'docker'}
                        </span>
                      </div>

                      <div className="flex items-center space-x-2">
                        {/* Status Badge */}
                        <span
                          className={`px-2.5 py-1 rounded-full text-xs font-bold flex items-center space-x-1 border ${
                            isAutoHealed
                              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                              : isNeedsReview
                              ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                              : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          }`}
                        >
                          {isAutoHealed ? (
                            <>
                              <Sparkles className="w-3 h-3 text-amber-400" />
                              <span>Auto-Healed</span>
                            </>
                          ) : isNeedsReview ? (
                            <>
                              <AlertTriangle className="w-3 h-3 text-rose-400" />
                              <span>Needs Review</span>
                            </>
                          ) : (
                            <>
                              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                              <span>Verified</span>
                            </>
                          )}
                        </span>

                        <span className="text-xs font-mono text-slate-400">
                          {snip.attempts_count || 1} attempt(s)
                        </span>
                      </div>
                    </div>

                    {/* Metadata Details Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-xs">
                      {/* Command Executed */}
                      <div>
                        <div className={`text-[11px] font-semibold mb-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                          Command Executed:
                        </div>
                        <div className="p-2 rounded-lg bg-black/60 font-mono text-[11px] text-emerald-400 truncate border border-slate-800">
                          $ {snip.command_executed || `${snip.language} run snippet`}
                        </div>
                      </div>

                      {/* Model Used */}
                      <div>
                        <div className={`text-[11px] font-semibold mb-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                          Model Used:
                        </div>
                        <div className="p-2 rounded-lg bg-black/60 font-mono text-[11px] text-blue-300 border border-slate-800">
                          {isAutoHealed ? `${modelUsed} (Self-Healing)` : 'Deterministic Sandbox Verifier'}
                        </div>
                      </div>
                    </div>

                    {/* Captured Stdout / Stderr Box */}
                    <div className="mt-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-[11px] font-semibold ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                          Captured Output (stdout / stderr):
                        </span>
                      </div>
                      <div className="rounded-lg bg-black/80 p-3 font-mono text-[11px] text-slate-200 border border-slate-800 max-h-32 overflow-y-auto space-y-1">
                        {snip.actual_output && (
                          <div className="text-emerald-400 whitespace-pre-wrap">
                            {snip.actual_output}
                          </div>
                        )}
                        {snip.stderr && (
                          <div className="text-rose-400 whitespace-pre-wrap">
                            {snip.stderr}
                          </div>
                        )}
                        {snip.compiler_output && (
                          <div className="text-amber-400 whitespace-pre-wrap">
                            {snip.compiler_output}
                          </div>
                        )}
                        {!snip.actual_output && !snip.stderr && !snip.compiler_output && (
                          <div className="text-slate-500 italic">
                            (No output produced; exit code: {snip.exit_code || 0})
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Repair Diff Toggle (For Auto-Healed Snippets) */}
                    {isAutoHealed && repairDiff && (
                      <div className="mt-3 pt-2 border-t border-slate-200 dark:border-slate-800">
                        <button
                          onClick={() => setSelectedDiffId(showDiff ? null : snip.id)}
                          className="text-xs font-semibold text-amber-400 hover:text-amber-300 flex items-center space-x-1.5 transition-colors"
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          <span>{showDiff ? 'Hide Repair Diff' : 'View Repair Diff (Unified)'}</span>
                          {showDiff ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                        </button>

                        {showDiff && (
                          <div className="mt-2 rounded-lg bg-black/90 p-3 font-mono text-[11px] border border-amber-500/30 overflow-x-auto max-h-48 overflow-y-auto">
                            {repairDiff.split('\n').map((line, lidx) => {
                              const isAdded = line.startsWith('+');
                              const isRemoved = line.startsWith('-');
                              return (
                                <div
                                  key={lidx}
                                  className={`${
                                    isAdded
                                      ? 'text-emerald-400 bg-emerald-500/10'
                                      : isRemoved
                                      ? 'text-rose-400 bg-rose-500/10'
                                      : 'text-slate-400'
                                  }`}
                                >
                                  {line}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
