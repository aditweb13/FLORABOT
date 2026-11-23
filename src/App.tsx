import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertCircle, AlertTriangle, ArrowRight, ArrowUpRight, Camera, Check,
  ChevronDown, ChevronLeft, ChevronRight, Download, Droplet, ExternalLink, FileText,
  Filter, Flower2, HeartPulse, HelpCircle, Info, Layers, Leaf, Menu, MessageCircle,
  MoreHorizontal, Plus, RefreshCw, Search, Send, Settings as SettingsIcon, ShieldAlert,
  ShieldCheck, Sparkles, Sprout, Stethoscope, Trash2, Upload, Wifi, WifiOff, X
} from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const API = '';

// Data Types
type Plant = {
  id: number;
  name: string;
  species: string;
  category: string;
  image: string | null;
  registered_at: string;
  location: string;
  notes: string;
  health_status: string;
  pot_size_cm: number;
  soil_type: string;
  watering_frequency_days: number;
  scan_count: number;
  last_scan: string | null;
  latest_analysis?: Analysis | null;
  analyses?: Analysis[];
  reports?: ReportItem[];
};

type Analysis = {
  id: number;
  image_id: number | null;
  plant_id: number;
  device_id: string | null;
  image: string;
  timestamp: string;
  plant_identification: string;
  plant_confidence: number | null;
  disease_detected: string;
  disease_name: string;
  disease_confidence: number | null;
  severity: string;
  health_status: string;
  confidence: number | null;
  symptoms: string;
  recommendations: string;
  prevention: string;
  recovery_plan: string;
  stress_status: string;
  stress_observations: string;
  watering_status: string;
  watering_quantity_ml: number | null;
  watering_reason: string;
  watering_instructions: string;
  provider_engine: string;
  provider_reference: string;
  plant_name?: string;
};

type ReportItem = {
  id: number;
  plant_id: number;
  plant_name?: string;
  analysis_id?: number | null;
  created_at: string;
  download_url: string;
};

type Device = {
  id: number;
  identifier: string;
  name: string;
  type: string;
  status: 'online' | 'offline' | 'stale';
  ip_address: string;
  stream_url: string;
  snapshot_url: string;
  last_communication: string | null;
  last_image_received: string | null;
  poll_interval_sec: number;
  is_active: boolean;
  created_at: string;
};

type DeviceLog = {
  id: number;
  event_type: string;
  message: string;
  timestamp: string;
};

type KnowledgeEntry = {
  id: number;
  title: string;
  category: string;
  plant_species: string;
  disease_name: string;
  summary: string;
  details_markdown: string;
  care_data: Record<string, string>;
  treatment_plan: string;
  prevention_tips: string;
  source_name: string;
  source_url: string;
};

type Conversation = {
  id: number;
  title: string;
  plant_id: number | null;
  created_at: string;
  message_count: number;
};

type ChatMessage = {
  id?: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at?: string;
};

type DashboardData = {
  total_plants: number;
  healthy_count: number;
  attention_count: number;
  diseased_count: number;
  unscanned_count: number;
  camera_online: boolean;
  latest_camera_image: string | null;
  latest_image_time: string | null;
  plants: Plant[];
  recent_analyses: Analysis[];
  recent_reports: ReportItem[];
  devices: Device[];
};

// API Helper
const api = async (path: string, init?: RequestInit) => {
  const res = await fetch(API + path, init);
  if (!res.ok) {
    let msg = 'Something went wrong. Please try again.';
    try {
      const err = await res.json();
      msg = err.detail || msg;
    } catch {}
    throw new Error(msg);
  }
  return res.headers.get('content-type')?.includes('application/json') ? res.json() : res;
};

const imgUrl = (p?: string | null) => (p ? `${API}${p}` : '');
const fmtDate = (d?: string | null) =>
  d ? new Date(d).toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
const fmtTime = (d?: string | null) =>
  d ? new Date(d).toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' }) : '';

const healthBadgeClass = (s = '') => {
  const low = s.toLowerCase();
  if (low.includes('healthy')) return 'healthy';
  if (low.includes('disease')) return 'danger';
  if (low.includes('stress') || low.includes('wilting') || low.includes('attention')) return 'attention';
  if (low.includes('inconclusive') || low.includes('unsuitable')) return 'muted';
  return 'neutral';
};

export default function App() {
  const [viewMode, setViewMode] = useState<'landing' | 'app'>('app');
  const [page, setPage] = useState('Dashboard');
  const [plants, setPlants] = useState<Plant[]>([]);
  const [dash, setDash] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedPlant, setSelectedPlant] = useState<Plant | null>(null);
  const [plantDetail, setPlantDetail] = useState<Plant | null>(null);
  const [activeModal, setActiveModal] = useState<string>('');
  const [activeAnalysis, setActiveAnalysis] = useState<Analysis | null>(null);
  const [activeKnowledge, setActiveKnowledge] = useState<KnowledgeEntry | null>(null);
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Plant | null>(null);

  const refreshAll = async () => {
    setLoading(true);
    try {
      const [d, p] = await Promise.all([api('/api/dashboard'), api('/api/plants')]);
      setDash(d);
      setPlants(p);
      if (selectedPlant) {
        const updated = p.find((x: Plant) => x.id === selectedPlant.id);
        if (updated) setSelectedPlant(updated);
      }
      setError('');
    } catch (e: any) {
      setError(e.message || 'Could not connect to FloraBOT backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(''), 3500);
      return () => clearTimeout(t);
    }
  }, [toast]);

  const openPlant = async (p: Plant) => {
    setSelectedPlant(p);
    try {
      const d = await api(`/api/plants/${p.id}`);
      setPlantDetail(d);
      setPage('Plant profile');
    } catch (e: any) {
      setToast(e.message);
    }
  };

  const navItems = [
    { section: 'MONITORING', items: ['Dashboard', 'Live Plant Monitor', 'AI Analysis', 'Health Reports', 'Monitoring History'] },
    { section: 'INTELLIGENCE', items: ['Plant AI Assistant', 'Plant Knowledge'] },
    { section: 'SYSTEM', items: ['Device Status', 'Settings'] }
  ];

  const getNavIcon = (name: string) => {
    switch (name) {
      case 'Dashboard': return <Activity size={18} />;
      case 'Live Plant Monitor': return <Camera size={18} />;
      case 'AI Analysis': return <Stethoscope size={18} />;
      case 'Health Reports': return <FileText size={18} />;
      case 'Monitoring History': return <HeartPulse size={18} />;
      case 'Plant AI Assistant': return <MessageCircle size={18} />;
      case 'Plant Knowledge': return <Sprout size={18} />;
      case 'Device Status': return <Wifi size={18} />;
      case 'Settings': return <SettingsIcon size={18} />;
      default: return <Leaf size={18} />;
    }
  };

  if (viewMode === 'landing') {
    return (
      <LandingPage
        dash={dash}
        onLaunch={() => setViewMode('app')}
        onOpenPage={(p: string) => {
          setViewMode('app');
          setPage(p);
        }}
      />
    );
  }

  return (
    <div className="shell">
      {/* Sidebar */}
      <aside className={`sidebar ${mobileNav ? 'show' : ''}`}>
        <div className="brand" onClick={() => setViewMode('landing')} style={{ cursor: 'pointer' }} title="Visit Public Landing Page">
          <div className="brand-mark">
            <Sprout size={22} />
          </div>
          <span>
            flora<span className="brand-light">bot</span> <small style={{ fontSize: '11px', color: '#52b788', fontWeight: 800 }}>AI</small>
          </span>
          <button className="icon-btn close-nav" onClick={() => setMobileNav(false)}>
            <X size={18} />
          </button>
        </div>

        <nav style={{ marginTop: '20px' }}>
          {navItems.map((group) => (
            <div key={group.section}>
              <div className="nav-group-title">{group.section}</div>
              {group.items.map((n) => (
                <button
                  key={n}
                  className={`nav-item ${page === n ? 'active' : ''}`}
                  onClick={() => {
                    setPage(n);
                    setMobileNav(false);
                  }}
                >
                  {getNavIcon(n)}
                  <span>{n}</span>
                  {n === 'Live Plant Monitor' && dash?.camera_online && <i className="nav-dot" style={{ background: '#52b788' }} />}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <button
            className="garden-card"
            style={{ width: '100%', cursor: 'pointer', textAlign: 'left', border: '1px solid #e1ece2' }}
            onClick={() => setViewMode('landing')}
          >
            <div className="garden-icon">
              <Flower2 size={18} />
            </div>
            <div>
              <b>FloraBOT Public Site</b>
              <span>View Landing Page</span>
            </div>
            <ExternalLink size={14} />
          </button>
          <div className="user-chip">
            <div className="avatar">FB</div>
            <div className="user-copy">
              <b>ESP32-CAM Gateway</b>
              <span>{dash?.camera_online ? '1 Camera Online' : 'Device Standby'}</span>
            </div>
          </div>
        </div>
      </aside>

      {mobileNav && <div className="mobile-scrim" onClick={() => setMobileNav(false)} />}

      {/* Main Content Area */}
      <main className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setMobileNav(true)}>
            <Menu />
          </button>
          <div className="breadcrumbs">
            <span style={{ cursor: 'pointer' }} onClick={() => setViewMode('landing')}>FloraBOT AI</span>
            <ChevronRight size={14} />
            <b>{page}</b>
          </div>
          <div className="top-actions">
            <span className="local-status">
              <i style={{ background: dash?.camera_online ? '#52b788' : '#9ca3af' }} />
              {dash?.camera_online ? 'ESP32-CAM Online' : 'Device Awaiting Stream'}
            </span>
            <button className="btn secondary small" onClick={refreshAll} disabled={loading} title="Refresh backend data">
              <RefreshCw size={14} className={loading ? 'spinner' : ''} /> Refresh
            </button>
            <button className="top-avatar" title="Settings" onClick={() => setPage('Settings')}>
              AI
            </button>
          </div>
        </header>

        <div className="content">
          {error && (
            <div className="alert error">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button onClick={refreshAll}>
                <RefreshCw size={14} /> Retry
              </button>
            </div>
          )}

          {page === 'Dashboard' && (
            <DashboardOverview
              dash={dash}
              loading={loading}
              onNavigate={(p: string) => setPage(p)}
              onRegister={() => setActiveModal('register')}
              onOpenPlant={openPlant}
              onAnalysisClick={(a: Analysis) => {
                setActiveAnalysis(a);
                setActiveModal('result');
              }}
              setToast={setToast}
            />
          )}

          {page === 'Live Plant Monitor' && (
            <LivePlantMonitorPage
              dash={dash}
              plants={plants}
              selectedPlant={selectedPlant}
              setSelectedPlant={setSelectedPlant}
              onAnalysisComplete={(a: Analysis) => {
                setActiveAnalysis(a);
                setActiveModal('result');
                refreshAll();
              }}
              onOpenSettings={() => setPage('Settings')}
              setToast={setToast}
            />
          )}

          {page === 'AI Analysis' && (
            <AIAnalysisPage
              plants={plants}
              selectedPlant={selectedPlant}
              onSelectAnalysis={(a: Analysis) => {
                setActiveAnalysis(a);
                setActiveModal('result');
              }}
              onConsultAssistant={(a: Analysis) => {
                setActiveAnalysis(a);
                setPage('Plant AI Assistant');
              }}
              setToast={setToast}
            />
          )}

          {page === 'Health Reports' && (
            <HealthReportsPage
              plants={plants}
              onOpenPlant={openPlant}
              onConsultChat={(r: ReportItem) => {
                setPage('Plant AI Assistant');
              }}
              setToast={setToast}
            />
          )}

          {page === 'Monitoring History' && (
            <MonitoringHistoryPage
              plants={plants}
              onSelectAnalysis={(a: Analysis) => {
                setActiveAnalysis(a);
                setActiveModal('result');
              }}
            />
          )}

          {page === 'Plant AI Assistant' && (
            <PlantAIAssistantPage
              plants={plants}
              selectedPlant={selectedPlant}
              activeAnalysis={activeAnalysis}
              setToast={setToast}
            />
          )}

          {page === 'Plant Knowledge' && (
            <PlantKnowledgePage
              onSelectEntry={(k: KnowledgeEntry) => setActiveKnowledge(k)}
              onAskChat={(k: KnowledgeEntry) => {
                setPage('Plant AI Assistant');
              }}
            />
          )}

          {page === 'Device Status' && (
            <DeviceStatusPage
              dash={dash}
              onRefresh={refreshAll}
              setToast={setToast}
            />
          )}

          {page === 'Settings' && (
            <SettingsPage
              onSave={() => {
                refreshAll();
                setToast('Settings successfully updated.');
              }}
              setToast={setToast}
            />
          )}

          {page === 'Plant profile' && plantDetail && (
            <PlantProfileView
              plant={plantDetail}
              onBack={() => setPage('Dashboard')}
              onScan={() => {
                setSelectedPlant(plantDetail);
                setPage('AI Analysis');
              }}
              onAnalysisClick={(a: Analysis) => {
                setActiveAnalysis(a);
                setActiveModal('result');
              }}
              onGenerateReport={async () => {
                try {
                  const r = await api(`/api/plants/${plantDetail.id}/reports`, { method: 'POST' });
                  window.open(r.download_url, '_blank');
                  setToast('PDF report generated and downloaded.');
                } catch (e: any) {
                  setToast(e.message);
                }
              }}
              onDelete={() => setDeleteTarget(plantDetail)}
              setToast={setToast}
            />
          )}
        </div>
      </main>

      {/* Modals */}
      {activeModal === 'register' && (
        <RegisterPlantModal
          onClose={() => setActiveModal('')}
          onSaved={(p: Plant) => {
            setPlants((prev) => [p, ...prev]);
            setSelectedPlant(p);
            setActiveModal('');
            setToast(`${p.name} registered into FloraBOT.`);
            refreshAll();
          }}
        />
      )}

      {deleteTarget && (
        <DeletePlantModal
          plant={deleteTarget}
          busy={busy}
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            setBusy(true);
            try {
              await api(`/api/plants/${deleteTarget.id}`, { method: 'DELETE' });
              setToast(`${deleteTarget.name} and all associated analyses deleted.`);
              setDeleteTarget(null);
              if (selectedPlant?.id === deleteTarget.id) setSelectedPlant(null);
              setPage('Dashboard');
              refreshAll();
            } catch (e: any) {
              setToast(e.message);
            } finally {
              setBusy(false);
            }
          }}
        />
      )}

      {activeModal === 'result' && activeAnalysis && (
        <AnalysisResultModal
          analysis={activeAnalysis}
          plant={plants.find((p) => p.id === activeAnalysis.plant_id) || selectedPlant}
          onClose={() => setActiveModal('')}
          onDownloadPdf={async () => {
            // Look up the report associated with this analysis
            try {
              const reps = await api(`/api/reports?plant_id=${activeAnalysis.plant_id}`);
              const match = reps.find((r: ReportItem) => r.analysis_id === activeAnalysis.id);
              if (match) {
                window.open(match.download_url, '_blank');
              } else {
                // Fall back: generate a new report on-demand
                const gen = await api(`/api/plants/${activeAnalysis.plant_id}/reports`, { method: 'POST' });
                window.open(gen.download_url, '_blank');
              }
            } catch {
              setToast('Could not fetch or generate PDF report.');
            }
          }}
          onAskAssistant={() => {
            setActiveModal('');
            setPage('Plant AI Assistant');
          }}
        />
      )}

      {activeKnowledge && (
        <KnowledgeDetailModal
          entry={activeKnowledge}
          onClose={() => setActiveKnowledge(null)}
          onAskAssistant={() => {
            setActiveKnowledge(null);
            setPage('Plant AI Assistant');
          }}
        />
      )}

      {/* Toast Notification */}
      {toast && (
        <div className="toast">
          <Check size={16} />
          <span>{toast}</span>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// 1. PUBLIC LANDING PAGE
// ============================================================================
function LandingPage({ dash, onLaunch, onOpenPage }: any) {
  return (
    <div className="landing-shell">
      <header className="landing-nav">
        <div className="brand">
          <div className="brand-mark">
            <Sprout size={22} />
          </div>
          <span>
            flora<span className="brand-light">bot</span> <small style={{ fontSize: '11px', color: '#52b788', fontWeight: 800 }}>AI</small>
          </span>
        </div>
        <nav className="landing-links">
          <a href="#features">Features</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#hardware">ESP32-CAM</a>
          <button className="btn primary small" onClick={onLaunch}>
            Launch Dashboard <ArrowRight size={14} />
          </button>
        </nav>
      </header>

      <section className="landing-hero">
        <div className="hero-copy">
          <div className="hero-badge">
            <Sparkles size={14} /> AUTONOMOUS BOTANICAL AI SYSTEM
          </div>
          <h1>Understand Your Plants. Help Them Thrive.</h1>
          <p>
            Real-time indoor plant monitoring powered by ESP32-CAM computer vision, automated disease diagnostics,
            wilting and moisture stress detection, and grounded botanical intelligence.
          </p>
          <div className="hero-actions">
            <button className="btn primary" onClick={onLaunch}>
              Open Dashboard <ArrowRight size={16} />
            </button>
            <button className="btn secondary" onClick={() => onOpenPage('Live Plant Monitor')}>
              <Camera size={16} /> Connect ESP32-CAM
            </button>
          </div>
        </div>

        <div className="hero-preview">
          <div className="hero-cam-tag">
            <i /> {dash?.camera_online ? 'ESP32-CAM STREAMING' : 'ESP32-CAM READY'}
          </div>
          {dash?.latest_camera_image ? (
            <img src={imgUrl(dash.latest_camera_image)} alt="Latest Camera Observation" />
          ) : (
            <div style={{ height: '290px', display: 'grid', placeItems: 'center', background: '#0f291c', borderRadius: '14px' }}>
              <Leaf size={64} style={{ color: '#52b788', opacity: 0.6 }} />
            </div>
          )}
          <div className="hero-diag-pill">
            <Stethoscope size={20} style={{ color: '#2d744a' }} />
            <div>
              <b>Automated Health Scan</b>
              <span>Computer Vision + Botanical RAG</span>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="landing-section" style={{ background: '#fff', borderTop: '1px solid #eef2ec' }}>
        <div className="section-center-head">
          <div className="eyebrow">INTELLIGENT CAPABILITIES</div>
          <h2>Designed for Real Botany, Not Just Uploads</h2>
          <p>
            FloraBOT AI is built around continuous hardware observation, scientific diagnostic pipelines,
            and contextual care explanations.
          </p>
        </div>
        <div className="feature-grid-3">
          <div className="f-card">
            <div className="f-icon"><Camera size={22} /></div>
            <h3>ESP32-CAM Integration</h3>
            <p>Wi-Fi enabled automatic image ingestion and heartbeat tracking. Live preview and automated periodic capture.</p>
          </div>
          <div className="f-card">
            <div className="f-icon"><Activity size={22} /></div>
            <h3>Computer Vision Diagnostics</h3>
            <p>Dual-engine leaf inspection analyzes chlorosis, necrotic spotting, and vegetative pigmentation with calibrated confidence.</p>
          </div>
          <div className="f-card">
            <div className="f-icon"><Droplet size={22} /></div>
            <h3>Watering Intelligence</h3>
            <p>Calculates millilitre watering targets based on container volume, leaf posture, and species drought tolerance.</p>
          </div>
          <div className="f-card">
            <div className="f-icon"><AlertTriangle size={22} /></div>
            <h3>Wilting &amp; Stress Analysis</h3>
            <p>Distinguishes thirst-induced leaf droop from root-rot suffocation before irreversible damage occurs.</p>
          </div>
          <div className="f-card">
            <div className="f-icon"><MessageCircle size={22} /></div>
            <h3>Contextual Plant AI Chatbot</h3>
            <p>An intelligent assistant that references your plant’s real history, latest scans, and curated botanical knowledge.</p>
          </div>
          <div className="f-card">
            <div className="f-icon"><FileText size={22} /></div>
            <h3>Automated PDF Reports</h3>
            <p>One-click downloadable formal botanical reports formatted with ReportLab containing treatment and recovery plans.</p>
          </div>
        </div>
      </section>

      <section id="how-it-works" className="landing-section">
        <div className="section-center-head">
          <div className="eyebrow">SYSTEM WORKFLOW</div>
          <h2>How FloraBOT AI Monitors Your Garden</h2>
        </div>
        <div className="how-it-works-steps">
          <div className="step-card">
            <span className="step-num">01</span>
            <h4>ESP32-CAM Capture</h4>
            <p>The camera captures high-resolution frames of plant leaves and posts them via Wi-Fi.</p>
          </div>
          <div className="step-card">
            <span className="step-num">02</span>
            <h4>Image Validation</h4>
            <p>The backend validates frame dimensions, verifies integrity, and filters corrupted frames.</p>
          </div>
          <div className="step-card">
            <span className="step-num">03</span>
            <h4>AI &amp; Stress Analysis</h4>
            <p>Computer vision inspects discoloration, spotting patterns, and leaf droop posture.</p>
          </div>
          <div className="step-card">
            <span className="step-num">04</span>
            <h4>Report &amp; Care Guidance</h4>
            <p>Botanical RAG retrieves treatment plans and calculates precise millilitre hydration targets.</p>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <b>FloraBOT AI System</b> — Complete Indoor Plant Monitoring &amp; Diagnostics Architecture.
      </footer>
    </div>
  );
}

// ============================================================================
// 2. DASHBOARD OVERVIEW PAGE
// ============================================================================
function DashboardOverview({ dash, loading, onNavigate, onRegister, onOpenPlant, onAnalysisClick, setToast }: any) {
  const chartData = useMemo(() => {
    if (!dash) return [];
    return [
      { name: 'Mon', healthy: dash.healthy_count || 1, issues: dash.attention_count + dash.diseased_count },
      { name: 'Today', healthy: dash.healthy_count, issues: dash.attention_count + dash.diseased_count }
    ];
  }, [dash]);

  const latestAnalysis = dash?.recent_analyses?.[0];

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">BOTANICAL HEALTH WORKSPACE</div>
          <h1>Plant Health Overview</h1>
          <p>Monitor, analyse and care for your indoor plants with real-time computer vision.</p>
        </div>
        <div className="heading-actions">
          <button className="btn secondary" onClick={onRegister}>
            <Plus size={16} /> Register Plant
          </button>
          <button className="btn primary" onClick={() => onNavigate('Live Plant Monitor')}>
            <Camera size={16} /> Live Camera Feed
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon green">
            <Sprout />
          </div>
          <span className="stat-label">Total Plants</span>
          <div className="stat-number">{loading ? '—' : dash?.total_plants ?? 0}</div>
          <span className="stat-note">Monitored indoor specimens</span>
          <span className="stat-ghost">01</span>
        </div>
        <div className="stat-card">
          <div className="stat-icon mint">
            <ShieldCheck />
          </div>
          <span className="stat-label">Healthy Vitality</span>
          <div className="stat-number">{loading ? '—' : dash?.healthy_count ?? 0}</div>
          <span className="stat-note">Normal vegetative turgor</span>
          <span className="stat-ghost">02</span>
        </div>
        <div className="stat-card">
          <div className="stat-icon orange">
            <HeartPulse />
          </div>
          <span className="stat-label">Needs Attention</span>
          <div className="stat-number">{loading ? '—' : dash?.attention_count ?? 0}</div>
          <span className="stat-note">Possible wilting or stress</span>
          <span className="stat-ghost">03</span>
        </div>
        <div className="stat-card">
          <div className="stat-icon purple">
            <AlertTriangle />
          </div>
          <span className="stat-label">Disease Alerts</span>
          <div className="stat-number">{loading ? '—' : dash?.diseased_count ?? 0}</div>
          <span className="stat-note">Detected active pathology</span>
          <span className="stat-ghost">04</span>
        </div>
      </div>

      {/* Camera & Diagnostics Split */}
      <div className="dashboard-lower" style={{ marginBottom: '24px' }}>
        {/* Camera Live Card */}
        <div className="card" style={{ padding: '19px' }}>
          <div className="card-heading">
            <div>
              <div className="eyebrow">HARDWARE FEED</div>
              <h3>Latest ESP32-CAM Observation</h3>
            </div>
            <button className="text-link" onClick={() => onNavigate('Live Plant Monitor')}>
              Live Monitor <ArrowRight size={14} />
            </button>
          </div>
          <div style={{ marginTop: '12px', height: '175px', borderRadius: '9px', overflow: 'hidden', background: '#1c2821', position: 'relative' }}>
            {dash?.latest_camera_image ? (
              <img src={imgUrl(dash.latest_camera_image)} alt="Camera Observation" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            ) : (
              <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#97a89b', gap: '8px' }}>
                <Camera size={32} />
                <span style={{ fontSize: '11px' }}>Awaiting frame transmission from ESP32-CAM</span>
              </div>
            )}
            <div style={{ position: 'absolute', bottom: '8px', left: '8px', background: '#0e1f16d4', color: '#fff', padding: '4px 8px', borderRadius: '5px', fontSize: '10px' }}>
              {dash?.latest_image_time ? `Received: ${fmtDate(dash.latest_image_time)} ${fmtTime(dash.latest_image_time)}` : 'No frames recorded yet'}
            </div>
          </div>
          <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: '#687e70' }}>
            <span>Hardware Status: <b style={{ color: dash?.camera_online ? '#2e7d32' : '#b45309' }}>{dash?.camera_online ? 'Connected / Online' : 'Standby / Awaiting Heartbeat'}</b></span>
            <button className="btn secondary small" onClick={async () => {
              try {
                await api('/api/camera/poll-now', { method: 'POST' });
                setToast('Camera frame polled and analyzed.');
              } catch (e: any) {
                setToast(e.message);
              }
            }}>
              <RefreshCw size={12} /> Poll Snapshot Now
            </button>
          </div>
        </div>

        {/* Latest AI Diagnostics Card */}
        <div className="card" style={{ padding: '19px' }}>
          <div className="card-heading">
            <div>
              <div className="eyebrow">LATEST ANALYSIS</div>
              <h3>Most Recent Diagnostic Check</h3>
            </div>
            {latestAnalysis && (
              <span className={`badge ${healthBadgeClass(latestAnalysis.health_status)}`}>
                {latestAnalysis.health_status}
              </span>
            )}
          </div>
          {latestAnalysis ? (
            <div style={{ marginTop: '12px', display: 'grid', gap: '10px' }}>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <img src={imgUrl(latestAnalysis.image)} alt="Analyzed leaf" style={{ width: '56px', height: '56px', borderRadius: '8px', objectFit: 'cover' }} />
                <div>
                  <b style={{ fontSize: '13px', color: '#253f30' }}>{latestAnalysis.plant_name || 'Plant'}</b>
                  <span style={{ fontSize: '11px', color: '#708376', display: 'block' }}>{latestAnalysis.plant_identification} · {fmtDate(latestAnalysis.timestamp)}</span>
                  <span style={{ fontSize: '10px', color: '#4b6b55' }}>Condition: {latestAnalysis.disease_name || 'Healthy'}</span>
                </div>
              </div>
              <div style={{ background: '#f6f9f5', padding: '10px', borderRadius: '8px', fontSize: '11px', color: '#4d6455', lineHeight: 1.5 }}>
                <b>Observation:</b> {latestAnalysis.symptoms}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', color: '#6a7d71' }}>
                  Watering: <b>{latestAnalysis.watering_quantity_ml ? `${latestAnalysis.watering_quantity_ml} ml` : latestAnalysis.watering_status}</b>
                </span>
                <button className="btn primary small" onClick={() => onAnalysisClick(latestAnalysis)}>
                  View Full Report
                </button>
              </div>
            </div>
          ) : (
            <div className="empty-activity">
              <Leaf />
              <b>No diagnostics run yet</b>
              <span>Transmit an ESP32-CAM frame or upload a photo to start.</span>
            </div>
          )}
        </div>
      </div>

      {/* Registered Plants Grid */}
      <div className="section-top plant-section-top">
        <div>
          <div className="eyebrow">YOUR COLLECTION</div>
          <h2>Monitored Plants</h2>
        </div>
        <button className="btn secondary small" onClick={onRegister}>
          <Plus size={14} /> Add Plant
        </button>
      </div>

      {dash?.plants?.length ? (
        <div className="plant-grid">
          {dash.plants.map((p: Plant) => (
            <article className="plant-card" key={p.id}>
              <div className="plant-photo">
                {p.image ? (
                  <img src={imgUrl(p.image)} alt={p.name} />
                ) : (
                  <div className="plant-placeholder">
                    <Leaf size={35} />
                    <span>{p.name.slice(0, 2).toUpperCase()}</span>
                  </div>
                )}
                <span className={`badge ${healthBadgeClass(p.health_status)} photo-badge`}>
                  {p.health_status}
                </span>
                <button className="card-arrow" onClick={() => onOpenPlant(p)} aria-label={`Open ${p.name}`}>
                  <ArrowUpRight size={17} />
                </button>
              </div>
              <div className="plant-card-copy">
                <h3>{p.name}</h3>
                <span className="species">{p.species} · {p.category}</span>
                <div className="plant-meta">
                  <span><Activity size={14} /> {p.scan_count} scans</span>
                  <span>Container: {p.pot_size_cm} cm</span>
                </div>
                <button className="view-plant" onClick={() => onOpenPlant(p)}>
                  Inspect Plant <ArrowRight size={14} />
                </button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="inline-empty">
          <div className="inline-empty-icon"><Flower2 /></div>
          <div>
            <b>No plants registered yet</b>
            <span>Register your indoor plants so ESP32-CAM observations are automatically assigned.</span>
          </div>
          <button className="btn secondary" onClick={onRegister}><Plus size={15} /> Register First Plant</button>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// 3. LIVE PLANT MONITOR PAGE
// ============================================================================
function LivePlantMonitorPage({ dash, plants, selectedPlant, setSelectedPlant, onAnalysisComplete, onOpenSettings, setToast }: any) {
  const [streamUrl, setStreamUrl] = useState(dash?.devices?.[0]?.stream_url || 'http://10.105.234.29:81/stream');
  const [snapshotUrl, setSnapshotUrl] = useState(dash?.devices?.[0]?.snapshot_url || 'http://10.105.234.29/capture');
  const [latestFrame, setLatestFrame] = useState<string | null>(dash?.latest_camera_image || null);
  const [isLiveStream, setIsLiveStream] = useState(false);
  const [pollingBusy, setPollingBusy] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const activeDevice = dash?.devices?.[0];

  const handlePollNow = async () => {
    setPollingBusy(true);
    try {
      const res = await api(`/api/camera/poll-now?url=${encodeURIComponent(snapshotUrl)}${selectedPlant ? `&plant_id=${selectedPlant.id}` : ''}`, {
        method: 'POST'
      });
      setLatestFrame(res.image_url);
      setToast('ESP32-CAM frame successfully ingested and analyzed!');
      if (res.analysis_id) {
        const fullA = await api(`/api/analyses/${res.analysis_id}`);
        onAnalysisComplete(fullA);
      }
    } catch (e: any) {
      setToast(`Snapshot failed: ${e.message}`);
    } finally {
      setPollingBusy(false);
    }
  };

  const handleManualUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploadFile(f);
    setPollingBusy(true);
    const fd = new FormData();
    fd.append('image', f);
    if (selectedPlant) fd.append('plant_id', String(selectedPlant.id));
    fd.append('device_id', activeDevice?.identifier || 'esp32-cam-01');

    try {
      const res = await api('/api/camera/upload', { method: 'POST', body: fd });
      setLatestFrame(res.image_url);
      setToast('Frame ingested into ESP32-CAM pipeline and analyzed.');
      if (res.analysis_id) {
        const fullA = await api(`/api/analyses/${res.analysis_id}`);
        onAnalysisComplete(fullA);
      }
    } catch (err: any) {
      setToast(err.message);
    } finally {
      setPollingBusy(false);
    }
  };

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">HARDWARE INTEGRATION</div>
          <h1>Live Plant Monitor</h1>
          <p>Real-time video preview and autonomous image ingestion from your ESP32-CAM hardware.</p>
        </div>
        <div className="heading-actions">
          <button className="btn secondary" onClick={onOpenSettings}>
            <SettingsIcon size={16} /> Configure Stream URLs
          </button>
        </div>
      </div>

      <div className="camera-layout">
        <div className="card camera-card">
          <div className="camera-top">
            <div className="cam-title">
              <span className={`cam-status ${activeDevice?.status === 'online' ? 'connected' : ''}`}>
                <i />
                {activeDevice?.status?.toUpperCase() || 'STANDBY'}
              </span>
              <span>{isLiveStream ? streamUrl : 'Latest Captured Frame'}</span>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                className={`btn small ${isLiveStream ? 'primary' : 'secondary'}`}
                onClick={() => setIsLiveStream(!isLiveStream)}
              >
                {isLiveStream ? 'Showing Live MJPEG' : 'Switch to Live MJPEG'}
              </button>
            </div>
          </div>

          <div className="camera-viewport" style={{ height: '360px' }}>
            {isLiveStream ? (
              <img
                src={streamUrl}
                alt="Live Camera Stream"
                className="camera-stream"
                onError={() => {
                  setToast('Live MJPEG stream unreachable. Ensure ESP32-CAM is powered and on the same Wi-Fi.');
                  setIsLiveStream(false);
                }}
              />
            ) : latestFrame ? (
              <img src={imgUrl(latestFrame)} alt="Latest Snapshot" className="camera-preview" />
            ) : (
              <div className="camera-unset">
                <div className="camera-icon-large">
                  <Camera size={34} />
                </div>
                <b>No Camera Image Available</b>
                <span>Click &quot;Poll Camera Now&quot; to fetch a snapshot from your ESP32-CAM.</span>
              </div>
            )}
            <span className="viewfinder v1" />
            <span className="viewfinder v2" />
            <span className="camera-time">
              {dash?.latest_image_time ? `Last frame: ${fmtDate(dash.latest_image_time)} ${fmtTime(dash.latest_image_time)}` : 'Hardware ready'}
            </span>
          </div>

          <div className="camera-controls">
            <button className="btn secondary" onClick={handlePollNow} disabled={pollingBusy}>
              <RefreshCw size={15} className={pollingBusy ? 'spinner' : ''} />
              {pollingBusy ? 'Fetching & Analyzing…' : 'Poll Camera Now'}
            </button>
            <label className="btn secondary" style={{ cursor: 'pointer' }}>
              <Upload size={15} /> Upload Test Leaf
              <input type="file" accept="image/*" hidden onChange={handleManualUpload} />
            </label>
          </div>

          <div className="camera-foot">
            <span><Wifi size={14} /> IP: {activeDevice?.ip_address || '10.105.234.29'}</span>
            <span>Images are automatically processed by Computer Vision upon arrival.</span>
          </div>
        </div>

        {/* Camera Sidebar info */}
        <div className="card camera-side">
          <div className="eyebrow">MONITORED TARGET</div>
          <h3>Assign Incoming Frames</h3>
          <p>Frames sent by ESP32-CAM will be associated with this plant record.</p>

          <label className="field-label">Target Plant</label>
          <select
            value={selectedPlant?.id || ''}
            onChange={(e) => setSelectedPlant(plants.find((p: Plant) => p.id === Number(e.target.value)) || null)}
          >
            <option value="">Select monitored plant…</option>
            {plants.map((p: Plant) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.species})
              </option>
            ))}
          </select>

          <div className="camera-tip">
            <div><Leaf size={18} /></div>
            <span>
              <b>Camera Positioning</b> Point the lens 15–35 cm from the foliage in bright, indirect light. Avoid strong backlight behind the leaves.
            </span>
          </div>

          <div style={{ marginTop: '16px', background: '#f8faf7', border: '1px solid #e7eee6', borderRadius: '8px', padding: '12px', fontSize: '11px', color: '#526859', lineHeight: 1.6 }}>
            <b>Hardware Endpoint:</b>
            <code style={{ display: 'block', margin: '4px 0', background: '#eef5ec', padding: '4px', borderRadius: '4px', fontSize: '10px' }}>
              POST /api/devices/{activeDevice?.identifier || 'esp32-cam-01'}/images
            </code>
            <span>ESP32-CAM firmware can POST JPEG directly to this URL at regular intervals.</span>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================================
// 4. AI ANALYSIS PAGE
// ============================================================================
function AIAnalysisPage({ plants, selectedPlant, onSelectAnalysis, onConsultAssistant, setToast }: any) {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);

  const fetchAnalyses = async () => {
    setLoading(true);
    try {
      const data = await api(`/api/analyses${filter !== 'all' ? `?health_filter=${filter}` : ''}`);
      setAnalyses(data);
    } catch (e: any) {
      setToast(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalyses();
  }, [filter]);

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">DIAGNOSTIC LOG</div>
          <h1>AI Health Analysis Records</h1>
          <p>Every analyzed camera frame with computer vision metrics, wilting status, and watering advice.</p>
        </div>
      </div>

      {/* Filter pills */}
      <div className="filter-bar">
        {['all', 'Healthy', 'Disease', 'Stress', 'Wilting', 'Inconclusive'].map((f) => (
          <button
            key={f}
            className={`filter-pill ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? 'All Analyses' : f}
          </button>
        ))}
      </div>

      {loading ? (
        <SkeletonGrid />
      ) : analyses.length ? (
        <div className="analysis-grid">
          {analyses.map((a: Analysis) => (
            <div className="analysis-card-full" key={a.id}>
              <div className="ac-top">
                <img src={imgUrl(a.image)} alt="Analyzed specimen" className="ac-img" />
                <div className="ac-head">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <h4>{a.plant_name || 'Monitored Plant'}</h4>
                    <span className={`badge ${healthBadgeClass(a.health_status)}`}>
                      {a.health_status}
                    </span>
                  </div>
                  <span>{a.plant_identification} · {fmtDate(a.timestamp)}</span>
                  <span style={{ color: '#2d6a4f', fontWeight: 600, marginTop: '2px' }}>
                    {a.disease_name || 'No Pathology Detected'}
                  </span>
                </div>
              </div>

              <div className="ac-box">
                <b>Visual Symptoms:</b> {a.symptoms}
              </div>

              {a.stress_status !== 'None' && (
                <div style={{ background: '#fef3c7', color: '#92400e', borderRadius: '7px', padding: '8px 10px', fontSize: '10px', marginTop: '6px' }}>
                  <b>Stress Observed:</b> {a.stress_status}
                </div>
              )}

              <div className="ac-water-row">
                <span>Watering Guidance:</span>
                <b>{a.watering_quantity_ml ? `${a.watering_quantity_ml} ml Target` : a.watering_status}</b>
              </div>

              <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                <button className="btn secondary small" style={{ flex: 1 }} onClick={() => onSelectAnalysis(a)}>
                  Inspect Findings
                </button>
                <button className="btn primary small" style={{ flex: 1 }} onClick={() => onConsultAssistant(a)}>
                  <MessageCircle size={13} /> Chat with AI
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Activity size={48} style={{ color: '#78a27c', marginBottom: '12px' }} />
          <h2>No analyses matching filter</h2>
          <p>Run a live camera capture or leaf upload to populate the diagnostics repository.</p>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// 5. HEALTH REPORTS PAGE
// ============================================================================
function HealthReportsPage({ plants, onOpenPlant, onConsultChat, setToast }: any) {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api('/api/reports')
      .then(setReports)
      .catch((e) => setToast(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return reports.filter((r) =>
      (r.plant_name || '').toLowerCase().includes(search.toLowerCase())
    );
  }, [reports, search]);

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">FORMAL DOCUMENTATION</div>
          <h1>Health &amp; Diagnostic Reports</h1>
          <p>Exportable PDF records generated automatically from your plant monitoring observations.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="search">
          <Search size={16} />
          <input
            placeholder="Search reports by plant name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span className="subtle">{filtered.length} reports</span>
      </div>

      <div className="card history-card">
        {loading ? (
          <div style={{ padding: '20px', textAlign: 'center' }}>Loading documents…</div>
        ) : filtered.length ? (
          filtered.map((r: ReportItem) => (
            <div className="report-row" key={r.id}>
              <div className="report-icon">
                <FileText />
              </div>
              <div className="history-main">
                <b>{r.plant_name} Health Report</b>
                <span>Generated {fmtDate(r.created_at)} · Formal PDF Document #{r.id}</span>
              </div>
              <a className="btn secondary small" href={r.download_url} target="_blank" rel="noreferrer">
                <Download size={14} /> Download PDF
              </a>
              <button className="btn primary small" onClick={() => onConsultChat(r)}>
                <MessageCircle size={14} /> Discuss with Bot
              </button>
            </div>
          ))
        ) : (
          <div className="empty-history">
            <div className="empty-icon"><FileText /></div>
            <b>No reports generated yet</b>
            <span>Reports are generated automatically each time an image is processed.</span>
          </div>
        )}
      </div>
    </section>
  );
}

// ============================================================================
// 6. MONITORING HISTORY & IMAGE COMPARISON PAGE
// ============================================================================
function MonitoringHistoryPage({ plants, onSelectAnalysis }: any) {
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [compareLeft, setCompareLeft] = useState<Analysis | null>(null);
  const [compareRight, setCompareRight] = useState<Analysis | null>(null);

  useEffect(() => {
    api('/api/analyses').then((data) => {
      setAnalyses(data);
      if (data.length >= 2) {
        setCompareLeft(data[0]);
        setCompareRight(data[1]);
      } else if (data.length === 1) {
        setCompareLeft(data[0]);
      }
    });
  }, []);

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">CHRONOLOGICAL LOG</div>
          <h1>Monitoring History &amp; Comparison</h1>
          <p>Inspect visual leaf changes over time to monitor recovery and growth.</p>
        </div>
      </div>

      {/* Side-by-Side Comparison */}
      <div className="card" style={{ padding: '20px', marginBottom: '24px' }}>
        <div className="card-heading" style={{ marginBottom: '16px' }}>
          <div>
            <div className="eyebrow">VISUAL PROGRESSION</div>
            <h3>Side-by-Side Image Comparison</h3>
          </div>
        </div>

        {compareLeft ? (
          <div className="compare-container">
            <div className="compare-side">
              <label className="field-label">Primary Scan</label>
              <select
                value={compareLeft.id}
                onChange={(e) => setCompareLeft(analyses.find((a) => a.id === Number(e.target.value)) || null)}
              >
                {analyses.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.plant_name} — {fmtDate(a.timestamp)} ({a.health_status})
                  </option>
                ))}
              </select>
              <img src={imgUrl(compareLeft.image)} alt="Scan Left" style={{ marginTop: '10px' }} />
              <span>{compareLeft.plant_identification} · {compareLeft.health_status}</span>
            </div>

            <div className="compare-side">
              <label className="field-label">Comparison Scan</label>
              {compareRight ? (
                <>
                  <select
                    value={compareRight.id}
                    onChange={(e) => setCompareRight(analyses.find((a) => a.id === Number(e.target.value)) || null)}
                  >
                    {analyses.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.plant_name} — {fmtDate(a.timestamp)} ({a.health_status})
                      </option>
                    ))}
                  </select>
                  <img src={imgUrl(compareRight.image)} alt="Scan Right" style={{ marginTop: '10px' }} />
                  <span>{compareRight.plant_identification} · {compareRight.health_status}</span>
                </>
              ) : (
                <div style={{ height: '220px', display: 'grid', placeItems: 'center', background: '#f5f7f3', borderRadius: '8px', color: '#88998d' }}>
                  Record a second scan to compare side-by-side.
                </div>
              )}
            </div>
          </div>
        ) : (
          <div style={{ padding: '24px', textAlign: 'center', color: '#829388' }}>
            No monitoring check-ins available for comparison.
          </div>
        )}
      </div>

      {/* Timeline List */}
      <div className="card history-card">
        <div className="card-heading" style={{ padding: '10px 0' }}>
          <h3>All Observation Check-ins ({analyses.length})</h3>
        </div>
        {analyses.map((a: Analysis) => (
          <button className="history-row" key={a.id} onClick={() => onSelectAnalysis(a)}>
            <img src={imgUrl(a.image)} alt={a.plant_name} />
            <div className="history-main">
              <span className="timeline-date">{fmtDate(a.timestamp)} at {fmtTime(a.timestamp)}</span>
              <b>{a.plant_name} <span className="soft-separator">/</span> {a.disease_name || a.health_status}</b>
              <span>{a.symptoms}</span>
            </div>
            <span className={`badge ${healthBadgeClass(a.health_status)}`}>{a.health_status}</span>
            <ChevronRight size={18} />
          </button>
        ))}
      </div>
    </section>
  );
}

// ============================================================================
// 7. PLANT AI ASSISTANT (CHATBOT)
// ============================================================================
function PlantAIAssistantPage({ plants, selectedPlant, activeAnalysis, setToast }: any) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvoId, setActiveConvoId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [busy, setBusy] = useState(false);
  const [plantContextId, setPlantContextId] = useState<number | null>(selectedPlant?.id || null);

  const fetchConversations = async () => {
    try {
      const data = await api('/api/conversations');
      setConversations(data);
      if (data.length > 0 && !activeConvoId) {
        loadConversation(data[0].id);
      } else if (data.length === 0) {
        startNewConversation();
      }
    } catch (e: any) {
      setToast(e.message);
    }
  };

  const loadConversation = async (id: number) => {
    setActiveConvoId(id);
    try {
      const res = await api(`/api/conversations/${id}`);
      setMessages(res.messages || []);
      if (res.plant_id) setPlantContextId(res.plant_id);
    } catch (e: any) {
      setToast(e.message);
    }
  };

  const startNewConversation = () => {
    setActiveConvoId(null);
    setMessages([
      {
        role: 'assistant',
        content: 'Hello, I am FloraBOT AI. I can assist with diagnosing visible leaf symptoms, calculating watering targets, and explaining your plant care reports. How can I help today?'
      }
    ]);
  };

  useEffect(() => {
    fetchConversations();
  }, []);

  const handleSend = async (textToSend?: string) => {
    const text = textToSend || inputText.trim();
    if (!text || busy) return;

    setInputText('');
    const newMsgs = [...messages, { role: 'user' as const, content: text }];
    setMessages(newMsgs);
    setBusy(true);

    try {
      const payload: any = {
        message: text,
        conversation_id: activeConvoId,
        plant_id: plantContextId
      };
      const res = await api('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      setActiveConvoId(res.conversation_id);
      setMessages(res.messages.map((m: any) => ({ role: m.role, content: m.content, created_at: m.created_at })));
      fetchConversations();
    } catch (err: any) {
      setMessages([...newMsgs, { role: 'assistant', content: `Notice: ${err.message}` }]);
    } finally {
      setBusy(false);
    }
  };

  const suggestedPrompts = [
    'Why are my plant leaves wilting?',
    'Explain the latest health analysis',
    'How much water in ml should I give?',
    'How do I treat fungal leaf spot?',
    'What light levels does my plant need?'
  ];

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">INTELLIGENT CONSULTATION</div>
          <h1>Plant AI Assistant</h1>
          <p>Ask questions grounded in your plant’s real camera scans and botanical knowledge.</p>
        </div>
      </div>

      <div className="full-chat-wrapper">
        {/* Left Conversations Sidebar */}
        <aside className="chat-convo-sidebar">
          <button className="btn primary small" onClick={startNewConversation} style={{ width: '100%' }}>
            <Plus size={14} /> New Conversation
          </button>
          <div className="convo-list">
            {conversations.map((c) => (
              <button
                key={c.id}
                className={`convo-item ${activeConvoId === c.id ? 'active' : ''}`}
                onClick={() => loadConversation(c.id)}
              >
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</span>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </aside>

        {/* Chat Main Area */}
        <div className="chat-main-area">
          <header className="chat-main-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '9px' }}>
              <div className="brand-mark" style={{ width: '28px', height: '28px' }}>
                <Sprout size={16} />
              </div>
              <b style={{ fontSize: '13px', color: '#274232' }}>FloraBOT Assistant</b>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '11px', color: '#748679' }}>Plant Context:</span>
              <select
                className="chat-context-select"
                value={plantContextId || ''}
                onChange={(e) => setPlantContextId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">General Botanical Knowledge</option>
                {plants.map((p: Plant) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.species})
                  </option>
                ))}
              </select>
            </div>
          </header>

          {/* Messages */}
          <div className="chat-messages-container">
            {messages.map((m, idx) => (
              <div key={idx} className={`chat-message ${m.role}`}>
                {m.role === 'assistant' && (
                  <div className="mini-bot">
                    <Sprout size={14} />
                  </div>
                )}
                <div>{m.content}</div>
              </div>
            ))}
            {busy && (
              <div className="chat-message assistant">
                <div className="mini-bot"><Sprout size={14} /></div>
                <div className="typing"><i /><i /><i /></div>
              </div>
            )}
          </div>

          {/* Suggested prompt pills */}
          <div className="prompt-pills-bar">
            {suggestedPrompts.map((txt) => (
              <button key={txt} className="prompt-pill-btn" onClick={() => handleSend(txt)}>
                {txt}
              </button>
            ))}
          </div>

          {/* Compose bar */}
          <form
            className="chat-input-bar"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <input
              placeholder="Ask about plant diseases, wilting symptoms, or watering recommendations…"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              disabled={busy}
              style={{ flex: 1, height: '40px', border: '1px solid #e2eae1', borderRadius: '8px', padding: '0 12px', fontSize: '12px' }}
            />
            <button className="btn primary" disabled={busy || !inputText.trim()}>
              <Send size={15} /> Send
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}

// ============================================================================
// 8. PLANT KNOWLEDGE PAGE
// ============================================================================
function PlantKnowledgePage({ onSelectEntry, onAskChat }: any) {
  const [entries, setEntries] = useState<KnowledgeEntry[]>([]);
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api(`/api/knowledge?category=${category}&query=${encodeURIComponent(search)}`)
      .then(setEntries)
      .finally(() => setLoading(false));
  }, [category, search]);

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">REFERENCE LIBRARY</div>
          <h1>Plant Knowledge &amp; Diagnostics Guide</h1>
          <p>Curated botanical profiles, phytopathological disease guides, and symptom treatments.</p>
        </div>
      </div>

      <div className="toolbar">
        <div className="search">
          <Search size={16} />
          <input
            placeholder="Search botanical library by species or disease…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="filter-bar" style={{ margin: 0 }}>
          {['all', 'indoor_plants', 'diseases', 'care_guides'].map((cat) => (
            <button
              key={cat}
              className={`filter-pill ${category === cat ? 'active' : ''}`}
              onClick={() => setCategory(cat)}
            >
              {cat === 'all' ? 'All Guides' : cat.replace('_', ' ').toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <SkeletonGrid />
      ) : entries.length ? (
        <div className="knowledge-grid">
          {entries.map((k) => (
            <div className="k-card" key={k.id}>
              <div>
                <span className={`k-badge ${k.category}`}>{k.category.replace('_', ' ')}</span>
                <h3>{k.title}</h3>
                <p>{k.summary}</p>
              </div>
              <div>
                <div className="k-meta">
                  <span>Source: {k.source_name}</span>
                </div>
                <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                  <button className="btn secondary small" style={{ flex: 1 }} onClick={() => onSelectEntry(k)}>
                    Read Full Profile
                  </button>
                  <button className="btn primary small" style={{ flex: 1 }} onClick={() => onAskChat(k)}>
                    Ask Bot
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <h2>No matching guides found</h2>
          <p>Try searching for Monstera, Pothos, Root Rot, or Powdery Mildew.</p>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// 9. DEVICE STATUS PAGE
// ============================================================================
function DeviceStatusPage({ dash, onRefresh, setToast }: any) {
  const [logs, setLogs] = useState<DeviceLog[]>([]);
  const device = dash?.devices?.[0];

  useEffect(() => {
    if (device) {
      api(`/api/devices/${device.identifier}/logs`).then(setLogs).catch(() => {});
    }
  }, [device]);

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">HARDWARE TOPOLOGY</div>
          <h1>ESP32-CAM Device Status</h1>
          <p>Real-time telemetry, communication logs, and connection health metrics.</p>
        </div>
        <button className="btn secondary" onClick={onRefresh}>
          <RefreshCw size={15} /> Check Health
        </button>
      </div>

      <div className="device-grid">
        <div className="device-card-full">
          <div className="dev-top">
            <div className="dev-icon">
              <Camera size={22} />
            </div>
            <span className={`dev-state ${device?.status || 'offline'}`}>
              <i style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'currentColor' }} />
              {(device?.status || 'offline').toUpperCase()}
            </span>
          </div>

          <h3 style={{ margin: '0 0 10px', font: '700 15px Manrope', color: '#1f382a' }}>
            {device?.name || 'ESP32-CAM Node'}
          </h3>

          <div className="dev-data-rows">
            <div><span>Device Identifier</span><b>{device?.identifier || 'esp32-cam-01'}</b></div>
            <div><span>Hardware Module</span><b>{device?.type || 'AI-Thinker ESP32-CAM'}</b></div>
            <div><span>Assigned IP</span><b>{device?.ip_address || '10.105.234.29'}</b></div>
            <div><span>Last Communication</span><b>{device?.last_communication ? fmtDate(device.last_communication) + ' ' + fmtTime(device.last_communication) : 'Never'}</b></div>
            <div><span>Last Image Received</span><b>{device?.last_image_received ? fmtDate(device.last_image_received) + ' ' + fmtTime(device.last_image_received) : 'None'}</b></div>
            <div><span>Poll Interval</span><b>{device?.poll_interval_sec || 60} seconds</b></div>
          </div>
        </div>

        <div className="device-card-full" style={{ background: '#f8faf7' }}>
          <div className="eyebrow" style={{ marginBottom: '8px' }}>FIRMWARE ENDPOINTS</div>
          <p style={{ fontSize: '11px', color: '#687e70', lineHeight: 1.6 }}>
            The ESP32-CAM firmware should be configured with the following parameters:
          </p>
          <div style={{ background: '#fff', border: '1px solid #e1ebe0', borderRadius: '8px', padding: '10px', fontSize: '10px', color: '#334e3e', fontFamily: 'monospace' }}>
            <div>Image POST: http://&lt;IP&gt;:8000/api/devices/esp32-cam-01/images</div>
            <div>Heartbeat: http://&lt;IP&gt;:8000/api/devices/esp32-cam-01/heartbeat</div>
            <div>Local Stream: http://10.105.234.29:81/stream</div>
            <div>Local Capture: http://10.105.234.29/capture</div>
          </div>
          <div style={{ marginTop: '14px', fontSize: '10px', color: '#7c8e82' }}>
            Firmware source code located at: <code>firmware/esp32_cam_florabot/esp32_cam_florabot.ino</code>
          </div>
        </div>
      </div>

      {/* Device Event Logs Table */}
      <div className="card" style={{ padding: '20px' }}>
        <h3 style={{ font: '700 15px Manrope', margin: '0 0 14px', color: '#213a2c' }}>Communication Activity Logs</h3>
        {logs.length ? (
          <table className="logs-table">
            <thead>
              <tr>
                <th>Event Type</th>
                <th>Message</th>
                <th>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td><span className="badge neutral">{l.event_type}</span></td>
                  <td>{l.message}</td>
                  <td>{fmtDate(l.timestamp)} {fmtTime(l.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ textAlign: 'center', padding: '20px', color: '#829589', fontSize: '11px' }}>
            No hardware events logged yet. Once the ESP32-CAM sends heartbeats or frames, they will appear here.
          </div>
        )}
      </div>
    </section>
  );
}

// ============================================================================
// 10. SETTINGS PAGE
// ============================================================================
function SettingsPage({ onSave, setToast }: any) {
  const [settingsData, setSettingsData] = useState<any>(null);
  const [streamUrl, setStreamUrl] = useState('http://10.105.234.29:81/stream');
  const [snapshotUrl, setSnapshotUrl] = useState('http://10.105.234.29/capture');
  const [testResult, setTestResult] = useState<any>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api('/api/settings').then((data) => {
      setSettingsData(data);
      if (data.camera_stream_url) setStreamUrl(data.camera_stream_url);
      if (data.camera_snapshot_url) setSnapshotUrl(data.camera_snapshot_url);
    });
  }, []);

  const handleTestCamera = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api(`/api/settings/test-camera?url=${encodeURIComponent(streamUrl)}`, { method: 'POST' });
      setTestResult(res);
      setToast(res.connected ? 'Camera endpoint responded!' : 'Camera endpoint unreachable.');
    } catch (e: any) {
      setTestResult({ connected: false, message: e.message });
    } finally {
      setTesting(false);
    }
  };

  return (
    <section>
      <div className="page-heading">
        <div>
          <div className="eyebrow">SYSTEM CONFIGURATION</div>
          <h1>System &amp; Camera Settings</h1>
          <p>Configure hardware endpoints, AI credentials status, and monitoring timeouts.</p>
        </div>
      </div>

      <div className="settings-grid">
        {/* Camera settings card */}
        <div className="card settings-card">
          <div className="settings-title">
            <div className="settings-icon"><Camera /></div>
            <div>
              <h3>ESP32-CAM Stream URLs</h3>
              <p>Configure the local network address of your ESP32-CAM hardware.</p>
            </div>
          </div>

          <label>
            Live MJPEG Stream URL
            <input
              value={streamUrl}
              onChange={(e) => setStreamUrl(e.target.value)}
              placeholder="http://10.105.234.29:81/stream"
            />
            <small>Used for continuous live preview in the dashboard.</small>
          </label>

          <label>
            Snapshot Still URL
            <input
              value={snapshotUrl}
              onChange={(e) => setSnapshotUrl(e.target.value)}
              placeholder="http://10.105.234.29/capture"
            />
            <small>Endpoint returning a single high-res JPEG frame on demand.</small>
          </label>

          <div className="settings-actions">
            <button className="btn primary" onClick={onSave}>Save URLs</button>
            <button className="btn secondary" onClick={handleTestCamera} disabled={testing}>
              <Wifi size={14} className={testing ? 'spinner' : ''} /> Test Connection
            </button>
          </div>

          {testResult && (
            <div className={`connection-note ${testResult.connected ? 'good' : ''}`}>
              <i /> {testResult.message}
            </div>
          )}
        </div>

        {/* AI & Services Card */}
        <div className="card settings-card">
          <div className="settings-title">
            <div className="settings-icon soft-purple"><Stethoscope /></div>
            <div>
              <h3>AI Diagnostics &amp; LLM</h3>
              <p>Environment configuration read securely from <code>backend/.env</code>.</p>
            </div>
          </div>

          <div className="service-row">
            <div className="service-mark"><Leaf size={16} /></div>
            <div>
              <b>Plant.id Health Assessment</b>
              <span>External Phytopathological Cloud API</span>
            </div>
            <span className={`service-state ${settingsData?.diagnosis_configured ? 'on' : ''}`}>
              <i /> {settingsData?.diagnosis_configured ? 'Active' : 'Using Local CV Engine'}
            </span>
          </div>

          <div className="service-row">
            <div className="service-mark groq"><MessageCircle size={16} /></div>
            <div>
              <b>Groq Chat LLM ({settingsData?.chat_model || 'llama-3.3-70b'})</b>
              <span>Conversational Assistant Provider</span>
            </div>
            <span className={`service-state ${settingsData?.chat_configured ? 'on' : ''}`}>
              <i /> {settingsData?.chat_configured ? 'Configured' : 'Using Local Botanical Agent'}
            </span>
          </div>

          <div className="service-row">
            <div className="service-mark"><Activity size={16} /></div>
            <div>
              <b>FloraBOT Computer Vision Engine</b>
              <span>Local Chlorosis, Wilting &amp; Leaf Geometry Analysis</span>
            </div>
            <span className="service-state on"><i /> Always Active</span>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================================
// 11. PLANT PROFILE VIEW
// ============================================================================
function PlantProfileView({ plant, onBack, onScan, onAnalysisClick, onGenerateReport, onDelete }: any) {
  return (
    <section>
      <button className="back-link" onClick={onBack}>
        <ChevronLeft size={16} /> Back to Dashboard
      </button>

      <div className="profile-hero">
        <div className="profile-image">
          {plant.image ? (
            <img src={imgUrl(plant.image)} alt={plant.name} />
          ) : (
            <div className="plant-placeholder"><Leaf size={45} /></div>
          )}
        </div>
        <div className="profile-info">
          <div className="eyebrow">PLANT SPECIMEN · #{String(plant.id).padStart(3, '0')}</div>
          <h1>{plant.name}</h1>
          <p>{plant.species} · {plant.category}</p>
          <div className="profile-tags">
            <span className={`badge ${healthBadgeClass(plant.health_status)}`}>{plant.health_status}</span>
            <span>Container: {plant.pot_size_cm} cm</span>
            <span>Soil: {plant.soil_type}</span>
          </div>
        </div>
        <div className="profile-actions">
          <button className="btn secondary" onClick={onGenerateReport}>
            <Download size={15} /> PDF Report
          </button>
          <button className="btn primary" onClick={onScan}>
            <Camera size={15} /> Check-in Scan
          </button>
          <button className="icon-btn" onClick={onDelete} title="Delete Plant" style={{ color: '#b94e46' }}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className="profile-stats">
        <div><span>Scans Logged</span><b>{plant.scan_count}</b></div>
        <div><span>Current Health</span><b className={`health-text ${healthBadgeClass(plant.health_status)}`}>{plant.health_status}</b></div>
        <div><span>Last Checked</span><b>{fmtDate(plant.last_scan)}</b></div>
        <div><span>Care Notes</span><b>{plant.notes || 'None recorded'}</b></div>
      </div>

      <div className="section-top profile-history-head">
        <div>
          <div className="eyebrow">CHECK-IN TIMELINE</div>
          <h2>Diagnostic History ({plant.analyses?.length || 0})</h2>
        </div>
      </div>

      {plant.analyses?.length ? (
        <div className="timeline">
          {plant.analyses.map((a: Analysis) => (
            <button className="timeline-entry" key={a.id} onClick={() => onAnalysisClick(a)}>
              <div className={`timeline-dot ${healthBadgeClass(a.health_status)}`} />
              <img src={imgUrl(a.image)} alt="Observation" className="timeline-photo" />
              <div className="timeline-info">
                <span className="timeline-date">{fmtDate(a.timestamp)} {fmtTime(a.timestamp)}</span>
                <b>{a.disease_name || a.health_status}</b>
                <span>{a.symptoms}</span>
              </div>
              <span className={`badge ${healthBadgeClass(a.health_status)}`}>{a.health_status}</span>
              <ChevronRight size={18} />
            </button>
          ))}
        </div>
      ) : (
        <div className="empty-history">
          <Activity size={36} />
          <b>No diagnostic scans logged yet</b>
          <span>Run a scan or transmit an image from ESP32-CAM.</span>
        </div>
      )}
    </section>
  );
}

// ============================================================================
// 12. MODAL COMPONENTS
// ============================================================================
function RegisterPlantModal({ onClose, onSaved }: any) {
  const [name, setName] = useState('');
  const [species, setSpecies] = useState('');
  const [category, setCategory] = useState('Houseplant');
  const [location, setLocation] = useState('Indoor Camera Station');
  const [notes, setNotes] = useState('');
  const [potSize, setPotSize] = useState(15);
  const [soilType, setSoilType] = useState('Well-Draining Potting Mix');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-head">
          <div>
            <div className="eyebrow">MONITORED SPECIMEN</div>
            <h2>Register Plant</h2>
            <p>Assign this plant to your ESP32-CAM monitoring stream.</p>
          </div>
          <button className="icon-btn" onClick={onClose}><X /></button>
        </div>

        <form onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError('');
          const fd = new FormData();
          fd.append('name', name);
          fd.append('species', species || 'Unknown');
          fd.append('category', category);
          fd.append('location', location);
          fd.append('notes', notes);
          fd.append('pot_size_cm', String(potSize));
          fd.append('soil_type', soilType);
          if (file) fd.append('image', file);

          try {
            const res = await api('/api/plants', { method: 'POST', body: fd });
            onSaved(res);
          } catch (err: any) {
            setError(err.message);
          } finally {
            setBusy(false);
          }
        }}>
          <label className="upload-drop">
            {preview ? <img src={preview} alt="Upload preview" /> : (
              <>
                <div className="upload-circle"><Upload size={16} /></div>
                <b>Add plant profile photo</b>
                <small>Optional · JPG, PNG, WEBP</small>
              </>
            )}
            <input type="file" accept="image/*" onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                setFile(f);
                setPreview(URL.createObjectURL(f));
              }
            }} />
          </label>

          <div className="form-grid">
            <label>Plant Name <b className="required">*</b>
              <input required placeholder="e.g. Sunny, Fiddle Leaf Fig" value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>Botanical Species
              <input placeholder="e.g. Monstera deliciosa" value={species} onChange={(e) => setSpecies(e.target.value)} />
            </label>
            <label>Category
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {['Houseplant', 'Succulent', 'Vegetable', 'Herb', 'Fern', 'Tree', 'Other'].map((x) => (
                  <option key={x} value={x}>{x}</option>
                ))}
              </select>
            </label>
            <label>Pot Diameter (cm)
              <input type="number" min="5" max="100" value={potSize} onChange={(e) => setPotSize(Number(e.target.value))} />
            </label>
          </div>

          <label className="wide-label" style={{ marginTop: '10px' }}>Soil Substrate
            <input placeholder="e.g. Aroid mix, Perlite &amp; Peat" value={soilType} onChange={(e) => setSoilType(e.target.value)} />
          </label>

          <label className="wide-label">Notes
            <textarea placeholder="Observations, special watering schedule, etc." value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>

          {error && <div className="form-error">{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn secondary" onClick={onClose}>Cancel</button>
            <button className="btn primary" disabled={busy}>
              {busy ? 'Saving…' : 'Register Plant'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function AnalysisResultModal({ analysis, plant, onClose, onDownloadPdf, onAskAssistant }: any) {
  return (
    <div className="modal-backdrop result-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="result-modal">
        <div className="result-top">
          <button className="icon-btn result-close" onClick={onClose}><X /></button>
          <div className={`result-emblem ${healthBadgeClass(analysis.health_status)}`}>
            {analysis.health_status === 'Healthy' ? <ShieldCheck size={24} /> : <AlertTriangle size={24} />}
          </div>
          <div className="eyebrow">FLORABOT DIAGNOSTIC REPORT</div>
          <h2>{analysis.health_status}</h2>
          <p>{analysis.disease_name ? `Visible signs consistent with ${analysis.disease_name}.` : 'Uniform healthy vegetative pigmentation observed.'}</p>
          <div className={`badge ${healthBadgeClass(analysis.health_status)}`}>
            Confidence: {analysis.confidence ? `${Math.round(analysis.confidence * 100)}%` : 'Calibrated Heuristic'}
          </div>
        </div>

        <div className="result-body">
          <div className="result-image">
            <img src={imgUrl(analysis.image)} alt="Analyzed specimen" />
            <span>ANALYZED SPECIMEN</span>
          </div>

          <div className="result-facts">
            <div><span>Species</span><b>{analysis.plant_identification}</b></div>
            <div><span>Identified Condition</span><b>{analysis.disease_name || 'None Identified'}</b></div>
            <div><span>Stress Posture</span><b>{analysis.stress_status}</b></div>
            <div><span>Watering Advice</span><b>{analysis.watering_quantity_ml ? `${analysis.watering_quantity_ml} ml Target` : analysis.watering_status}</b></div>
          </div>

          <div className="result-copy">
            <div>
              <h4>Observed Findings</h4>
              <p>{analysis.symptoms || 'Normal leaf pigmentation.'}</p>
            </div>
            <div>
              <h4>Hydration Reasoning</h4>
              <p>{analysis.watering_reason || 'Check soil moisture before applying water.'}</p>
            </div>
            <div>
              <h4>Treatment Protocol &amp; Care Guidance</h4>
              <p>{analysis.recommendations || 'Continue standard care and observe foliage.'}</p>
            </div>
          </div>

          <div className="result-actions" style={{ marginTop: '16px' }}>
            <button className="btn secondary" onClick={onAskAssistant}>
              <MessageCircle size={15} /> Ask Assistant About This
            </button>
            <button className="btn primary" onClick={onDownloadPdf}>
              <Download size={15} /> Download PDF Report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function KnowledgeDetailModal({ entry, onClose, onAskAssistant }: any) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ maxWidth: '640px' }}>
        <div className="modal-head">
          <div>
            <span className={`k-badge ${entry.category}`}>{entry.category.replace('_', ' ')}</span>
            <h2>{entry.title}</h2>
            <p>Source: {entry.source_name}</p>
          </div>
          <button className="icon-btn" onClick={onClose}><X /></button>
        </div>

        <div style={{ fontSize: '12px', color: '#3f5748', lineHeight: 1.7, whiteSpace: 'pre-line' }}>
          {entry.details_markdown}
        </div>

        {entry.treatment_plan && (
          <div style={{ background: '#f6faf4', border: '1px solid #d9ebda', borderRadius: '8px', padding: '12px', marginTop: '14px', fontSize: '11px', color: '#2b5a38' }}>
            <b>Treatment &amp; Action Plan:</b>
            <p style={{ margin: '4px 0 0' }}>{entry.treatment_plan}</p>
          </div>
        )}

        {entry.prevention_tips && (
          <div style={{ background: '#fefce8', border: '1px solid #fef08a', borderRadius: '8px', padding: '12px', marginTop: '10px', fontSize: '11px', color: '#854d0e' }}>
            <b>Prevention Protocol:</b>
            <p style={{ margin: '4px 0 0' }}>{entry.prevention_tips}</p>
          </div>
        )}

        <div className="modal-actions">
          <button className="btn secondary" onClick={onClose}>Close</button>
          <button className="btn primary" onClick={onAskAssistant}>
            <MessageCircle size={14} /> Ask Assistant About This Guide
          </button>
        </div>
      </div>
    </div>
  );
}

function DeletePlantModal({ plant, busy, onClose, onConfirm }: any) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && !busy && onClose()}>
      <div className="delete-modal">
        <button className="icon-btn delete-close" onClick={onClose} disabled={busy}><X size={18} /></button>
        <div className="delete-emblem"><Trash2 size={22} /></div>
        <div className="eyebrow">PERMANENT ACTION</div>
        <h2>Delete {plant.name}?</h2>
        <p>This permanently removes <b>{plant.name}</b> and all associated scan records, reports, and camera images.</p>
        <div className="delete-actions">
          <button className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn delete-confirm" onClick={onConfirm} disabled={busy}>
            {busy ? 'Deleting…' : 'Delete Plant'}
          </button>
        </div>
      </div>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="plant-grid">
      {[1, 2, 3].map((x) => (
        <div className="skeleton-card" key={x}>
          <div /><span /><i />
        </div>
      ))}
    </div>
  );
}
