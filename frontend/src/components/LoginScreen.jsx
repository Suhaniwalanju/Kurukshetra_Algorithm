import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  GraduationCap,
  Presentation,
  KeyRound,
  User,
  School,
  Lock,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';

export default function LoginScreen({ onLoginSuccess, theme }) {
  const isDark = theme === 'dark';

  const [role, setRole] = useState('trainer'); // 'student', 'trainer', 'admin'
  const [institutes, setInstitutes] = useState([]);
  const [selectedInstitute, setSelectedInstitute] = useState('dpu');

  // Credentials
  const [loginId, setLoginId] = useState('trainer');
  const [password, setPassword] = useState('Trainer@12345');
  const [rollNumber, setRollNumber] = useState('STUDENT01');
  const [passkey, setPasskey] = useState('Student@123');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Fetch active institutes
  useEffect(() => {
    fetch('http://localhost:8000/api/institutes')
      .then((res) => res.json())
      .then((data) => {
        if (data && data.length > 0) {
          setInstitutes(data);
          setSelectedInstitute(data[0].id);
        }
      })
      .catch((err) => console.error('Failed to load institutes:', err));
  }, []);

  const handleRoleSwitch = (newRole) => {
    setRole(newRole);
    setError('');
    if (newRole === 'admin') {
      setLoginId('admin');
      setPassword('Admin@NewPassword2026!');
    } else if (newRole === 'trainer') {
      setLoginId('trainer');
      setPassword('Trainer@12345');
    } else {
      setRollNumber('STUDENT01');
      setPasskey('Student@123');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const payload = {
        institute_id: selectedInstitute,
        role: role,
        login_id: role === 'student' ? rollNumber.trim() : loginId.trim(),
        roll_number: role === 'student' ? rollNumber.trim() : undefined,
        password: role !== 'student' ? password : undefined,
        passkey: role === 'student' ? passkey : undefined,
      };

      const res = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: json_payload_string(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Authentication failed. Please verify credentials.');
      }

      // Store token and user
      localStorage.setItem('auth_token', data.token);
      localStorage.setItem('auth_user', JSON.stringify(data.user));
      onLoginSuccess(data.user, data.token, data.must_change_password);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  function json_payload_string(obj) {
    return JSON.stringify(obj);
  }

  return (
    <div className={`min-h-[85vh] flex items-center justify-center p-4 transition-colors duration-200`}>
      <div className={`w-full max-w-md rounded-3xl p-8 border shadow-2xl backdrop-blur-xl relative overflow-hidden transition-all ${
        isDark
          ? 'bg-[#0F172A]/90 border-slate-800 text-white shadow-indigo-950/40'
          : 'bg-white/95 border-slate-200 text-slate-900 shadow-slate-200/60'
      }`}>
        {/* Glow decoration */}
        <div className="absolute -top-24 -right-24 w-48 h-48 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -left-24 w-48 h-48 bg-purple-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-purple-600 flex items-center justify-center shadow-xl shadow-blue-500/25 mb-3">
            <Presentation className="w-7 h-7 text-white" />
          </div>
          <h2 className="font-heading font-extrabold text-2xl tracking-tight">
            Verified Studio Portal
          </h2>
          <p className={`text-xs mt-1 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
            Sign in to access course materials, decks, and student learning
          </p>
        </div>

        {/* Role Switcher Tabs */}
        <div className={`grid grid-cols-3 p-1 rounded-2xl border mb-6 ${
          isDark ? 'bg-slate-900/90 border-slate-800' : 'bg-slate-100 border-slate-200'
        }`}>
          <button
            type="button"
            onClick={() => handleRoleSwitch('student')}
            className={`py-2 px-3 rounded-xl text-xs font-bold flex items-center justify-center space-x-1.5 transition-all ${
              role === 'student'
                ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <GraduationCap className="w-3.5 h-3.5" />
            <span>Student</span>
          </button>

          <button
            type="button"
            onClick={() => handleRoleSwitch('trainer')}
            className={`py-2 px-3 rounded-xl text-xs font-bold flex items-center justify-center space-x-1.5 transition-all ${
              role === 'trainer'
                ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md shadow-blue-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Presentation className="w-3.5 h-3.5" />
            <span>Trainer</span>
          </button>

          <button
            type="button"
            onClick={() => handleRoleSwitch('admin')}
            className={`py-2 px-3 rounded-xl text-xs font-bold flex items-center justify-center space-x-1.5 transition-all ${
              role === 'admin'
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-md shadow-purple-600/20'
                : isDark ? 'text-slate-400 hover:text-white' : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Admin</span>
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-start space-x-2 text-rose-400 text-xs animate-shake">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Institute Selection */}
          <div className="space-y-1.5">
            <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
              <School className="w-3.5 h-3.5 text-blue-500" />
              <span>Institute *</span>
            </label>
            <select
              value={selectedInstitute}
              onChange={(e) => setSelectedInstitute(e.target.value)}
              className={`w-full rounded-xl px-3.5 py-2.5 text-xs font-medium border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                isDark
                  ? 'bg-slate-900 border-slate-700 text-white'
                  : 'bg-slate-50 border-slate-300 text-slate-900'
              }`}
              required
            >
              {institutes.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.name} ({inst.short_name})
                </option>
              ))}
            </select>
          </div>

          {/* Student Fields */}
          {role === 'student' ? (
            <>
              <div className="space-y-1.5">
                <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                  <User className="w-3.5 h-3.5 text-emerald-500" />
                  <span>Student Roll Number *</span>
                </label>
                <input
                  type="text"
                  value={rollNumber}
                  onChange={(e) => setRollNumber(e.target.value)}
                  placeholder="e.g. STUDENT01"
                  className={`w-full rounded-xl px-3.5 py-2.5 text-xs border focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-colors ${
                    isDark
                      ? 'bg-slate-900 border-slate-700 text-white placeholder-slate-500'
                      : 'bg-slate-50 border-slate-300 text-slate-900 placeholder-slate-400'
                  }`}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                  <KeyRound className="w-3.5 h-3.5 text-emerald-500" />
                  <span>Passkey *</span>
                </label>
                <input
                  type="password"
                  value={passkey}
                  onChange={(e) => setPasskey(e.target.value)}
                  placeholder="Enter secure passkey"
                  className={`w-full rounded-xl px-3.5 py-2.5 text-xs border focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-colors ${
                    isDark
                      ? 'bg-slate-900 border-slate-700 text-white placeholder-slate-500'
                      : 'bg-slate-50 border-slate-300 text-slate-900 placeholder-slate-400'
                  }`}
                  required
                />
              </div>
            </>
          ) : (
            /* Admin & Trainer Fields */
            <>
              <div className="space-y-1.5">
                <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                  <User className="w-3.5 h-3.5 text-blue-500" />
                  <span>Login ID *</span>
                </label>
                <input
                  type="text"
                  value={loginId}
                  onChange={(e) => setLoginId(e.target.value)}
                  placeholder={role === 'admin' ? 'admin' : 'trainer'}
                  className={`w-full rounded-xl px-3.5 py-2.5 text-xs border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                    isDark
                      ? 'bg-slate-900 border-slate-700 text-white placeholder-slate-500'
                      : 'bg-slate-50 border-slate-300 text-slate-900 placeholder-slate-400'
                  }`}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label className={`text-xs font-semibold flex items-center space-x-1.5 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
                  <Lock className="w-3.5 h-3.5 text-blue-500" />
                  <span>Password *</span>
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  className={`w-full rounded-xl px-3.5 py-2.5 text-xs border focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors ${
                    isDark
                      ? 'bg-slate-900 border-slate-700 text-white placeholder-slate-500'
                      : 'bg-slate-50 border-slate-300 text-slate-900 placeholder-slate-400'
                  }`}
                  required
                />
              </div>
            </>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className={`w-full py-3 rounded-xl font-bold text-xs flex items-center justify-center space-x-2 text-white shadow-xl transition-all transform hover:scale-[1.01] active:scale-[0.99] mt-2 ${
              role === 'student'
                ? 'bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 shadow-emerald-500/25 hover:from-emerald-500 hover:to-cyan-500'
                : role === 'admin'
                ? 'bg-gradient-to-r from-purple-600 via-indigo-600 to-pink-600 shadow-purple-500/25 hover:from-purple-500 hover:to-pink-500'
                : 'bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 shadow-blue-500/25 hover:from-blue-500 hover:to-purple-500'
            } ${loading ? 'opacity-70 cursor-not-allowed' : ''}`}
          >
            <span>{loading ? 'Authenticating...' : `Sign In as ${role.toUpperCase()}`}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        {/* Quick Demo Pre-fill Pills */}
        <div className="mt-6 pt-5 border-t border-slate-800/40 text-center">
          <p className={`text-[11px] font-semibold mb-2 ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
            Quick Demo Login Accounts:
          </p>
          <div className="flex flex-wrap justify-center gap-1.5">
            <button
              type="button"
              onClick={() => handleRoleSwitch('student')}
              className="text-[10px] font-medium px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20"
            >
              Student (STUDENT01)
            </button>
            <button
              type="button"
              onClick={() => handleRoleSwitch('trainer')}
              className="text-[10px] font-medium px-2 py-1 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20"
            >
              Trainer (trainer)
            </button>
            <button
              type="button"
              onClick={() => handleRoleSwitch('admin')}
              className="text-[10px] font-medium px-2 py-1 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 hover:bg-purple-500/20"
            >
              Admin (admin)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
