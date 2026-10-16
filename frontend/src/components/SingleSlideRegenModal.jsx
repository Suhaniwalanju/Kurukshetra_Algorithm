import React, { useState } from 'react';
import {
  X,
  RefreshCw,
  Sparkles,
  CheckCircle,
  FileCode,
  Terminal,
  AlertCircle,
  ArrowRight,
} from 'lucide-react';

export default function SingleSlideRegenModal({
  deckId,
  slides = [],
  initialSlideIndex = 0,
  onClose,
  onRegenerated,
  theme,
}) {
  const isDark = theme === 'dark';
  const [slideIndex, setSlideIndex] = useState(initialSlideIndex);
  const [instruction, setInstruction] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  const handleRegenerate = async () => {
    setLoading(true);
    setErrorMsg('');
    setResult(null);

    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/slides/${slideIndex}/regenerate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction }),
      });

      if (res.ok) {
        const data = await res.json();
        setResult(data);
        if (onRegenerated) onRegenerated(data);
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Slide regeneration failed');
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
        className={`relative w-full max-w-3xl rounded-3xl border shadow-2xl p-6 md:p-8 space-y-6 overflow-hidden ${
          isDark ? 'bg-[#0B1120] border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-700/40">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                Single Slide Maintenance
              </span>
              <span className="text-xs text-slate-400">• Other Slides Byte-Identical</span>
            </div>
            <h2 className="font-heading font-bold text-2xl tracking-tight">
              Regenerate Single Slide & Snippet
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Slide Selector & Instruction */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Target Slide
            </label>
            <select
              value={slideIndex}
              onChange={(e) => setSlideIndex(parseInt(e.target.value))}
              disabled={loading}
              className={`w-full p-3 rounded-xl border text-sm font-semibold transition-colors ${
                isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
              }`}
            >
              {slides.map((s, idx) => (
                <option key={idx} value={idx}>
                  Slide {s.id || idx + 1}: {s.title}
                </option>
              ))}
            </select>
          </div>

          <div className="md:col-span-2 space-y-1.5">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Refinement Instruction (Optional)
            </label>
            <input
              type="text"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="e.g. Include timing calculation or add comments"
              disabled={loading}
              className={`w-full p-3 rounded-xl border text-sm transition-colors ${
                isDark ? 'bg-slate-900 border-slate-800 text-white placeholder-slate-500' : 'bg-slate-50 border-slate-300 text-slate-900 placeholder-slate-400'
              }`}
            />
          </div>
        </div>

        {errorMsg && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-400 flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Action Button */}
        <div className="flex justify-end">
          <button
            onClick={handleRegenerate}
            disabled={loading}
            className="px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-sm flex items-center space-x-2 shadow-lg shadow-blue-500/20 disabled:opacity-50"
          >
            {loading ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Re-verifying in Sandbox & Checking Layout...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>Regenerate Slide {slideIndex + 1}</span>
              </>
            )}
          </button>
        </div>

        {/* Results & Diff View */}
        {result && (
          <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4 max-h-[35vh] overflow-y-auto">
            <div className="flex items-center space-x-2 text-emerald-400 text-xs font-bold">
              <CheckCircle className="w-4 h-4" />
              <span>Slide {result.slide_id} Regenerated & Verified Successfully!</span>
            </div>

            {/* Bullets diff */}
            {result.diff && (
              <div className="space-y-2 text-xs">
                <span className="font-bold text-slate-400 uppercase tracking-wider">Bullet Points Diff</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                  <div className="p-2.5 rounded-lg bg-rose-500/10 border border-rose-500/20 space-y-1">
                    <span className="font-bold text-rose-400">Before:</span>
                    <ul className="list-disc list-inside text-slate-300">
                      {result.diff.bullets_before.map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 space-y-1">
                    <span className="font-bold text-emerald-400">After:</span>
                    <ul className="list-disc list-inside text-slate-300">
                      {result.diff.bullets_after.map((b, i) => (
                        <li key={i}>{b}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                {/* Code Diff */}
                {result.diff.code_diff && (
                  <div className="space-y-1 pt-2">
                    <span className="font-bold text-slate-400 uppercase tracking-wider">Unified Code Diff</span>
                    <pre className="p-3 rounded-lg bg-black text-[11px] font-mono text-slate-300 overflow-x-auto">
                      {result.diff.code_diff}
                    </pre>
                  </div>
                )}

                {/* Real output */}
                <div className="space-y-1 pt-1">
                  <span className="font-bold text-slate-400 uppercase tracking-wider">Captured Sandbox Output</span>
                  <pre className="p-2.5 rounded-lg bg-black text-[11px] font-mono text-emerald-400">
                    {result.diff.captured_output || '(Clean run 0)'}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
