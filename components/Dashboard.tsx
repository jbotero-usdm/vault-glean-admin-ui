'use client';

import { useState, useEffect } from 'react';
import { Play, Shield, Activity, RefreshCw, LogOut, AlertCircle, CheckCircle2, Clock, ChevronDown, ChevronRight } from 'lucide-react';

interface Job {
  jobId: string;
  type: string;
  status: 'queued' | 'running' | 'success' | 'failure';
  startedAt?: string;
  finishedAt?: string;
  output?: string;
  metrics?: Record<string, any>;
  error?: string;
}

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  
  async function fetchJobs() {
    setRefreshing(true);
    try {
      const res = await fetch('/api/jobs');
      if (res.ok) {
        const data = await res.json();
        setJobs(data);
      }
    } catch (e) {
      console.error('Failed to fetch jobs:', e);
    } finally {
      setRefreshing(false);
    }
  }
  
  useEffect(() => {
    fetchJobs();
    // Auto-refresh every 10s if any job is running
    const interval = setInterval(() => {
      if (jobs.some((j) => j.status === 'running' || j.status === 'queued')) {
        fetchJobs();
      }
    }, 10000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.length]);
  
  async function runAction(action: 'sync' | 'sync-force' | 'audit' | 'monitor') {
    setLoading(action);
    try {
      const body = action === 'sync-force' ? { force_full_reconcile: true } : 
                   action === 'monitor' ? { user_email: 'jbotero@partnersi-usdm.com' } : {};
      const endpoint = action === 'sync-force' ? 'sync' : action;
      
      const res = await fetch(`/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      
      if (!res.ok) {
        const err = await res.json();
        alert(`Failed: ${err.error || 'Unknown error'}`);
      } else {
        await fetchJobs();
      }
    } catch (e: any) {
      alert(`Failed: ${e.message}`);
    } finally {
      setLoading(null);
    }
  }
  
  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  }
  
  const StatusBadge = ({ status }: { status: string }) => {
    const colors: Record<string, string> = {
      queued: 'bg-gray-100 text-gray-700',
      running: 'bg-blue-100 text-blue-700',
      success: 'bg-green-100 text-green-700',
      failure: 'bg-red-100 text-red-700',
    };
    const icons: Record<string, JSX.Element> = {
      queued: <Clock className="w-3 h-3" />,
      running: <RefreshCw className="w-3 h-3 animate-spin" />,
      success: <CheckCircle2 className="w-3 h-3" />,
      failure: <AlertCircle className="w-3 h-3" />,
    };
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${colors[status]}`}>
        {icons[status]}
        {status}
      </span>
    );
  };
  
  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold" style={{ color: 'var(--usdm-blue)' }}>
              Vault → Glean Admin Console
            </h1>
            <p className="text-xs text-gray-500">USDM Quality Vault integration</p>
          </div>
          <button onClick={logout} className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900">
            <LogOut className="w-4 h-4" />
            Sign out
          </button>
        </div>
      </header>
      
      <main className="max-w-6xl mx-auto px-6 py-8">
        <section>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <ActionCard
              icon={<Play className="w-5 h-5" />}
              title="Run Sync Now"
              description="Incremental Vault → Glean sync"
              onClick={() => runAction('sync')}
              loading={loading === 'sync'}
            />
            <ActionCard
              icon={<RefreshCw className="w-5 h-5" />}
              title="Force Full Reconcile"
              description="Re-push everything (10-15 min)"
              onClick={() => {
                if (confirm('This will re-push all 193+ documents and objects to Glean. Continue?')) {
                  runAction('sync-force');
                }
              }}
              loading={loading === 'sync-force'}
              danger
            />
            <ActionCard
              icon={<Shield className="w-5 h-5" />}
              title="Audit Vault Security"
              description="Check doc + object ACLs"
              onClick={() => runAction('audit')}
              loading={loading === 'audit'}
            />
            <ActionCard
              icon={<Activity className="w-5 h-5" />}
              title="Glean Monitor Report"
              description="Verify indexing + access"
              onClick={() => runAction('monitor')}
              loading={loading === 'monitor'}
            />
          </div>
        </section>
        
        <section className="mt-10">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Recent Jobs</h2>
            <button 
              onClick={fetchJobs} 
              disabled={refreshing}
              className="text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
          
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            {jobs.length === 0 && (
              <div className="px-6 py-12 text-center text-gray-500 text-sm">
                No jobs yet. Click an action above to run one.
              </div>
            )}
            {jobs.map((job) => (
              <div key={job.jobId} className="border-b border-gray-100 last:border-b-0">
                <button
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-50 text-left"
                  onClick={() => setExpanded(expanded === job.jobId ? null : job.jobId)}
                >
                  <div className="flex items-center gap-3">
                    {expanded === job.jobId ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
                    <div>
                      <div className="font-medium text-sm">{job.type}</div>
                      <div className="text-xs text-gray-500">
                        {job.startedAt ? new Date(job.startedAt).toLocaleString() : 'Pending'}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={job.status} />
                </button>
                {expanded === job.jobId && (
                  <div className="px-4 py-3 bg-gray-50 border-t border-gray-100">
                    <div className="text-xs text-gray-500 mb-1">Job ID: {job.jobId}</div>
                    {job.metrics && (
                      <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                        {Object.entries(job.metrics).map(([k, v]) => (
                          <div key={k}>
                            <span className="text-gray-500">{k}:</span> <span className="font-medium">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {job.error && (
                      <div className="mt-2 p-2 bg-red-50 text-red-800 text-xs rounded">
                        {job.error}
                      </div>
                    )}
                    {job.output && (
                      <details className="mt-2">
                        <summary className="text-xs text-gray-600 cursor-pointer">View log output</summary>
                        <pre className="mt-2 p-2 bg-gray-900 text-gray-100 rounded text-xs overflow-x-auto whitespace-pre-wrap">{job.output}</pre>
                      </details>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

function ActionCard({
  icon, title, description, onClick, loading, danger
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  onClick: () => void;
  loading: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`bg-white rounded-lg border p-4 text-left hover:shadow-md transition-shadow disabled:opacity-50 disabled:cursor-not-allowed ${
        danger ? 'border-orange-200 hover:border-orange-300' : 'border-gray-200 hover:border-gray-300'
      }`}
    >
      <div className={`inline-flex items-center justify-center w-10 h-10 rounded-lg mb-3 ${
        danger ? 'bg-orange-50 text-orange-700' : 'bg-blue-50 text-blue-700'
      }`}>
        {loading ? <RefreshCw className="w-5 h-5 animate-spin" /> : icon}
      </div>
      <div className="font-medium text-sm">{title}</div>
      <div className="text-xs text-gray-500 mt-1">{description}</div>
    </button>
  );
}
