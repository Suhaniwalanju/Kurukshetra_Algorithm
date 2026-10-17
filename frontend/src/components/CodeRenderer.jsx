import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

export default function CodeRenderer({ code = '', language = 'text', title = '' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!code) return;
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const highlightSyntax = (text, lang) => {
    const lines = text.split('\n');
    return lines.map((line, lineIdx) => {
      // Regex tokens for simple syntax highlighting
      const parts = line.split(/(\/\/.*$|#.*$|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:def|class|return|if|else|elif|for|while|import|from|public|static|void|int|float|boolean|String|const|let|var|function|try|catch|throw|assert|new|null|true|false|None|True|False)\b|\b\d+\b)/g);

      return (
        <div key={lineIdx} className="table-row leading-relaxed hover:bg-white/[0.02]">
          <span className="table-cell select-none pr-4 text-right text-[11px] text-gray-600 font-mono w-8">
            {lineIdx + 1}
          </span>
          <span className="table-cell font-mono text-xs whitespace-pre">
            {parts.map((part, partIdx) => {
              if (!part) return null;
              if (part.startsWith('//') || part.startsWith('#')) {
                return <span key={partIdx} className="text-gray-500 italic">{part}</span>;
              }
              if (part.startsWith('"') || part.startsWith("'")) {
                return <span key={partIdx} className="text-emerald-400">{part}</span>;
              }
              if (/^\d+$/.test(part)) {
                return <span key={partIdx} className="text-amber-300">{part}</span>;
              }
              if (/^(def|class|return|if|else|elif|for|while|import|from|public|static|void|int|float|boolean|String|const|let|var|function|try|catch|throw|assert|new|null|true|false|None|True|False)$/.test(part)) {
                return <span key={partIdx} className="text-purple-400 font-semibold">{part}</span>;
              }
              return <span key={partIdx} className="text-gray-200">{part}</span>;
            })}
          </span>
        </div>
      );
    });
  };

  return (
    <div className="rounded-xl overflow-hidden border border-gray-800 bg-[#090D16] shadow-inner text-left my-2">
      <div className="flex items-center justify-between px-3.5 py-2 bg-gray-950/80 border-b border-gray-800/80 text-[11px]">
        <div className="flex items-center space-x-2">
          <span className="px-2 py-0.5 rounded font-mono uppercase text-[10px] font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30">
            {language}
          </span>
          {title && <span className="text-gray-400 font-medium">{title}</span>}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center space-x-1 px-2 py-1 rounded hover:bg-gray-800 text-gray-400 hover:text-white transition-colors"
          title="Copy to clipboard"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 text-[10px]">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span className="text-[10px]">Copy</span>
            </>
          )}
        </button>
      </div>
      <div className="p-3.5 overflow-x-auto">
        <div className="table w-full">
          {highlightSyntax(code, language)}
        </div>
      </div>
    </div>
  );
}
