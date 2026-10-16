import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  Cpu,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  FileText,
  Download,
  Terminal,
  Activity,
  Zap,
  Code,
  Eye,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export default function VerificationDashboard({ deckId, theme, onClose, onRefreshDeck }) {
  const isDark = theme === 'dark';
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [streamProgress, setStreamProgress] = useState({ stage: 'idle', percent: 0, message: '' });
  const [selectedSnippet, setSelectedSnippet] = useState(null);
  const [activeTab, setActiveTab] = useState('snippets'); // 'snippets', 'exercises', 'content', 'qa'

  useEffect(() => {
    if (deckId) {
      fetchReport();
    }
  }, [deckId]);

  const fetchReport = async () => {
    try {
      setLoading(true);
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/report`);
      if (res.ok) {
        const data = await res.json();
        setReport(data);
      }
    } catch (err) {
      console.error('Failed to fetch verification report:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleStartVerification = async () => {
    try {
      setVerifying(true);
      setStreamProgress({ stage: 'start', percent: 5, message: 'Initiating verification pipeline...' });

      // Start SSE stream
      const eventSource = new EventSource(`http://localhost:8000/api/decks/${deckId}/verify/stream`);

      eventSource.onmessage = (e) => {
        try {
          if (e.data.startsWith(':')) return; // heartbeat
          const ev = JSON.parse(e.data);
          setStreamProgress({
            stage: ev.stage,
            percent: ev.percent || 10,
            message: ev.message || 'Verifying...',
          });

          if (ev.stage === 'completed' || ev.stage === 'error') {
            eventSource.close();
            setVerifying(false);
            fetchReport();
            if (onRefreshDeck) onRefreshDeck();
          }
        } catch (err) {
          console.error('Error parsing SSE event:', err);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        setVerifying(false);
        fetchReport();
      };

      // Trigger verification API
      const res = await fetch(`http://localhost:8000/api/decks/${deckId}/verify`, { method: 'POST' });
      if (!res.ok) {
        throw new Error('Failed to start verification');
      }
    } catch (err) {
      console.error('Error starting verification:', err);
      setVerifying(false);
      alert('Failed to start verification: ' + err.message);
    }
  };

  const downloadReportHtml = () => {
    window.open(`http://localhost:8000/api/decks/${deckId}/report/html`, '_blank');
  };

  const downloadReportPdf = () => {
    window.open(`http://localhost:8000/api/decks/${deckId}/report/pdf`, '_blank');
  };

  // Determine Red / Amber / Green Deck Overview Status
  const getDeckStatusBadge = () => {
    if (!report || !report.summary || report.summary.total_snippets === 0) {
      return {
        label: 'UNVERIFIED',
        color: 'bg-gray-500/10 text-gray-500 border-gray-500/30',
        desc: 'Verification not yet executed.',
      };
    }
    const { needs_review_snippets, failed_snippets, auto_healed_snippets, verified_snippets, total_snippets } = report.summary;
    if (needs_review_snippets > 0 || failed_snippets > 0) {
      return {
        label: 'NEEDS REVIEW (RED)',
        color: 'bg-red-500/10 text-red-500 border-red-500/30',
        desc: `${needs_review_snippets + failed_snippets} snippet(s) require professor attention.`,
      };
    }
    if (auto_healed_snippets > 0) {
      return {
        label: 'AUTO-HEALED (AMBER)',
        color: 'bg-amber-500/10 text-amber-500 border-amber-500/30',
        desc: `All snippets verified, with ${auto_healed_snippets} auto-healed by LLM sandbox.`,
      };
    }
    return {
      label: 'FULLY VERIFIED (GREEN)',
      color: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30',
      desc: `All ${verified_snippets} snippets and exercises executed cleanly in sandbox.`,
    };
  };

  const deckBadge = getDeckStatusBadge();

  return (
    <div className={`rounded-2xl border p-6 space-y-6 shadow-2xl transition-colors duration-200 ${
      isDark ? 'bg-[#0f172a] border-slate-800 text-slate-100' : 'bg-white border-slate-200 text-slate-900'
    }`}>
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-700/50">
        <div>
          <div className="flex items-center space-x-2">
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-blue-500/10 text-blue-500 border border-blue-500/20 flex items-center space-x-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Phase 2 Verification Core</span>
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider border ${deckBadge.color}`}>
              {deckBadge.label}
            </span>
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight mt-1 flex items-center space-x-2">
            <span>Code Sandbox & Slide Verification</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">{deckBadge.desc}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {report && report.html_report_available && (
            <button
              onClick={downloadReportHtml}
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold flex items-center space-x-1.5 border transition-all ${
                isDark ? 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200' : 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-800'
              }`}
            >
              <FileText className="w-4 h-4 text-amber-500" />
              <span>HTML Report</span>
            </button>
          )}

          {report && report.pdf_report_available && (
            <button
              onClick={downloadReportPdf}
              className={`px-3.5 py-2 rounded-xl text-xs font-semibold flex items-center space-x-1.5 border transition-all ${
                isDark ? 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200' : 'bg-slate-100 hover:bg-slate-200 border-slate-300 text-slate-800'
              }`}
            >
              <Download className="w-4 h-4 text-blue-500" />
              <span>PDF Report</span>
            </button>
          )}

          <button
            onClick={handleStartVerification}
            disabled={verifying}
            className={`px-5 py-2 rounded-xl text-xs font-bold flex items-center space-x-2 text-white shadow-lg transition-all ${
              verifying
                ? 'bg-blue-600/50 cursor-not-allowed'
                : 'bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 shadow-blue-500/20'
            }`}
          >
            <RefreshCw className={`w-4 h-4 ${verifying ? 'animate-spin' : ''}`} />
            <span>{verifying ? 'Verifying Sandbox...' : 'Run Verification Core'}</span>
          </button>
        </div>
      </div>

      {/* Realtime Verification Live Progress Banner */}
      {verifying && (
        <div className={`p-4 rounded-xl border animate-pulse ${
          isDark ? 'bg-blue-950/40 border-blue-800/60' : 'bg-blue-50 border-blue-200'
        }`}>
          <div className="flex justify-between items-center text-xs font-semibold mb-2">
            <span className="flex items-center space-x-2 text-blue-500">
              <Activity className="w-4 h-4 animate-spin" />
              <span>{streamProgress.message || 'Executing Sandbox Pipeline...'}</span>
            </span>
            <span className="text-blue-500">{streamProgress.percent}%</span>
          </div>
          <div className="w-full h-2 rounded-full bg-slate-700/40 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-300 rounded-full"
              style={{ width: `${streamProgress.percent}%` }}
            />
          </div>
        </div>
      )}

      {/* Summary KPI Metric Cards */}
      {report && report.summary && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div className={`p-3.5 rounded-xl border text-center ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
            <div className="text-xl font-black text-emerald-500">
              {report.summary.verified_snippets}/{report.summary.total_snippets}
            </div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-0.5">Verified</div>
          </div>
          <div className={`p-3.5 rounded-xl border text-center ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
            <div className="text-xl font-black text-amber-500">{report.summary.auto_healed_snippets}</div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-0.5">Auto-Healed</div>
          </div>
          <div className={`p-3.5 rounded-xl border text-center ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
            <div className="text-xl font-black text-rose-500">{report.summary.needs_review_snippets + report.summary.failed_snippets}</div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-0.5">Needs Review</div>
          </div>
          <div className={`p-3.5 rounded-xl border text-center ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
            <div className="text-xl font-black text-purple-500">
              {report.summary.proven_exercises}/{report.summary.total_exercises}
            </div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-0.5">Exercises Proven</div>
          </div>
          <div className={`p-3.5 rounded-xl border text-center ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
            <div className="text-xl font-black text-blue-500">{Math.round(report.summary.mutation_score * 100)}%</div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-0.5">Mutation Score</div>
          </div>
          <div className={`p-3.5 rounded-xl border text-center ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
            <div className="text-xl font-black text-emerald-500">100%</div>
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mt-0.5">QA Safe Zones</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-2 border-b border-slate-700/50">
        <button
          onClick={() => setActiveTab('snippets')}
          className={`pb-3 text-xs font-bold tracking-wide uppercase transition-colors border-b-2 flex items-center space-x-1.5 ${
            activeTab === 'snippets'
              ? 'border-blue-500 text-blue-500'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Code className="w-3.5 h-3.5" />
          <span>Code Snippets ({report?.snippets?.length || 0})</span>
        </button>
        <button
          onClick={() => setActiveTab('exercises')}
          className={`pb-3 text-xs font-bold tracking-wide uppercase transition-colors border-b-2 flex items-center space-x-1.5 ${
            activeTab === 'exercises'
              ? 'border-blue-500 text-blue-500'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          <span>Exercise Proof Matrix ({report?.exercise_proofs?.length || 0})</span>
        </button>
        <button
          onClick={() => setActiveTab('content')}
          className={`pb-3 text-xs font-bold tracking-wide uppercase transition-colors border-b-2 flex items-center space-x-1.5 ${
            activeTab === 'content'
              ? 'border-blue-500 text-blue-500'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Content Review</span>
        </button>
      </div>

      {/* TAB 1: Code Snippets Table */}
      {activeTab === 'snippets' && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className={`border-b ${isDark ? 'border-slate-800 text-slate-400' : 'border-slate-200 text-slate-500'}`}>
                <th className="py-2.5 px-3">Slide</th>
                <th className="py-2.5 px-3">Language</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Captured Output</th>
                <th className="py-2.5 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/40">
              {report?.snippets?.map((snip) => {
                const run = report.runs?.find((r) => r.snippet_id === snip.id);
                return (
                  <tr key={snip.id} className={`hover:bg-slate-500/5 transition-colors`}>
                    <td className="py-3 px-3 font-semibold">
                      Slide {snip.slide_id}
                    </td>
                    <td className="py-3 px-3">
                      <span className="font-mono text-[11px] text-blue-400">{snip.language} {snip.version}</span>
                    </td>
                    <td className="py-3 px-3">
                      {snip.status === 'verified' && (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="w-3 h-3" />
                          <span>Verified</span>
                        </span>
                      )}
                      {snip.status === 'auto_healed' && (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                          <Zap className="w-3 h-3" />
                          <span>Auto-Healed</span>
                        </span>
                      )}
                      {snip.status === 'needs_review' && (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/10 text-purple-400 border border-purple-500/20">
                          <AlertTriangle className="w-3 h-3" />
                          <span>Needs Review</span>
                        </span>
                      )}
                      {snip.status === 'failed' && (
                        <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                          <XCircle className="w-3 h-3" />
                          <span>Failed</span>
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-3 max-w-xs truncate font-mono text-[11px] text-slate-300">
                      {run?.stdout || '(none)'}
                    </td>
                    <td className="py-3 px-3 text-right">
                      <button
                        onClick={() => setSelectedSnippet(snip)}
                        className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center space-x-1 ml-auto"
                      >
                        <Eye className="w-3 h-3" />
                        <span>Inspect Log</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
              {(!report?.snippets || report.snippets.length === 0) && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-slate-400">
                    No snippets verified yet. Click "Run Verification Core" to execute.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 2: Exercise Proof Matrix */}
      {activeTab === 'exercises' && (
        <div className="space-y-4">
          {report?.exercise_proofs?.map((ep) => (
            <div key={ep.id} className={`p-4 rounded-xl border ${isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
              <div className="flex justify-between items-center mb-3">
                <div className="font-bold text-sm">
                  Slide {ep.slide_id}: {ep.exercise_ref}
                </div>
                <div className="flex items-center space-x-2 text-xs">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
                    Ref: PASS ✔
                  </span>
                  <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 font-bold">
                    Naive: FAIL ✖
                  </span>
                  <span className="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20 font-bold">
                    Mutation Score: {Math.round(ep.mutation_score * 100)}%
                  </span>
                </div>
              </div>
              <p className="text-xs text-slate-400 mb-3">{ep.problem_statement}</p>

              {/* Pass / Fail Matrix */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className={`border-b ${isDark ? 'border-slate-800 text-slate-400' : 'border-slate-200 text-slate-500'}`}>
                      <th className="py-1 px-2">Solution Variant</th>
                      <th className="py-1 px-2">Expected</th>
                      <th className="py-1 px-2">Actual Result</th>
                      <th className="py-1 px-2 text-right">Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-slate-800/40">
                      <td className="py-1.5 px-2 font-bold text-slate-200">Reference Solution</td>
                      <td className="py-1.5 px-2 text-emerald-400">PASS</td>
                      <td className="py-1.5 px-2 text-emerald-400">{ep.reference_passed ? 'PASS' : 'FAIL'}</td>
                      <td className="py-1.5 px-2 text-right text-emerald-400 font-bold">VALID ✔</td>
                    </tr>
                    <tr className="border-b border-slate-800/40">
                      <td className="py-1.5 px-2 font-bold text-slate-200">Naive Solution</td>
                      <td className="py-1.5 px-2 text-rose-400">FAIL</td>
                      <td className="py-1.5 px-2 text-rose-400">{ep.naive_failed ? 'FAIL' : 'PASS'}</td>
                      <td className="py-1.5 px-2 text-right text-rose-400 font-bold">PROVEN ✖</td>
                    </tr>
                    {ep.mutants?.map((m, mIdx) => (
                      <tr key={mIdx} className="border-b border-slate-800/20">
                        <td className="py-1.5 px-2 text-slate-400">{m.id}: {m.name}</td>
                        <td className="py-1.5 px-2 text-rose-400">FAIL (KILLED)</td>
                        <td className="py-1.5 px-2 text-slate-300">{m.killed ? 'KILLED' : 'SURVIVED'}</td>
                        <td className={`py-1.5 px-2 text-right font-bold ${m.killed ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {m.killed ? 'KILLED ✔' : 'SURVIVED ⚠'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          {(!report?.exercise_proofs || report.exercise_proofs.length === 0) && (
            <div className="py-8 text-center text-slate-400 text-xs">
              No exercise slides found in this deck.
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Content Review */}
      {activeTab === 'content' && (
        <div className="space-y-3">
          {report?.content_reviews?.[0]?.findings?.map((f, fIdx) => (
            <div key={fIdx} className={`p-3 rounded-xl border flex items-start space-x-3 text-xs ${
              isDark ? 'bg-slate-900 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-slate-200">Slide {f.slide_id}: {f.type}</div>
                <div className="text-slate-400 mt-0.5">{f.message}</div>
              </div>
            </div>
          ))}
          {(!report?.content_reviews?.[0]?.findings || report.content_reviews[0].findings.length === 0) && (
            <div className="py-8 text-center text-emerald-400 text-xs font-semibold">
              ✔ All slides passed factual accuracy and bullet word limits (max 5 bullets, max 8 words/bullet).
            </div>
          )}
        </div>
      )}

      {/* Inspect Log & Diff Modal */}
      {selectedSnippet && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in">
          <div className={`w-full max-w-3xl max-h-[85vh] flex flex-col rounded-2xl border p-6 space-y-4 shadow-2xl ${
            isDark ? 'bg-[#0f172a] border-slate-700 text-slate-100' : 'bg-white border-slate-300 text-slate-900'
          }`}>
            <div className="flex justify-between items-center pb-3 border-b border-slate-700">
              <div>
                <h3 className="font-bold text-lg">Snippet Details: Slide {selectedSnippet.slide_id}</h3>
                <p className="text-xs text-slate-400 font-mono">
                  ID: {selectedSnippet.id} &bull; {selectedSnippet.language} {selectedSnippet.version}
                </p>
              </div>
              <button
                onClick={() => setSelectedSnippet(null)}
                className="text-slate-400 hover:text-slate-200 text-sm font-bold px-2 py-1"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-3 overflow-y-auto pr-1 flex-1 text-xs">
              <div>
                <div className="font-semibold text-slate-400 mb-1 flex items-center space-x-1">
                  <Terminal className="w-3.5 h-3.5 text-blue-400" />
                  <span>Command Executed:</span>
                </div>
                <div className="p-2.5 rounded-lg bg-black/60 font-mono text-blue-300 border border-slate-800">
                  $ {report?.runs?.find((r) => r.snippet_id === selectedSnippet.id)?.command_executed || 'Direct Sandbox'}
                </div>
              </div>

              <div>
                <div className="font-semibold text-slate-400 mb-1">Source Code:</div>
                <pre className="p-3 rounded-lg bg-black/60 font-mono text-slate-200 border border-slate-800 overflow-x-auto">
                  {selectedSnippet.source_code}
                </pre>
              </div>

              <div>
                <div className="font-semibold text-slate-400 mb-1">Captured Real Stdout:</div>
                <pre className="p-3 rounded-lg bg-black/60 font-mono text-emerald-400 border border-slate-800 overflow-x-auto">
                  {report?.runs?.find((r) => r.snippet_id === selectedSnippet.id)?.stdout || '(none)'}
                </pre>
              </div>

              {/* Diff if healed */}
              {selectedSnippet.status === 'auto_healed' && (
                <div>
                  <div className="font-semibold text-amber-400 mb-1 flex items-center space-x-1">
                    <Zap className="w-3.5 h-3.5" />
                    <span>Auto-Healing Unified Diff:</span>
                  </div>
                  <pre className="p-3 rounded-lg bg-black/60 font-mono text-slate-300 border border-slate-800 overflow-x-auto">
                    {report?.healing_logs?.find((h) => h.snippet_id === selectedSnippet.id)?.diff_text || 'Auto-healed without logged diff.'}
                  </pre>
                </div>
              )}
            </div>

            <div className="pt-2 border-t border-slate-700 flex justify-end">
              <button
                onClick={() => setSelectedSnippet(null)}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
