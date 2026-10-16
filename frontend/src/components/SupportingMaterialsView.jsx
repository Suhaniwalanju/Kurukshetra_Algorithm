import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  GraduationCap,
  HelpCircle,
  FileCheck2,
  CheckCircle,
  AlertTriangle,
  Clock,
  Code2,
  Terminal,
  Download,
  RefreshCw,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
  Bug,
  Eye,
  Check,
  X,
} from 'lucide-react';

export default function SupportingMaterialsView({
  deckId,
  theme,
  isApproved,
  onApprove,
  onOpenExport,
  onOpenRegenerate,
  onOpenMigration,
  onOpenLiveMode,
}) {
  const isDark = theme === 'dark';
  const [activeTab, setActiveTab] = useState('student_notes'); // 'student_notes', 'prof_notes', 'quiz', 'cheat_sheet'
  const [materials, setMaterials] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [revealedAnswers, setRevealedAnswers] = useState({});

  const fetchMaterials = async () => {
    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/materials`);
      if (res.ok) {
        const data = await res.json();
        setMaterials(data);
      } else {
        const err = await res.json();
        if (err.detail && err.detail.includes('not ready')) {
          setMaterials(null);
        } else {
          setErrorMsg(err.detail || 'Failed to load materials');
        }
      }
    } catch (e) {
      console.error(e);
      setErrorMsg('Failed to communicate with backend');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (deckId && isApproved) {
      fetchMaterials();
    }
  }, [deckId, isApproved]);

  const handleGenerateMaterials = async () => {
    setGenerating(true);
    setErrorMsg('');
    try {
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/materials/generate`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setMaterials(data.materials);
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Failed to generate materials');
      }
    } catch (e) {
      console.error(e);
      setErrorMsg('Network error while generating materials');
    } finally {
      setGenerating(false);
    }
  };

  const toggleRevealAnswer = (qIdx) => {
    setRevealedAnswers((prev) => ({
      ...prev,
      [qIdx]: !prev[qIdx],
    }));
  };

  const selectAnswer = (qIdx, opt) => {
    setSelectedAnswers((prev) => ({
      ...prev,
      [qIdx]: opt,
    }));
  };

  // 1. APPROVAL GATE
  if (!isApproved) {
    return (
      <div
        className={`rounded-2xl p-8 border text-center space-y-6 shadow-xl transition-colors ${
          isDark
            ? 'bg-gradient-to-b from-[#0F172A] to-[#1E1B4B]/40 border-indigo-900/40 text-white'
            : 'bg-gradient-to-b from-white to-indigo-50/50 border-indigo-200 text-slate-900'
        }`}
      >
        <div className="w-16 h-16 mx-auto rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
          <GraduationCap className="w-8 h-8" />
        </div>
        <div className="max-w-xl mx-auto space-y-2">
          <h3 className="font-heading font-bold text-2xl tracking-tight">
            Professor Approval Required
          </h3>
          <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
            Per course material studio specification, the slide deck must be verified and approved by the
            professor before Student Notes, Professor Notes, Quiz questions, and Cheat Sheets are generated.
          </p>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-4 pt-2">
          <button
            onClick={onApprove}
            className="px-8 py-3.5 rounded-xl bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white font-bold text-sm shadow-xl shadow-emerald-500/20 flex items-center space-x-2 transition-all transform hover:scale-[1.02]"
          >
            <CheckCircle className="w-5 h-5" />
            <span>Approve Deck & Unlock Supporting Materials</span>
          </button>
        </div>
      </div>
    );
  }

  // 2. MATERIALS NOT GENERATED YET
  if (!materials || !materials.student_notes || materials.student_notes.length === 0) {
    return (
      <div
        className={`rounded-2xl p-8 border text-center space-y-6 shadow-xl transition-colors ${
          isDark
            ? 'bg-[#0F172A] border-slate-800 text-white'
            : 'bg-white border-slate-200 text-slate-900'
        }`}
      >
        <div className="w-16 h-16 mx-auto rounded-2xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
          <Sparkles className="w-8 h-8 animate-pulse" />
        </div>
        <div className="max-w-xl mx-auto space-y-2">
          <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle className="w-3.5 h-3.5" />
            <span>Deck Approved by Professor</span>
          </div>
          <h3 className="font-heading font-bold text-2xl tracking-tight">
            Ready to Generate Supporting Materials
          </h3>
          <p className={`text-sm ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
            Generate comprehensive 150-250 word Student Notes with real captured outputs, Professor Notes with
            talking points & student mistake predictions, an executed Quiz with distractor explanations, and a
            strictly 1-page A4 brand Cheat Sheet.
          </p>
        </div>

        {errorMsg && (
          <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-400 max-w-md mx-auto">
            {errorMsg}
          </div>
        )}

        <div className="flex justify-center pt-2">
          <button
            onClick={handleGenerateMaterials}
            disabled={generating}
            className="px-8 py-3.5 rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 text-white font-bold text-sm shadow-xl shadow-blue-500/25 flex items-center space-x-2 transition-all disabled:opacity-60"
          >
            {generating ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                <span>Synthesizing & Executing Sandbox Pipeline...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-5 h-5" />
                <span>Generate Supporting Materials Now</span>
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  // 3. MATERIALS ARE READY - TABBED INTERFACE
  const studentNotes = materials.student_notes || [];
  const profNotes = materials.professor_notes || [];
  const quizQuestions = materials.quiz || [];
  const cheatSheet = materials.cheat_sheet || {};

  return (
    <div className="space-y-6">
      {/* Action Bar */}
      <div
        className={`rounded-2xl p-5 border flex flex-col md:flex-row md:items-center justify-between gap-4 transition-colors ${
          isDark ? 'bg-[#0F172A] border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
        }`}
      >
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <CheckCircle className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-heading font-bold text-lg leading-tight">Supporting Materials Studio</h3>
            <p className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              Approved Deck Materials · Verified Code & Real Captured Outputs
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {onOpenLiveMode && (
            <button
              onClick={onOpenLiveMode}
              className="px-3.5 py-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 text-xs font-semibold flex items-center space-x-1.5 transition-all"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Live Class Mode</span>
            </button>
          )}

          {onOpenRegenerate && (
            <button
              onClick={onOpenRegenerate}
              className={`px-3.5 py-2 rounded-xl border text-xs font-semibold flex items-center space-x-1.5 transition-all ${
                isDark
                  ? 'border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200'
                  : 'border-slate-200 bg-slate-100 hover:bg-slate-200 text-slate-800'
              }`}
            >
              <RefreshCw className="w-3.5 h-3.5 text-blue-400" />
              <span>Regenerate Single Slide</span>
            </button>
          )}

          {onOpenMigration && (
            <button
              onClick={onOpenMigration}
              className={`px-3.5 py-2 rounded-xl border text-xs font-semibold flex items-center space-x-1.5 transition-all ${
                isDark
                  ? 'border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200'
                  : 'border-slate-200 bg-slate-100 hover:bg-slate-200 text-slate-800'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-purple-400" />
              <span>Version Migration</span>
            </button>
          )}

          <button
            onClick={onOpenExport}
            className="px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold flex items-center space-x-1.5 shadow-lg shadow-blue-500/20 transition-all"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export Center & Download All</span>
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-700/40 gap-2">
        <button
          onClick={() => setActiveTab('student_notes')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center space-x-2 border-b-2 transition-all ${
            activeTab === 'student_notes'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <BookOpen className="w-4 h-4" />
          <span>Student Notes ({studentNotes.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('prof_notes')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center space-x-2 border-b-2 transition-all ${
            activeTab === 'prof_notes'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <GraduationCap className="w-4 h-4" />
          <span>Professor Notes & Mistakes ({profNotes.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('quiz')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center space-x-2 border-b-2 transition-all ${
            activeTab === 'quiz'
              ? 'border-emerald-500 text-emerald-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <HelpCircle className="w-4 h-4" />
          <span>Interactive Quiz ({quizQuestions.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('cheat_sheet')}
          className={`pb-3 px-4 text-sm font-semibold flex items-center space-x-2 border-b-2 transition-all ${
            activeTab === 'cheat_sheet'
              ? 'border-amber-500 text-amber-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileCheck2 className="w-4 h-4" />
          <span>1-Page Cheat Sheet</span>
        </button>
      </div>

      {/* TAB 1: STUDENT NOTES */}
      {activeTab === 'student_notes' && (
        <div className="space-y-6">
          {studentNotes.map((note, idx) => (
            <div
              key={idx}
              className={`rounded-2xl p-6 border transition-colors shadow-sm space-y-4 ${
                isDark ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center space-x-2">
                  <span className="px-2.5 py-0.5 rounded-md text-xs font-mono font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    Slide {note.slide_id}
                  </span>
                  <h4 className="font-heading font-bold text-lg text-slate-100">{note.slide_title}</h4>
                </div>
                <div className="flex items-center space-x-2">
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                      note.word_count >= 140 && note.word_count <= 260
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}
                  >
                    {note.word_count} words (150-250 target)
                  </span>
                </div>
              </div>

              {/* Plain Language Explanation */}
              <div className="space-y-1">
                <span className="text-xs uppercase font-bold text-slate-400 tracking-wider">
                  Plain-Language Concept
                </span>
                <p className={`text-sm leading-relaxed ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>
                  {note.plain_explanation}
                </p>
              </div>

              {/* Why It Matters */}
              <div className="space-y-1">
                <span className="text-xs uppercase font-bold text-indigo-400 tracking-wider">
                  Why It Matters
                </span>
                <p className={`text-sm leading-relaxed ${isDark ? 'text-slate-300' : 'text-slate-600'}`}>
                  {note.why_it_matters}
                </p>
              </div>

              {/* Verified Code with Real Output */}
              {note.verified_code && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pt-2">
                  <div className="space-y-1">
                    <span className="text-xs uppercase font-mono font-bold text-slate-400 flex items-center space-x-1">
                      <Code2 className="w-3.5 h-3.5 text-blue-400" />
                      <span>Verified Snippet</span>
                    </span>
                    <pre className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-emerald-300 overflow-x-auto leading-relaxed max-h-48">
                      {note.verified_code}
                    </pre>
                  </div>

                  <div className="space-y-1">
                    <span className="text-xs uppercase font-mono font-bold text-slate-400 flex items-center space-x-1">
                      <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Real Captured Sandbox Output</span>
                    </span>
                    <pre className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto leading-relaxed max-h-48">
                      {note.real_output || '(Clean exit code 0 / No stdout)'}
                    </pre>
                  </div>
                </div>
              )}

              {/* Common Mistake Alert */}
              {note.common_mistake && (
                <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-300 flex items-start space-x-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
                  <div>
                    <span className="font-bold">Common Student Pitfall: </span>
                    <span>{note.common_mistake}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* TAB 2: PROFESSOR NOTES & PREDICTED MISTAKES */}
      {activeTab === 'prof_notes' && (
        <div className="space-y-6">
          {profNotes.map((pn, idx) => (
            <div
              key={idx}
              className={`rounded-2xl p-6 border transition-colors shadow-sm space-y-5 ${
                isDark ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center space-x-2">
                  <span className="px-2.5 py-0.5 rounded-md text-xs font-mono font-bold bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                    Slide {pn.slide_id}
                  </span>
                  <h4 className="font-heading font-bold text-lg text-slate-100">{pn.slide_title}</h4>
                </div>
                <div className="flex items-center space-x-2 text-xs font-semibold text-slate-400">
                  <Clock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Suggested Timing: ~{pn.timing_minutes} mins</span>
                </div>
              </div>

              {/* Talking Points */}
              <div className="space-y-2">
                <span className="text-xs uppercase font-bold text-slate-400 tracking-wider">
                  Instructional Talking Points
                </span>
                <ul className="space-y-1.5 list-disc list-inside text-sm text-slate-300">
                  {pn.talking_points.map((tp, tpIdx) => (
                    <li key={tpIdx}>{tp}</li>
                  ))}
                </ul>
              </div>

              {/* Likely Student Questions */}
              {pn.likely_questions && pn.likely_questions.length > 0 && (
                <div className="space-y-2">
                  <span className="text-xs uppercase font-bold text-indigo-400 tracking-wider">
                    Anticipated Student Questions & Model Answers
                  </span>
                  <div className="space-y-2">
                    {pn.likely_questions.map((qObj, qIdx) => (
                      <div
                        key={qIdx}
                        className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 text-xs space-y-1"
                      >
                        <div className="font-semibold text-indigo-300">Q: {qObj.question}</div>
                        <div className="text-slate-300">A: {qObj.answer}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Pre-captured Fallback Output */}
              {pn.fallback_output && (
                <div className="space-y-1">
                  <span className="text-xs uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
                    <Terminal className="w-3.5 h-3.5 text-amber-400" />
                    <span>Demo Fallback Output (In Case Live Execution Fails)</span>
                  </span>
                  <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-amber-200/90 overflow-x-auto">
                    {pn.fallback_output}
                  </pre>
                </div>
              )}

              {/* Student Mistake Predictor */}
              {pn.predicted_mistakes && pn.predicted_mistakes.length > 0 && (
                <div className="space-y-3 pt-2">
                  <div className="flex items-center space-x-2">
                    <Bug className="w-4 h-4 text-rose-400" />
                    <span className="text-xs uppercase font-bold text-rose-400 tracking-wider">
                      Student Mistake Predictor (3 Buggy Variants Executed in Sandbox)
                    </span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    {pn.predicted_mistakes.map((pm, mIdx) => (
                      <div
                        key={mIdx}
                        className="p-3.5 rounded-xl bg-rose-500/5 border border-rose-500/20 text-xs space-y-2 flex flex-col justify-between"
                      >
                        <div className="space-y-1">
                          <span className="font-bold text-rose-400">Variant {mIdx + 1}</span>
                          <pre className="p-2 rounded-lg bg-black/50 text-[11px] font-mono text-rose-200 overflow-x-auto max-h-28">
                            {pm.buggy_code}
                          </pre>
                          <div className="text-[11px] font-mono text-slate-300 bg-slate-900/80 p-2 rounded border border-slate-800 overflow-x-auto max-h-20">
                            <span className="text-rose-400 font-bold">Real Error: </span>
                            {pm.real_error}
                          </div>
                        </div>
                        <div className="text-[11px] text-slate-300 italic pt-1 border-t border-rose-500/20">
                          {pm.explanation}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* TAB 3: QUIZ */}
      {activeTab === 'quiz' && (
        <div className="space-y-6">
          <div
            className={`p-4 rounded-xl border flex items-center justify-between text-xs ${
              isDark ? 'bg-slate-900/60 border-slate-800 text-slate-300' : 'bg-slate-50 border-slate-200 text-slate-600'
            }`}
          >
            <span>
              Total Questions: <span className="font-bold text-white">{quizQuestions.length}</span> (Includes MCQs
              and Sandbox Code-Output Predictions)
            </span>
            <span className="text-emerald-400 font-semibold">Answers Confirmed by Container Execution ✔</span>
          </div>

          <div className="space-y-6">
            {quizQuestions.map((q, qIdx) => {
              const isRevealed = revealedAnswers[qIdx];
              const userSelected = selectedAnswers[qIdx];
              const isCodePrediction = q.type === 'code_output_prediction';

              return (
                <div
                  key={qIdx}
                  className={`rounded-2xl p-6 border transition-colors shadow-sm space-y-4 ${
                    isDark ? 'bg-[#0F172A] border-slate-800' : 'bg-white border-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center space-x-2">
                      <span className="px-2.5 py-0.5 rounded-md text-xs font-mono font-bold bg-blue-500/20 text-blue-400 border border-blue-500/30">
                        Q{q.id}
                      </span>
                      {isCodePrediction && (
                        <span className="px-2.5 py-0.5 rounded-md text-[10px] font-bold uppercase bg-purple-500/20 text-purple-400 border border-purple-500/30">
                          Code Prediction
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => toggleRevealAnswer(qIdx)}
                      className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center space-x-1"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>{isRevealed ? 'Hide Answer & Distractors' : 'Reveal Answer Key'}</span>
                    </button>
                  </div>

                  <p className="font-semibold text-sm text-slate-100">{q.question}</p>

                  {/* Code snippet if present */}
                  {q.code_snippet && (
                    <pre className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-emerald-300 overflow-x-auto max-h-36">
                      {q.code_snippet}
                    </pre>
                  )}

                  {/* Options */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                    {q.options.map((opt, optIdx) => {
                      const isCorrect = opt === q.correct_answer;
                      const isChosen = userSelected === opt;

                      let optStyle = isDark
                        ? 'bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700'
                        : 'bg-slate-50 border-slate-200 text-slate-700 hover:border-slate-300';

                      if (isRevealed) {
                        if (isCorrect) {
                          optStyle = 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300';
                        } else if (isChosen) {
                          optStyle = 'bg-rose-500/10 border-rose-500/40 text-rose-300';
                        }
                      } else if (isChosen) {
                        optStyle = 'bg-blue-500/20 border-blue-500/40 text-blue-200';
                      }

                      return (
                        <button
                          key={optIdx}
                          onClick={() => selectAnswer(qIdx, opt)}
                          className={`p-3 rounded-xl border text-left text-xs transition-all flex items-start space-x-2.5 ${optStyle}`}
                        >
                          <span className="w-5 h-5 rounded-full border flex items-center justify-center shrink-0 text-[10px] font-bold">
                            {String.fromCharCode(65 + optIdx)}
                          </span>
                          <span className="flex-1 leading-snug">{opt}</span>
                          {isRevealed && isCorrect && (
                            <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                          )}
                          {isRevealed && isChosen && !isCorrect && (
                            <X className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                          )}
                        </button>
                      );
                    })}
                  </div>

                  {/* Revealed Answer & Detailed Distractor Analysis */}
                  {isRevealed && (
                    <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/20 space-y-3 text-xs">
                      <div>
                        <span className="font-bold text-emerald-400">Correct Answer: </span>
                        <span className="text-slate-200 font-semibold">{q.correct_answer}</span>
                      </div>
                      <div className="text-slate-300 leading-relaxed">
                        <span className="font-bold text-indigo-300">Explanation: </span>
                        {q.explanation}
                      </div>

                      {/* Why each distractor is wrong */}
                      {q.distractor_explanations && Object.keys(q.distractor_explanations).length > 0 && (
                        <div className="space-y-1 pt-2 border-t border-indigo-500/20">
                          <span className="font-bold text-rose-400">Why Distractors are Incorrect:</span>
                          <div className="space-y-1 pt-1">
                            {Object.entries(q.distractor_explanations).map(([optKey, exp], expIdx) => (
                              <div key={expIdx} className="text-slate-300">
                                <span className="font-mono text-slate-400">• {optKey}: </span>
                                <span>{exp}</span>
                              </div>
                            ))}
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
      )}

      {/* TAB 4: CHEAT SHEET */}
      {activeTab === 'cheat_sheet' && (
        <div className="space-y-6">
          <div
            className={`rounded-2xl p-6 border transition-colors shadow-sm space-y-5 ${
              isDark ? 'bg-[#0F172A] border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
            }`}
          >
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center space-x-1">
                    <CheckCircle className="w-3 h-3" />
                    <span>Strictly 1-Page A4 Verified ✔</span>
                  </span>
                  <span className="text-xs text-slate-400">• Brand Palettes Pinned</span>
                </div>
                <h3 className="font-heading font-bold text-xl mt-1">{cheatSheet.title || 'Course Cheat Sheet'}</h3>
                <p className="text-xs text-slate-400">
                  {cheatSheet.college} • {cheatSheet.topic} • {cheatSheet.tech} {cheatSheet.tech_version}
                </p>
              </div>

              <a
                href={`http://localhost:8000/api/decks/${deckId}/exports/cheat_sheet`}
                target="_blank"
                rel="noreferrer"
                className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-semibold text-xs flex items-center space-x-2 shadow-lg shadow-blue-500/20"
              >
                <Download className="w-4 h-4" />
                <span>Download CheatSheet.pdf (A4)</span>
              </a>
            </div>

            {/* Syntax Cards */}
            <div className="space-y-2">
              <span className="text-xs uppercase font-bold text-blue-400 tracking-wider">
                Core Syntax Essentials
              </span>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(cheatSheet.syntax_cards || []).map((card, cIdx) => (
                  <div key={cIdx} className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1">
                    <div className="font-semibold text-xs text-slate-200">{card.title}</div>
                    <pre className="p-2 rounded bg-black/60 text-[11px] font-mono text-emerald-300 overflow-x-auto">
                      {card.code}
                    </pre>
                    <div className="text-[11px] text-slate-400">{card.notes}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Pitfall Cards */}
            <div className="space-y-2">
              <span className="text-xs uppercase font-bold text-amber-400 tracking-wider">
                Common Pitfalls & Fixes
              </span>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {(cheatSheet.pitfalls || []).map((pf, pIdx) => (
                  <div
                    key={pIdx}
                    className="p-3 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs space-y-1"
                  >
                    <div className="font-semibold text-amber-300">{pf.pitfall}</div>
                    <div className="text-slate-300">
                      <span className="text-emerald-400 font-bold">Fix: </span>
                      {pf.fix}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Tiny Example */}
            {cheatSheet.tiny_example && (
              <div className="space-y-1">
                <span className="text-xs uppercase font-bold text-slate-400 tracking-wider">
                  Tiny Executable Example ({cheatSheet.tiny_example.title})
                </span>
                <pre className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 text-xs font-mono text-indigo-300 overflow-x-auto">
                  {cheatSheet.tiny_example.code}
                </pre>
                <div className="text-xs font-mono text-emerald-400">
                  Captured Output: {cheatSheet.tiny_example.output}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
