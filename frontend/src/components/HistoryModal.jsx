import React, { useState, useEffect } from 'react';
import {
  X,
  History,
  Presentation,
  CheckCircle,
  Clock,
  Sparkles,
  ExternalLink,
  BookOpen,
  Calendar,
} from 'lucide-react';

export default function HistoryModal({
  onSelectDeck,
  onClose,
  theme,
}) {
  const isDark = theme === 'dark';
  const [decks, setDecks] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchDecks();
  }, []);

  const fetchDecks = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/decks');
      if (res.ok) {
        const data = await res.json();
        setDecks(data || []);
      }
    } catch (e) {
      console.error('Failed to load past decks:', e);
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
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20 flex items-center space-x-1">
                <History className="w-3.5 h-3.5" />
                <span>Deck Repository</span>
              </span>
              <span className="text-xs text-slate-400">• Persistent Studio History</span>
            </div>
            <h2 className="font-heading font-bold text-2xl tracking-tight">
              Previously Generated Decks
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Deck List */}
        <div className="space-y-3 max-h-[55vh] overflow-y-auto pr-1">
          {loading ? (
            <div className="p-8 text-center text-sm text-slate-400 animate-pulse">
              Loading decks from studio database...
            </div>
          ) : decks.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400 border border-slate-800 rounded-2xl bg-slate-900/40">
              No decks found. Generate your first minimal-text verified coding deck!
            </div>
          ) : (
            decks.map((d) => (
              <div
                key={d.id}
                className={`p-4 rounded-2xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                  isDark
                    ? 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
                    : 'bg-slate-50 border-slate-200 hover:border-slate-300 hover:bg-white'
                }`}
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex items-center flex-wrap gap-2">
                    <span className="px-2.5 py-0.5 rounded-md text-[10px] font-bold uppercase bg-blue-500/20 text-blue-400 border border-blue-500/30">
                      {d.tech} {d.tech_version}
                    </span>
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                      {d.college}
                    </span>
                    {d.verified && (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 flex items-center space-x-1">
                        <CheckCircle className="w-2.5 h-2.5" />
                        <span>Verified</span>
                      </span>
                    )}
                    {d.approved ? (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-teal-500/20 text-teal-300">
                        Approved
                      </span>
                    ) : (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/20 text-amber-300">
                        Pending Approval
                      </span>
                    )}
                    {d.materials_status === 'ready' && (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-500/20 text-purple-300 flex items-center space-x-1">
                        <BookOpen className="w-2.5 h-2.5" />
                        <span>Materials Ready</span>
                      </span>
                    )}
                  </div>

                  <h3 className="font-heading font-bold text-base text-slate-100 truncate">
                    {d.topic}
                  </h3>

                  <div className="flex items-center space-x-3 text-xs text-slate-400">
                    <span>Prof. {d.professor_name}</span>
                    <span>•</span>
                    <span>{d.student_level || 'Beginner'}</span>
                    <span>•</span>
                    <span>{d.session_length || 30} mins</span>
                    {d.created_at && (
                      <>
                        <span>•</span>
                        <span className="flex items-center space-x-1">
                          <Calendar className="w-3 h-3" />
                          <span>{new Date(d.created_at).toLocaleDateString()}</span>
                        </span>
                      </>
                    )}
                  </div>
                </div>

                <button
                  onClick={() => {
                    onSelectDeck(d.id);
                    onClose();
                  }}
                  className="px-4 py-2.5 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 hover:text-blue-300 border border-blue-500/30 font-semibold text-xs flex items-center space-x-1.5 shrink-0 transition-colors"
                >
                  <span>Open Deck</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
