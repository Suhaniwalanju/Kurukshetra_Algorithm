import React from 'react';
import { Loader2 } from 'lucide-react';

export default function GenerationProgress({ statusMessage, theme }) {
  const isDark = theme === 'dark';

  const steps = [
    { title: "Topic Validation", desc: "Checking coding taxonomy & CS focus" },
    { title: "Template Layout", desc: "Aligning safe zones & brand palette" },
    { title: "Ollama LLM Generation", desc: "Structuring concept slides & executable code" },
    { title: "Collision-Free Solver", desc: "PIL ImageFont measurement & 0.2\" gutter" },
    { title: "PowerPoint Assembly", desc: "Pygments syntax highlighting & blank layout" },
    { title: "Automated Verification", desc: "Checking zero overlap & 8-word bullet limit" },
  ];

  return (
    <div className={`rounded-2xl p-6 sm:p-8 border shadow-xl relative overflow-hidden animate-in fade-in transition-colors duration-200 ${
      isDark
        ? 'bg-[#111827]/90 border-blue-500/30 text-white'
        : 'bg-white border-blue-200 text-gray-900 shadow-md'
    }`}>
      <div className="flex items-center space-x-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-blue-500/20 text-blue-500 flex items-center justify-center animate-spin">
          <Loader2 className="w-5 h-5" />
        </div>
        <div>
          <h3 className="font-heading font-bold text-lg">
            Deck Generation in Progress
          </h3>
          <p className="text-xs text-blue-500 font-mono mt-0.5">
            {statusMessage || "Processing curriculum and executing layout engine..."}
          </p>
        </div>
      </div>

      {/* Progress Bar Animation */}
      <div className={`w-full rounded-full h-2 mb-8 overflow-hidden border ${
        isDark ? 'bg-gray-900 border-gray-800' : 'bg-gray-100 border-gray-200'
      }`}>
        <div className="bg-gradient-to-r from-blue-500 via-indigo-500 to-purple-500 h-2 rounded-full w-3/4 animate-pulse" />
      </div>

      {/* Steps List */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {steps.map((st, i) => (
          <div
            key={i}
            className={`p-3.5 rounded-xl border flex items-start space-x-3 transition-colors ${
              isDark ? 'bg-gray-900/60 border-gray-800' : 'bg-gray-50 border-gray-200'
            }`}
          >
            <div className="w-5 h-5 rounded-full bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-[11px] font-bold text-blue-500 mt-0.5 shrink-0">
              {i + 1}
            </div>
            <div>
              <h4 className="text-xs font-semibold">{st.title}</h4>
              <p className={`text-[11px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>{st.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
