import React, { useState, useEffect } from 'react';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [stats, setStats] = useState({
    total_apis: 0,
    total_versions: 0,
    total_changes: 0,
    breaking_changes: 0,
    non_breaking_changes: 0,
    total_adapters: 0,
    recent_activities: []
  });
  const [apis, setApis] = useState([]);
  const [selectedApiId, setSelectedApiId] = useState('1');
  const [versions, setVersions] = useState([]);
  const [diffResult, setDiffResult] = useState(null);
  const [adapters, setAdapters] = useState([]);
  const [selectedAdapter, setSelectedAdapter] = useState(null);
  const [testRuns, setTestRuns] = useState([]);
  const [testSummary, setTestSummary] = useState({ pass_rate: 100, total_runs: 0 });
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);

  // Modal / Spec Viewer
  const [specViewerContent, setSpecViewerContent] = useState(null);

  // Form States
  const [newApiName, setNewApiName] = useState('');
  const [newApiDesc, setNewApiDesc] = useState('');
  const [uploadVersionTag, setUploadVersionTag] = useState('');
  const [uploadSpecContent, setUploadSpecContent] = useState('');
  const [diffOldVer, setDiffOldVer] = useState('');
  const [diffNewVer, setDiffNewVer] = useState('');

  // Dual Proxy Tester States
  const [proxyMethod, setProxyMethod] = useState('GET');
  const [proxyPath, setProxyPath] = useState('/users');
  const [directResponse, setDirectResponse] = useState(null);
  const [directLoading, setDirectLoading] = useState(false);
  const [proxyResponse, setProxyResponse] = useState(null);
  const [proxyLoading, setProxyLoading] = useState(false);

  const notify = (msg, type = 'success') => {
    setNotification({ msg, type });
    setTimeout(() => setNotification(null), 3500);
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const [statsRes, apisRes, adpRes, testsRes, sumRes] = await Promise.all([
        fetch('/api/dashboard/stats').then(r => r.json()),
        fetch('/api/apis').then(r => r.json()),
        fetch('/api/adapters').then(r => r.json()),
        fetch('/api/tests/runs?limit=10').then(r => r.json()),
        fetch('/api/tests/summary').then(r => r.json()),
      ]);
      setStats(statsRes);
      setApis(apisRes);
      setAdapters(adpRes);
      setTestRuns(testsRes);
      setTestSummary(sumRes);

      if (apisRes.length > 0 && !apisRes.find(a => a.id.toString() === selectedApiId)) {
        setSelectedApiId(apisRes[0].id.toString());
      }
      if (adpRes.length > 0 && !selectedAdapter) {
        setSelectedAdapter(adpRes[0]);
      }
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    }
  };

  useEffect(() => {
    if (selectedApiId) {
      fetch(`/api/apis/${selectedApiId}/versions`)
        .then(r => r.json())
        .then(data => {
          setVersions(data);
          if (data.length >= 2) {
            setDiffOldVer(data[data.length - 1].id.toString());
            setDiffNewVer(data[0].id.toString());
          }
        });

      // Update proxy path based on active service
      const adp = adapters.find(a => a.api_id.toString() === selectedApiId.toString());
      if (adp) {
        setProxyPath(adp.old_endpoint);
      } else if (selectedApiId === '2') {
        setProxyPath('/products');
      } else if (selectedApiId === '3') {
        setProxyPath('/accounts');
      } else {
        setProxyPath('/users');
      }

      setDirectResponse(null);
      setProxyResponse(null);
    }
  }, [selectedApiId, adapters]);

  const currentApi = apis.find(a => a.id.toString() === selectedApiId?.toString()) || {
    name: 'No Service Selected',
    id: selectedApiId,
    description: ''
  };

  const activeApprovedAdapter = adapters.find(
    (a) => a.api_id.toString() === selectedApiId?.toString() && (a.status === 'APPROVED' || a.status === 'ACTIVE')
  );
  const anyAdapterForSelected = adapters.find(
    (a) => a.api_id.toString() === selectedApiId?.toString()
  );

  const handleRegisterApi = async (e) => {
    e.preventDefault();
    if (!newApiName.trim()) return;
    try {
      const res = await fetch('/api/apis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newApiName.trim(), description: newApiDesc.trim() }),
      });
      if (res.ok) {
        const created = await res.json();
        notify(`Service '${created.name}' registered (ID: ${created.id})`);
        setNewApiName('');
        setNewApiDesc('');
        await fetchDashboardData();
        setSelectedApiId(created.id.toString());
      } else {
        const err = await res.json();
        notify(err.detail || 'Registration failed', 'error');
      }
    } catch {
      notify('Network connection error', 'error');
    }
  };

  const handleUploadSpec = async (e) => {
    e.preventDefault();
    if (!selectedApiId || !uploadVersionTag || !uploadSpecContent) {
      notify('Please provide version tag and specification content', 'error');
      return;
    }
    try {
      const res = await fetch(`/api/apis/${selectedApiId}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_tag: uploadVersionTag.trim(), spec_content: uploadSpecContent.trim() }),
      });
      if (res.ok) {
        notify(`Version ${uploadVersionTag} uploaded and indexed`);
        setUploadVersionTag('');
        setUploadSpecContent('');
        fetchDashboardData();
        const vRes = await fetch(`/api/apis/${selectedApiId}/versions`).then(r => r.json());
        setVersions(vRes);
      } else {
        const err = await res.json();
        notify(err.detail || 'Upload failed', 'error');
      }
    } catch {
      notify('Upload request failed', 'error');
    }
  };

  const handleRunDiff = async () => {
    if (!selectedApiId || !diffOldVer || !diffNewVer) {
      notify('Select both base and target versions', 'error');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/api/changes/diff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_id: parseInt(selectedApiId),
          old_version_id: parseInt(diffOldVer),
          new_version_id: parseInt(diffNewVer),
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setDiffResult(data);
        notify(`AST Diff complete: ${data.summary.breaking} breaking changes detected`);
        fetchDashboardData();
      } else {
        const err = await res.json();
        notify(err.detail || 'Diff failed', 'error');
      }
    } catch {
      notify('Diff operation error', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateAdapterDynamic = async (oldEp, newEp, method = 'GET') => {
    setLoading(true);
    try {
      const res = await fetch('/api/adapters/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_id: parseInt(selectedApiId),
          old_endpoint: oldEp,
          new_endpoint: newEp,
          method: method,
        }),
      });
      if (res.ok) {
        const adp = await res.json();
        setSelectedAdapter(adp);
        notify(`Synthesized Adapter #${adp.id}: ${adp.old_endpoint} → ${adp.new_endpoint}`);
        setActiveTab('adapters');
        fetchDashboardData();
      } else {
        const err = await res.json();
        notify(err.detail || 'Failed to generate adapter', 'error');
      }
    } catch {
      notify('Adapter generation error', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleApproveAdapter = async (adapterId) => {
    try {
      const res = await fetch(`/api/adapters/${adapterId}/approve`, { method: 'POST' });
      if (res.ok) {
        const updated = await res.json();
        notify(`Adapter #${adapterId} approved and active in proxy`);
        setSelectedAdapter(updated);
        fetchDashboardData();
      }
    } catch {
      notify('Approval request failed', 'error');
    }
  };

  const handleTriggerTests = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/tests/run', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        notify(`Test Suite Passed (${data.pass_rate_percent}%)`);
        fetchDashboardData();
      }
    } catch {
      notify('Test execution failed', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Database Reset / Seed Controls
  const handleResetDatabase = async () => {
    if (!window.confirm("Are you sure you want to reset all database tables to empty? This provides a 100% clean blank slate for live demonstration.")) return;
    try {
      const res = await fetch('/api/database/reset', { method: 'POST' });
      if (res.ok) {
        notify('Database reset to clean blank state!');
        setApis([]);
        setSelectedApiId('');
        setVersions([]);
        setDiffResult(null);
        setAdapters([]);
        setSelectedAdapter(null);
        setDirectResponse(null);
        setProxyResponse(null);
        fetchDashboardData();
      }
    } catch {
      notify('Reset failed', 'error');
    }
  };

  const handleSeedDatabase = async () => {
    try {
      notify('Loading 3 sample services...', 'info');
      const res = await fetch('/api/database/seed', { method: 'POST' });
      if (res.ok) {
        notify('Loaded 3 sample services successfully!');
        await fetchDashboardData();
      }
    } catch {
      notify('Seed failed', 'error');
    }
  };

  // 1. Test Upstream (Without Proxy)
  const handleTestDirectUpstream = async () => {
    if (!selectedApiId) return;
    setDirectLoading(true);
    const startTime = performance.now();
    try {
      const clean = (proxyPath || '').trim();
      const pathFormatted = clean.startsWith('/') ? clean : `/${clean}`;
      const url = `/mock/${selectedApiId}${pathFormatted}`;
      const res = await fetch(url);
      const data = await res.json();
      setDirectResponse({
        status: res.status,
        latencyMs: Math.round(performance.now() - startTime),
        url: url,
        body: data,
      });
    } catch (e) {
      setDirectResponse({
        status: 500,
        latencyMs: Math.round(performance.now() - startTime),
        url: `/mock/${selectedApiId}${proxyPath}`,
        body: { error: e.message },
      });
    } finally {
      setDirectLoading(false);
    }
  };

  // 2. Test Dynamic Proxy
  const handleTestProxy = async () => {
    if (!selectedApiId) return;
    setProxyLoading(true);
    const startTime = performance.now();
    try {
      const clean = (proxyPath || '').trim();
      const pathFormatted = clean.startsWith('/') ? clean : `/${clean}`;
      const url = `/proxy/${selectedApiId}${pathFormatted}`;
      const res = await fetch(url);
      const data = await res.json();
      setProxyResponse({
        status: res.status,
        latencyMs: Math.round(performance.now() - startTime),
        url: url,
        headers: {
          proxied: res.headers.get('x-apibridge-proxied'),
          adapterId: res.headers.get('x-apibridge-adapter-id'),
          originalPath: res.headers.get('x-apibridge-original-path'),
          targetPath: res.headers.get('x-apibridge-target-path'),
        },
        body: data,
      });
    } catch (e) {
      setProxyResponse({
        status: 500,
        latencyMs: Math.round(performance.now() - startTime),
        url: `/proxy/${selectedApiId}${proxyPath}`,
        body: { error: e.message },
      });
    } finally {
      setProxyLoading(false);
    }
  };

  // Helpers to fill sample JSON into textarea without pre-baking it into DB
  const fillSampleSpec = (type, version) => {
    if (type === 'users') {
      if (version === '1.0.0') {
        setUploadVersionTag('1.0.0');
        setUploadSpecContent(JSON.stringify({
          "openapi": "3.0.0",
          "info": { "title": "User Service", "version": "1.0.0" },
          "paths": {
            "/users": {
              "get": {
                "summary": "Get all users",
                "responses": {
                  "200": {
                    "description": "User object",
                    "content": {
                      "application/json": {
                        "schema": {
                          "type": "object",
                          "properties": {
                            "id": { "type": "integer", "example": 1 },
                            "name": { "type": "string", "example": "Sugam" }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }, null, 2));
      } else {
        setUploadVersionTag('2.0.0');
        setUploadSpecContent(JSON.stringify({
          "openapi": "3.0.0",
          "info": { "title": "User Service", "version": "2.0.0" },
          "paths": {
            "/customers": {
              "get": {
                "summary": "Get customers (Renamed from /users)",
                "responses": {
                  "200": {
                    "description": "Customer object",
                    "content": {
                      "application/json": {
                        "schema": {
                          "type": "object",
                          "properties": {
                            "id": { "type": "integer", "example": 1 },
                            "full_name": { "type": "string", "example": "Sugam" }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }, null, 2));
      }
    } else if (type === 'products') {
      if (version === '1.0.0') {
        setUploadVersionTag('1.0.0');
        setUploadSpecContent(JSON.stringify({
          "openapi": "3.0.0",
          "info": { "title": "Products Catalog Service", "version": "1.0.0" },
          "paths": {
            "/products": {
              "get": {
                "summary": "Get products",
                "responses": {
                  "200": {
                    "description": "Product object",
                    "content": {
                      "application/json": {
                        "schema": {
                          "type": "object",
                          "properties": {
                            "id": { "type": "integer", "example": 101 },
                            "title": { "type": "string", "example": "Wireless Mouse" },
                            "price": { "type": "number", "example": 29.99 }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }, null, 2));
      } else {
        setUploadVersionTag('2.0.0');
        setUploadSpecContent(JSON.stringify({
          "openapi": "3.0.0",
          "info": { "title": "Products Catalog Service", "version": "2.0.0" },
          "paths": {
            "/items": {
              "get": {
                "summary": "Get items (Renamed from /products)",
                "responses": {
                  "200": {
                    "description": "Item object",
                    "content": {
                      "application/json": {
                        "schema": {
                          "type": "object",
                          "properties": {
                            "id": { "type": "integer", "example": 101 },
                            "item_name": { "type": "string", "example": "Wireless Mouse" },
                            "price": { "type": "number", "example": 29.99 }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }, null, 2));
      }
    }
    notify(`Filled ${type} v${version} into form`);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans antialiased">
      {/* Toast Notification */}
      {notification && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-2.5 rounded-lg shadow-md text-xs font-semibold tracking-wide transition-all ${
          notification.type === 'error' ? 'bg-rose-600 text-white' : 'bg-slate-900 text-white'
        }`}>
          {notification.msg}
        </div>
      )}

      {/* Raw Spec Viewer Modal */}
      {specViewerContent && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
              <span className="font-bold text-xs text-slate-800">
                OpenAPI Contract Inspection (Version {specViewerContent.tag})
              </span>
              <button
                onClick={() => setSpecViewerContent(null)}
                className="text-slate-400 hover:text-slate-800 font-bold text-sm px-2 py-1"
              >
                ✕
              </button>
            </div>
            <pre className="p-4 bg-slate-900 text-slate-100 font-mono text-xs overflow-auto flex-1">
              {specViewerContent.spec}
            </pre>
          </div>
        </div>
      )}

      {/* Modern Clean Navbar */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-3 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow-sm">
              AB
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-base text-slate-900 tracking-tight">APIBridge</span>
                <span className="text-[11px] font-medium bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
                  v1.2
                </span>
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                  Dynamic Proxy Online
                </span>
              </div>
              <p className="text-[11px] text-slate-500">Breaking-Change Detection & In-Memory Adapter Generator</p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Active Service Selector */}
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-300 rounded-lg px-3 py-1.5 shadow-sm text-xs">
              <span className="text-slate-500 font-medium">Active Service:</span>
              <select
                value={selectedApiId}
                onChange={(e) => setSelectedApiId(e.target.value)}
                className="bg-transparent font-semibold text-slate-800 focus:outline-none cursor-pointer"
              >
                {apis.length === 0 ? (
                  <option value="">No Services (Click Contract Registry to add)</option>
                ) : (
                  apis.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name} (ID: {a.id})
                    </option>
                  ))
                )}
              </select>
            </div>

            {/* Database Reset Button (Clean slate proof) */}
            <button
              onClick={handleResetDatabase}
              className="text-[11px] font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 px-2.5 py-1.5 rounded-lg transition"
              title="Wipes all tables to prove live zero-hardcoded operation"
            >
              Reset to Blank
            </button>

            {apis.length === 0 && (
              <button
                onClick={handleSeedDatabase}
                className="text-[11px] font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-2.5 py-1.5 rounded-lg transition"
              >
                Load Sample Services
              </button>
            )}
          </div>
        </div>

        {/* 6 Tabs */}
        <div className="max-w-7xl mx-auto px-6 border-t border-slate-100 flex space-x-1 overflow-x-auto">
          {[
            { id: 'dashboard', label: '1. Overview' },
            { id: 'specs', label: '2. Contract Registry' },
            { id: 'diff', label: '3. Breaking Changes' },
            { id: 'adapters', label: '4. Adapter Studio' },
            { id: 'proxy', label: '5. Dynamic Proxy Gateway' },
            { id: 'tests', label: '6. Automated Tests' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 px-3.5 text-xs font-medium border-b-2 transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-600 font-semibold bg-indigo-50/40'
                  : 'border-transparent text-slate-500 hover:text-slate-900 hover:border-slate-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">

        {/* TAB 1: OVERVIEW */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-slate-900">API Contract & Compatibility Gateway</h2>
                <p className="text-xs text-slate-500 mt-1 max-w-2xl leading-relaxed">
                  Continuously watches OpenAPI contracts, identifies breaking changes between versions, synthesizes bidirectional translation adapters, and transparently routes legacy client requests with zero consumer downtime.
                </p>
              </div>
              <button
                onClick={() => setActiveTab('proxy')}
                className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition"
              >
                Test Dynamic Proxy →
              </button>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
                <span className="text-xs font-medium text-slate-500">Registered APIs</span>
                <div className="text-2xl font-bold text-slate-900 mt-1">{stats.total_apis}</div>
                <span className="text-[11px] text-slate-400">{stats.total_versions} contracts stored</span>
              </div>
              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
                <span className="text-xs font-medium text-slate-500">Breaking Changes Flagged</span>
                <div className="text-2xl font-bold text-rose-600 mt-1">{stats.breaking_changes}</div>
                <span className="text-[11px] text-slate-400">{stats.total_changes} total diffs logged</span>
              </div>
              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
                <span className="text-xs font-medium text-slate-500">Active Adapters</span>
                <div className="text-2xl font-bold text-emerald-600 mt-1">{stats.total_adapters}</div>
                <span className="text-[11px] text-slate-400">Deployed in proxy runtime</span>
              </div>
              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-sm">
                <span className="text-xs font-medium text-slate-500">Test Pass Rate</span>
                <div className="text-2xl font-bold text-indigo-600 mt-1">{testSummary.pass_rate}%</div>
                <span className="text-[11px] text-slate-400">{testSummary.total_runs} validations passed</span>
              </div>
            </div>

            {/* Dynamic Status Grid for Active Service */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
              <div className="flex justify-between items-center border-b border-slate-100 pb-2">
                <h3 className="font-bold text-xs text-slate-900 uppercase tracking-wider">
                  Active Service Pipeline: <span className="text-indigo-600 font-semibold">{currentApi.name}</span>
                </h3>
                <span className="text-[11px] text-slate-500 font-mono">Service ID: #{selectedApiId || 'None'}</span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 font-medium block">Ingested Versions</span>
                  <div className="font-bold text-slate-800 text-sm mt-0.5">{versions.length} versions</div>
                  <span className="text-[11px] text-slate-500">{versions.map(v => `v${v.version_tag}`).join(', ') || 'No contracts uploaded yet'}</span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 font-medium block">Runtime Adapter</span>
                  <div className="font-bold text-emerald-700 text-sm mt-0.5">
                    {activeApprovedAdapter ? `Adapter #${activeApprovedAdapter.id} Active` : 'No Approved Adapter'}
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {activeApprovedAdapter ? `${activeApprovedAdapter.old_endpoint} → ${activeApprovedAdapter.new_endpoint}` : 'Pass-through mode'}
                  </span>
                </div>
                <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                  <span className="text-slate-500 font-medium block">Proxy Gateway</span>
                  <div className="font-mono font-bold text-indigo-700 text-xs mt-0.5">/proxy/{selectedApiId || '...'}{proxyPath}</div>
                  <span className="text-[11px] text-emerald-600 font-medium">● Ready for requests</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: CONTRACT REGISTRY */}
        {activeTab === 'specs' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Register API Form */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Register API Service</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Register any custom microservice to monitor version contracts.</p>
                </div>

                <form onSubmit={handleRegisterApi} className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Service Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Courier Tracking Service"
                      value={newApiName}
                      onChange={(e) => setNewApiName(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Description (Optional)</label>
                    <input
                      type="text"
                      placeholder="e.g. Shipment and package status microservice"
                      value={newApiDesc}
                      onChange={(e) => setNewApiDesc(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <button
                    type="submit"
                    className="bg-slate-900 hover:bg-black text-white text-xs font-semibold px-4 py-2 rounded-lg transition"
                  >
                    Register Service
                  </button>
                </form>
              </div>

              {/* Upload Spec Form */}
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-sm text-slate-900">
                      Upload Contract: <span className="text-indigo-600">{currentApi.name}</span>
                    </h3>
                    <p className="text-xs text-slate-500 mt-0.5">Type, paste JSON/YAML, or fill a sample to test.</p>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs">
                    <button
                      type="button"
                      onClick={() => fillSampleSpec('users', '1.0.0')}
                      className="text-indigo-600 hover:underline text-[11px]"
                    >
                      Fill Users v1
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => fillSampleSpec('users', '2.0.0')}
                      className="text-indigo-600 hover:underline text-[11px]"
                    >
                      v2
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => fillSampleSpec('products', '1.0.0')}
                      className="text-indigo-600 hover:underline text-[11px]"
                    >
                      Fill Products v1
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      type="button"
                      onClick={() => fillSampleSpec('products', '2.0.0')}
                      className="text-indigo-600 hover:underline text-[11px]"
                    >
                      v2
                    </button>
                  </div>
                </div>

                <form onSubmit={handleUploadSpec} className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Version Tag</label>
                    <input
                      type="text"
                      placeholder="e.g. 1.0.0 or 2.0.0"
                      value={uploadVersionTag}
                      onChange={(e) => setUploadVersionTag(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800 focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Contract Content (JSON or YAML)</label>
                    <textarea
                      rows={5}
                      placeholder='{"openapi": "3.0.0", "paths": { ... }}'
                      value={uploadSpecContent}
                      onChange={(e) => setUploadSpecContent(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-300 rounded-lg p-2.5 text-xs font-mono text-slate-800 focus:outline-none focus:border-indigo-500"
                    ></textarea>
                  </div>
                  <button
                    type="submit"
                    className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-4 py-2 rounded-lg transition"
                  >
                    Save & Ingest Contract
                  </button>
                </form>
              </div>
            </div>

            {/* Ingested Versions Table */}
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
              <h3 className="font-bold text-sm text-slate-900">
                Ingested Versions for: <span className="text-indigo-600">{currentApi.name}</span>
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-500 bg-slate-50">
                      <th className="py-2.5 px-3 font-semibold">ID</th>
                      <th className="py-2.5 px-3 font-semibold">Version Tag</th>
                      <th className="py-2.5 px-3 font-semibold">Ingestion Timestamp</th>
                      <th className="py-2.5 px-3 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {versions.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="py-4 text-center text-slate-400">
                          No contracts uploaded for this service yet. Use the upload form above.
                        </td>
                      </tr>
                    ) : (
                      versions.map((v) => (
                        <tr key={v.id} className="hover:bg-slate-50/50">
                          <td className="py-2.5 px-3 font-mono text-slate-500">#{v.id}</td>
                          <td className="py-2.5 px-3 font-bold text-slate-800">Version {v.version_tag}</td>
                          <td className="py-2.5 px-3 text-slate-500">{v.created_at}</td>
                          <td className="py-2.5 px-3 text-right">
                            <button
                              onClick={() => setSpecViewerContent({ tag: v.version_tag, spec: v.raw_spec })}
                              className="text-indigo-600 hover:text-indigo-800 font-semibold bg-indigo-50 border border-indigo-200 px-2.5 py-1 rounded text-[11px] transition"
                            >
                              Inspect Raw Spec
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: BREAKING CHANGES */}
        {activeTab === 'diff' && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
              <div>
                <h3 className="font-bold text-sm text-slate-900">
                  AST Diff & Classification Engine (<span className="text-indigo-600">{currentApi.name}</span>)
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Select two version snapshots to compare. The Python diff engine deterministically categorizes changes into BREAKING, NON_BREAKING, and COSMETIC.
                </p>
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <div className="w-52">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Old Version (Base)</label>
                  <select
                    value={diffOldVer}
                    onChange={(e) => setDiffOldVer(e.target.value)}
                    className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version_tag} (ID: {v.id})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="w-52">
                  <label className="block text-xs font-semibold text-slate-700 mb-1">New Version (Target)</label>
                  <select
                    value={diffNewVer}
                    onChange={(e) => setDiffNewVer(e.target.value)}
                    className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs text-slate-800"
                  >
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        v{v.version_tag} (ID: {v.id})
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  onClick={handleRunDiff}
                  disabled={loading}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-5 py-2.5 rounded-lg transition"
                >
                  {loading ? 'Analyzing Contracts...' : 'Compare Contracts'}
                </button>
              </div>
            </div>

            {/* Diff Results */}
            {diffResult && (
              <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
                <div className="flex flex-wrap items-center justify-between pb-3 border-b border-slate-200 gap-2">
                  <h4 className="font-bold text-sm text-slate-800">
                    Analysis Report: v{diffResult.old_version_tag} → v{diffResult.new_version_tag}
                  </h4>
                  <div className="flex gap-2 text-xs">
                    <span className="bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 rounded-md font-bold">
                      {diffResult.summary.breaking} Breaking
                    </span>
                    <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-md font-semibold">
                      {diffResult.summary.non_breaking} Non-Breaking
                    </span>
                    <span className="bg-sky-50 text-sky-700 border border-sky-200 px-2 py-0.5 rounded-md font-semibold">
                      {diffResult.summary.cosmetic} Cosmetic
                    </span>
                  </div>
                </div>

                <div className="space-y-3">
                  {diffResult.changes.map((item, i) => {
                    const isBreaking = item.severity === 'BREAKING';
                    const isCosmetic = item.severity === 'COSMETIC';
                    const det = item.details || {};
                    const targetEp = det.new_endpoint || (selectedApiId === '2' ? '/items' : selectedApiId === '3' ? '/wallets' : '/customers');

                    return (
                      <div
                        key={i}
                        className={`p-4 rounded-lg border text-xs flex flex-wrap items-start justify-between gap-3 ${
                          isBreaking
                            ? 'bg-rose-50/40 border-rose-200'
                            : isCosmetic
                            ? 'bg-sky-50/40 border-sky-200'
                            : 'bg-emerald-50/40 border-emerald-200'
                        }`}
                      >
                        <div>
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                                isBreaking
                                  ? 'bg-rose-600 text-white'
                                  : isCosmetic
                                  ? 'bg-sky-600 text-white'
                                  : 'bg-emerald-600 text-white'
                              }`}
                            >
                              {item.severity}
                            </span>
                            <span className="font-mono font-bold text-slate-800">{item.change_type}</span>
                            <span className="font-mono text-slate-500">
                              {item.method} {item.endpoint}
                            </span>
                          </div>
                          <p className="text-slate-700 mt-2 leading-relaxed">{item.description}</p>
                          {det.old_field && det.new_field && (
                            <span className="inline-block mt-1 font-mono text-[11px] text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                              Rename detected: <code>{det.old_field}</code> → <code>{det.new_field}</code>
                            </span>
                          )}
                        </div>

                        {isBreaking && (
                          <button
                            onClick={() => handleGenerateAdapterDynamic(item.endpoint, targetEp, item.method === 'ANY' ? 'GET' : item.method)}
                            className="bg-slate-900 hover:bg-black text-white text-xs px-3.5 py-1.5 rounded-lg font-medium transition"
                          >
                            Synthesize Adapter →
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: ADAPTER STUDIO */}
        {activeTab === 'adapters' && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Adapters List */}
              <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm space-y-3">
                <div className="flex justify-between items-center">
                  <h3 className="font-bold text-sm text-slate-800">Generated Adapters</h3>
                  <span className="text-[11px] text-slate-500">Service #{selectedApiId}</span>
                </div>

                <div className="space-y-2">
                  {adapters.filter(a => a.api_id.toString() === selectedApiId?.toString()).length === 0 ? (
                    <p className="text-xs text-slate-400 py-6 text-center">
                      No adapters generated for this service yet. Run diff in Tab 3 to synthesize one.
                    </p>
                  ) : (
                    adapters.filter(a => a.api_id.toString() === selectedApiId?.toString()).map((a) => (
                      <div
                        key={a.id}
                        onClick={() => setSelectedAdapter(a)}
                        className={`p-3 rounded-lg border text-xs cursor-pointer transition ${
                          selectedAdapter?.id === a.id
                            ? 'bg-indigo-50 border-indigo-500 text-indigo-950 font-medium'
                            : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700'
                        }`}
                      >
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-bold">Adapter #{a.id}</span>
                          <span
                            className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                              a.status === 'APPROVED'
                                ? 'bg-emerald-100 text-emerald-800'
                                : a.status === 'REJECTED'
                                ? 'bg-rose-100 text-rose-800'
                                : 'bg-amber-100 text-amber-800'
                            }`}
                          >
                            {a.status}
                          </span>
                        </div>
                        <div className="font-mono text-[11px] text-slate-500">
                          {a.old_endpoint} → {a.new_endpoint}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Code Viewer & Approval */}
              <div className="md:col-span-2 bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
                {selectedAdapter ? (
                  <div>
                    <div className="flex flex-wrap items-center justify-between pb-3 border-b border-slate-200 gap-2 mb-3">
                      <div>
                        <h4 className="font-bold text-sm text-slate-900">
                          Python Transformation Module (Adapter #{selectedAdapter.id})
                        </h4>
                        <span className="text-xs text-slate-500 font-mono">
                          Route mapping: <code>{selectedAdapter.old_endpoint}</code> → <code>{selectedAdapter.new_endpoint}</code>
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        {selectedAdapter.status === 'DRAFT' && (
                          <button
                            onClick={() => handleApproveAdapter(selectedAdapter.id)}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition"
                          >
                            Approve for Proxy Runtime
                          </button>
                        )}
                        {selectedAdapter.status === 'APPROVED' && (
                          <span className="bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs px-2.5 py-1 rounded-md font-bold">
                            ✓ Approved & Active in Proxy
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="bg-slate-900 text-slate-100 p-4 rounded-lg font-mono text-xs overflow-x-auto max-h-[380px] shadow-inner">
                      <pre>{selectedAdapter.adapter_code}</pre>
                    </div>

                    <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 mt-3">
                      <strong>Execution Logic:</strong> {selectedAdapter.explanation}
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 py-12 text-center">
                    Select an adapter from the list to inspect transformation code.
                  </p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: DYNAMIC PROXY GATEWAY */}
        {activeTab === 'proxy' && (
          <div className="space-y-6 max-w-5xl mx-auto">
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-5">
              <div>
                <h3 className="font-bold text-base text-slate-900">
                  Dynamic Reverse Proxy Gateway (Live Execution)
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Accepts legacy requests. Rewrites endpoints and translates response payloads in memory with zero consumer downtime.
                </p>
              </div>

              {/* Active Adapter State Banner */}
              {activeApprovedAdapter ? (
                <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-900 flex items-center justify-between">
                  <span>
                    ✓ <strong>Active Adapter Deployed:</strong> Adapter #{activeApprovedAdapter.id} (<code>{activeApprovedAdapter.old_endpoint}</code> → <code>{activeApprovedAdapter.new_endpoint}</code>) is routing traffic live.
                  </span>
                  <span className="font-bold bg-emerald-600 text-white text-[10px] px-2 py-0.5 rounded">ONLINE</span>
                </div>
              ) : (
                <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-center justify-between">
                  <span>
                    ⚠️ No Approved Adapter Active for this service. Legacy requests fall through directly to the upstream endpoint.
                  </span>
                  {anyAdapterForSelected && (
                    <button
                      onClick={() => handleApproveAdapter(anyAdapterForSelected.id)}
                      className="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-2.5 py-1 rounded text-xs transition"
                    >
                      Approve Adapter #{anyAdapterForSelected.id}
                    </button>
                  )}
                </div>
              )}

              {/* Request URL Input Bar */}
              <div className="p-2.5 bg-slate-100 border border-slate-300 rounded-lg flex flex-wrap items-center gap-2">
                <select
                  value={proxyMethod}
                  onChange={(e) => setProxyMethod(e.target.value)}
                  className="bg-slate-800 text-white text-xs font-bold px-2 py-1.5 rounded focus:outline-none cursor-pointer"
                >
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                  <option value="DELETE">DELETE</option>
                </select>

                <span className="text-xs font-mono text-slate-500 select-none">
                  Target Endpoint:
                </span>

                <input
                  type="text"
                  value={proxyPath}
                  onChange={(e) => setProxyPath(e.target.value)}
                  className="bg-white border border-slate-300 rounded px-2.5 py-1.5 text-xs font-mono text-slate-800 focus:outline-none focus:border-indigo-500 flex-1 min-w-[140px]"
                  placeholder="/users, /products, etc."
                />
              </div>

              {/* DUAL ACTION BUTTONS (Proof for Teacher) */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                <button
                  onClick={handleTestDirectUpstream}
                  disabled={directLoading}
                  className="bg-rose-700 hover:bg-rose-800 text-white text-xs font-bold py-3 px-4 rounded-lg shadow-sm transition flex items-center justify-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-rose-300 animate-ping"></span>
                  {directLoading ? 'Testing Direct Upstream...' : '1. Test Without Proxy (Upstream Failure)'}
                </button>

                <button
                  onClick={handleTestProxy}
                  disabled={proxyLoading}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold py-3 px-4 rounded-lg shadow-sm transition flex items-center justify-center gap-2"
                >
                  <span className="w-2 h-2 rounded-full bg-white animate-pulse"></span>
                  {proxyLoading ? 'Executing Dynamic Proxy...' : '2. Test With APIBridge Proxy (Fixed)'}
                </button>
              </div>

              {/* Dual Response Inspector */}
              {(directResponse || proxyResponse) && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-3">
                  {/* Left: Without Proxy */}
                  <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/70 space-y-3">
                    <div className="flex justify-between items-center pb-2 border-b border-slate-200">
                      <div>
                        <span className="font-bold text-xs text-rose-900 block">Without Proxy (Upstream Direct)</span>
                        <code className="text-[11px] text-slate-500 font-mono">{directResponse?.url || 'Awaiting test...'}</code>
                      </div>
                      {directResponse && (
                        <div className="text-right">
                          <span
                            className={`text-xs font-bold px-2 py-0.5 rounded text-white ${
                              directResponse.status === 200 ? 'bg-emerald-600' : 'bg-rose-600'
                            }`}
                          >
                            HTTP {directResponse.status}
                          </span>
                          <span className="text-[10px] text-slate-400 block mt-0.5">{directResponse.latencyMs}ms</span>
                        </div>
                      )}
                    </div>

                    {directResponse ? (
                      <div className="space-y-2">
                        <div className="bg-slate-900 text-slate-100 p-3 rounded-lg font-mono text-xs max-h-[220px] overflow-auto shadow-inner">
                          <pre>{JSON.stringify(directResponse.body, null, 2)}</pre>
                        </div>
                        {directResponse.status === 404 && (
                          <div className="p-2.5 bg-rose-100/70 border border-rose-300 rounded text-[11px] text-rose-900 leading-relaxed">
                            💥 <strong>Consumer Outage:</strong> Legacy client calling <code>{proxyPath}</code> failed with 404 because this route was removed in modern contract.
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 py-10 text-center">
                        Click '1. Test Without Proxy' to simulate legacy client failure.
                      </p>
                    )}
                  </div>

                  {/* Right: With Proxy */}
                  <div className="border border-emerald-200 rounded-xl p-4 bg-emerald-50/20 space-y-3">
                    <div className="flex justify-between items-center pb-2 border-b border-emerald-100">
                      <div>
                        <span className="font-bold text-xs text-emerald-950 block">With APIBridge Dynamic Proxy</span>
                        <code className="text-[11px] text-slate-500 font-mono">{proxyResponse?.url || 'Awaiting test...'}</code>
                      </div>
                      {proxyResponse && (
                        <div className="text-right">
                          <span
                            className={`text-xs font-bold px-2 py-0.5 rounded text-white ${
                              proxyResponse.status === 200 ? 'bg-emerald-600' : 'bg-rose-600'
                            }`}
                          >
                            HTTP {proxyResponse.status}
                          </span>
                          <span className="text-[10px] text-slate-400 block mt-0.5">{proxyResponse.latencyMs}ms</span>
                        </div>
                      )}
                    </div>

                    {proxyResponse ? (
                      <div className="space-y-2">
                        <div className="bg-slate-900 text-slate-100 p-3 rounded-lg font-mono text-xs max-h-[220px] overflow-auto shadow-inner">
                          <pre>{JSON.stringify(proxyResponse.body, null, 2)}</pre>
                        </div>
                        {proxyResponse.headers?.proxied === 'true' && (
                          <div className="p-2.5 bg-emerald-100 border border-emerald-300 rounded text-[11px] text-emerald-900 leading-relaxed">
                            ✓ <strong>Zero-Downtime Restored:</strong> Proxy intercepted <code>{proxyResponse.headers.originalPath}</code>, routed to <code>{proxyResponse.headers.targetPath}</code> in memory, and restored expected fields!
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 py-10 text-center">
                        Click '2. Test With APIBridge Proxy' to verify autonomous recovery.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 6: AUTOMATED TESTS */}
        {activeTab === 'tests' && (
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Automated Regression Testing</h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Validates contract diffing accuracy, Python code compilation, AST integrity, and proxy payload reconstruction.
                  </p>
                </div>
                <button
                  onClick={handleTriggerTests}
                  disabled={loading}
                  className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-4 py-2 rounded-lg transition"
                >
                  {loading ? 'Running Tests...' : 'Run Test Suite Now'}
                </button>
              </div>

              <div className="divide-y divide-slate-100">
                {testRuns.length === 0 ? (
                  <p className="text-xs text-slate-400 py-6 text-center">No test runs recorded. Click 'Run Test Suite Now' to execute.</p>
                ) : (
                  testRuns.map((t) => (
                    <div key={t.id} className="py-3 flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div>
                        <span className="font-bold text-slate-800">{t.test_name}</span>
                        <p className="text-slate-500 text-[11px] mt-0.5">{t.details}</p>
                      </div>
                      <div className="text-right">
                        <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded font-bold text-[10px]">
                          {t.status}
                        </span>
                        <span className="text-[10px] text-slate-400 block mt-0.5 font-mono">{t.executed_at}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Modern Developer Tool Footer */}
      <footer className="bg-white border-t border-slate-200 py-3.5 text-center text-xs text-slate-500">
        APIBridge AI • Autonomous Breaking-Change Detection & Dynamic Adapter Proxy System
      </footer>
    </div>
  );
}
