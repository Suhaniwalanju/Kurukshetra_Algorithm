import React, { useState } from 'react';
import {
  X,
  Play,
  RefreshCw,
  Terminal,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Clock,
  Sparkles,
  BookOpen,
  HelpCircle,
  AlertTriangle,
} from 'lucide-react';

export default function LiveClassModeModal({
  deck,
  materials,
  onClose,
  theme,
}) {
  const isDark = theme === 'dark';
  const [slideIndex, setSlideIndex] = useState(0);
  const [running, setRunning] = useState(false);
  const [liveOutput, setLiveOutput] = useState('');
  const [showFallback, setShowFallback] = useState(false);
  const [showDrawer, setShowDrawer] = useState(true);

  if (!deck || !deck.slides || deck.slides.length === 0) return null;

  const currentSlide = deck.slides[slideIndex];
  const slideCount = deck.slides.length;
  const currentPreview = deck.preview_paths && deck.preview_paths[slideIndex]
    ? `http://localhost:8000${deck.preview_paths[slideIndex]}`
    : null;

  const profNote = materials?.professor_notes?.[slideIndex] || null;

  // Extract snippet code if present
  let codeSnippet = '';
  if (currentSlide.code) {
    if (typeof currentSlide.code === 'string') {
      codeSnippet = currentSlide.code;
    } else if (currentSlide.code.source) {
      codeSnippet = currentSlide.code.source;
    }
  }

  const handleRunSnippet = async () => {
    if (!codeSnippet) return;
    setRunning(true);
    setLiveOutput('');
    setShowFallback(false);

    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deck.id}/live/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          slide_id: currentSlide.id,
          code: codeSnippet,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setLiveOutput(data.stdout || data.stderr || '(Process completed with 0 output)');
      } else {
        const err = await res.json();
        setLiveOutput(`Error: ${err.detail || 'Execution failed'}`);
      }
    } catch (e) {
      console.error(e);
      setLiveOutput('Sandbox execution network error');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#050811] text-white">
      {/* Top Bar */}
      <div className="h-14 px-6 border-b border-slate-800 flex items-center justify-between bg-slate-950/80 backdrop-blur-md">
        <div className="flex items-center space-x-3">
          <span className="px-2.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center space-x-1">
            <Terminal className="w-3 h-3" />
            <span>Live Class Trainer Mode</span>
          </span>
          <span className="text-xs font-semibold text-slate-300 truncate max-w-md">
            {deck.topic} • {deck.tech} {deck.tech_version}
          </span>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5 text-xs text-slate-400 font-mono">
            <span>Slide</span>
            <span className="font-bold text-white">{slideIndex + 1}</span>
            <span>of</span>
            <span>{slideCount}</span>
          </div>

          <button
            onClick={() => setShowDrawer(!showDrawer)}
            className="px-3 py-1 rounded-lg text-xs font-semibold border border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 transition-colors"
          >
            {showDrawer ? 'Hide Talking Points' : 'Show Talking Points'}
          </button>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Main Presentation Stage */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: High-Res Slide Canvas */}
        <div className="flex-1 flex flex-col justify-between p-6 overflow-hidden">
          <div className="flex-1 relative flex items-center justify-center bg-black/40 rounded-2xl border border-slate-800/80 overflow-hidden shadow-2xl">
            {currentPreview ? (
              <img
                src={currentPreview}
                alt={`Slide ${slideIndex + 1}`}
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <div className="p-8 text-center space-y-4 max-w-lg">
                <span className="text-xs uppercase font-bold text-blue-400">{currentSlide.type}</span>
                <h3 className="font-heading font-bold text-3xl">{currentSlide.title}</h3>
                <ul className="text-left space-y-2 list-disc list-inside text-slate-300">
                  {(currentSlide.bullets || []).map((b, bi) => (
                    <li key={bi}>{b}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Bottom Slide Navigation Bar */}
          <div className="pt-4 flex items-center justify-between">
            <button
              onClick={() => setSlideIndex((p) => Math.max(0, p - 1))}
              disabled={slideIndex === 0}
              className="px-4 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold flex items-center space-x-2 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-800 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Previous Slide</span>
            </button>

            <div className="flex items-center space-x-2">
              {codeSnippet && (
                <button
                  onClick={handleRunSnippet}
                  disabled={running}
                  className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs flex items-center space-x-2 shadow-lg shadow-emerald-500/25 transition-all disabled:opacity-50"
                >
                  {running ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Executing in Pinned Sandbox...</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-4 h-4 fill-white" />
                      <span>Run Snippet Live</span>
                    </>
                  )}
                </button>
              )}

              {profNote?.fallback_output && (
                <button
                  onClick={() => setShowFallback(!showFallback)}
                  className="px-4 py-2 rounded-xl bg-slate-900 border border-amber-500/30 text-amber-400 hover:bg-slate-800 text-xs font-semibold flex items-center space-x-1.5 transition-colors"
                >
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>{showFallback ? 'Hide Fallback' : 'Show Fallback Output'}</span>
                </button>
              )}
            </div>

            <button
              onClick={() => setSlideIndex((p) => Math.min(slideCount - 1, p + 1))}
              disabled={slideIndex === slideCount - 1}
              className="px-4 py-2 rounded-xl bg-slate-900 border border-slate-800 text-xs font-semibold flex items-center space-x-2 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-800 transition-colors"
            >
              <span>Next Slide</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Right Drawer: Live Console & Professor Talking Points */}
        {showDrawer && (
          <div className="w-96 border-l border-slate-800 bg-slate-950 p-6 flex flex-col justify-between space-y-6 overflow-y-auto">
            {/* Live Terminal Output */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold uppercase tracking-wider text-slate-400 flex items-center space-x-1">
                  <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Live Sandbox Output</span>
                </span>
                {liveOutput && (
                  <button
                    onClick={() => setLiveOutput('')}
                    className="text-[10px] text-slate-500 hover:text-slate-300"
                  >
                    Clear
                  </button>
                )}
              </div>

              <pre className="p-3.5 rounded-xl bg-black border border-slate-800 text-xs font-mono text-emerald-300 min-h-[120px] max-h-48 overflow-x-auto leading-relaxed">
                {liveOutput || '(Click "Run Snippet Live" to execute in sandbox)'}
              </pre>

              {/* Pre-captured Fallback Output */}
              {showFallback && profNote?.fallback_output && (
                <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs space-y-1">
                  <div className="font-bold text-amber-300">Pre-Captured Fallback Output:</div>
                  <pre className="font-mono text-amber-200 overflow-x-auto">
                    {profNote.fallback_output}
                  </pre>
                </div>
              )}
            </div>

            {/* Professor Notes for this slide */}
            <div className="flex-1 space-y-4 pt-4 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <span className="text-xs uppercase font-bold text-indigo-400 tracking-wider flex items-center space-x-1">
                  <BookOpen className="w-3.5 h-3.5" />
                  <span>Instructor Notes</span>
                </span>
                {profNote?.timing_minutes && (
                  <span className="text-[11px] text-slate-400 flex items-center space-x-1">
                    <Clock className="w-3 h-3 text-indigo-400" />
                    <span>~{profNote.timing_minutes} mins</span>
                  </span>
                )}
              </div>

              {profNote ? (
                <div className="space-y-3 text-xs text-slate-300">
                  <div className="space-y-1">
                    <span className="font-bold text-slate-400">Key Talking Points:</span>
                    <ul className="space-y-1 list-disc list-inside">
                      {profNote.talking_points.map((tp, i) => (
                        <li key={i}>{tp}</li>
                      ))}
                    </ul>
                  </div>

                  {profNote.likely_questions && profNote.likely_questions.length > 0 && (
                    <div className="space-y-1 pt-2">
                      <span className="font-bold text-indigo-300">Likely Student Q:</span>
                      <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-[11px]">
                        <div>Q: {profNote.likely_questions[0].question}</div>
                        <div className="text-slate-400 mt-1">A: {profNote.likely_questions[0].answer}</div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-xs text-slate-500 italic">
                  Generate supporting materials to view talking points and student mistake predictions.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
