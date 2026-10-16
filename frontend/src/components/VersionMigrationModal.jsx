import React, { useState } from 'react';
import {
  X,
  Sparkles,
  RefreshCw,
  CheckCircle,
  AlertTriangle,
  ArrowRight,
  Code2,
} from 'lucide-react';

export default function VersionMigrationModal({
  deckId,
  currentTech,
  currentVersion,
  onClose,
  onMigrated,
  theme,
}) {
  const isDark = theme === 'dark';
  const [newVersion, setNewVersion] = useState(
    currentTech?.toLowerCase() === 'java' ? '21' : 'latest'
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleMigrate = async () => {
    setLoading(true);
    setErrorMsg('');
    setResult(null);

    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/migrate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_version: newVersion }),
      });

      if (res.ok) {
        const data = await res.json();
        setResult(data);
        if (onMigrated) onMigrated(data);
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Version migration failed');
      }
    } catch (e) {
      console.error(e);
      setErrorMsg('Network error connecting to backend');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-150">
      <div
        className={`relative w-full max-w-4xl rounded-3xl border shadow-2xl p-6 md:p-8 space-y-6 overflow-hidden ${
          isDark ? 'bg-[#0B1120] border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-700/40">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                Multi-Version Sandbox Migration
              </span>
              <span className="text-xs text-slate-400">• Automated Healing & Diff Table</span>
            </div>
            <h2 className="font-heading font-bold text-2xl tracking-tight">
              Migrate Deck & Re-Verify Snippets
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Current vs New Version */}
        <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="text-center sm:text-left">
              <div className="text-xs text-slate-400">Current Pinned Runtime</div>
              <div className="font-mono font-bold text-base text-slate-200">
                {currentTech} {currentVersion || 'Legacy'}
              </div>
            </div>
            <ArrowRight className="w-5 h-5 text-purple-400" />
            <div className="text-center sm:text-left">
              <div className="text-xs text-slate-400">Target Upgrade Version</div>
              <input
                type="text"
                value={newVersion}
                onChange={(e) => setNewVersion(e.target.value)}
                placeholder="e.g. 21, 3.4, latest"
                disabled={loading}
                className={`p-2 rounded-lg border font-mono font-bold text-sm w-36 transition-colors ${
                  isDark ? 'bg-black border-slate-700 text-purple-300' : 'bg-white border-slate-300 text-purple-700'
                }`}
              />
            </div>
          </div>

          <button
            onClick={handleMigrate}
            disabled={loading}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold text-xs flex items-center space-x-2 shadow-lg shadow-purple-500/20 disabled:opacity-50"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Running Sandbox & Healing...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>Run Migration Pipeline</span>
              </>
            )}
          </button>
        </div>

        {errorMsg && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-400">
            {errorMsg}
          </div>
        )}

        {/* Diff Table */}
        {result && (
          <div className="space-y-4 max-h-[42vh] overflow-y-auto pr-1">
            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-400 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckCircle className="w-4 h-4" />
                <span>
                  Successfully migrated to {result.to_version}! {result.diff_table.length} snippet(s) updated.
                </span>
              </div>
            </div>

            {result.diff_table.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400 rounded-xl border border-slate-800 bg-slate-900/40">
                All snippets are fully compatible with {result.to_version}. Zero code changes were needed.
              </div>
            ) : (
              <div className="space-y-3">
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Migration Changes & Verification Proof
                </span>
                {result.diff_table.map((entry, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-purple-400">
                        Slide {entry.slide_id} · Snippet {entry.snippet_id}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400">
                        {entry.status}
                      </span>
                    </div>

                    <div className="text-slate-300">
                      <span className="font-bold text-slate-400">Reason: </span>
                      {entry.reason}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px] pt-1">
                      <div className="space-y-1">
                        <span className="text-rose-400 font-bold">Previous:</span>
                        <pre className="p-2.5 rounded bg-black/60 font-mono text-slate-300 overflow-x-auto max-h-28">
                          {entry.old_code}
                        </pre>
                      </div>

                      <div className="space-y-1">
                        <span className="text-emerald-400 font-bold">Migrated & Verified:</span>
                        <pre className="p-2.5 rounded bg-black/60 font-mono text-emerald-300 overflow-x-auto max-h-28">
                          {entry.new_code}
                        </pre>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
