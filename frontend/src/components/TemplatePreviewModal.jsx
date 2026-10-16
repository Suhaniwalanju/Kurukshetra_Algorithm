import React, { useState, useEffect } from 'react';
import { X, Eye, Edit3, Save, CheckCircle, RefreshCw, Palette, Layers } from 'lucide-react';

export default function TemplatePreviewModal({ college, onClose, onConfigSaved }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [jsonText, setJsonText] = useState('');
  const [saveStatus, setSaveStatus] = useState('');
  const [previewTimestamp, setPreviewTimestamp] = useState(Date.now());
  const [visibleZones, setVisibleZones] = useState({
    title: true,
    content: true,
    code: true,
    diagram: true,
    presented_by: true,
    footer: true,
  });

  useEffect(() => {
    fetchConfig();
  }, [college]);

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const res = await fetch(`http://localhost:8000/api/templates/${college}/config`);
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
        setJsonText(JSON.stringify(data, null, 2));
      }
    } catch (err) {
      console.error('Error fetching template config:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveJson = async () => {
    try {
      setSaveStatus('Saving...');
      const parsed = JSON.parse(jsonText);
      const res = await fetch(`http://localhost:8000/api/templates/${college}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: jsonText,
      });
      if (res.ok) {
        setConfig(parsed);
        setSaveStatus('Saved successfully!');
        setPreviewTimestamp(Date.now());
        if (onConfigSaved) onConfigSaved(parsed);
        setTimeout(() => {
          setSaveStatus('');
          setEditMode(false);
        }, 1200);
      } else {
        const err = await res.json();
        setSaveStatus(`Save failed: ${err.detail || 'Invalid format'}`);
      }
    } catch (e) {
      setSaveStatus(`Invalid JSON: ${e.message}`);
    }
  };

  if (!college) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-[#0F172A] border border-gray-800 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between bg-gray-900/50">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/20 text-blue-400 flex items-center justify-center font-bold">
              {college[0]}
            </div>
            <div>
              <h3 className="font-heading font-bold text-lg text-white">
                Template Layout Config: <span className="text-blue-400">{college}</span>
              </h3>
              <p className="text-xs text-gray-400">
                Full-slide background with auto-detected safe boundaries & brand colors
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setEditMode(!editMode)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition-colors ${
                editMode
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-800 hover:bg-gray-700 text-gray-300'
              }`}
            >
              {editMode ? <Eye className="w-3.5 h-3.5" /> : <Edit3 className="w-3.5 h-3.5" />}
              <span>{editMode ? 'Visual Overlay View' : 'Edit JSON Config'}</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-20 text-gray-400">
              <RefreshCw className="w-6 h-6 animate-spin mr-2" />
              Loading template metadata...
            </div>
          ) : editMode ? (
            /* JSON Edit Mode */
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  You can manually fine-tune coordinates (left, top, width, height) in 1920x1080 pixels:
                </span>
                {saveStatus && (
                  <span className={`text-xs font-medium ${saveStatus.includes('failed') ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {saveStatus}
                  </span>
                )}
              </div>
              <textarea
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                rows={20}
                className="w-full bg-[#090D16] border border-gray-800 rounded-xl p-4 font-mono text-xs text-blue-300 focus:outline-none focus:border-blue-500 shadow-inner"
              />
              <div className="flex justify-end space-x-3">
                <button
                  onClick={() => setEditMode(false)}
                  className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-sm text-gray-300"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveJson}
                  className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-sm font-semibold text-white flex items-center space-x-2 shadow-lg shadow-blue-500/20"
                >
                  <Save className="w-4 h-4" />
                  <span>Save Layout Config</span>
                </button>
              </div>
            </div>
          ) : (
            /* Visual Overlay View */
            <div className="space-y-6">
              {/* Image Preview with Overlay */}
              <div className="relative rounded-xl border border-gray-800 overflow-hidden bg-black aspect-video flex items-center justify-center shadow-2xl">
                <img
                  src={`http://localhost:8000/api/templates/${college}/preview?t=${previewTimestamp}`}
                  alt={`${college} Layout Zones`}
                  className="w-full h-full object-contain"
                />
              </div>

              {/* Sampled Brand Colors and Fonts */}
              {config && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Colors */}
                  <div className="glass-card rounded-xl p-4 border border-gray-800">
                    <div className="flex items-center space-x-2 mb-3">
                      <Palette className="w-4 h-4 text-purple-400" />
                      <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Sampled Brand Colors
                      </h4>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <div className="flex items-center space-x-2 bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800">
                        <span className="w-4 h-4 rounded-full border border-white/20" style={{ backgroundColor: config.colors.primary }} />
                        <span className="text-xs text-gray-300">Primary:</span>
                        <span className="font-mono text-xs text-white">{config.colors.primary}</span>
                      </div>
                      <div className="flex items-center space-x-2 bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800">
                        <span className="w-4 h-4 rounded-full border border-white/20" style={{ backgroundColor: config.colors.secondary }} />
                        <span className="text-xs text-gray-300">Secondary:</span>
                        <span className="font-mono text-xs text-white">{config.colors.secondary}</span>
                      </div>
                      <div className="flex items-center space-x-2 bg-gray-900 px-3 py-1.5 rounded-lg border border-gray-800">
                        <span className="w-4 h-4 rounded-full border border-white/20" style={{ backgroundColor: config.colors.text }} />
                        <span className="text-xs text-gray-300">Text:</span>
                        <span className="font-mono text-xs text-white">{config.colors.text}</span>
                      </div>
                    </div>
                  </div>

                  {/* Fonts */}
                  <div className="glass-card rounded-xl p-4 border border-gray-800">
                    <div className="flex items-center space-x-2 mb-3">
                      <Layers className="w-4 h-4 text-blue-400" />
                      <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
                        Configured Typography
                      </h4>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="bg-gray-900 p-2 rounded-lg border border-gray-800 text-center">
                        <span className="text-gray-400 block text-[10px]">Title Font</span>
                        <span className="font-medium text-white">{config.fonts.title}</span>
                      </div>
                      <div className="bg-gray-900 p-2 rounded-lg border border-gray-800 text-center">
                        <span className="text-gray-400 block text-[10px]">Body Font</span>
                        <span className="font-medium text-white">{config.fonts.body}</span>
                      </div>
                      <div className="bg-gray-900 p-2 rounded-lg border border-gray-800 text-center">
                        <span className="text-gray-400 block text-[10px]">Code Font</span>
                        <span className="font-medium text-white">{config.fonts.code}</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Safe zone legend */}
              <div className="flex flex-wrap gap-3 pt-2 text-xs">
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-500/20 border border-blue-500/40 text-blue-300">
                  <span className="w-2 h-2 rounded-full bg-blue-400 mr-2" /> Title Zone
                </span>
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-emerald-500/20 border border-emerald-500/40 text-emerald-300">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 mr-2" /> Content Safe Zone
                </span>
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-purple-500/20 border border-purple-500/40 text-purple-300">
                  <span className="w-2 h-2 rounded-full bg-purple-400 mr-2" /> Code Zone
                </span>
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-pink-500/20 border border-pink-500/40 text-pink-300">
                  <span className="w-2 h-2 rounded-full bg-pink-400 mr-2" /> Diagram Zone
                </span>
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-orange-500/20 border border-orange-500/40 text-orange-300">
                  <span className="w-2 h-2 rounded-full bg-orange-400 mr-2" /> Presented By Zone (Bottom)
                </span>
                <span className="inline-flex items-center px-2.5 py-1 rounded-md bg-slate-500/20 border border-slate-500/40 text-slate-300">
                  <span className="w-2 h-2 rounded-full bg-slate-400 mr-2" /> Footer Zone
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-800 bg-gray-900/60 flex items-center justify-between">
          <span className="text-xs text-gray-400">
            Slide Resolution: <span className="text-white font-mono">1920 x 1080 (16:9 Widescreen)</span>
          </span>
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-sm font-medium text-white transition-colors"
          >
            Confirm & Close
          </button>
        </div>
      </div>
    </div>
  );
}
