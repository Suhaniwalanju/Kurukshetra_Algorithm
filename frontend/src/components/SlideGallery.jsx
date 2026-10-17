import React, { useState, useEffect } from 'react';
import {
  Download,
  Code2,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  CheckCircle,
  CheckCircle2,
  ShieldCheck,
  RefreshCw,
  Sparkles,
  Terminal,
} from 'lucide-react';
import VerificationReportPanel from './VerificationReportPanel';
import SupportingMaterialsView from './SupportingMaterialsView';
import ExercisesSection from './ExercisesSection';

export default function SlideGallery({
  deck,
  onDownload,
  theme,
  isApproved,
  onApprove,
  onOpenExport,
  onOpenRegenerate,
  onOpenMigration,
  onOpenLiveMode,
}) {
  const isDark = theme === 'dark';
  const [selectedSlideIndex, setSelectedSlideIndex] = useState(0);
  const [fullscreenImage, setFullscreenImage] = useState(null);

  // Keyboard navigation (Left / Right arrow keys)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'ArrowLeft') {
        setSelectedSlideIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === 'ArrowRight') {
        setSelectedSlideIndex((prev) => Math.min((deck?.slides?.length || 1) - 1, prev + 1));
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [deck?.slides?.length]);

  if (!deck || !deck.slides || deck.slides.length === 0) return null;

  const currentSlide = deck.slides[selectedSlideIndex] || deck.slides[0];
  const currentPreviewUrl = deck.preview_paths && deck.preview_paths[selectedSlideIndex]
    ? `http://localhost:8000${deck.preview_paths[selectedSlideIndex]}`
    : null;

  return (
    <div className="space-y-8 animate-in fade-in">
      {/* Deck Header & Actions */}
      <div className={`rounded-2xl p-6 border flex flex-col md:flex-row md:items-center justify-between gap-4 transition-colors duration-200 shadow-xl ${
        isDark ? 'bg-[#111827]/90 border-gray-800 text-white' : 'bg-white border-gray-200 text-gray-900 shadow-md'
      }`}>
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 flex items-center space-x-1">
              <CheckCircle className="w-3 h-3" />
              <span>Layout & Bounds Verified</span>
            </span>
            <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              • {deck.slides.length} Slides Generated
            </span>
          </div>
          <h2 className="font-heading font-bold text-2xl tracking-tight mt-1">
            {deck.topic}
          </h2>
          <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Presented By <span className={`font-semibold ${isDark ? 'text-white' : 'text-gray-900'}`}>{deck.professor_name}</span> • {deck.college} • {deck.tech} {deck.tech_version}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {!isApproved && onApprove && (
            <button
              onClick={onApprove}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-emerald-500/20 transition-all transform hover:scale-[1.02]"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Approve Deck</span>
            </button>
          )}

          {onOpenLiveMode && (
            <button
              onClick={onOpenLiveMode}
              className="px-3.5 py-2.5 rounded-xl border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 font-semibold text-xs flex items-center space-x-1.5 transition-all"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Live Class Mode</span>
            </button>
          )}

          {onOpenMigration && (
            <button
              onClick={onOpenMigration}
              className={`px-3.5 py-2.5 rounded-xl font-semibold text-xs flex items-center space-x-1.5 border transition-all ${
                isDark
                  ? 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'
                  : 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-800'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>Migrate</span>
            </button>
          )}

          {onOpenExport ? (
            <button
              onClick={onOpenExport}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 text-white font-semibold text-xs flex items-center space-x-1.5 shadow-xl shadow-blue-500/25 transition-all"
            >
              <Download className="w-4 h-4" />
              <span>Export All</span>
            </button>
          ) : (
            <button
              onClick={onDownload}
              className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 text-white font-semibold text-xs flex items-center space-x-1.5 shadow-xl shadow-blue-500/25 transition-all"
            >
              <Download className="w-4 h-4" />
              <span>Download .PPTX</span>
            </button>
          )}
        </div>
      </div>

      {/* Collapsible Verification Report Panel */}
      <VerificationReportPanel
        deckId={deck.id}
        theme={theme}
        isApproved={isApproved}
        onApprove={onApprove}
      />

      {/* Main Slide Stage + Metadata Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: High-Res Slide Preview Canvas */}
        <div className={`lg:col-span-2 rounded-2xl p-5 border flex flex-col justify-between shadow-2xl transition-colors duration-200 ${
          isDark ? 'bg-[#0F172A]/90 border-slate-800' : 'bg-white border-slate-200 shadow-md'
        }`}>
          {/* Authentic Studio Presentation Canvas */}
          <div className="relative rounded-2xl overflow-hidden bg-slate-100 dark:bg-[#080D1A] border border-slate-200 dark:border-slate-800/80 p-3 sm:p-4 flex items-center justify-center shadow-inner">
            <div className="relative w-full aspect-video rounded-xl overflow-hidden shadow-[0_14px_40px_rgba(0,0,0,0.12)] dark:shadow-[0_20px_50px_rgba(0,0,0,0.7)] border border-slate-200/90 dark:border-slate-700/70 bg-white group flex items-center justify-center">
              {currentPreviewUrl ? (
                <img
                  src={currentPreviewUrl}
                  alt={`Slide ${currentSlide.id} Preview`}
                  className="w-full h-full object-contain"
                />
              ) : (
                <div className="text-slate-400 text-sm animate-pulse">Rendering high-resolution slide preview...</div>
              )}

              {/* Quick Enlarge Overlay Button */}
              {currentPreviewUrl && (
                <button
                  onClick={() => setFullscreenImage(currentPreviewUrl)}
                  className="absolute top-3 right-3 px-2.5 py-1.5 rounded-xl bg-black/60 hover:bg-black/80 text-white/90 hover:text-white backdrop-blur-md opacity-0 group-hover:opacity-100 transition-all text-xs flex items-center space-x-1.5 shadow-lg"
                  title="View Full Resolution (Fullscreen)"
                >
                  <Maximize2 className="w-3.5 h-3.5" />
                  <span>Expand</span>
                </button>
              )}
            </div>
          </div>

          {/* Slide Navigation controls */}
          <div className="flex items-center justify-between pt-4 px-1">
            <button
              onClick={() => setSelectedSlideIndex((prev) => Math.max(0, prev - 1))}
              disabled={selectedSlideIndex === 0}
              className={`px-3.5 py-2 rounded-xl border text-xs font-semibold flex items-center space-x-1.5 disabled:opacity-35 disabled:cursor-not-allowed transition-all ${
                isDark
                  ? 'bg-slate-900 border-slate-800 text-slate-200 hover:bg-slate-800 hover:border-slate-700'
                  : 'bg-slate-100 border-slate-300 text-slate-700 hover:bg-slate-200 hover:border-slate-400'
              }`}
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Previous</span>
              <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono rounded bg-black/10 dark:bg-white/10 text-slate-400">←</kbd>
            </button>

            <div className="flex items-center space-x-2">
              <span className={`text-xs font-mono font-medium ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Slide <span className={`font-bold ${isDark ? 'text-white' : 'text-slate-900'}`}>{selectedSlideIndex + 1}</span> of {deck.slides.length}
              </span>
              <div className="hidden sm:flex items-center space-x-1 pl-2">
                {deck.slides.map((_, i) => (
                  <button
                    key={i}
                    onClick={() => setSelectedSlideIndex(i)}
                    className={`w-2 h-2 rounded-full transition-all ${
                      selectedSlideIndex === i
                        ? 'w-5 bg-blue-600'
                        : isDark
                        ? 'bg-slate-800 hover:bg-slate-700'
                        : 'bg-slate-300 hover:bg-slate-400'
                    }`}
                  />
                ))}
              </div>
            </div>

            <button
              onClick={() => setSelectedSlideIndex((prev) => Math.min(deck.slides.length - 1, prev + 1))}
              disabled={selectedSlideIndex === deck.slides.length - 1}
              className={`px-3.5 py-2 rounded-xl border text-xs font-semibold flex items-center space-x-1.5 disabled:opacity-35 disabled:cursor-not-allowed transition-all ${
                isDark
                  ? 'bg-slate-900 border-slate-800 text-slate-200 hover:bg-slate-800 hover:border-slate-700'
                  : 'bg-slate-100 border-slate-300 text-slate-700 hover:bg-slate-200 hover:border-slate-400'
              }`}
            >
              <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono rounded bg-black/10 dark:bg-white/10 text-slate-400">→</kbd>
              <span>Next</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Right: Slide Inspector & Code Details */}
        <div className={`rounded-2xl p-6 border space-y-5 overflow-y-auto max-h-[620px] transition-colors duration-200 ${
          isDark ? 'bg-[#111827]/90 border-gray-800 text-white' : 'bg-white border-gray-200 text-gray-900 shadow-md'
        }`}>
          <div>
            <span className="px-2.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
              {currentSlide.type} Slide
            </span>
            <h3 className="font-heading font-bold text-lg mt-1">
              {currentSlide.title || 'Untitled Slide'}
            </h3>
            <span className={`text-[11px] font-mono ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Words in title: {(currentSlide.title || '').trim().split(/\s+/).filter(Boolean).length} / 8 max
            </span>
          </div>

          {/* Bullets Inspector with Word Count Tags */}
          <div className="space-y-2">
            <h4 className={`text-xs font-semibold uppercase tracking-wider ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              Bullet Points ({(currentSlide.bullets || []).length} / 5 max)
            </h4>
            <div className="space-y-2">
              {(currentSlide.bullets || []).map((b, idx) => {
                const wordCount = (b || '').trim().split(/\s+/).filter(Boolean).length;
                return (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-xl border flex items-start justify-between text-xs transition-colors ${
                      isDark ? 'bg-gray-900/80 border-gray-800 text-gray-200' : 'bg-gray-50 border-gray-200 text-gray-800'
                    }`}
                  >
                    <span className="pr-2">{b}</span>
                    <span className="shrink-0 px-1.5 py-0.5 rounded text-[10px] font-mono bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
                      {wordCount} words
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Code Snippet with Expected Output */}
          {(() => {
            if (!currentSlide.code) return null;
            const codeSource = typeof currentSlide.code === 'string' ? currentSlide.code : currentSlide.code?.source;
            const codeLang = (typeof currentSlide.code === 'object' && currentSlide.code?.language) ? currentSlide.code.language : (deck.tech || 'CODE');
            const expectedOut = typeof currentSlide.code === 'object' ? currentSlide.code?.expected_output : null;
            if (!codeSource) return null;

            return (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className={`text-xs font-semibold uppercase tracking-wider flex items-center space-x-1.5 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                    <Code2 className="w-3.5 h-3.5 text-blue-500" />
                    <span>Code Block ({(codeLang || 'CODE').toUpperCase()})</span>
                  </h4>
                  {currentSlide.imports_omitted && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-purple-500/15 text-purple-400 border border-purple-500/30">
                      * imports omitted
                    </span>
                  )}
                </div>
                <div className="p-3.5 rounded-xl bg-[#090D16] border border-gray-800 font-mono text-xs space-y-3">
                  <pre className="text-blue-300 overflow-x-auto leading-relaxed">
                    {codeSource}
                  </pre>
                  {expectedOut && (
                    <div className="pt-2 border-t border-gray-800 text-[11px]">
                      <span className="text-emerald-400 font-bold">Expected Output: </span>
                      <span className="text-gray-300">{expectedOut}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}

          {/* Trainer Notes with Full Runnable Version */}
          {currentSlide.trainer_notes && (
            <div className="p-3.5 rounded-xl bg-purple-950/20 border border-purple-500/30 text-xs space-y-1.5">
              <span className="text-purple-400 font-semibold block text-[11px] uppercase tracking-wider">
                Trainer Notes (Full Runnable Version):
              </span>
              <pre className="p-2.5 rounded-lg bg-black/40 font-mono text-[11px] text-purple-200 overflow-x-auto whitespace-pre-wrap leading-relaxed border border-purple-500/20">
                {currentSlide.trainer_notes}
              </pre>
            </div>
          )}

          {/* Speaker Hint */}
          {currentSlide.speaker_hint && (
            <div className="p-3 rounded-xl bg-purple-500/5 border border-purple-500/20 text-xs">
              <span className="text-purple-600 dark:text-purple-400 font-semibold block mb-0.5">Speaker Hint:</span>
              <p className={`italic ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>{currentSlide.speaker_hint}</p>
            </div>
          )}

          {/* Quick Single Slide Regenerate Button */}
          {onOpenRegenerate && (
            <div className="pt-2">
              <button
                onClick={() => onOpenRegenerate(selectedSlideIndex)}
                className="w-full py-2.5 px-3 rounded-xl border border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 text-xs font-semibold flex items-center justify-center space-x-1.5 transition-colors"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Regenerate Slide {selectedSlideIndex + 1} Only</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Thumbnail Strip Gallery */}
      <div className={`rounded-2xl p-6 border space-y-4 transition-colors duration-200 ${
        isDark ? 'bg-[#111827]/90 border-gray-800' : 'bg-white border-gray-200 shadow-md'
      }`}>
        <div className="flex items-center justify-between">
          <h3 className="font-heading font-bold text-base">
            Slide Thumbnail Gallery ({deck.slides.length} Slides)
          </h3>
          <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Click any slide to inspect</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          {deck.slides.map((s, idx) => {
            const previewUrl = deck.preview_paths && deck.preview_paths[idx]
              ? `http://localhost:8000${deck.preview_paths[idx]}`
              : null;
            const isSelected = selectedSlideIndex === idx;

            return (
              <button
                key={s.id}
                onClick={() => setSelectedSlideIndex(idx)}
                className={`relative rounded-xl overflow-hidden aspect-video border transition-all text-left group ${
                  isSelected
                    ? 'border-blue-500 ring-2 ring-blue-500/40 scale-105 z-10 shadow-xl'
                    : isDark
                    ? 'border-gray-800 hover:border-gray-600 opacity-75 hover:opacity-100'
                    : 'border-gray-200 hover:border-gray-400 opacity-80 hover:opacity-100'
                }`}
              >
                {previewUrl ? (
                  <img src={previewUrl} alt={`Slide ${s.id}`} className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full bg-gray-900 flex items-center justify-center text-xs text-gray-500">
                    Slide {s.id}
                  </div>
                )}
                <div className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/70 backdrop-blur-sm text-[10px] font-mono text-white">
                  #{s.id}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Hands-On Coding Exercises Section (Easy, Medium, Stretch) */}
      <ExercisesSection deck={deck} theme={theme} />

      {/* Phase 3: Supporting Materials View (Student Notes, Professor Notes, Quiz, Cheat Sheet) */}
      <SupportingMaterialsView
        deckId={deck.id}
        theme={theme}
        isApproved={isApproved}
        onApprove={onApprove}
        onOpenExport={onOpenExport}
        onOpenRegenerate={() => onOpenRegenerate && onOpenRegenerate(selectedSlideIndex)}
        onOpenMigration={onOpenMigration}
        onOpenLiveMode={onOpenLiveMode}
      />

      {/* Fullscreen Image Lightbox Modal */}
      {fullscreenImage && (
        <div
          onClick={() => setFullscreenImage(null)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/95 backdrop-blur-md cursor-zoom-out animate-in fade-in"
        >
          <img
            src={fullscreenImage}
            alt="Fullscreen Slide"
            className="max-w-[95vw] max-h-[95vh] object-contain rounded-xl shadow-2xl"
          />
        </div>
      )}
    </div>
  );
}
