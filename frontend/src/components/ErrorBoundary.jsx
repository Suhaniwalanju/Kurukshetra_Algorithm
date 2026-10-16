import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReload = () => {
    localStorage.removeItem('studio_theme');
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[#080C14] text-white flex items-center justify-center p-6">
          <div className="max-w-xl w-full p-8 rounded-3xl bg-[#0F172A] border border-red-500/30 shadow-2xl space-y-5 text-center">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-red-500/20 border border-red-500/30 flex items-center justify-center text-red-400">
              <AlertTriangle className="w-7 h-7" />
            </div>

            <div className="space-y-1">
              <h2 className="font-heading font-bold text-2xl tracking-tight text-white">
                Course Material Studio Recovered
              </h2>
              <p className="text-xs text-slate-400">
                A UI render exception was caught. Your generated slides and sandbox data remain safe.
              </p>
            </div>

            {this.state.error && (
              <pre className="p-3.5 rounded-xl bg-black border border-slate-800 text-xs font-mono text-rose-300 text-left overflow-x-auto max-h-36">
                {this.state.error.toString()}
              </pre>
            )}

            <button
              onClick={this.handleReload}
              className="px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs flex items-center space-x-2 mx-auto shadow-lg transition-all"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Reload Studio</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
