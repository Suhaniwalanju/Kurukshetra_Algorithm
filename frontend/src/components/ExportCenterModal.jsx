import React from 'react';
import {
  X,
  Download,
  FileText,
  FileCheck2,
  FolderArchive,
  Presentation,
  ShieldCheck,
  CheckCircle2,
  BookOpen,
  HelpCircle,
} from 'lucide-react';

export default function ExportCenterModal({ deckId, onClose, theme }) {
  const isDark = theme === 'dark';

  const exportItems = [
    {
      type: 'pptx',
      title: 'PowerPoint Presentation',
      filename: 'Deck.pptx',
      desc: 'Minimal-text branded deck with verified snippets and zero-overflow layout.',
      icon: Presentation,
      color: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
    },
    {
      type: 'pdf',
      title: 'Deck PDF Handout',
      filename: 'Deck.pdf',
      desc: 'High-resolution rendered slide document ready for printing or offline review.',
      icon: FileText,
      color: 'text-red-400 bg-red-500/10 border-red-500/20',
    },
    {
      type: 'student_notes',
      title: 'Student Notes PDF',
      filename: 'Student_Notes.pdf',
      desc: '150-250 words per slide with plain explanations, why it matters, verified code & output.',
      icon: BookOpen,
      color: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
    },
    {
      type: 'quiz',
      title: 'Student Quiz (No Answers)',
      filename: 'Quiz.pdf',
      desc: '8-12 MCQs and 2 code-output predictions for classroom assessment.',
      icon: HelpCircle,
      color: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20',
    },
    {
      type: 'quiz_answer_key',
      title: 'Professor Quiz Key & Distractors',
      filename: 'Quiz_AnswerKey.pdf',
      desc: 'Complete answer key with pedagogical explanations for why each distractor is wrong.',
      icon: CheckCircle2,
      color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',
    },
    {
      type: 'cheat_sheet',
      title: '1-Page A4 Cheat Sheet',
      filename: 'CheatSheet.pdf',
      desc: 'Strictly 1 page A4 document in institute brand colors with key syntax & pitfalls.',
      icon: FileCheck2,
      color: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
    },
    {
      type: 'exercises',
      title: 'Coding Exercises Package',
      filename: 'Exercises.zip',
      desc: 'Starter code, automated tests, and separated reference solution for the professor.',
      icon: FolderArchive,
      color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
    },
    {
      type: 'verification_report',
      title: 'Formal Verification Report',
      filename: 'Verification_Report.pdf',
      desc: 'Signed compliance report with sandbox execution proof and zero-overlap QA logs.',
      icon: ShieldCheck,
      color: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-150">
      <div
        className={`relative w-full max-w-4xl rounded-3xl border shadow-2xl p-6 md:p-8 space-y-6 overflow-hidden ${
          isDark ? 'bg-[#0B1120] border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-700/40">
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                Phase 3 Deliverables
              </span>
              <span className="text-xs text-slate-400">• All Formats Verified</span>
            </div>
            <h2 className="font-heading font-bold text-2xl tracking-tight">
              Export Center & Supporting Material Archive
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Master Download All ZIP Button */}
        <div className="p-5 rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 text-white flex flex-col sm:flex-row items-center justify-between gap-4 shadow-xl shadow-blue-500/20">
          <div className="space-y-1 text-center sm:text-left">
            <h3 className="font-heading font-bold text-lg">Download Complete Material Bundle (.ZIP)</h3>
            <p className="text-xs text-blue-100 max-w-xl">
              Includes all verified slides (.pptx + .pdf), notes, quiz keys, cheat sheet, exercise zip,
              and verification report in one packaged archive.
            </p>
          </div>
          <a
            href={`http://localhost:8000/api/decks/${deckId}/exports/all_zip`}
            download="All_Materials.zip"
            className="px-6 py-3 rounded-xl bg-white text-blue-900 hover:bg-blue-50 font-bold text-sm flex items-center space-x-2 shrink-0 shadow-lg transition-transform hover:scale-[1.02]"
          >
            <Download className="w-4 h-4" />
            <span>Download All (ZIP)</span>
          </a>
        </div>

        {/* Individual File Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 max-h-[50vh] overflow-y-auto pr-1">
          {exportItems.map((item, idx) => {
            const Icon = item.icon;
            return (
              <div
                key={idx}
                className={`p-4 rounded-2xl border transition-colors flex items-start justify-between gap-3 ${
                  isDark ? 'bg-slate-900/60 border-slate-800/80 hover:border-slate-700' : 'bg-slate-50 border-slate-200 hover:border-slate-300'
                }`}
              >
                <div className="flex items-start space-x-3 min-w-0">
                  <div className={`w-9 h-9 rounded-xl border flex items-center justify-center shrink-0 ${item.color}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <div className="min-w-0 space-y-0.5">
                    <div className="text-sm font-semibold truncate leading-tight">{item.title}</div>
                    <div className="text-[11px] font-mono text-slate-400 truncate">{item.filename}</div>
                    <div className="text-xs text-slate-400 leading-snug line-clamp-2">{item.desc}</div>
                  </div>
                </div>

                <a
                  href={`http://localhost:8000/api/decks/${deckId}/exports/${item.type}`}
                  download={item.filename}
                  className={`p-2.5 rounded-xl border shrink-0 text-slate-300 hover:text-white transition-colors ${
                    isDark ? 'bg-slate-800 border-slate-700 hover:bg-slate-700' : 'bg-white border-slate-300 hover:bg-slate-100 text-slate-700'
                  }`}
                  title={`Download ${item.filename}`}
                >
                  <Download className="w-4 h-4" />
                </a>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
