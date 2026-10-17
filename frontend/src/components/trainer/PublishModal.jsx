import React, { useState, useEffect } from 'react';
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  X,
  FileText,
  HelpCircle,
  Code2,
  Presentation,
  ShieldCheck,
  History,
  Trash2,
} from 'lucide-react';

export default function PublishModal({
  deck,
  materials,
  onClose,
  theme,
  token,
  user,
}) {
  const isDark = theme === 'dark';
  const [subjects, setSubjects] = useState([]);
  const [selectedSubject, setSelectedSubject] = useState('');
  const [newSubjectName, setNewSubjectName] = useState('');
  const [includeSlides, setIncludeSlides] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [publications, setPublications] = useState([]);
  const [publishSuccess, setPublishSuccess] = useState(null);
  const [error, setError] = useState('');
  const [confirmedWarnings, setConfirmedWarnings] = useState(false);

  // Check for items needing review or low assurance
  const reviewItems = [];
  if (deck?.slides) {
    deck.slides.forEach((s, idx) => {
      if (s.verification_status === 'needs_review' || s.verification_status === 'low_assurance') {
        reviewItems.push(`Slide #${idx + 1}: ${s.title || 'Untitled'} (${s.verification_status})`);
      }
    });
  }
  if (materials?.exercises) {
    materials.exercises.forEach((ex, idx) => {
      if (ex.proof_status === 'needs_review' || ex.proof_status === 'low_assurance') {
        reviewItems.push(`Exercise #${idx + 1}: ${ex.title || 'Untitled'} (${ex.proof_status})`);
      }
    });
  }

  const allMaterialsReady = deck && materials && materials.notes && materials.quiz && materials.exercises;

  const fetchSubjectsAndPubs = async () => {
    try {
      const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch('http://localhost:8000/api/trainer/subjects', {
        headers: authHeader,
      });
      if (res.ok) {
        const data = await res.json();
        setSubjects(data);
        if (data.length > 0 && !selectedSubject) {
          setSelectedSubject(data[0].name);
        }
      }

      const pRes = await fetch('http://localhost:8000/api/trainer/publications', {
        headers: authHeader,
      });
      if (pRes.ok) {
        const pData = await pRes.json();
        setPublications(pData);
      }
    } catch (e) {
      console.error('Error fetching subjects:', e);
    }
  };

  useEffect(() => {
    fetchSubjectsAndPubs();
    if (deck?.topic && !selectedSubject) {
      setSelectedSubject(deck.topic);
    }
  }, [deck]);

  const handlePublish = async () => {
    if (reviewItems.length > 0 && !confirmedWarnings) {
      alert('Please confirm that you acknowledge the items requiring review before publishing.');
      return;
    }

    const subjectToUse = (selectedSubject === '__new__' ? newSubjectName : selectedSubject) || deck?.topic;
    if (!subjectToUse.trim()) {
      setError('Please provide a valid subject name');
      return;
    }

    setPublishing(true);
    setError('');
    setPublishSuccess(null);

    try {
      const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch('http://localhost:8000/api/trainer/publish', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeader,
        },
        body: JSON.stringify({
          deck_id: deck.id,
          subject_name: subjectToUse.trim(),
          include_slides: includeSlides,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Publishing failed');
      }

      const data = await res.json();
      setPublishSuccess(data);
      fetchSubjectsAndPubs();
    } catch (e) {
      setError(e.message || 'Publishing failed');
    } finally {
      setPublishing(false);
    }
  };

  const handleUnpublish = async (pubId) => {
    if (!confirm('Are you sure you want to unpublish this version from students?')) return;
    try {
      const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
      const res = await fetch(`http://localhost:8000/api/trainer/unpublish/${pubId}`, {
        method: 'POST',
        headers: authHeader,
      });
      if (res.ok) {
        fetchSubjectsAndPubs();
      } else {
        const err = await res.json();
        alert(err.detail || 'Failed to unpublish');
      }
    } catch (e) {
      alert('Error unpublishing');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in">
      <div className={`w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl p-6 sm:p-8 border shadow-2xl transition-all ${
        isDark ? 'bg-[#0E131F] border-gray-800 text-white' : 'bg-white border-gray-200 text-gray-900'
      }`}>
        <div className="flex items-center justify-between pb-4 border-b border-gray-700/50">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20 text-white">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-heading font-bold text-xl tracking-tight">Publish to Student Dashboard</h3>
              <p className={`text-xs ${isDark ? 'text-gray-400' : 'text-gray-500'}`}>
                Converts material into student-safe packages (zero answers, zero solutions)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className={`p-2 rounded-xl border transition-all ${
              isDark ? 'border-gray-800 hover:bg-gray-800 text-gray-400' : 'border-gray-200 hover:bg-gray-100 text-gray-600'
            }`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="mt-4 p-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-xs flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {publishSuccess ? (
          <div className="mt-6 space-y-4">
            <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <div className="flex items-center space-x-2 font-bold text-sm">
                <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                <span>Published Successfully as Version {publishSuccess.version}!</span>
              </div>
              <p className="text-xs text-emerald-300 mt-2">
                {publishSuccess.message}
              </p>
              <div className="mt-3 p-3 rounded-lg bg-black/40 font-mono text-[11px] text-gray-300 space-y-1">
                <div>📁 Storage: {publishSuccess.published_path}</div>
                <div>🔒 Security: Verified 100% free of answers & solutions</div>
                <div>📦 Modules: Notes PDF, Quiz (questions only), Exercises (starter + tests)</div>
              </div>
            </div>

            <div className="flex justify-end space-x-3 pt-2">
              <button
                onClick={() => setPublishSuccess(null)}
                className={`px-4 py-2 rounded-xl text-xs font-semibold border ${
                  isDark ? 'border-gray-700 hover:bg-gray-800' : 'border-gray-300 hover:bg-gray-100'
                }`}
              >
                Publish Another
              </button>
              <button
                onClick={onClose}
                className="px-5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-lg shadow-emerald-500/20"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            {/* Prerequisite Checklist */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Material Readiness Checks
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className={`p-2.5 rounded-xl border flex items-center space-x-2 text-xs font-medium ${
                  deck ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-red-500/10 border-red-500/30 text-red-400'
                }`}>
                  <Presentation className="w-4 h-4 shrink-0" />
                  <span>Slide Deck {deck ? '✓' : '✗'}</span>
                </div>
                <div className={`p-2.5 rounded-xl border flex items-center space-x-2 text-xs font-medium ${
                  materials?.notes ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                }`}>
                  <FileText className="w-4 h-4 shrink-0" />
                  <span>Notes {materials?.notes ? '✓' : 'Pending'}</span>
                </div>
                <div className={`p-2.5 rounded-xl border flex items-center space-x-2 text-xs font-medium ${
                  materials?.quiz ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                }`}>
                  <HelpCircle className="w-4 h-4 shrink-0" />
                  <span>Quiz {materials?.quiz ? '✓' : 'Pending'}</span>
                </div>
                <div className={`p-2.5 rounded-xl border flex items-center space-x-2 text-xs font-medium ${
                  materials?.exercises ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                }`}>
                  <Code2 className="w-4 h-4 shrink-0" />
                  <span>Exercises {materials?.exercises ? '✓' : 'Pending'}</span>
                </div>
              </div>
            </div>

            {/* Warnings if needs review or low assurance */}
            {reviewItems.length > 0 && (
              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400 space-y-2">
                <div className="flex items-center space-x-2 font-bold text-xs">
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                  <span>Warning: {reviewItems.length} items require review / have low assurance:</span>
                </div>
                <ul className="text-[11px] list-disc list-inside space-y-0.5 max-h-24 overflow-y-auto pl-1">
                  {reviewItems.map((item, idx) => (
                    <li key={idx}>{item}</li>
                  ))}
                </ul>
                <div className="pt-2 flex items-center space-x-2">
                  <input
                    type="checkbox"
                    id="confirm_warnings"
                    checked={confirmedWarnings}
                    onChange={(e) => setConfirmedWarnings(e.target.checked)}
                    className="w-4 h-4 text-amber-500 rounded cursor-pointer"
                  />
                  <label htmlFor="confirm_warnings" className="text-xs cursor-pointer font-medium">
                    I acknowledge these items and wish to publish anyway
                  </label>
                </div>
              </div>
            )}

            {/* Subject Selector */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-gray-300">
                Target Subject / Course
              </label>
              <div className="space-y-2">
                <select
                  value={selectedSubject}
                  onChange={(e) => setSelectedSubject(e.target.value)}
                  className={`w-full rounded-xl px-4 py-2.5 text-xs border focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
                    isDark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'
                  }`}
                >
                  <option value={deck?.topic || 'Current Deck'}>
                    Use Deck Topic: {deck?.topic || 'Untitled'}
                  </option>
                  {subjects.map((s) => (
                    <option key={s.id} value={s.name}>
                      {s.name} ({s.folder_slug})
                    </option>
                  ))}
                  <option value="__new__">+ Create New Subject Folder...</option>
                </select>

                {selectedSubject === '__new__' && (
                  <input
                    type="text"
                    value={newSubjectName}
                    onChange={(e) => setNewSubjectName(e.target.value)}
                    placeholder="Enter new subject name e.g. Advanced Operating Systems"
                    className={`w-full rounded-xl px-4 py-2 text-xs border focus:outline-none focus:ring-2 focus:ring-emerald-500 ${
                      isDark ? 'bg-gray-900 border-gray-700 text-white' : 'bg-gray-50 border-gray-300 text-gray-900'
                    }`}
                  />
                )}
              </div>
            </div>

            {/* Include Slides Checkbox */}
            <div className={`p-3 rounded-xl border flex items-center justify-between ${
              isDark ? 'bg-gray-900/60 border-gray-800' : 'bg-gray-50 border-gray-200'
            }`}>
              <div className="flex items-center space-x-2.5">
                <input
                  type="checkbox"
                  id="include_slides"
                  checked={includeSlides}
                  onChange={(e) => setIncludeSlides(e.target.checked)}
                  className="w-4 h-4 text-emerald-600 rounded cursor-pointer"
                />
                <label htmlFor="include_slides" className="text-xs font-medium cursor-pointer">
                  Include Slides PDF for student download
                </label>
              </div>
              <span className="text-[10px] font-mono text-emerald-400">
                slides/deck.pdf
              </span>
            </div>

            {/* Publishing Guarantee Note */}
            <div className="p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs flex items-center space-x-2.5">
              <ShieldCheck className="w-5 h-5 shrink-0" />
              <span>
                <strong>Academic Integrity Guarantee:</strong> Answers, reference solutions, and proof test harnesses are strictly isolated and never copied to published folders.
              </span>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={onClose}
                className={`px-4 py-2 rounded-xl text-xs font-semibold border ${
                  isDark ? 'border-gray-700 hover:bg-gray-800 text-gray-300' : 'border-gray-300 hover:bg-gray-100 text-gray-700'
                }`}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePublish}
                disabled={publishing || !allMaterialsReady || (reviewItems.length > 0 && !confirmedWarnings)}
                className={`px-6 py-2.5 rounded-xl font-bold text-xs text-white flex items-center space-x-2 shadow-lg transition-all ${
                  publishing || !allMaterialsReady || (reviewItems.length > 0 && !confirmedWarnings)
                    ? 'bg-emerald-600/50 cursor-not-allowed'
                    : 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/20 hover:scale-[1.02]'
                }`}
              >
                <UploadCloud className={`w-4 h-4 ${publishing ? 'animate-bounce' : ''}`} />
                <span>{publishing ? 'Publishing...' : 'Publish to Students'}</span>
              </button>
            </div>

            {/* Publications History */}
            {publications.length > 0 && (
              <div className="pt-4 border-t border-gray-700/50 space-y-2">
                <div className="flex items-center space-x-1.5 text-xs font-semibold text-gray-400">
                  <History className="w-3.5 h-3.5" />
                  <span>Existing Institute Publications ({publications.length})</span>
                </div>
                <div className="max-h-36 overflow-y-auto space-y-1.5">
                  {publications.map((pub) => (
                    <div
                      key={pub.id}
                      className={`p-2.5 rounded-xl border flex items-center justify-between text-xs ${
                        isDark ? 'bg-gray-900 border-gray-800' : 'bg-gray-50 border-gray-200'
                      }`}
                    >
                      <div>
                        <div className="font-semibold text-white flex items-center space-x-2">
                          <span>{pub.subject_name || pub.folder_slug}</span>
                          <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-blue-500/20 text-blue-400">
                            v{pub.version}
                          </span>
                          <span className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                            pub.status === 'published' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-gray-500/20 text-gray-400'
                          }`}>
                            {pub.status}
                          </span>
                        </div>
                        <div className="text-[10px] text-gray-400 mt-0.5">
                          Published: {pub.published_at ? new Date(pub.published_at).toLocaleString() : 'N/A'}
                        </div>
                      </div>
                      {pub.status === 'published' && (
                        <button
                          onClick={() => handleUnpublish(pub.id)}
                          className="px-2.5 py-1 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 text-[11px] font-semibold transition-all flex items-center space-x-1"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Unpublish</span>
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
