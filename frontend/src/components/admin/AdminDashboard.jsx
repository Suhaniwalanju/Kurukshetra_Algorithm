import React, { useState, useEffect } from 'react';
import {
  School,
  Upload,
  Users,
  GraduationCap,
  BookOpen,
  Sliders,
  RefreshCw,
  Plus,
  Trash2,
  CheckCircle2,
  AlertTriangle,
  Download,
  KeyRound,
  ShieldAlert,
  Copy,
  Eye,
  FileSpreadsheet,
} from 'lucide-react';

export default function AdminDashboard({ token, theme }) {
  const isDark = theme === 'dark';
  const [activeTab, setActiveTab] = useState('overview'); // 'overview', 'template', 'trainers', 'students', 'subjects'

  // Overview metrics
  const [overview, setOverview] = useState(null);
  const [loadingOverview, setLoadingOverview] = useState(true);

  // Institute settings & template
  const [institute, setInstitute] = useState({
    name: '',
    short_name: '',
    contact_email: '',
    safe_area_top: 100,
    safe_area_bottom: 100,
    safe_area_left: 120,
    safe_area_right: 120,
    template_png: '',
  });
  const [savingSettings, setSavingSettings] = useState(false);
  const [templateUploadMessage, setTemplateUploadMessage] = useState('');
  const [previewRefreshKey, setPreviewRefreshKey] = useState(Date.now());

  // Trainers state
  const [trainers, setTrainers] = useState([]);
  const [showAddTrainerModal, setShowAddTrainerModal] = useState(false);
  const [newTrainer, setNewTrainer] = useState({ display_name: '', login_id: '', contact_email: '' });
  const [tempPasswordModal, setTempPasswordModal] = useState(null); // { user, password, title }

  // Students state
  const [students, setStudents] = useState([]);
  const [showAddStudentModal, setShowAddStudentModal] = useState(false);
  const [newStudent, setNewStudent] = useState({ roll_number: '', display_name: '', class_branch: '' });
  const [showBulkUploadModal, setShowBulkUploadModal] = useState(false);
  const [bulkCsvText, setBulkCsvText] = useState('');
  const [downloadableCredentials, setDownloadableCredentials] = useState(null);

  // Subjects state
  const [subjects, setSubjects] = useState([]);
  const [showAddSubjectModal, setShowAddSubjectModal] = useState(false);
  const [newSubject, setNewSubject] = useState({ name: '', folder_slug: '' });

  // Common headers
  const authHeaders = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // Fetch initial data
  const fetchOverview = async () => {
    try {
      setLoadingOverview(true);
      const res = await fetch('http://localhost:8000/api/admin/overview', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setOverview(data);
        if (data.institute) {
          setInstitute(data.institute);
        }
      }
    } catch (err) {
      console.error('Error fetching overview:', err);
    } finally {
      setLoadingOverview(false);
    }
  };

  const fetchTrainers = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/admin/trainers', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTrainers(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  const fetchStudents = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/admin/students', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setStudents(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  const fetchSubjects = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/admin/subjects', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setSubjects(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchOverview();
    fetchTrainers();
    fetchStudents();
    fetchSubjects();
  }, [token]);

  // Handle Save Settings
  const handleSaveInstituteSettings = async (e) => {
    if (e) e.preventDefault();
    try {
      setSavingSettings(true);
      const res = await fetch('http://localhost:8000/api/admin/institute', {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify(institute),
      });
      if (res.ok) {
        const data = await res.json();
        setInstitute(data.institute);
        setPreviewRefreshKey(Date.now());
        alert('Institute settings and safe areas saved successfully!');
      } else {
        alert('Failed to save settings.');
      }
    } catch (err) {
      console.error(err);
      alert('Network error saving settings.');
    } finally {
      setSavingSettings(false);
    }
  };

  // Handle Template PNG Upload
  const handleTemplateUpload = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.png')) {
      alert('Only .png image files are permitted.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert('Image file size exceeds 10 MB limit.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      setTemplateUploadMessage('Uploading and analyzing template PNG...');
      const res = await fetch('http://localhost:8000/api/admin/institute/template', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        setTemplateUploadMessage(data.message);
        setPreviewRefreshKey(Date.now());
        fetchOverview();
      } else {
        setTemplateUploadMessage(`Error: ${data.detail || 'Upload failed'}`);
      }
    } catch (err) {
      console.error(err);
      setTemplateUploadMessage('Network error uploading template.');
    }
  };

  // Create Trainer
  const handleCreateTrainer = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('http://localhost:8000/api/admin/trainers', {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(newTrainer),
      });
      const data = await res.json();
      if (res.ok) {
        setShowAddTrainerModal(false);
        setNewTrainer({ display_name: '', login_id: '', contact_email: '' });
        fetchTrainers();
        fetchOverview();
        setTempPasswordModal({
          title: 'Trainer Created Successfully',
          name: data.trainer.display_name,
          loginId: data.trainer.login_id,
          password: data.temporary_password,
        });
      } else {
        alert(data.detail || 'Failed to create trainer');
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Reset Trainer Password
  const handleResetTrainerPassword = async (trainerId, trainerName) => {
    if (!confirm(`Reset password for ${trainerName}?`)) return;
    try {
      const res = await fetch(`http://localhost:8000/api/admin/trainers/${trainerId}/reset-password`, {
        method: 'POST',
        headers: authHeaders,
      });
      const data = await res.json();
      if (res.ok) {
        setTempPasswordModal({
          title: 'Password Reset',
          name: trainerName,
          password: data.temporary_password,
        });
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Toggle Trainer Active
  const handleToggleTrainerActive = async (trainer) => {
    try {
      await fetch(`http://localhost:8000/api/admin/trainers/${trainer.id}`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({ is_active: !trainer.is_active }),
      });
      fetchTrainers();
    } catch (err) {
      console.error(err);
    }
  };

  // Create Single Student
  const handleCreateStudent = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('http://localhost:8000/api/admin/students', {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(newStudent),
      });
      const data = await res.json();
      if (res.ok) {
        setShowAddStudentModal(false);
        setNewStudent({ roll_number: '', display_name: '', class_branch: '' });
        fetchStudents();
        fetchOverview();
        setTempPasswordModal({
          title: 'Student Registered Successfully',
          name: data.student.display_name,
          loginId: data.student.roll_number,
          password: data.passkey,
          isStudent: true,
        });
      } else {
        alert(data.detail || 'Failed to register student');
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Handle Bulk Students CSV
  const handleBulkUploadStudents = async () => {
    if (!bulkCsvText.trim()) return;
    const blob = new Blob([bulkCsvText], { type: 'text/csv' });
    const formData = new FormData();
    formData.append('file', blob, 'students.csv');

    try {
      const res = await fetch('http://localhost:8000/api/admin/students/bulk', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const data = await res.json();
      if (res.ok) {
        setDownloadableCredentials(data.credentials);
        fetchStudents();
        fetchOverview();
      } else {
        alert(data.detail || 'Bulk upload failed');
      }
    } catch (err) {
      console.error(err);
    }
  };

  const downloadCredentialsCsv = () => {
    if (!downloadableCredentials) return;
    let csv = 'Roll Number,Name,Class/Branch,Passkey\n';
    downloadableCredentials.forEach((c) => {
      csv += `"${c.roll_number}","${c.name}","${c.class_branch}","${c.passkey}"\n`;
    });
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Student_Credentials_${institute.short_name || 'DPU'}.csv`;
    a.click();
  };

  // Create Subject
  const handleCreateSubject = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch('http://localhost:8000/api/admin/subjects', {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(newSubject),
      });
      const data = await res.json();
      if (res.ok) {
        setShowAddSubjectModal(false);
        setNewSubject({ name: '', folder_slug: '' });
        fetchSubjects();
        fetchOverview();
      } else {
        alert(data.detail || 'Failed to add subject');
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Toggle Subject Active
  const handleToggleSubjectActive = async (subject) => {
    try {
      await fetch(`http://localhost:8000/api/admin/subjects/${subject.id}`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({ is_active: !subject.is_active }),
      });
      fetchSubjects();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Top Header & Navigation Tabs */}
      <div className={`p-6 rounded-3xl border shadow-xl flex flex-col md:flex-row md:items-center md:justify-between gap-4 transition-colors ${
        isDark ? 'bg-slate-900/80 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
      }`}>
        <div>
          <div className="flex items-center space-x-2">
            <span className="text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
              Admin Portal
            </span>
            <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {institute.name} ({institute.short_name})
            </span>
          </div>
          <h2 className="font-heading font-extrabold text-2xl tracking-tight mt-1">
            Institute Governance & Branding Control
          </h2>
        </div>

        {/* Navigation Tabs */}
        <div className={`flex flex-wrap items-center p-1 rounded-2xl border ${
          isDark ? 'bg-slate-950/80 border-slate-800' : 'bg-slate-100 border-slate-200'
        }`}>
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'overview'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Overview & Template
          </button>
          <button
            onClick={() => setActiveTab('trainers')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'trainers'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Trainers ({trainers.length})
          </button>
          <button
            onClick={() => setActiveTab('students')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'students'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Students ({students.length})
          </button>
          <button
            onClick={() => setActiveTab('subjects')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all ${
              activeTab === 'subjects'
                ? 'bg-purple-600 text-white shadow-md shadow-purple-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Subjects ({subjects.length})
          </button>
        </div>
      </div>

      {/* ------------------------------------------------------------- */}
      {/* TAB 1: OVERVIEW & TEMPLATE BRANDING SETTINGS                  */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'overview' && (
        <div className="space-y-6 animate-fade-in">
          {/* Metrics Overview Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className={`p-4 rounded-2xl border ${isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-white border-slate-200'}`}>
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs font-medium">Trainers</span>
                <Users className="w-4 h-4 text-blue-400" />
              </div>
              <span className="text-2xl font-extrabold">{overview?.metrics?.trainers_count ?? trainers.length}</span>
            </div>

            <div className={`p-4 rounded-2xl border ${isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-white border-slate-200'}`}>
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs font-medium">Students</span>
                <GraduationCap className="w-4 h-4 text-emerald-400" />
              </div>
              <span className="text-2xl font-extrabold">{overview?.metrics?.students_count ?? students.length}</span>
            </div>

            <div className={`p-4 rounded-2xl border ${isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-white border-slate-200'}`}>
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs font-medium">Published Subjects</span>
                <BookOpen className="w-4 h-4 text-purple-400" />
              </div>
              <span className="text-2xl font-extrabold">{overview?.metrics?.published_subjects_count ?? 0}</span>
            </div>

            <div className={`p-4 rounded-2xl border ${isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-white border-slate-200'}`}>
              <div className="flex items-center justify-between text-slate-400 mb-1">
                <span className="text-xs font-medium">Template Status</span>
                <School className="w-4 h-4 text-amber-400" />
              </div>
              <span className="text-sm font-bold text-emerald-400 flex items-center space-x-1 mt-1">
                <CheckCircle2 className="w-4 h-4" />
                <span>1920×1080 Active</span>
              </span>
            </div>
          </div>

          {/* Two-Column: Left Settings & Upload, Right Live Preview */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Left: Institute & Safe Area Controls */}
            <div className={`lg:col-span-5 p-6 rounded-3xl border space-y-6 ${
              isDark ? 'bg-slate-900/70 border-slate-800' : 'bg-white border-slate-200'
            }`}>
              <div>
                <h3 className="font-heading font-bold text-lg flex items-center space-x-2">
                  <Sliders className="w-5 h-5 text-purple-400" />
                  <span>Template & Safe-Area Settings</span>
                </h3>
                <p className={`text-xs mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                  Margins guarantee generated code and text never collide with institute artwork.
                </p>
              </div>

              {/* Template PNG Upload */}
              <div className="space-y-2">
                <label className="text-xs font-semibold block">Template PNG Upload (1920×1080 16:9)</label>
                <div className="flex items-center space-x-3">
                  <label className="cursor-pointer px-4 py-2.5 rounded-xl border border-dashed border-purple-500/40 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 font-semibold text-xs flex items-center space-x-2 transition-all">
                    <Upload className="w-4 h-4" />
                    <span>Upload Template PNG</span>
                    <input
                      type="file"
                      accept=".png,image/png"
                      className="hidden"
                      onChange={handleTemplateUpload}
                    />
                  </label>
                  <span className="text-[11px] text-slate-400">Max 10 MB PNG</span>
                </div>
                {templateUploadMessage && (
                  <p className="text-xs text-purple-400 font-medium">{templateUploadMessage}</p>
                )}
              </div>

              {/* Margin Controls */}
              <form onSubmit={handleSaveInstituteSettings} className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold">Institute Name</label>
                    <input
                      type="text"
                      value={institute.name}
                      onChange={(e) => setInstitute({ ...institute, name: e.target.value })}
                      className={`w-full rounded-xl px-3 py-2 text-xs border ${
                        isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                      }`}
                      required
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold">Short Name (Code)</label>
                    <input
                      type="text"
                      value={institute.short_name}
                      onChange={(e) => setInstitute({ ...institute, short_name: e.target.value })}
                      className={`w-full rounded-xl px-3 py-2 text-xs border ${
                        isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                      }`}
                      required
                    />
                  </div>
                </div>

                {/* Safe Area Margins Sliders */}
                <div className="pt-2 border-t border-slate-800/40 space-y-3">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                    Safe-Area Margins (Pixels)
                  </span>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Top Margin</span>
                        <span className="font-bold text-purple-400">{institute.safe_area_top} px</span>
                      </div>
                      <input
                        type="range"
                        min="20"
                        max="250"
                        value={institute.safe_area_top}
                        onChange={(e) => setInstitute({ ...institute, safe_area_top: Number(e.target.value) })}
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Bottom Margin</span>
                        <span className="font-bold text-purple-400">{institute.safe_area_bottom} px</span>
                      </div>
                      <input
                        type="range"
                        min="20"
                        max="250"
                        value={institute.safe_area_bottom}
                        onChange={(e) => setInstitute({ ...institute, safe_area_bottom: Number(e.target.value) })}
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Left Margin</span>
                        <span className="font-bold text-purple-400">{institute.safe_area_left} px</span>
                      </div>
                      <input
                        type="range"
                        min="20"
                        max="400"
                        value={institute.safe_area_left}
                        onChange={(e) => setInstitute({ ...institute, safe_area_left: Number(e.target.value) })}
                        className="w-full accent-purple-500"
                      />
                    </div>

                    <div className="space-y-1">
                      <div className="flex justify-between text-xs">
                        <span>Right Margin</span>
                        <span className="font-bold text-purple-400">{institute.safe_area_right} px</span>
                      </div>
                      <input
                        type="range"
                        min="20"
                        max="400"
                        value={institute.safe_area_right}
                        onChange={(e) => setInstitute({ ...institute, safe_area_right: Number(e.target.value) })}
                        className="w-full accent-purple-500"
                      />
                    </div>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={savingSettings}
                  className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs shadow-lg shadow-purple-600/20 transition-all flex items-center justify-center space-x-1.5"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{savingSettings ? 'Saving Settings...' : 'Save Institute & Safe-Area Settings'}</span>
                </button>
              </form>
            </div>

            {/* Right: Live Sample Slide Preview */}
            <div className={`lg:col-span-7 p-6 rounded-3xl border flex flex-col justify-between ${
              isDark ? 'bg-slate-900/70 border-slate-800' : 'bg-white border-slate-200'
            }`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <Eye className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-bold uppercase tracking-wider">
                    Live Sample Slide Preview (With Safe Area Overlay)
                  </span>
                </div>
                <button
                  onClick={() => setPreviewRefreshKey(Date.now())}
                  className="text-xs text-purple-400 flex items-center space-x-1 hover:underline"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Refresh Preview</span>
                </button>
              </div>

              <div className="rounded-2xl overflow-hidden border border-slate-800 bg-black aspect-video flex items-center justify-center shadow-2xl relative">
                <img
                  src={`http://localhost:8000/api/admin/institute/preview?t=${previewRefreshKey}`}
                  alt="Sample Slide Preview"
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    e.target.style.display = 'none';
                  }}
                />
              </div>

              <p className={`text-[11px] mt-3 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                The green border represents your configured Safe-Area. All generated title text, concept bullet points, and syntax-highlighted code blocks strictly conform within these boundaries.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 2: MANAGE TRAINERS                                        */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'trainers' && (
        <div className={`p-6 rounded-3xl border shadow-xl space-y-6 animate-fade-in ${
          isDark ? 'bg-slate-900/80 border-slate-800' : 'bg-white border-slate-200'
        }`}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-heading font-bold text-lg">Trainer Faculty Management</h3>
              <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Trainers generate decks, lead classes, and publish verified materials.
              </p>
            </div>
            <button
              onClick={() => setShowAddTrainerModal(true)}
              className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-purple-600/20"
            >
              <Plus className="w-4 h-4" />
              <span>Add Trainer</span>
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className={`border-b ${isDark ? 'border-slate-800 text-slate-400' : 'border-slate-200 text-slate-500'}`}>
                  <th className="py-3 px-4">Trainer Name</th>
                  <th className="py-3 px-4">Login ID</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Created</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {trainers.map((tr) => (
                  <tr key={tr.id} className="hover:bg-slate-800/20">
                    <td className="py-3 px-4 font-semibold">{tr.display_name}</td>
                    <td className="py-3 px-4 font-mono text-purple-400">{tr.login_id}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        tr.is_active
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      }`}>
                        {tr.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-400">
                      {tr.created_at ? new Date(tr.created_at).toLocaleDateString() : 'N/A'}
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <button
                        onClick={() => handleResetTrainerPassword(tr.id, tr.display_name)}
                        className="px-2.5 py-1 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 font-medium text-[11px]"
                      >
                        Reset Password
                      </button>
                      <button
                        onClick={() => handleToggleTrainerActive(tr)}
                        className={`px-2.5 py-1 rounded-lg font-medium text-[11px] ${
                          tr.is_active
                            ? 'text-rose-400 hover:bg-rose-500/10'
                            : 'text-emerald-400 hover:bg-emerald-500/10'
                        }`}
                      >
                        {tr.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 3: MANAGE STUDENTS                                        */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'students' && (
        <div className={`p-6 rounded-3xl border shadow-xl space-y-6 animate-fade-in ${
          isDark ? 'bg-slate-900/80 border-slate-800' : 'bg-white border-slate-200'
        }`}>
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h3 className="font-heading font-bold text-lg">Enrolled Students & Passkeys</h3>
              <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Students log in using roll number and passkey to access published course notes, quizzes, and exercises.
              </p>
            </div>
            <div className="flex items-center space-x-2.5">
              <button
                onClick={() => setShowBulkUploadModal(true)}
                className="px-3.5 py-2 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-xs flex items-center space-x-1.5"
              >
                <FileSpreadsheet className="w-4 h-4 text-emerald-400" />
                <span>Bulk CSV Upload</span>
              </button>
              <button
                onClick={() => setShowAddStudentModal(true)}
                className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-purple-600/20"
              >
                <Plus className="w-4 h-4" />
                <span>Add Student</span>
              </button>
            </div>
          </div>

          {/* Downloadable Credentials Alert if available */}
          {downloadableCredentials && (
            <div className="p-4 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-between">
              <div>
                <span className="font-bold text-xs text-emerald-400 block">
                  New Credentials Generated for {downloadableCredentials.length} Students
                </span>
                <span className="text-[11px] text-slate-400">
                  Please download the credentials CSV now. Passkeys are not stored in plaintext.
                </span>
              </div>
              <button
                onClick={downloadCredentialsCsv}
                className="px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-1.5"
              >
                <Download className="w-4 h-4" />
                <span>Download Credentials (.CSV)</span>
              </button>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className={`border-b ${isDark ? 'border-slate-800 text-slate-400' : 'border-slate-200 text-slate-500'}`}>
                  <th className="py-3 px-4">Roll Number</th>
                  <th className="py-3 px-4">Student Name</th>
                  <th className="py-3 px-4">Class / Branch</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40">
                {students.map((st) => (
                  <tr key={st.id} className="hover:bg-slate-800/20">
                    <td className="py-3 px-4 font-mono font-bold text-emerald-400">{st.roll_number}</td>
                    <td className="py-3 px-4 font-semibold">{st.display_name}</td>
                    <td className="py-3 px-4 text-slate-400">{st.class_branch || 'General'}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        st.is_active
                          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                          : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      }`}>
                        {st.is_active ? 'Active' : 'Deactivated'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right space-x-2">
                      <button
                        onClick={async () => {
                          const res = await fetch(`http://localhost:8000/api/admin/students/${st.id}/reset-passkey`, {
                            method: 'POST',
                            headers: authHeaders,
                          });
                          const data = await res.json();
                          if (res.ok) {
                            setTempPasswordModal({
                              title: 'Student Passkey Reset',
                              name: st.display_name,
                              loginId: st.roll_number,
                              password: data.new_passkey,
                              isStudent: true,
                            });
                          }
                        }}
                        className="px-2.5 py-1 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 font-medium text-[11px]"
                      >
                        Reset Passkey
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* TAB 4: MANAGE SUBJECTS                                        */}
      {/* ------------------------------------------------------------- */}
      {activeTab === 'subjects' && (
        <div className={`p-6 rounded-3xl border shadow-xl space-y-6 animate-fade-in ${
          isDark ? 'bg-slate-900/80 border-slate-800' : 'bg-white border-slate-200'
        }`}>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-heading font-bold text-lg">Curriculum Subjects & Topics</h3>
              <p className={`text-xs mt-0.5 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                Add or toggle curriculum subjects that trainers can publish to students.
              </p>
            </div>
            <button
              onClick={() => setShowAddSubjectModal(true)}
              className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-lg shadow-purple-600/20"
            >
              <Plus className="w-4 h-4" />
              <span>Add Subject</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {subjects.map((sub) => (
              <div
                key={sub.id}
                className={`p-5 rounded-2xl border flex flex-col justify-between ${
                  isDark ? 'bg-slate-900/60 border-slate-800' : 'bg-white border-slate-200 shadow-sm'
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-[10px] text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded-md">
                      /{sub.folder_slug}
                    </span>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      sub.is_active ? 'text-emerald-400 bg-emerald-500/10' : 'text-slate-500 bg-slate-800'
                    }`}>
                      {sub.is_active ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                  <h4 className="font-bold text-sm tracking-tight">{sub.name}</h4>
                </div>

                <div className="pt-4 mt-3 border-t border-slate-800/40 flex justify-end">
                  <button
                    onClick={() => handleToggleSubjectActive(sub)}
                    className="text-xs text-purple-400 hover:underline"
                  >
                    {sub.is_active ? 'Disable Subject' : 'Enable Subject'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: Show One-Time Temporary Password / Passkey             */}
      {/* ------------------------------------------------------------- */}
      {tempPasswordModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fade-in">
          <div className={`w-full max-w-md rounded-3xl p-6 border shadow-2xl ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <div className="text-center mb-4">
              <div className="w-12 h-12 mx-auto rounded-2xl bg-purple-500/10 text-purple-400 flex items-center justify-center mb-2">
                <KeyRound className="w-6 h-6" />
              </div>
              <h3 className="font-heading font-bold text-lg">{tempPasswordModal.title}</h3>
              <p className={`text-xs mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
                {tempPasswordModal.name} ({tempPasswordModal.loginId || ''})
              </p>
            </div>

            <div className="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs mb-4">
              <p className="font-bold">Important Security Notice:</p>
              <p className="text-[11px] mt-0.5">
                This password/passkey is displayed only once. Please copy and provide it to the user now.
              </p>
            </div>

            <div className={`p-4 rounded-xl border flex items-center justify-between font-mono font-bold text-sm mb-6 ${
              isDark ? 'bg-slate-950 border-slate-700 text-emerald-400' : 'bg-slate-100 border-slate-300 text-emerald-700'
            }`}>
              <span>{tempPasswordModal.password}</span>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(tempPasswordModal.password);
                  alert('Password copied to clipboard!');
                }}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
                title="Copy password"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>

            <button
              onClick={() => setTempPasswordModal(null)}
              className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs"
            >
              Done & Close
            </button>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: Add Trainer                                            */}
      {/* ------------------------------------------------------------- */}
      {showAddTrainerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fade-in">
          <div className={`w-full max-w-md rounded-3xl p-6 border shadow-2xl ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <h3 className="font-heading font-bold text-lg mb-4">Add Faculty Trainer</h3>
            <form onSubmit={handleCreateTrainer} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Full Name *</label>
                <input
                  type="text"
                  value={newTrainer.display_name}
                  onChange={(e) => setNewTrainer({ ...newTrainer, display_name: e.target.value })}
                  placeholder="e.g. Dr. A. Sharma"
                  className={`w-full rounded-xl px-3.5 py-2 text-xs border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold">Login ID *</label>
                <input
                  type="text"
                  value={newTrainer.login_id}
                  onChange={(e) => setNewTrainer({ ...newTrainer, login_id: e.target.value })}
                  placeholder="e.g. asharma"
                  className={`w-full rounded-xl px-3.5 py-2 text-xs border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                  required
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddTrainerModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-700 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold"
                >
                  Create Trainer
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: Add Single Student                                     */}
      {/* ------------------------------------------------------------- */}
      {showAddStudentModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fade-in">
          <div className={`w-full max-w-md rounded-3xl p-6 border shadow-2xl ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <h3 className="font-heading font-bold text-lg mb-4">Register Student</h3>
            <form onSubmit={handleCreateStudent} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Roll Number *</label>
                <input
                  type="text"
                  value={newStudent.roll_number}
                  onChange={(e) => setNewStudent({ ...newStudent, roll_number: e.target.value })}
                  placeholder="e.g. CS2026_042"
                  className={`w-full rounded-xl px-3.5 py-2 text-xs border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold">Student Full Name *</label>
                <input
                  type="text"
                  value={newStudent.display_name}
                  onChange={(e) => setNewStudent({ ...newStudent, display_name: e.target.value })}
                  placeholder="e.g. Samruddhi K."
                  className={`w-full rounded-xl px-3.5 py-2 text-xs border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold">Class / Branch</label>
                <input
                  type="text"
                  value={newStudent.class_branch}
                  onChange={(e) => setNewStudent({ ...newStudent, class_branch: e.target.value })}
                  placeholder="e.g. TE Computer Science"
                  className={`w-full rounded-xl px-3.5 py-2 text-xs border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddStudentModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-700 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold"
                >
                  Register Student
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: Bulk CSV Upload Students                               */}
      {/* ------------------------------------------------------------- */}
      {showBulkUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fade-in">
          <div className={`w-full max-w-lg rounded-3xl p-6 border shadow-2xl ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <h3 className="font-heading font-bold text-lg mb-2">Bulk Enroll Students via CSV</h3>
            <p className={`text-xs mb-4 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              Paste comma-separated rows: <code className="text-purple-400">roll_number,name,class_branch</code>. Passkeys will be auto-generated for each student.
            </p>

            <textarea
              rows={6}
              value={bulkCsvText}
              onChange={(e) => setBulkCsvText(e.target.value)}
              placeholder="CS101,Aarav Patel,TE Comp&#10;CS102,Diya Sharma,TE Comp&#10;CS103,Rohan Deshmukh,TE Comp"
              className={`w-full rounded-xl p-3 text-xs font-mono border focus:outline-none focus:ring-2 focus:ring-purple-500 mb-4 ${
                isDark ? 'bg-slate-950 border-slate-800 text-white' : 'bg-slate-50 border-slate-300 text-slate-900'
              }`}
            />

            <div className="flex items-center justify-between">
              <label className="cursor-pointer text-xs text-purple-400 hover:underline">
                <span>Upload CSV File Instead</span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files && e.target.files[0];
                    if (f) {
                      const reader = new FileReader();
                      reader.onload = (re) => setBulkCsvText(re.target.result);
                      reader.readAsText(f);
                    }
                  }}
                />
              </label>

              <div className="flex space-x-2">
                <button
                  type="button"
                  onClick={() => setShowBulkUploadModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-700 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await handleBulkUploadStudents();
                    setShowBulkUploadModal(false);
                  }}
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold"
                >
                  Process Students
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* MODAL: Add Subject                                            */}
      {/* ------------------------------------------------------------- */}
      {showAddSubjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fade-in">
          <div className={`w-full max-w-md rounded-3xl p-6 border shadow-2xl ${
            isDark ? 'bg-slate-900 border-slate-800 text-white' : 'bg-white border-slate-200 text-slate-900'
          }`}>
            <h3 className="font-heading font-bold text-lg mb-4">Add Curriculum Subject</h3>
            <form onSubmit={handleCreateSubject} className="space-y-4">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Subject Name *</label>
                <input
                  type="text"
                  value={newSubject.name}
                  onChange={(e) => setNewSubject({
                    ...newSubject,
                    name: e.target.value,
                    folder_slug: e.target.value.toLowerCase().replace(/\s+/g, '-'),
                  })}
                  placeholder="e.g. Python Async Programming"
                  className={`w-full rounded-xl px-3.5 py-2 text-xs border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                  required
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold">Storage Folder Slug *</label>
                <input
                  type="text"
                  value={newSubject.folder_slug}
                  onChange={(e) => setNewSubject({ ...newSubject, folder_slug: e.target.value })}
                  placeholder="e.g. python-async-programming"
                  className={`w-full rounded-xl px-3.5 py-2 text-xs font-mono border ${
                    isDark ? 'bg-slate-800 border-slate-700 text-white' : 'bg-slate-50 border-slate-300'
                  }`}
                  required
                />
              </div>

              <div className="flex justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddSubjectModal(false)}
                  className="px-4 py-2 rounded-xl border border-slate-700 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold"
                >
                  Create Subject
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
