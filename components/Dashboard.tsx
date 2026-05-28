'use client';

import { useState, useEffect } from 'react';
import {
  Play, Shield, Activity, RefreshCw, LogOut, AlertCircle, CheckCircle2,
  Clock, ChevronDown, ChevronRight, Heart, Database, Users, Lock,
  Tag, ListChecks, FileText, Layers,
} from 'lucide-react';

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

interface Health {
  checkedAt?: string;
  vault?: {
    status: string;
    dns?: string;
    users?: number;
    groups?: number;
    urs_records?: number;
    document_count?: number;
    qms_object_total?: number;
    qms_object_counts?: Record<string, number>;
    direct_data?: { available: boolean; latest_filename?: string; latest_stop_time?: string };
  };
  glean?: {
    status: string;
    datasource?: string;
    object_definitions?: number;
  };
  metadata?: {
    object_tab_mappings?: number;
    object_type_labels?: number;
    picklists?: number;
  };
  alerts?: { severity: 'critical' | 'warning' | 'info'; message: string }[];
  health_score?: number;
  overall_status?: 'healthy' | 'degraded' | 'unhealthy';
  duration_ms?: number;
  error?: string;
}

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  
  async function fetchJobs() {
    setRefreshing(true);
    try {
      const res = await fetch('/api/jobs', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setJobs(Array.isArray(data) ? data : []);
      }
    } catch (e) {
      console.error('Failed to fetch jobs:', e);
    } finally {
      setRefreshing(false);
    }
  }
  
  async function fetchHealth() {
    setHealthLoading(true);
    try {
      const res = await fetch('/api/health', { credentials: 'include' });
      const data = await res.json();
      setHealth(data);
    } catch (e: any) {
      setHealth({ error: e.message, overall_status: 'unhealthy', health_score: 0 });
    } finally {
      setHealthLoading(false);
    }
  }
  
  useEffect(() => {
    fetchJobs();
    fetchHealth();
    const jobsInterval = setInterval(() => {
      if (jobs.some((j) => j.status === 'running' || j.status === 'queued')) {
        fetchJobs();
      }
    }, 10000);
    const healthInterval = setInterval(fetchHealth, 60000);
    return () => {
      clearInterval(jobsInterval);
      clearInterval(healthInterval);
    };
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
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      
      if (!res.ok) {
        let errMsg = `HTTP ${res.status}`;
        try {
          const err = await res.json();
          errMsg = err.error || errMsg;
        } catch {}
        alert(`Failed: ${errMsg}`);
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
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
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
        
        {/* HEALTH MONITORING PANEL */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">System Health</h2>
            <div className="flex items-center gap-3">
              {health?.checkedAt && (
                <span className="text-xs text-gray-500">
                  Last checked {new Date(health.checkedAt).toLocaleTimeString()}
                </span>
              )}
              <button
                onClick={fetchHealth}
                disabled={healthLoading}
                className="text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1 disabled:opacity-50"
              >
                <RefreshCw className={`w-4 h-4 ${healthLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>
          </div>
          
          {!health && (
            <div className="bg-white rounded-lg border border-gray-200 p-6 text-center text-gray-500 text-sm">
              <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2" />
              Probing Vault and Glean…
            </div>
          )}
          
          {health && (
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              {/* Overall status banner */}
              <div className={`px-4 py-3 flex items-center justify-between ${
                health.overall_status === 'healthy' ? 'bg-green-50' :
                health.overall_status === 'degraded' ? 'bg-yellow-50' :
                'bg-red-50'
              }`}>
                <div className="flex items-center gap-2">
                  <Heart className={`w-5 h-5 ${
                    health.overall_status === 'healthy' ? 'text-green-600' :
                    health.overall_status === 'degraded' ? 'text-yellow-600' :
                    'text-red-600'
                  }`} />
                  <div>
                    <div className="font-medium text-sm capitalize">
                      {health.overall_status || 'Unknown'}
                    </div>
                    <div className="text-xs text-gray-600">
                      Health Score: {health.health_score ?? 0} / 100
                      {health.duration_ms && ` · Probe took ${health.duration_ms}ms`}
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Alerts */}
              {health.alerts && health.alerts.length > 0 && (
                <div className="px-4 py-3 border-t border-gray-100 space-y-2">
                  {health.alerts.map((alert, i) => (
                    <div key={i} className={`flex items-start gap-2 text-xs px-3 py-2 rounded ${
                      alert.severity === 'critical' ? 'bg-red-100 text-red-800' :
                      alert.severity === 'warning' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-blue-100 text-blue-800'
                    }`}>
                      <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                      <span>{alert.message}</span>
                    </div>
                  ))}
                </div>
              )}
              
              {/* Metric tiles */}
              <div className="px-4 py-4 grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-gray-100">
                <MetricTile
                  icon={<Database className="w-4 h-4" />}
                  label="Vault"
                  value={health.vault?.status === 'ok' ? 'Connected' : 'Error'}
                  status={health.vault?.status === 'ok' ? 'ok' : 'error'}
                />
                <MetricTile
                  icon={<Database className="w-4 h-4" />}
                  label="Glean"
                  value={health.glean?.status === 'ok' ? 'Connected' : 'Error'}
                  status={health.glean?.status === 'ok' ? 'ok' : 'error'}
                />
                <MetricTile
                  icon={<Users className="w-4 h-4" />}
                  label="Vault Users"
                  value={health.vault?.users ?? '—'}
                />
                <MetricTile
                  icon={<Users className="w-4 h-4" />}
                  label="Groups"
                  value={health.vault?.groups ?? '—'}
                />
                <MetricTile
                  icon={<Lock className="w-4 h-4" />}
                  label="URS Records"
                  value={health.vault?.urs_records ?? '—'}
                />
                <MetricTile
                  icon={<FileText className="w-4 h-4" />}
                  label="Documents"
                  value={health.vault?.document_count ?? '—'}
                />
                <MetricTile
                  icon={<Layers className="w-4 h-4" />}
                  label="QMS Records"
                  value={health.vault?.qms_object_total ?? '—'}
                />
                <MetricTile
                  icon={<Tag className="w-4 h-4" />}
                  label="Picklists"
                  value={health.metadata?.picklists ?? '—'}
                />
              </div>
              
              {/* Metadata loaders */}
              <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
                <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">
                  Sync Metadata Resolvers
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className={`w-3 h-3 ${(health.metadata?.object_tab_mappings ?? 0) > 0 ? 'text-green-600' : 'text-gray-400'}`} />
                    <span>Tab mappings: <strong>{health.metadata?.object_tab_mappings ?? 0}</strong></span>
                  </div>
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className={`w-3 h-3 ${(health.metadata?.object_type_labels ?? 0) > 0 ? 'text-green-600' : 'text-gray-400'}`} />
                    <span>Object types: <strong>{health.metadata?.object_type_labels ?? 0}</strong></span>
                  </div>
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className={`w-3 h-3 ${(health.metadata?.picklists ?? 0) > 0 ? 'text-green-600' : 'text-gray-400'}`} />
                    <span>Picklists: <strong>{health.metadata?.picklists ?? 0}</strong></span>
                  </div>
                </div>
              </div>
              
              {/* Direct Data status */}
              {health.vault?.direct_data && (
                <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ListChecks className={`w-4 h-4 ${health.vault.direct_data.available ? 'text-green-600' : 'text-yellow-600'}`} />
                    <div>
                      <div className="text-sm font-medium">
                        Direct Data Extract: {health.vault.direct_data.available ? 'Available' : 'Not Ready'}
                      </div>
                      {health.vault.direct_data.latest_filename && (
                        <div className="text-xs text-gray-500">
                          Latest: {health.vault.direct_data.latest_filename}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}
              
              {/* QMS object breakdown */}
              {health.vault?.qms_object_counts && Object.keys(health.vault.qms_object_counts).length > 0 && (
                <details className="border-t border-gray-100">
                  <summary className="px-4 py-3 cursor-pointer text-xs text-gray-600 hover:bg-gray-50">
                    QMS Object Breakdown ({Object.keys(health.vault.qms_object_counts).length} types)
                  </summary>
                  <div className="px-4 pb-3 grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                    {Object.entries(health.vault.qms_object_counts).map(([name, count]) => (
                      <div key={name} className="flex justify-between bg-gray-50 px-2 py-1 rounded">
                        <span className="text-gray-600 font-mono">{name}</span>
                        <span className="font-medium">{count}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </section>
        
        <section className="mt-10">
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
                if (confirm('This will re-push all documents and objects to Glean. Continue?')) {
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
                    {job.metrics && Object.keys(job.metrics).length > 0 && (
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

function MetricTile({ icon, label, value, status }: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  status?: 'ok' | 'error';
}) {
  return (
    <div className={`p-3 rounded-lg border ${
      status === 'error' ? 'border-red-200 bg-red-50' :
      status === 'ok' ? 'border-green-200 bg-green-50' :
      'border-gray-200 bg-gray-50'
    }`}>
      <div className="flex items-center gap-1 text-xs text-gray-600 mb-1">
        {icon}
        <span>{label}</span>
      </div>
      <div className="font-semibold text-sm">{value}</div>
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
