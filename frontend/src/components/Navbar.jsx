import React from 'react';
import {
  Presentation,
  Sun,
  Moon,
  LogOut,
  ShieldAlert,
  GraduationCap,
  Sparkles,
  School,
} from 'lucide-react';

export default function Navbar({
  theme,
  onToggleTheme,
  hasDeck,
  onOpenLiveMode,
  onOpenHistory,
  user,
  institute,
  onLogout,
}) {
  const isDark = theme === 'dark';

  const getRoleBadge = (role) => {
    switch (role) {
      case 'admin':
        return {
          label: 'Admin',
          classes: 'bg-rose-500/10 text-rose-400 border-rose-500/30',
          icon: ShieldAlert,
        };
      case 'trainer':
        return {
          label: 'Trainer',
          classes: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
          icon: Sparkles,
        };
      case 'student':
        return {
          label: 'Student',
          classes: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
          icon: GraduationCap,
        };
      default:
        return {
          label: role || 'User',
          classes: 'bg-gray-500/10 text-gray-400 border-gray-500/30',
          icon: GraduationCap,
        };
    }
  };

  const roleMeta = user ? getRoleBadge(user.role) : null;
  const RoleIcon = roleMeta ? roleMeta.icon : null;

  return (
    <header className={`border-b sticky top-0 z-40 backdrop-blur-md transition-colors duration-200 ${
      isDark
        ? 'border-gray-800 bg-[#0B0F19]/80 text-white'
        : 'border-gray-200 bg-white/90 text-gray-900 shadow-sm'
    }`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand / Logo */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white">
            <Presentation className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="font-heading font-bold text-lg tracking-tight leading-tight">
                Verified Course Material Studio
              </h1>
              {institute && (
                <span className="hidden sm:inline-flex items-center space-x-1 text-[11px] font-semibold px-2 py-0.5 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <School className="w-3 h-3" />
                  <span>{institute.name || institute.short_name}</span>
                </span>
              )}
            </div>
            <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              Minimal-Text Branded Coding Decks with Guaranteed Zero-Overlap
            </p>
          </div>
        </div>

        {/* Right Actions: User Role, History, Live Mode, Theme, Logout */}
        <div className="flex items-center space-x-2 sm:space-x-3">
          {/* User Profile Pill */}
          {user && (
            <div className={`hidden md:flex items-center space-x-2 px-3 py-1.5 rounded-xl border ${
              isDark ? 'bg-gray-900/80 border-gray-800' : 'bg-gray-100 border-gray-200'
            }`}>
              <div className="text-right">
                <div className="text-xs font-bold leading-none">{user.display_name}</div>
                <div className="text-[10px] text-gray-400 mt-0.5 font-mono">{user.login_id}</div>
              </div>
              <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-md border flex items-center space-x-1 ${roleMeta.classes}`}>
                <RoleIcon className="w-3 h-3" />
                <span>{roleMeta.label}</span>
              </span>
            </div>
          )}

          {user?.role === 'trainer' && onOpenHistory && (
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

          {user?.role === 'trainer' && hasDeck && onOpenLiveMode && (
            <button
              onClick={onOpenLiveMode}
              className="hidden lg:flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/30 border border-indigo-500/40 text-indigo-400 text-xs font-semibold transition-all shadow-sm"
              title="Enter full-screen Trainer Live Class Mode"
            >
              <span>Live Class Mode</span>
            </button>
          )}

          {/* Theme Switcher */}
          <button
            onClick={onToggleTheme}
            className={`p-2 rounded-xl border text-xs font-semibold transition-all shadow-sm ${
              isDark
                ? 'bg-gray-900 border-gray-700 text-gray-200 hover:bg-gray-800 hover:border-gray-600'
                : 'bg-gray-100 border-gray-300 text-gray-700 hover:bg-gray-200 hover:border-gray-400'
            }`}
            title={`Switch to ${isDark ? 'White' : 'Black'} theme`}
          >
            {isDark ? (
              <Sun className="w-4 h-4 text-amber-400" />
            ) : (
              <Moon className="w-4 h-4 text-indigo-600" />
            )}
          </button>

          {/* Logout Button */}
          {user && onLogout && (
            <button
              onClick={onLogout}
              className={`flex items-center space-x-1 px-3 py-1.5 rounded-xl border text-xs font-semibold transition-all ${
                isDark
                  ? 'border-gray-800 hover:border-red-500/40 text-gray-400 hover:text-red-400 hover:bg-red-500/10'
                  : 'border-gray-300 hover:border-red-400 text-gray-600 hover:text-red-600 hover:bg-red-50'
              }`}
              title="Sign Out"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Logout</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
