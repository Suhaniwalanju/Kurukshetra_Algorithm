import React, { useState, useEffect } from 'react';
import {
  School,
  User,
  BookOpen,
  GraduationCap,
  Clock,
  Code,
  Sparkles,
} from 'lucide-react';

const TECH_PRESETS = [
  { name: 'Java', version: '21' },
  { name: 'Spring Boot', version: '3.x' },
  { name: 'Python', version: '3.12' },
  { name: 'Node.js', version: '20' },
  { name: 'C++', version: '20' },
  { name: 'TypeScript', version: '5.x' },
  { name: 'Go', version: '1.22' },
  { name: 'Rust', version: '1.76' },
];

export default function DeckForm({
  colleges,
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
      setFormData((prev) => ({
        ...prev,
        topic: initialData.topic || prev.topic,
        tech: initialData.tech || prev.tech,
        tech_version: initialData.version || prev.tech_version,
      }));
    }
  }, [initialData]);

  // Derived slide count: ~1 slide per 3-4 minutes + 4 structural slides (cover, agenda, summary, closing)
  const estimatedConceptSlides = Math.max(2, Math.min(12, Math.floor(formData.session_length / 3)));
  const estimatedTotalSlides = estimatedConceptSlides + 4;

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
            onChange={(e) => setFormData({ ...formData, topic: e.target.value })}
            placeholder="Enter coding topic (e.g. Java 21 Virtual Threads, Spring Boot Microservices, etc.)"
            className={`w-full rounded-xl px-4 py-2.5 text-sm border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
              isDark
                ? 'bg-gray-900 border-gray-700 text-white placeholder-gray-500 hover:border-gray-600'
                : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-400 hover:border-gray-400 focus:bg-white'
            }`}
            required
          />
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
              <span>Technology & Version *</span>
            </span>
            <span className={`text-[11px] ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>Quick Presets:</span>
          </label>

          {/* Quick Presets Pills */}
          <div className="flex flex-wrap gap-2">
            {TECH_PRESETS.map((p) => {
              const isMatch = formData.tech === p.name && formData.tech_version === p.version;
              return (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => handlePresetSelect(p)}
                  className={`text-xs px-2.5 py-1 rounded-lg border transition-all ${
                    isMatch
                      ? 'bg-blue-500/10 border-blue-500 text-blue-600 dark:text-blue-400 font-medium'
                      : isDark
                      ? 'bg-gray-900 border-gray-800 text-gray-400 hover:text-white hover:border-gray-700'
                      : 'bg-gray-100 border-gray-200 text-gray-600 hover:text-gray-900 hover:border-gray-300'
                  }`}
                >
                  {p.name} {p.version}
                </button>
              );
            })}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="col-span-2">
              <input
                type="text"
                value={formData.tech}
                onChange={(e) => setFormData({ ...formData, tech: e.target.value })}
                placeholder="Tech e.g. Java, Python, React, C++"
                className={`w-full rounded-xl px-4 py-2.5 text-sm border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                  isDark
                    ? 'bg-gray-900 border-gray-700 text-white placeholder-gray-500 hover:border-gray-600'
                    : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-400 hover:border-gray-400 focus:bg-white'
                }`}
                required
              />
            </div>
            <div>
              <input
                type="text"
                value={formData.tech_version}
                onChange={(e) => setFormData({ ...formData, tech_version: e.target.value })}
                placeholder="Version e.g. 21, 3.12"
                className={`w-full rounded-xl px-4 py-2.5 text-sm border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                  isDark
                    ? 'bg-gray-900 border-gray-700 text-white placeholder-gray-500 hover:border-gray-600'
                    : 'bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-400 hover:border-gray-400 focus:bg-white'
                }`}
              />
            </div>
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
