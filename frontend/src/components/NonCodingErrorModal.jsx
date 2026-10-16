import React from 'react';
import { Code2, Sparkles, X, ArrowRight } from 'lucide-react';

export default function NonCodingErrorModal({ error, onClose, onSelectSuggestedTopic, theme }) {
  if (!error) return null;
  const isDark = theme === 'dark';

  const suggestions = [
    { topic: "Python 3.12 AsyncIO and Coroutines Architecture", tech: "Python", version: "3.12" },
    { topic: "Java 21 Virtual Threads & Structured Concurrency", tech: "Java", version: "21" },
    { topic: "C Memory Safety: Pointers, Allocations & Sanitizers", tech: "C", version: "17" },
    { topic: "Modern C++20 Concepts, Ranges & Move Semantics", tech: "C++", version: "20" },
    { topic: "PostgreSQL Advanced Indexing, Query Optimization & EXPLAIN", tech: "PostgreSQL", version: "16.6" },
    { topic: "Node.js & Express RESTful API Design with Middleware", tech: "Node.js + Express", version: "20" },
    { topic: "React 18 State Management, Hooks & Component Lifecycle", tech: "React", version: "18.3" },
    { topic: "Tailwind CSS Utility-First Responsive Design", tech: "Tailwind CSS", version: "3.4" },
    { topic: "MongoDB Document Modeling, Indexing & Aggregations", tech: "MongoDB", version: "7.0" },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className={`border rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden transition-colors duration-200 ${
        isDark ? 'bg-[#0F172A] border-amber-500/30 text-white' : 'bg-white border-amber-400 text-gray-900'
      }`}>
        {/* Top Accent Strip */}
        <div className="h-1.5 w-full bg-gradient-to-r from-amber-500 via-orange-500 to-rose-500" />

        <div className="p-6 space-y-5">
          <div className="flex items-start justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500 shrink-0">
                <Code2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-heading font-bold text-lg">
                  Coding Topics Required
                </h3>
                <span className="text-xs text-amber-500 font-medium">
                  Verified Course Material Studio Focus
                </span>
              </div>
            </div>

            <button
              onClick={onClose}
              className={`p-1 rounded-lg transition-colors ${
                isDark ? 'text-gray-400 hover:text-white hover:bg-gray-800' : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
              }`}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className={`p-4 rounded-xl border text-sm leading-relaxed ${
            isDark ? 'bg-amber-500/5 border-amber-500/20 text-gray-300' : 'bg-amber-50 border-amber-200 text-amber-900'
          }`}>
            {error.message ||
              "Verified Course Material Studio is exclusively tailored for professors teaching programming languages, algorithms, software engineering, and computer science subjects."}
          </div>

          {/* Quick Suggestions */}
          <div className="space-y-2 pt-2">
            <span className={`text-xs font-semibold uppercase tracking-wider flex items-center ${
              isDark ? 'text-gray-400' : 'text-gray-500'
            }`}>
              <Sparkles className="w-3.5 h-3.5 text-blue-500 mr-1.5" />
              Suggested Coding Topics:
            </span>
            <div className="space-y-1.5">
              {suggestions.map((item, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    onSelectSuggestedTopic(item);
                    onClose();
                  }}
                  className={`w-full text-left p-2.5 rounded-lg border text-xs flex items-center justify-between group transition-all ${
                    isDark
                      ? 'bg-gray-900/80 hover:bg-gray-800 border-gray-800 hover:border-blue-500/40 text-gray-200'
                      : 'bg-gray-50 hover:bg-gray-100 border-gray-200 hover:border-blue-400 text-gray-800'
                  }`}
                >
                  <span className="truncate pr-2 font-medium">{item.topic}</span>
                  <div className="flex items-center space-x-1.5 text-blue-500 shrink-0">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 border border-blue-500/20">
                      {item.tech} {item.version}
                    </span>
                    <ArrowRight className="w-3 h-3 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={onClose}
              className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-sm font-semibold text-white shadow-lg shadow-blue-500/20 transition-colors"
            >
              Got it, let me adjust
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
