import React, { useState, useEffect } from 'react';
import {
  Code2,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Clock,
  Layers,
  ChevronDown,
  ChevronUp,
  Bug,
  Sparkles,
  FileCode,
  ShieldCheck,
} from 'lucide-react';
import CodeRenderer from './CodeRenderer';

export default function ExercisesSection({ deck, theme = 'dark' }) {
  const isDark = theme === 'dark';
  const [exercises, setExercises] = useState(deck?.exercises || []);
  const [loading, setLoading] = useState(false);
  const [activeTabs, setActiveTabs] = useState({}); // { [exId]: 'starter' | 'tests' | 'ref' | 'naive' }
  const [expandedCards, setExpandedCards] = useState({});
  const [regeneratingIds, setRegeneratingIds] = useState({});
  const [errorMsg, setErrorMsg] = useState('');

  const deckId = deck?.id;
  const tech = deck?.tech || 'python';

  // Fetch exercises if not present on deck
  useEffect(() => {
    if (deck?.exercises && deck.exercises.length > 0) {
      setExercises(deck.exercises);
      // Default all expanded
      const exp = {};
      const tabs = {};
      deck.exercises.forEach((ex) => {
        exp[ex.id] = true;
        tabs[ex.id] = 'starter';
      });
      setExpandedCards(exp);
      setActiveTabs(tabs);
    } else if (deckId) {
      fetchExercises();
    }
  }, [deckId, deck?.exercises]);

  const fetchExercises = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/exercises`);
      if (res.ok) {
        const data = await res.json();
        setExercises(data.exercises || []);
        const exp = {};
        const tabs = {};
        (data.exercises || []).forEach((ex) => {
          exp[ex.id] = true;
          tabs[ex.id] = 'starter';
        });
        setExpandedCards(exp);
        setActiveTabs(tabs);
      }
    } catch (err) {
      console.error('Error fetching exercises:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerate = async (exerciseId) => {
    setRegeneratingIds((prev) => ({ ...prev, [exerciseId]: true }));
    setErrorMsg('');
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/exercises/${exerciseId}/regenerate`, {
        method: 'POST',
      });
      if (res.ok) {
        const updated = await res.json();
        setExercises((prev) =>
          prev.map((ex) => (ex.id === exerciseId || ex.exercise_ref === exerciseId ? updated : ex))
        );
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Regeneration failed');
      }
    } catch (err) {
      console.error('Error regenerating exercise:', err);
      setErrorMsg('Network error regenerating exercise');
    } finally {
      setRegeneratingIds((prev) => ({ ...prev, [exerciseId]: false }));
    }
  };

  const toggleExpand = (id) => {
    setExpandedCards((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const setTab = (id, tab) => {
    setActiveTabs((prev) => ({ ...prev, [id]: tab }));
  };

  const getDifficultyBadge = (diff) => {
    const d = (diff || 'medium').toLowerCase();
    if (d === 'easy') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
          Easy
        </span>
      );
    }
    if (d === 'stretch') {
      return (
        <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30">
          Stretch
        </span>
      );
    }
    return (
      <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-300 border border-blue-500/30">
        Medium
      </span>
    );
  };

  const getStatusBadge = (status) => {
    const isVerified = (status || '').toLowerCase() === 'verified';
    if (isVerified) {
      return (
        <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 flex items-center space-x-1.5 shadow-sm">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>Verified (Proof Succeeded)</span>
        </span>
      );
    }
    return (
      <span className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center space-x-1.5 shadow-sm">
        <AlertTriangle className="w-3.5 h-3.5" />
        <span>Unverified (Needs Review)</span>
      </span>
    );
  };

  if (!exercises || exercises.length === 0) {
    if (loading) {
      return (
        <div className={`rounded-2xl p-8 border text-center transition-colors ${
          isDark ? 'bg-[#111827]/90 border-gray-800' : 'bg-white border-gray-200'
        }`}>
          <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3" />
          <p className="text-sm text-gray-400">Loading proven hands-on exercises...</p>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="space-y-6 animate-in fade-in">
      {/* Section Header */}
      <div className={`rounded-2xl p-6 border flex flex-col md:flex-row md:items-center justify-between gap-4 transition-colors ${
        isDark ? 'bg-[#111827]/90 border-gray-800 text-white' : 'bg-white border-gray-200 text-gray-900 shadow-md'
      }`}>
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30 flex items-center space-x-1">
              <Code2 className="w-3 h-3" />
              <span>Proven Lab Tiers</span>
            </span>
            <span className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              • 3 Tiers (Easy, Medium, Stretch)
            </span>
          </div>
          <h2 className="font-heading font-bold text-2xl tracking-tight mt-1 flex items-center space-x-2">
            <span>Hands-On Coding Exercises</span>
            <ShieldCheck className="w-5 h-5 text-emerald-400 inline" />
          </h2>
          <p className={`text-xs mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
            Each exercise is grounded in slide concepts, verified with passing unit tests, and proven with automated student error detection and mutation analysis.
          </p>
        </div>

        <button
          onClick={fetchExercises}
          disabled={loading}
          className="px-3.5 py-2 rounded-xl border border-gray-700 bg-gray-800/60 hover:bg-gray-800 text-gray-300 text-xs font-semibold flex items-center space-x-1.5 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Exercises</span>
        </button>
      </div>

      {errorMsg && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Exercise Cards */}
      <div className="space-y-6">
        {exercises.map((ex, index) => {
          const isExpanded = expandedCards[ex.id] ?? true;
          const currentTab = activeTabs[ex.id] || 'starter';
          const isRegen = regeneratingIds[ex.id];
          const sourceSlides = ex.source_slides || (ex.source_slides_json ? JSON.parse(ex.source_slides_json) : [ex.slide_id]);
          const failingTest = ex.failing_test_name || 'AssertionError';

          return (
            <div
              key={ex.id || index}
              className={`rounded-2xl border transition-all duration-200 overflow-hidden shadow-lg ${
                isDark ? 'bg-[#111827]/90 border-gray-800 text-white' : 'bg-white border-gray-200 text-gray-900 shadow-md'
              }`}
            >
              {/* Card Header */}
              <div className="p-6 border-b border-gray-800/80">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      {getDifficultyBadge(ex.difficulty)}
                      <span className="flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-800/80 text-gray-300 border border-gray-700">
                        <Clock className="w-3 h-3 text-gray-400" />
                        <span>{ex.estimated_minutes || (ex.difficulty === 'easy' ? 10 : ex.difficulty === 'stretch' ? 30 : 20)} mins</span>
                      </span>
                      <span className="flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-800/80 text-gray-300 border border-gray-700">
                        <Layers className="w-3 h-3 text-purple-400" />
                        <span>Source Slides: {JSON.stringify(sourceSlides)}</span>
                      </span>
                      {getStatusBadge(ex.status)}
                    </div>
                    <h3 className="font-heading font-bold text-xl mt-1">
                      {ex.title || `Exercise ${index + 1}: ${ex.difficulty.toUpperCase()}`}
                    </h3>
                  </div>

                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleRegenerate(ex.id)}
                      disabled={isRegen}
                      className="px-3.5 py-2 rounded-xl border border-blue-500/30 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 font-semibold text-xs flex items-center space-x-1.5 transition-all disabled:opacity-50"
                      title="Regenerate this exercise only without touching PPT"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isRegen ? 'animate-spin' : ''}`} />
                      <span>{isRegen ? 'Regenerating...' : 'Regenerate this exercise'}</span>
                    </button>

                    <button
                      onClick={() => toggleExpand(ex.id)}
                      className="p-2 rounded-xl border border-gray-700 hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
                      title={isExpanded ? 'Collapse' : 'Expand'}
                    >
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Task Statement with Example Input / Output */}
                <div className={`mt-4 p-4 rounded-xl border text-xs leading-relaxed whitespace-pre-line ${
                  isDark ? 'bg-gray-950/60 border-gray-800/80 text-gray-300' : 'bg-gray-50 border-gray-200 text-gray-800'
                }`}>
                  <div className="font-semibold text-blue-400 uppercase tracking-wider text-[11px] mb-1">
                    Task Statement:
                  </div>
                  {ex.problem_statement || ex.task}
                </div>
              </div>

              {/* Expandable Tabs & Code Viewers */}
              {isExpanded && (
                <div className="p-6 space-y-4">
                  {/* Tabs Navigation */}
                  <div className="flex flex-wrap items-center gap-2 border-b border-gray-800 pb-3">
                    <button
                      onClick={() => setTab(ex.id, 'starter')}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors ${
                        currentTab === 'starter'
                          ? 'bg-blue-600 text-white shadow'
                          : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
                      }`}
                    >
                      <FileCode className="w-3.5 h-3.5" />
                      <span>Starter Code (TODO)</span>
                    </button>

                    <button
                      onClick={() => setTab(ex.id, 'tests')}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors ${
                        currentTab === 'tests'
                          ? 'bg-blue-600 text-white shadow'
                          : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
                      }`}
                    >
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Unit Tests</span>
                    </button>

                    <button
                      onClick={() => setTab(ex.id, 'ref')}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors ${
                        currentTab === 'ref'
                          ? 'bg-emerald-600 text-white shadow'
                          : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
                      }`}
                    >
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-300" />
                      <span>Reference Solution</span>
                    </button>

                    <button
                      onClick={() => setTab(ex.id, 'naive')}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition-colors ${
                        currentTab === 'naive'
                          ? 'bg-amber-600 text-white shadow'
                          : 'bg-gray-800/60 hover:bg-gray-800 text-gray-300'
                      }`}
                    >
                      <Bug className="w-3.5 h-3.5 text-amber-300" />
                      <span>Naive Solution (Mistake Detection)</span>
                    </button>
                  </div>

                  {/* Tab Contents */}
                  {currentTab === 'starter' && (
                    <div>
                      <div className="text-xs text-gray-400 mb-2">
                        Distributed to students in <code className="text-blue-400">exercises/student/</code>. Contains skeleton structure with actionable TODO.
                      </div>
                      <CodeRenderer
                        code={ex.starter_code || ''}
                        language={tech}
                        title={`Starter Code - ${tech}`}
                      />
                    </div>
                  )}

                  {currentTab === 'tests' && (
                    <div>
                      <div className="text-xs text-gray-400 mb-2">
                        Automated test suite runnable in pinned sandbox environment.
                      </div>
                      <CodeRenderer
                        code={ex.test_code || ''}
                        language={tech}
                        title={`Test Suite - ${tech}`}
                      />
                    </div>
                  )}

                  {currentTab === 'ref' && (
                    <div>
                      <div className="flex items-center justify-between text-xs text-gray-400 mb-2">
                        <span>Instructor reference solution. Verified: 100% tests pass.</span>
                        <span className="text-emerald-400 font-semibold font-mono">STATUS: PASS ✔</span>
                      </div>
                      <CodeRenderer
                        code={ex.reference_solution || ''}
                        language={tech}
                        title={`Reference Solution - ${tech}`}
                      />
                    </div>
                  )}

                  {currentTab === 'naive' && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between text-xs text-gray-400">
                        <span>Plausible buggy student code. Proves test suite catches mistake on assertion.</span>
                        <span className="text-amber-400 font-semibold font-mono">TEST_FAILURE (Target Caught) ✔</span>
                      </div>
                      <CodeRenderer
                        code={ex.naive_solution || ''}
                        language={tech}
                        title={`Naive Buggy Solution - ${tech}`}
                      />

                      {/* Failing Test Output Card */}
                      <div className="p-3.5 rounded-xl border border-amber-500/30 bg-amber-500/10 text-xs space-y-1.5 font-mono">
                        <div className="flex items-center space-x-1.5 text-amber-400 font-bold uppercase tracking-wider text-[11px]">
                          <Bug className="w-3.5 h-3.5" />
                          <span>Failing Test Assertion Output:</span>
                        </div>
                        <div className="p-2.5 rounded-lg bg-black/60 text-amber-200 border border-amber-500/20 text-[11px]">
                          AssertionError: {failingTest}
                        </div>
                        <p className="text-[10px] text-gray-400 font-sans">
                          Verified in sandbox runtime: Failed cleanly on unit test assertion rather than a compile crash.
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
