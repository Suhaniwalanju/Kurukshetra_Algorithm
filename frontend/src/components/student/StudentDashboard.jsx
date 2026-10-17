import React, { useState, useEffect } from 'react';
import {
  BookOpen,
  FileText,
  HelpCircle,
  Code2,
  Presentation,
  Download,
  CheckCircle2,
  XCircle,
  Award,
  Clock,
  ArrowLeft,
  ChevronRight,
  ExternalLink,
  History,
  RotateCcw,
} from 'lucide-react';

export default function StudentDashboard({ user, token, theme }) {
  const isDark = theme === 'dark';

  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSubject, setSelectedSubject] = useState(null);
  const [activeTab, setActiveTab] = useState('notes'); // 'notes', 'quiz', 'exercises', 'slides'

  // Notes state
  const [notesData, setNotesData] = useState(null);
  const [loadingNotes, setLoadingNotes] = useState(false);

  // Exercises state
  const [exercises, setExercises] = useState([]);
  const [loadingExercises, setLoadingExercises] = useState(false);
  const [selectedExerciseIndex, setSelectedExerciseIndex] = useState(0);

  // Quiz state
  const [quizQuestions, setQuizQuestions] = useState([]);
  const [loadingQuiz, setLoadingQuiz] = useState(false);
  const [studentAnswers, setStudentAnswers] = useState({});
  const [submittingQuiz, setSubmittingQuiz] = useState(false);
  const [quizResult, setQuizResult] = useState(null);
  const [pastAttempts, setPastAttempts] = useState([]);
  const [showAttemptsHistory, setShowAttemptsHistory] = useState(false);

  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // Fetch published subjects for student's institute
  const fetchPublishedSubjects = async () => {
    try {
      setLoading(true);
      const res = await fetch('http://localhost:8000/api/student/subjects', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSubjects(data);
      }
    } catch (err) {
      console.error('Error fetching student subjects:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPublishedSubjects();
  }, [token]);

  // When subject selected, load notes, quiz, exercises
  const handleSelectSubject = (subj) => {
    setSelectedSubject(subj);
    setActiveTab('notes');
    setQuizResult(null);
    setStudentAnswers({});
    loadNotes(subj.publication_id);
    loadQuiz(subj.publication_id);
    loadExercises(subj.publication_id);
    loadPastAttempts(subj.publication_id);
  };

  const loadNotes = async (pubId) => {
    try {
      setLoadingNotes(true);
      const res = await fetch(`http://localhost:8000/api/student/publications/${pubId}/notes`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setNotesData(await res.json());
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingNotes(false);
    }
  };

  const loadExercises = async (pubId) => {
    try {
      setLoadingExercises(true);
      const res = await fetch(`http://localhost:8000/api/student/publications/${pubId}/exercises`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setExercises(data);
        setSelectedExerciseIndex(0);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingExercises(false);
    }
  };

  const loadQuiz = async (pubId) => {
    try {
      setLoadingQuiz(true);
      const res = await fetch(`http://localhost:8000/api/student/publications/${pubId}/quiz`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setQuizQuestions(await res.json());
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingQuiz(false);
    }
  };

  const loadPastAttempts = async (pubId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/student/publications/${pubId}/quiz/attempts`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setPastAttempts(await res.json());
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleSelectAnswer = (qId, optionIdx) => {
    if (quizResult) return; // Locked after submission
    setStudentAnswers((prev) => ({
      ...prev,
      [qId]: optionIdx,
    }));
  };

  const handleSubmitQuiz = async () => {
    if (!selectedSubject) return;
    try {
      setSubmittingQuiz(true);
      const res = await fetch(`http://localhost:8000/api/student/publications/${selectedSubject.publication_id}/quiz/submit`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ answers: studentAnswers }),
      });
      if (res.ok) {
        const result = await res.json();
        setQuizResult(result);
        loadPastAttempts(selectedSubject.publication_id);
      } else {
        alert('Failed to submit quiz.');
      }
    } catch (err) {
      console.error(err);
    } finally {
      setSubmittingQuiz(false);
    }
  };

  const handleRetakeQuiz = () => {
    setQuizResult(null);
    setStudentAnswers({});
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Student Banner Header */}
      <div className={`p-6 rounded-3xl border shadow-xl flex flex-col md:flex-row md:items-center md:justify-between gap-4 transition-colors ${
        isDark ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
      }`}>
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Student Learning Portal
            </span>
            <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {user?.institute_short_name || 'DPU'} • Roll No: {user?.roll_number}
            </span>
          </div>
          <h2 className="font-heading font-extrabold text-2xl tracking-tight mt-1">
            Welcome, {user?.display_name}!
          </h2>
          <p className={`text-xs mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
            Access your course materials, verify your hands-on code exercises, and test your skills with quizzes.
          </p>
        </div>

        {selectedSubject && (
          <button
            onClick={() => setSelectedSubject(null)}
            className="px-3.5 py-2 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold flex items-center space-x-1.5 transition-all self-start md:self-auto"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to All Courses</span>
          </button>
        )}
      </div>

      {/* ------------------------------------------------------------- */}
      {/* 1. COURSES GRID (When no subject is active)                   */}
      {/* ------------------------------------------------------------- */}
      {!selectedSubject && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-heading font-bold text-lg">Enrolled Course Curriculum</h3>
            <span className="text-xs text-slate-400 font-medium">{subjects.length} Published Subject(s)</span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-xs text-slate-400">Loading course curriculum...</div>
          ) : subjects.length === 0 ? (
            <div className={`p-12 rounded-3xl border text-center ${
              isDark ? 'bg-slate-900/40 border-slate-800 text-slate-400' : 'bg-white border-slate-200 text-slate-500'
            }`}>
              No published subjects available yet for your institute.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {subjects.map((sub) => (
                <div
                  key={sub.publication_id}
                  onClick={() => handleSelectSubject(sub)}
                  className={`p-6 rounded-3xl border shadow-lg cursor-pointer transition-all transform hover:-translate-y-1 hover:shadow-2xl flex flex-col justify-between ${
                    isDark
                      ? 'bg-slate-900/70 border-slate-800 hover:border-emerald-500/40 text-white'
                      : 'bg-white border-slate-200 hover:border-emerald-500/40 text-slate-900'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                        Version {sub.version}
                      </span>
                      <span className="text-[11px] text-slate-400 font-medium">
                        {sub.tech} {sub.tech_version}
                      </span>
                    </div>

                    <h4 className="font-heading font-bold text-lg tracking-tight mb-1">
                      {sub.subject_name}
                    </h4>
                    <p className={`text-xs line-clamp-2 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                      {sub.topic}
                    </p>
                  </div>

                  <div className="pt-4 mt-4 border-t border-slate-800/40">
                    <div className="flex items-center justify-between text-xs font-semibold text-emerald-400">
                      <span>Open Course Materials</span>
                      <ChevronRight className="w-4 h-4" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* 2. SUBJECT DETAILS & STUDY TABS (Notes, Quiz, Exercises)      */}
      {/* ------------------------------------------------------------- */}
      {selectedSubject && (
        <div className="space-y-6">
          {/* Tabs bar */}
          <div className={`p-2 rounded-2xl border flex items-center space-x-2 ${
            isDark ? 'bg-slate-900/80 border-slate-800' : 'bg-white border-slate-200 shadow-sm'
          }`}>
            <button
              onClick={() => setActiveTab('notes')}
              className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center space-x-1.5 transition-all ${
                activeTab === 'notes'
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/20'
                  : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Course Notes</span>
            </button>

            <button
              onClick={() => setActiveTab('quiz')}
              className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center space-x-1.5 transition-all ${
                activeTab === 'quiz'
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/20'
                  : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <HelpCircle className="w-4 h-4" />
              <span>Concept Quiz ({quizQuestions.length})</span>
            </button>

            <button
              onClick={() => setActiveTab('exercises')}
              className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center space-x-1.5 transition-all ${
                activeTab === 'exercises'
                  ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/20'
                  : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <Code2 className="w-4 h-4" />
              <span>Practice Exercises ({exercises.length})</span>
            </button>

            {selectedSubject.has_slides && (
              <button
                onClick={() => setActiveTab('slides')}
                className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center space-x-1.5 transition-all ${
                  activeTab === 'slides'
                    ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/20'
                    : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Presentation className="w-4 h-4" />
                <span>Lecture Slides</span>
              </button>
            )}
          </div>

          {/* TAB 1: NOTES */}
          {activeTab === 'notes' && (
            <div className={`p-6 sm:p-8 rounded-3xl border shadow-xl space-y-6 animate-fade-in ${
              isDark ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
            }`}>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800/40 pb-4">
                <div>
                  <h3 className="font-heading font-bold text-xl">{selectedSubject.subject_name} - Course Notes</h3>
                  <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    Student-friendly summary, key takeaways, and syntax references.
                  </p>
                </div>
                {notesData?.has_pdf && (
                  <a
                    href={`http://localhost:8000/api/student/publications/${selectedSubject.publication_id}/notes/pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-emerald-600/20 self-start sm:self-auto"
                  >
                    <Download className="w-4 h-4" />
                    <span>Download Notes PDF</span>
                  </a>
                )}
              </div>

              {loadingNotes ? (
                <div className="py-8 text-center text-xs text-slate-400">Loading notes...</div>
              ) : notesData?.markdown ? (
                <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap font-sans text-xs sm:text-sm leading-relaxed">
                  {notesData.markdown}
                </div>
              ) : (
                <div className="py-8 text-center text-xs text-slate-400">No notes available.</div>
              )}
            </div>
          )}

          {/* TAB 2: QUIZ */}
          {activeTab === 'quiz' && (
            <div className={`p-6 sm:p-8 rounded-3xl border shadow-xl space-y-6 animate-fade-in ${
              isDark ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
            }`}>
              <div className="flex items-center justify-between border-b border-slate-800/40 pb-4">
                <div>
                  <h3 className="font-heading font-bold text-xl">Self-Assessment Quiz</h3>
                  <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    Test your understanding. Answers and explanations are revealed immediately after submission.
                  </p>
                </div>

                <div className="flex items-center space-x-2">
                  {pastAttempts.length > 0 && (
                    <button
                      onClick={() => setShowAttemptsHistory(!showAttemptsHistory)}
                      className="px-3 py-1.5 rounded-xl border border-slate-700 text-xs font-semibold flex items-center space-x-1 text-slate-300 hover:bg-slate-800"
                    >
                      <History className="w-3.5 h-3.5" />
                      <span>Past Attempts ({pastAttempts.length})</span>
                    </button>
                  )}
                </div>
              </div>

              {/* Quiz Result Banner if submitted */}
              {quizResult && (
                <div className="p-6 rounded-2xl bg-gradient-to-r from-emerald-950/60 to-teal-950/60 border border-emerald-500/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 animate-fade-in">
                  <div className="flex items-center space-x-4">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                      <Award className="w-6 h-6" />
                    </div>
                    <div>
                      <span className="text-xs uppercase font-bold tracking-wider text-emerald-400">
                        Quiz Completed
                      </span>
                      <h4 className="font-heading font-extrabold text-2xl text-white">
                        Your Score: {quizResult.score} / {quizResult.total} ({quizResult.percentage}%)
                      </h4>
                    </div>
                  </div>

                  <button
                    onClick={handleRetakeQuiz}
                    className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-1.5 self-start sm:self-auto"
                  >
                    <RotateCcw className="w-4 h-4" />
                    <span>Retake Quiz</span>
                  </button>
                </div>
              )}

              {/* Past Attempts Drawer */}
              {showAttemptsHistory && (
                <div className="p-4 rounded-2xl border border-slate-800 bg-slate-950/60 space-y-2">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-2">
                    Your Past Attempt History
                  </span>
                  {pastAttempts.map((att, idx) => (
                    <div key={att.id} className="flex items-center justify-between text-xs py-1.5 px-3 rounded-lg bg-slate-900 border border-slate-800">
                      <span>Attempt #{pastAttempts.length - idx}</span>
                      <span className="font-bold text-emerald-400">
                        Score: {att.score} / {att.total_questions} ({Math.round((att.score / Math.max(1, att.total_questions)) * 100)}%)
                      </span>
                      <span className="text-slate-500">{new Date(att.submitted_at).toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Questions List */}
              <div className="space-y-6">
                {quizQuestions.map((q, idx) => {
                  const qId = q.id || `q_${idx + 1}`;
                  const selectedIdx = studentAnswers[qId];
                  const evalDetail = quizResult?.details?.find((d) => d.id === qId || d.number === idx + 1);

                  return (
                    <div
                      key={qId}
                      className={`p-5 rounded-2xl border space-y-3 transition-colors ${
                        evalDetail
                          ? evalDetail.is_correct
                            ? 'bg-emerald-500/5 border-emerald-500/30'
                            : 'bg-rose-500/5 border-rose-500/30'
                          : isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-slate-50 border-slate-200'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <span className="font-heading font-bold text-sm">
                          {idx + 1}. {q.question}
                        </span>
                        {evalDetail && (
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center space-x-1 ${
                            evalDetail.is_correct
                              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                          }`}>
                            {evalDetail.is_correct ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                            <span>{evalDetail.is_correct ? 'Correct' : 'Incorrect'}</span>
                          </span>
                        )}
                      </div>

                      {q.code_snippet && (
                        <pre className="p-3 rounded-xl bg-black/60 border border-slate-800 text-[11px] font-mono text-purple-300 overflow-x-auto">
                          {q.code_snippet}
                        </pre>
                      )}

                      {/* Options */}
                      <div className="space-y-2 pt-1">
                        {q.options && q.options.map((opt, optIdx) => {
                          const isSelected = selectedIdx === optIdx;
                          const isRevealedCorrect = evalDetail && (
                            opt.trim().toLowerCase() === String(evalDetail.correct_answer).trim().toLowerCase()
                          );

                          return (
                            <label
                              key={optIdx}
                              onClick={() => handleSelectAnswer(qId, optIdx)}
                              className={`p-3 rounded-xl border text-xs flex items-center justify-between cursor-pointer transition-all ${
                                isRevealedCorrect
                                  ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300 font-bold'
                                  : isSelected
                                  ? evalDetail && !evalDetail.is_correct
                                    ? 'bg-rose-500/20 border-rose-500 text-rose-300 font-bold'
                                    : 'bg-emerald-500/15 border-emerald-500/60 text-emerald-400 font-semibold'
                                  : isDark
                                  ? 'bg-slate-900 border-slate-800 hover:border-slate-700'
                                  : 'bg-white border-slate-200 hover:border-slate-300'
                              }`}
                            >
                              <div className="flex items-center space-x-2.5">
                                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border ${
                                  isSelected
                                    ? 'bg-emerald-500 text-white border-emerald-500'
                                    : 'border-slate-600 text-slate-400'
                                }`}>
                                  {String.fromCharCode(65 + optIdx)}
                                </span>
                                <span>{opt}</span>
                              </div>
                            </label>
                          );
                        })}
                      </div>

                      {/* Explanation displayed ONLY after submission */}
                      {evalDetail && (
                        <div className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 text-xs space-y-1">
                          <span className="font-bold text-slate-300">Explanation:</span>
                          <p className="text-slate-400">{evalDetail.explanation}</p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {!quizResult && quizQuestions.length > 0 && (
                <button
                  onClick={handleSubmitQuiz}
                  disabled={submittingQuiz || Object.keys(studentAnswers).length === 0}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs shadow-xl shadow-emerald-500/20 transition-all flex items-center justify-center space-x-1.5"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{submittingQuiz ? 'Submitting & Evaluating...' : 'Submit Quiz Answers'}</span>
                </button>
              )}
            </div>
          )}

          {/* TAB 3: EXERCISES */}
          {activeTab === 'exercises' && (
            <div className={`p-6 sm:p-8 rounded-3xl border shadow-xl space-y-6 animate-fade-in ${
              isDark ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
            }`}>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800/40 pb-4">
                <div>
                  <h3 className="font-heading font-bold text-xl">Hands-on Coding Practice</h3>
                  <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                    Implement the required methods and run tests to verify your solutions.
                  </p>
                </div>

                <a
                  href={`http://localhost:8000/api/student/publications/${selectedSubject.publication_id}/exercises/zip`}
                  className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-emerald-600/20 self-start sm:self-auto"
                >
                  <Download className="w-4 h-4" />
                  <span>Download Exercises (.ZIP)</span>
                </a>
              </div>

              {loadingExercises ? (
                <div className="py-8 text-center text-xs text-slate-400">Loading exercises...</div>
              ) : exercises.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">No practice exercises available.</div>
              ) : (
                <div className="space-y-6">
                  {/* Exercise selector buttons */}
                  <div className="flex items-center space-x-2">
                    {exercises.map((ex, idx) => (
                      <button
                        key={idx}
                        onClick={() => setSelectedExerciseIndex(idx)}
                        className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all ${
                          selectedExerciseIndex === idx
                            ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/20'
                            : isDark ? 'bg-slate-800 text-slate-300 hover:bg-slate-700' : 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        Exercise {idx + 1}
                      </button>
                    ))}
                  </div>

                  {/* Active Exercise Detail */}
                  {exercises[selectedExerciseIndex] && (
                    <div className="space-y-4">
                      {/* Task Statement Markdown */}
                      <div className="p-4 rounded-2xl border border-slate-800 bg-slate-950/60 whitespace-pre-wrap text-xs leading-relaxed">
                        {exercises[selectedExerciseIndex].task_markdown}
                      </div>

                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        {/* Starter Code */}
                        <div className="space-y-1.5">
                          <span className="text-xs font-bold text-slate-400 flex items-center space-x-1">
                            <Code2 className="w-3.5 h-3.5 text-blue-400" />
                            <span>Starter Code ({exercises[selectedExerciseIndex].starter_filename || 'Solution'})</span>
                          </span>
                          <pre className="p-4 rounded-2xl bg-black border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto max-h-72">
                            {exercises[selectedExerciseIndex].starter_code}
                          </pre>
                        </div>

                        {/* Test Code */}
                        <div className="space-y-1.5">
                          <span className="text-xs font-bold text-slate-400 flex items-center space-x-1">
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                            <span>Unit Test File ({exercises[selectedExerciseIndex].test_filename || 'Test'})</span>
                          </span>
                          <pre className="p-4 rounded-2xl bg-black border border-slate-800 text-xs font-mono text-emerald-300 overflow-x-auto max-h-72">
                            {exercises[selectedExerciseIndex].test_code}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* TAB 4: SLIDES */}
          {activeTab === 'slides' && selectedSubject.has_slides && (
            <div className={`p-6 sm:p-8 rounded-3xl border shadow-xl space-y-4 animate-fade-in text-center ${
              isDark ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
            }`}>
              <Presentation className="w-12 h-12 mx-auto text-emerald-400 mb-2" />
              <h3 className="font-heading font-bold text-xl">Download Lecture Slide Deck</h3>
              <p className={`text-xs max-w-md mx-auto ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Download the verified lecture slide deck PDF formatted with institute branding.
              </p>
              <a
                href={`http://localhost:8000/api/student/publications/${selectedSubject.publication_id}/slides`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-lg shadow-emerald-600/20 transition-all mt-2"
              >
                <Download className="w-4 h-4" />
                <span>Download Slide Deck (.PDF)</span>
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
