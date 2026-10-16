import React from 'react';
import { Presentation, Sun, Moon } from 'lucide-react';

export default function Navbar({
  theme,
  onToggleTheme,
  hasDeck,
  onOpenLiveMode,
  onOpenHistory,
}) {
  const isDark = theme === 'dark';

  return (
    <header className={`border-b sticky top-0 z-40 backdrop-blur-md transition-colors duration-200 ${
      isDark
        ? 'border-gray-800 bg-[#0B0F19]/80 text-white'
        : 'border-gray-200 bg-white/90 text-gray-900 shadow-sm'
    }`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand / Logo */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Presentation className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-heading font-bold text-lg tracking-tight leading-tight">
              Verified Course Material Studio
            </h1>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Minimal-Text Branded Coding Decks with Guaranteed Zero-Overlap
            </p>
          </div>
        </div>

        {/* Right Actions: History, Live Mode, Theme Switcher */}
        <div className="flex items-center space-x-2.5">
          {onOpenHistory && (
            <button
              onClick={onOpenHistory}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all shadow-sm ${
                isDark
                  ? 'bg-slate-900 border-slate-700 text-slate-200 hover:bg-slate-800'
                  : 'bg-slate-100 border-slate-300 text-slate-700 hover:bg-slate-200'
              }`}
              title="Open past generated decks"
            >
              <span>History</span>
            </button>
          )}

          {hasDeck && onOpenLiveMode && (
            <button
              onClick={onOpenLiveMode}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-indigo-400 text-xs font-semibold transition-all shadow-sm"
              title="Enter full-screen Trainer Live Class Mode"
            >
              <span>Live Class Mode</span>
            </button>
          )}

          <button
            onClick={onToggleTheme}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all shadow-sm ${
              isDark
                ? 'bg-gray-900 border-gray-700 text-gray-200 hover:bg-gray-800 hover:border-gray-600'
                : 'bg-gray-100 border-gray-300 text-gray-700 hover:bg-gray-200 hover:border-gray-400'
            }`}
            title={`Switch to ${isDark ? 'White' : 'Black'} theme`}
          >
            {isDark ? (
              <>
                <Sun className="w-4 h-4 text-amber-400" />
                <span>Light</span>
              </>
            ) : (
              <>
                <Moon className="w-4 h-4 text-indigo-600" />
                <span>Dark</span>
              </>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
