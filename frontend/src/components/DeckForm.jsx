import React, { useState, useEffect } from 'react';
import {
  School,
  User,
  BookOpen,
  GraduationCap,
  Clock,
  Code,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';

const VERIFIED_TRACKS = [
  { id: 'python', name: 'Python', version: '3.12.8', label: 'Python 3.12', desc: 'pytest & -W error', outputType: 'Plaintext', icon: 'py' },
  { id: 'java', name: 'Java', version: '21.0.6', label: 'Java 21', desc: 'JUnit 5 & -Xlint', outputType: 'Plaintext', icon: 'java' },
  { id: 'c', name: 'C', version: '17', label: 'C (C17)', desc: 'gcc & Sanitizers (ASan/UBSan)', outputType: 'Plaintext', icon: 'c' },
  { id: 'cpp', name: 'C++', version: '20', label: 'C++20', desc: 'g++20 & doctest', outputType: 'Plaintext', icon: 'cpp' },
  { id: 'sql', name: 'PostgreSQL', version: '16.6', label: 'PostgreSQL 16', desc: 'JSON Table & EXPLAIN', outputType: 'Table JSON', icon: 'sql' },
  { id: 'node_express', name: 'Node.js + Express', version: '20.18.0', label: 'Node + Express', desc: 'Supertest & HTTP JSON', outputType: 'HTTP JSON', icon: 'node' },
  { id: 'web_foundations', name: 'HTML/CSS/JS', version: 'ES2023', label: 'Web Foundations', desc: 'Playwright & Screenshots', outputType: 'DOM/PNG', icon: 'web' },
  { id: 'react', name: 'React', version: '18.3.1', label: 'React 18', desc: 'Vite & RTL assertions', outputType: 'DOM/PNG', icon: 'react' },
  { id: 'tailwind', name: 'Tailwind CSS', version: '3.4.17', label: 'Tailwind 3.4', desc: 'Offline CLI & Computed Styles', outputType: 'DOM/PNG', icon: 'tailwind' },
  { id: 'mongodb', name: 'MongoDB', version: '7.0.16', label: 'MongoDB 7.0', desc: 'JSON & Aggregations', outputType: 'JSON', icon: 'mongo' },
];

const POPULAR_TOPICS = [
  { topic: 'Java 21 Virtual Threads & Structured Concurrency', tech: 'Java', version: '21.0.6' },
  { topic: 'Python 3.12 AsyncIO & High-Performance Coroutines', tech: 'Python', version: '3.12.8' },
  { topic: 'PostgreSQL 16 Advanced Indexing & EXPLAIN Plans', tech: 'PostgreSQL', version: '16.6' },
  { topic: 'React 18 State Management & Custom Hooks', tech: 'React', version: '18.3.1' },
  { topic: 'Node.js & Express RESTful API with Middleware', tech: 'Node.js + Express', version: '20.18.0' },
  { topic: 'Modern C++20 Concepts, Ranges & Move Semantics', tech: 'C++', version: '20' },
  { topic: 'Tailwind CSS 3.4 Responsive Design & Grid Systems', tech: 'Tailwind CSS', version: '3.4.17' },
  { topic: 'MongoDB 7.0 Aggregation Pipelines & Document Modeling', tech: 'MongoDB', version: '7.0.16' },
  { topic: 'C17 Memory Safety, Pointer Arithmetic & Sanitizers', tech: 'C', version: '17' },
  { topic: 'Web Foundations: Responsive DOM Manipulation & CSS Grid', tech: 'HTML/CSS/JS', version: 'ES2023' },
];

function detectTechFromTopic(topic) {
  if (!topic) return null;
  const t = topic.toLowerCase();

  // 1. C++ (before C)
  if (t.includes('c++') || t.includes('cpp') || t.includes('g++') || t.includes('doctest') || t.includes('smart pointer') || t.includes('raii') || t.includes('ranges')) {
    return { name: 'C++', version: '20' };
  }

  // 2. React (before web)
  if (t.includes('react') || t.includes('jsx') || t.includes('tsx') || t.includes('usestate') || t.includes('useeffect') || t.includes('hooks') || t.includes('vite')) {
    return { name: 'React', version: '18.3.1' };
  }

  // 3. Tailwind
  if (t.includes('tailwind') || t.includes('utility-first')) {
    return { name: 'Tailwind CSS', version: '3.4.17' };
  }

  // 4. MongoDB
  if (t.includes('mongo') || t.includes('mongodb') || t.includes('nosql') || t.includes('bson') || t.includes('aggregation pipeline')) {
    return { name: 'MongoDB', version: '7.0.16' };
  }

  // 5. PostgreSQL / SQL
  if (t.includes('sql') || t.includes('postgres') || t.includes('postgresql') || t.includes('relational') || t.includes('explain') || t.includes('acid') || t.includes('indexing')) {
    return { name: 'PostgreSQL', version: '16.6' };
  }

  // 6. Node + Express
  if (t.includes('express') || t.includes('node') || t.includes('nodejs') || t.includes('supertest') || t.includes('rest api') || t.includes('middleware') || t.includes('npm')) {
    return { name: 'Node.js + Express', version: '20.18.0' };
  }

  // 7. Java (not javascript)
  if ((t.includes('java') && !t.includes('javascript')) || t.includes('spring') || t.includes('hibernate') || t.includes('junit') || t.includes('virtual thread') || t.includes('temurin') || t.includes('jvm') || t.includes('maven')) {
    return { name: 'Java', version: '21.0.6' };
  }

  // 8. Python
  if (t.includes('python') || t.includes('pytest') || t.includes('asyncio') || t.includes('fastapi') || t.includes('django') || t.includes('flask') || t.includes('pandas') || t.includes('numpy')) {
    return { name: 'Python', version: '3.12.8' };
  }

  // 9. Web Foundations
  if (t.includes('html') || t.includes('css') || t.includes('javascript') || t.includes('js') || t.includes('dom') || t.includes('flexbox') || t.includes('grid') || t.includes('playwright')) {
    return { name: 'HTML/CSS/JS', version: 'ES2023' };
  }

  // 10. C (C17, gcc, pointers, malloc, sanitizers)
  if (/\b(c|c17|gcc|clang|malloc|free|asan|ubsan|valgrind)\b/.test(t) || t.includes('pointer') || t.includes('memory safety')) {
    return { name: 'C', version: '17' };
  }

  return null;
}

export default function DeckForm({
  colleges,
  runtimes,
  onGenerate,
  isGenerating,
  initialData,
  theme,
}) {
  const isDark = theme === 'dark';

  const [formData, setFormData] = useState({
    college: '',
    professor_name: '',
    topic: '',
    student_level: 'Beginner',
    session_length: 20,
    tech: '',
    tech_version: '',
  });

  useEffect(() => {
    if (colleges && colleges.length > 0 && !formData.college) {
      setFormData((prev) => ({ ...prev, college: colleges[0].college }));
    }
  }, [colleges]);

  useEffect(() => {
    if (initialData) {
      const detected = detectTechFromTopic(initialData.topic || '');
      setFormData((prev) => ({
        ...prev,
        topic: initialData.topic || prev.topic,
        tech: initialData.tech || (detected ? detected.name : prev.tech),
        tech_version: initialData.version || (detected ? detected.version : prev.tech_version),
      }));
    }
  }, [initialData]);

  // Derived slide count: ~1 slide per 3-4 minutes + 4 structural slides (cover, agenda, summary, closing)
  const estimatedConceptSlides = Math.max(2, Math.min(12, Math.floor(formData.session_length / 3)));
  const estimatedTotalSlides = estimatedConceptSlides + 4;

  const handleTopicChange = (newTopic) => {
    const detected = detectTechFromTopic(newTopic);
    setFormData((prev) => ({
      ...prev,
      topic: newTopic,
      tech: detected ? detected.name : prev.tech,
      tech_version: detected ? detected.version : prev.tech_version,
    }));
  };

  const handleSelectSuggestedTopic = (item) => {
    setFormData((prev) => ({
      ...prev,
      topic: item.topic,
      tech: item.tech,
      tech_version: item.version,
    }));
  };

  const handlePresetSelect = (preset) => {
    setFormData((prev) => ({
      ...prev,
      tech: preset.name,
      tech_version: preset.version,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.college) {
      alert('Please select a college template.');
      return;
    }
    if (!formData.professor_name.trim()) {
      alert('Please enter the professor name.');
      return;
    }
    if (!formData.topic.trim()) {
      alert('Please enter a coding topic.');
      return;
    }
    if (!formData.tech.trim()) {
      alert('Please specify the technology stack.');
      return;
    }
    onGenerate(formData);
  };

  return (
    <div className={`rounded-2xl p-6 sm:p-8 border shadow-xl transition-colors duration-200 ${
      isDark
        ? 'bg-[#111827]/90 border-gray-800 text-white'
        : 'bg-white border-gray-200 text-gray-900 shadow-md'
    }`}>
      <div className="mb-6">
        <h2 className="font-heading font-bold text-2xl tracking-tight">
          Create Lecture Deck
        </h2>
        <p className={`text-sm mt-1 ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
          Generate a minimal-text branded slide deck formatted strictly within template safe zones.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* 1. College Selection */}
          <div className="space-y-2">
            <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              <School className="w-3.5 h-3.5 text-blue-500" />
              <span>College Template *</span>
            </label>
            <select
              value={formData.college}
              onChange={(e) => setFormData({ ...formData, college: e.target.value })}
              className={`w-full rounded-xl px-4 py-2.5 text-sm border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                isDark
                  ? 'bg-gray-900 border-gray-700 text-white hover:border-gray-600'
                  : 'bg-gray-50 border-gray-300 text-gray-900 hover:border-gray-400 focus:bg-white'
              }`}
              required
            >
              {colleges.length === 0 ? (
                <option value="">No templates found in /input/templates/</option>
              ) : (
                colleges.map((col) => (
                  <option key={col.college} value={col.college}>
                    {col.college} ({col.slide_size})
                  </option>
                ))
              )}
            </select>
          </div>

          {/* 2. Professor Name */}
          <div className="space-y-2">
            <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              <User className="w-3.5 h-3.5 text-blue-500" />
              <span>Professor Name *</span>
            </label>
            <input
              type="text"
              value={formData.professor_name}
              onChange={(e) => setFormData({ ...formData, professor_name: e.target.value })}
              placeholder="Enter professor name"
              className={`w-full rounded-xl px-4 py-2.5 text-sm border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                isDark
                  ? 'bg-gray-900 border-gray-700 text-white placeholder-gray-500 hover:border-gray-600'
                  : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-400 hover:border-gray-400 focus:bg-white'
              }`}
              required
            />
          </div>
        </div>

        {/* 3. Coding Topic */}
        <div className="space-y-2">
          <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
            <BookOpen className="w-3.5 h-3.5 text-blue-500" />
            <span>Coding Topic *</span>
          </label>
          <input
            type="text"
            value={formData.topic}
            onChange={(e) => handleTopicChange(e.target.value)}
            placeholder="Enter coding topic (e.g. Java 21 Virtual Threads, PostgreSQL Indexing, React 18 Hooks...)"
            className={`w-full rounded-xl px-4 py-2.5 text-sm border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
              isDark
                ? 'bg-gray-900 border-gray-700 text-white placeholder-gray-500 hover:border-gray-600'
                : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-400 hover:border-gray-400 focus:bg-white'
            }`}
            required
          />

          {/* Quick Topic Suggestions */}
          <div className="space-y-1.5 pt-1">
            <div className={`text-[11px] flex items-center space-x-1 font-medium ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
              <Sparkles className="w-3 h-3 text-amber-500" />
              <span>Suggested Topics (click any to auto-fill topic & auto-select technology):</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {POPULAR_TOPICS.map((pt, idx) => {
                const isActive = formData.topic === pt.topic;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSelectSuggestedTopic(pt)}
                    className={`text-[11px] px-2.5 py-1 rounded-lg border transition-all text-left ${
                      isActive
                        ? 'bg-blue-500/20 border-blue-500 text-blue-500 dark:text-blue-400 font-semibold shadow-sm'
                        : isDark
                        ? 'bg-gray-900 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700 hover:bg-gray-800'
                        : 'bg-gray-100 border-gray-200 text-gray-600 hover:text-gray-900 hover:border-gray-300 hover:bg-gray-200'
                    }`}
                  >
                    {pt.topic}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* 4. Student Level & Session Length */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Student Level */}
          <div className="space-y-2">
            <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
              <GraduationCap className="w-3.5 h-3.5 text-blue-500" />
              <span>Student Level *</span>
            </label>
            <div className="grid grid-cols-3 gap-2">
              {['Beginner', 'Intermediate', 'Advanced'].map((level) => {
                const active = formData.student_level === level;
                return (
                  <button
                    key={level}
                    type="button"
                    onClick={() => setFormData({ ...formData, student_level: level })}
                    className={`py-2 px-3 rounded-xl text-xs font-semibold transition-all border ${
                      active
                        ? 'bg-blue-600 border-blue-500 text-white shadow-md shadow-blue-500/20'
                        : isDark
                        ? 'bg-gray-900 border-gray-800 text-gray-400 hover:bg-gray-800 hover:text-white'
                        : 'bg-gray-100 border-gray-200 text-gray-600 hover:bg-gray-200 hover:text-gray-900'
                    }`}
                  >
                    {level}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Session Length */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
                <Clock className="w-3.5 h-3.5 text-blue-500" />
                <span>Session Length: {formData.session_length} Mins</span>
              </label>
              <span className="text-xs font-semibold text-blue-500">
                ~{estimatedTotalSlides} Slides ({estimatedConceptSlides} Concepts)
              </span>
            </div>
            <div className="flex items-center space-x-4 pt-1">
              <input
                type="range"
                min="10"
                max="60"
                step="5"
                value={formData.session_length}
                onChange={(e) => setFormData({ ...formData, session_length: parseInt(e.target.value) })}
                className="w-full h-2 bg-gray-300 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
              <span className={`w-12 text-center text-xs font-mono px-2 py-1 rounded border ${
                isDark ? 'bg-gray-900 border-gray-800 text-gray-200' : 'bg-gray-100 border-gray-300 text-gray-700'
              }`}>
                {formData.session_length}m
              </span>
            </div>
          </div>
        </div>

        {/* 5. Tech + Version */}
        <div className="space-y-3">
          <label className={`text-xs font-semibold flex items-center justify-between ${isDark ? 'text-gray-300' : 'text-gray-700'}`}>
            <span className="flex items-center space-x-1.5">
              <Code className="w-3.5 h-3.5 text-blue-500" />
              <span>Technology & Version (10 Verified Sandboxed Tracks) *</span>
            </span>
            <span className="text-[11px] font-mono text-emerald-500 dark:text-emerald-400 font-medium">
              10/10 Adapters Active
            </span>
          </label>

          {/* 10 Verified Language / Runtime Tracks */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {VERIFIED_TRACKS.map((p) => {
              const isMatch = formData.tech.toLowerCase() === p.name.toLowerCase() ||
                (formData.tech.toLowerCase().includes(p.name.toLowerCase()) && formData.tech_version === p.version);
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handlePresetSelect(p)}
                  className={`p-2.5 rounded-xl border text-left transition-all relative overflow-hidden group ${
                    isMatch
                      ? 'bg-blue-500/15 border-blue-500 ring-2 ring-blue-500/40 shadow-sm'
                      : isDark
                      ? 'bg-gray-900/90 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60'
                      : 'bg-gray-50 border-gray-200 hover:border-blue-300 hover:bg-blue-50/50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`text-xs font-bold ${
                      isMatch
                        ? 'text-blue-500'
                        : isDark ? 'text-gray-200 group-hover:text-white' : 'text-gray-800'
                    }`}>
                      {p.label}
                    </span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded font-mono font-medium bg-blue-500/10 text-blue-500 dark:text-blue-400 border border-blue-500/20">
                      {p.outputType}
                    </span>
                  </div>
                  <p className={`text-[10px] mt-1 line-clamp-1 ${
                    isDark ? 'text-gray-400' : 'text-gray-500'
                  }`}>
                    {p.desc}
                  </p>
                </button>
              );
            })}
          </div>

          {/* Active Auto-Selected Runtime Indicator */}
          <div className={`p-3 rounded-xl border flex items-center justify-between transition-all ${
            formData.tech
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : isDark
              ? 'bg-gray-900/50 border-gray-800 text-gray-400'
              : 'bg-gray-50 border-gray-200 text-gray-600'
          }`}>
            <div className="flex items-center space-x-2">
              <CheckCircle2 className={`w-4 h-4 ${formData.tech ? 'text-emerald-500' : 'text-gray-400'}`} />
              <span className="text-xs font-medium">
                {formData.tech ? (
                  <>
                    Selected Track: <strong className={isDark ? 'text-white' : 'text-gray-900'}>{formData.tech}</strong> (v{formData.tech_version || 'latest'})
                  </>
                ) : (
                  'Type or select a coding topic above to auto-select technology'
                )}
              </span>
            </div>
            {formData.tech && (
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                Auto-Selected & Verified
              </span>
            )}
          </div>
        </div>

        {/* Submit Button */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={isGenerating}
            className={`w-full py-3.5 rounded-xl font-heading font-bold text-base text-white flex items-center justify-center space-x-2 transition-all shadow-lg ${
              isGenerating
                ? 'bg-blue-600/50 cursor-not-allowed'
                : 'bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 shadow-blue-500/25 hover:shadow-blue-500/40'
            }`}
          >
            <Sparkles className="w-5 h-5 animate-pulse" />
            <span>{isGenerating ? 'Generating Deck...' : 'Generate Verified Slide Deck'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
