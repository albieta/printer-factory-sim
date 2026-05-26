import type { Annotations, Data, Shape } from 'plotly.js';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Badge, Button, Form, ProgressBar, Spinner, Table } from 'react-bootstrap';
import { FaBolt, FaDownload, FaPlay, FaStop, FaSyncAlt, FaTrash } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { configAPI, getErrorMessage, scenariosAPI } from '../services/api';
import type {
  ConfigSummary,
  LogContents,
  LogFile,
  MetricsSnapshot,
  ScenarioRunRecord,
  ScenarioSummary,
  SimulationConfig,
} from '../types';
import { announceSimulationUpdate } from '../utils/simulationEvents';

const POLL_INTERVAL_MS = 2000;
const STDOUT_TAIL_LINES = 200;
const LS_CONFIG = 'scenarios.selectedConfig';
const LS_SCENARIO = 'scenarios.selectedScenario';
const LS_DAYS = 'scenarios.days';

const statusVariant = (status?: string): string => {
  switch (status) {
    case 'running':  return 'info';
    case 'stopping': return 'warning';
    case 'completed': return 'success';
    case 'failed':   return 'danger';
    default:         return 'secondary';
  }
};

const formatBytes = (size: number): string => {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
};

const AVAILABLE_MODELS = [
  { id: 'claude-opus-4-7',           label: 'Claude Opus 4.7',   description: 'Most capable, slower, expensive' },
  { id: 'claude-sonnet-4-6',         label: 'Claude Sonnet 4.6', description: 'Balanced performance and cost' },
  { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5',  description: 'Fast and cost-effective' },
];

// ── helpers ──────────────────────────────────────────────────────────────────

const lsGet = (key: string): string | null => {
  try { return localStorage.getItem(key); } catch { return null; }
};
const lsSet = (key: string, value: string): void => {
  try { localStorage.setItem(key, value); } catch { /* ignore */ }
};

// ── component ────────────────────────────────────────────────────────────────

const Scenarios: React.FC = () => {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [configs, setConfigs] = useState<ConfigSummary[]>([]);
  const [run, setRun] = useState<ScenarioRunRecord | null>(null);
  const [logFiles, setLogFiles] = useState<LogFile[]>([]);
  const [selectedLog, setSelectedLog] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<LogContents | null>(null);
  const [metrics, setMetrics] = useState<MetricsSnapshot[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // ── persisted selections ─────────────────────────────────────────────────
  const [selectedConfig, setSelectedConfigRaw] = useState<string>(lsGet(LS_CONFIG) ?? '');
  const [selectedScenario, setSelectedScenarioRaw] = useState<string>(lsGet(LS_SCENARIO) ?? '');
  const [days, setDaysRaw] = useState<number>(() => {
    const v = lsGet(LS_DAYS);
    return v ? (Number(v) || 5) : 5;
  });

  const setSelectedConfig = (v: string) => { lsSet(LS_CONFIG, v); setSelectedConfigRaw(v); };
  const setSelectedScenario = (v: string) => { lsSet(LS_SCENARIO, v); setSelectedScenarioRaw(v); };
  const setDays = (v: number) => { lsSet(LS_DAYS, String(v)); setDaysRaw(v); };

  const [autoFollow, setAutoFollow] = useState(true);
  const [selectedModel, setSelectedModel] = useState<string>('claude-haiku-4-5-20251001');
  const [thinkingEnabled, setThinkingEnabled] = useState<boolean>(false);
  const [fastMode, setFastMode] = useState<boolean>(false);
  const [parallelAgents, setParallelAgents] = useState<boolean>(false);
  const [currentConfig, setCurrentConfig] = useState<SimulationConfig | null>(null);
  const logBoxRef = useRef<HTMLPreElement | null>(null);

  // ── Loaders ─────────────────────────────────────────────────────────────

  const loadLibraries = useCallback(async () => {
    try {
      const [scenariosRes, configRes] = await Promise.all([
        scenariosAPI.list(),
        configAPI.getConfig(),
      ]);
      setScenarios(scenariosRes.data.scenarios);
      setConfigs(scenariosRes.data.configs);
      setCurrentConfig(configRes.data);

      // Only set defaults when localStorage has no saved value
      setSelectedConfigRaw((prev) => {
        if (prev) return prev;
        const stub = scenariosRes.data.configs.find((c) => c.name === 'sim-stub.json');
        const next = (stub ?? scenariosRes.data.configs[0])?.name ?? '';
        lsSet(LS_CONFIG, next);
        return next;
      });
      setSelectedScenarioRaw((prev) => {
        if (prev) return prev;
        const smoke = scenariosRes.data.scenarios.find((s) => s.name === 'smoke-test.json');
        const next = (smoke ?? scenariosRes.data.scenarios[0])?.name ?? '';
        lsSet(LS_SCENARIO, next);
        return next;
      });
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load scenarios.'));
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const response = await scenariosAPI.status();
      setRun(response.data.run);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load run status.'));
    }
  }, []);

  const loadLogFiles = useCallback(async () => {
    try {
      const response = await scenariosAPI.listLogs();
      setLogFiles(response.data.files);
      if (!selectedLog && response.data.files.length) {
        const agent = response.data.files.find((f) => f.name.endsWith('Factory.log'));
        setSelectedLog((agent ?? response.data.files[0]).name);
      }
    } catch {
      // non-fatal
    }
  }, [selectedLog]);

  const loadLogContent = useCallback(async (name: string) => {
    try {
      const response = await scenariosAPI.readLog(name);
      setLogContent(response.data);
    } catch (err) {
      setError(getErrorMessage(err, `Failed to read ${name}.`));
    }
  }, []);

  const loadMetrics = useCallback(async () => {
    try {
      const response = await scenariosAPI.metrics(200);
      setMetrics(response.data.snapshots);
    } catch {
      // non-fatal
    }
  }, []);

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    void loadLibraries();
    void loadStatus();
    void loadLogFiles();
    void loadMetrics();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Polling while a run is active ────────────────────────────────────────
  useEffect(() => {
    if (!run || run.status !== 'running') return;
    const id = window.setInterval(() => {
      void loadStatus();
      void loadLogFiles();
      void loadMetrics();
      if (selectedLog) void loadLogContent(selectedLog);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [run, loadStatus, loadLogFiles, loadMetrics, loadLogContent, selectedLog]);

  // ── Refresh log content when user picks another file ────────────────────
  useEffect(() => {
    if (selectedLog) void loadLogContent(selectedLog);
  }, [selectedLog, loadLogContent]);

  // ── Auto-scroll stdout pane while a run is active ────────────────────────
  useEffect(() => {
    if (autoFollow && logBoxRef.current) {
      logBoxRef.current.scrollTop = logBoxRef.current.scrollHeight;
    }
  }, [run?.stdout_lines.length, autoFollow]);

  // ── Notify other tabs when a run finishes ────────────────────────────────
  const lastStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (lastStatusRef.current === 'running' && run?.status && run.status !== 'running') {
      announceSimulationUpdate();
      setNotice(`Run ${run.run_id} ${run.status}.`);
    }
    lastStatusRef.current = run?.status;
  }, [run?.status, run?.run_id]);

  // ── Actions ──────────────────────────────────────────────────────────────

  const handleStart = async () => {
    if (!selectedConfig || !selectedScenario) return;
    try {
      setSubmitting(true);
      setNotice(null);
      const response = await scenariosAPI.start({
        config: selectedConfig,
        scenario: selectedScenario,
        days,
        model: selectedModel,
        thinking_enabled: thinkingEnabled,
        fast_mode: fastMode,
        parallel_agents: parallelAgents,
      });
      setRun(response.data);
      setNotice(`Started ${response.data.run_id} (${response.data.scenario} / ${response.data.config}).`);
      setError(null);
      await loadLogFiles();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to start scenario.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleStop = async () => {
    try {
      await scenariosAPI.stop();
      await loadStatus();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to stop scenario.'));
    }
  };

  const handleClearLogs = async () => {
    if (!window.confirm('Delete every file under logs/? This cannot be undone.')) return;
    try {
      await scenariosAPI.clearLogs();
      setLogContent(null);
      setSelectedLog(null);
      await loadLogFiles();
      await loadMetrics();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to clear logs.'));
    }
  };

  const handleDownloadLogs = () => {
    // Trigger a browser download by navigating to the streaming endpoint
    const a = document.createElement('a');
    a.href = '/api/scenarios/logs/download';
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // ── Derived data ─────────────────────────────────────────────────────────

  const stdoutTail = useMemo(() => {
    if (!run) return [];
    return run.stdout_lines.slice(-STDOUT_TAIL_LINES);
  }, [run]);

  const progress = useMemo(() => {
    if (!run) return 0;
    if (run.status === 'completed') return 100;
    if (run.days <= 0) return 0;
    return Math.min(100, Math.round((run.current_day / run.days) * 100));
  }, [run]);

  const scenarioDetail = useMemo(
    () => scenarios.find((s) => s.name === selectedScenario) ?? null,
    [scenarios, selectedScenario],
  );

  const configDetail = useMemo(
    () => configs.find((c) => c.name === selectedConfig) ?? null,
    [configs, selectedConfig],
  );

  const inventoryChart = useMemo(() => {
    if (!metrics.length) return null;
    const dayLabels = metrics.map((m) => `D${m.day}`);
    const mfg = metrics.map((m) => Object.values(m.manufacturer.inventory ?? {}).reduce((a, b) => a + Number(b || 0), 0));
    const retailStock = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + Object.values(r.stock ?? {}).reduce((a, b) => a + Number(b || 0), 0), 0),
    );
    const providerStock = metrics.map((m) =>
      m.providers.reduce((acc, p) => acc + Object.values(p.stock ?? {}).reduce((a, b) => a + Number(b || 0), 0), 0),
    );
    return { days: dayLabels, mfg, retailStock, providerStock };
  }, [metrics]);

  const demandChart = useMemo(() => {
    if (!metrics.length) return null;
    const dayLabels = metrics.map((m) => `D${m.day}`);
    const placed = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + (r.customer_orders?.placed_today ?? 0), 0),
    );
    const fulfilled = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + (r.customer_orders?.fulfilled_today ?? 0), 0),
    );
    const backordered = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + (r.customer_orders?.backordered_today ?? 0), 0),
    );
    return { days: dayLabels, placed, fulfilled, backordered };
  }, [metrics]);

  const capacityChart = useMemo(() => {
    if (!metrics.length) return null;
    const dayLabels: string[] = metrics.map((m) => `D${m.day}`);
    const lines: number[] = metrics.map((m) => m.manufacturer?.capacity?.assembly_lines ?? 1);
    const workers: number[] = metrics.map((m) => m.manufacturer?.capacity?.workers_per_line ?? 1);
    const dailyHours: number[] = metrics.map((m) => m.manufacturer?.capacity?.daily_assembly_hours ?? 8.0);
    return { days: dayLabels, lines, workers, dailyHours };
  }, [metrics]);

  const financialChart = useMemo(() => {
    if (!metrics.length) return null;
    const dayLabels: string[] = metrics.map((m) => `D${m.day}`);
    const costs: number[] = metrics.map((m) => m.manufacturer?.financials?.total_costs ?? 0);
    const revenue: number[] = metrics.map((m) => m.manufacturer?.financials?.total_revenue ?? 0);
    const profit: number[] = metrics.map((m) => m.manufacturer?.financials?.net_profit ?? 0);
    return { days: dayLabels, costs, revenue, profit };
  }, [metrics]);

  // ── Printer price chart: manufacturer wholesale + retailer retail ───────────
  const printerPriceChart = useMemo(() => {
    if (!metrics.length) return null;
    const dayLabels = metrics.map((m) => `D${m.day}`);
    const traces: Data[] = [];

    const productNames = new Set<string>();
    metrics.forEach((m) => Object.keys(m.manufacturer?.prices ?? {}).forEach((k) => productNames.add(k)));

    productNames.forEach((product) => {
      const vals = metrics.map((m) => {
        const p = m.manufacturer?.prices?.[product];
        return p != null ? Number(p) : null;
      });
      if (vals.some((v) => v != null)) {
        traces.push({
          x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers',
          name: `Wholesale: ${product}`, line: { dash: 'solid' }, connectgaps: true,
        } as Data);
      }
    });

    metrics[0]?.retailers.forEach((retailer, ri) => {
      const retailerName = retailer.name;
      const rProductNames = new Set<string>();
      metrics.forEach((m) => Object.keys(m.retailers[ri]?.prices ?? {}).forEach((k) => rProductNames.add(k)));
      rProductNames.forEach((product) => {
        const vals = metrics.map((m) => {
          const p = m.retailers[ri]?.prices?.[product];
          return p != null ? Number(p) : null;
        });
        if (vals.some((v) => v != null)) {
          traces.push({
            x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers',
            name: `${retailerName}: ${product}`, line: { dash: 'dot' }, connectgaps: true,
          } as Data);
        }
      });
    });

    return traces.length ? { days: dayLabels, traces } : null;
  }, [metrics]);

  // ── Material price chart: provider cheapest tier per component ────────────
  const materialPriceChart = useMemo(() => {
    if (!metrics.length) return null;
    const dayLabels = metrics.map((m) => `D${m.day}`);
    const traces: Data[] = [];

    const providerProductNames = new Set<string>();
    metrics.forEach((m) =>
      m.providers.forEach((p) => Object.keys(p.prices ?? {}).forEach((k) => providerProductNames.add(k))),
    );

    metrics[0]?.providers.forEach((provider, pi) => {
      const providerName = provider.name;
      providerProductNames.forEach((product) => {
        const vals = metrics.map((m) => {
          const tiers = m.providers[pi]?.prices?.[product];
          if (!tiers || typeof tiers !== 'object') return null;
          const tierVals = Object.values(tiers).map(Number).filter((v) => !isNaN(v));
          return tierVals.length ? Math.min(...tierVals) : null;
        });
        if (vals.some((v) => v != null)) {
          traces.push({
            x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers',
            name: `${providerName}: ${product}`, line: { dash: 'dashdot' }, connectgaps: true,
          } as Data);
        }
      });
    });

    return traces.length ? { days: dayLabels, traces } : null;
  }, [metrics]);

  // ── Events overlay: horizontal bars per scenario event (numeric x-axis) ───
  const eventsOverlay = useMemo(() => {
    const events = scenarioDetail?.events;
    if (!events?.length) return null;

    // Derive full day range from scenario definition (not just simulated days)
    const maxScenarioDay = Math.max(...events.map((ev) => ev.end_day ?? ev.start_day ?? 1), 1);

    const shapes: Partial<Shape>[] = events
      .filter((ev) => ev.start_day != null && ev.end_day != null)
      .map((ev, i) => ({
        type: 'rect' as const,
        xref: 'x' as const,
        yref: 'y' as const,
        x0: ev.start_day,
        x1: ev.end_day,
        y0: i - 0.4,
        y1: i + 0.4,
        fillcolor: `hsl(${(i * 67) % 360}, 60%, 55%)`,
        opacity: 0.75,
        line: { width: 0 },
      }));

    const annotations: Partial<Annotations>[] = events
      .filter((ev) => ev.start_day != null)
      .map((ev, i) => ({
        x: ev.start_day ?? 0,
        y: i,
        text: ev.name ?? `event ${i + 1}`,
        xanchor: 'left' as const,
        showarrow: false,
        font: { color: '#fff', size: 11 },
      }));

    const yLabels = events.map((ev, i) => ev.name ?? `event ${i + 1}`);

    return { shapes, annotations, yLabels, eventCount: events.length, maxScenarioDay };
  }, [scenarioDetail]);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Simulation</div>
          <h1>Run autonomous scenarios</h1>
          <p>
            Pick a config (which agents are active) and a scenario (which market events fire on which days), then watch
            the three apps respond in real time. Every run streams to <code>logs/</code> on disk and to the panels below.
          </p>
        </div>
      </div>

      <PageGuide
        title="Scenario Runner"
        controls="Choose a config + scenario + day count, then press Start. Use sim-stub.json to test plumbing without spending Claude tokens; switch to sim.json to bring the three skills online."
        next="Open the agent logs (Factory.log, ChipSupply Co.log, PrinterWorld.log) to see exactly what each role decided. Metrics chart aggregates all three apps."
        tip="A run keeps writing to the engine's databases. If you want a clean comparison, restart the dev script to reseed databases before launching a second scenario."
      />

      {error ? <Alert variant="danger" dismissible onClose={() => setError(null)}>{error}</Alert> : null}
      {notice ? <Alert variant="success" dismissible onClose={() => setNotice(null)}>{notice}</Alert> : null}

      <div className="action-bar">
        <div>
          <div className="section-kicker">Launch a run</div>
          <h3 className="mb-1">Configuration</h3>
          <p className="text-muted mb-0">
            Combine one config with one scenario and choose how many days to simulate (1–60).
          </p>
        </div>
        <div className="action-buttons d-flex flex-wrap gap-2">
          <Button variant="success" onClick={() => void handleStart()} disabled={submitting || run?.status === 'running'}>
            <FaPlay className="me-2" />
            {submitting ? 'Starting…' : 'Start scenario'}
          </Button>
          <Button variant="warning" onClick={() => void handleStop()} disabled={run?.status !== 'running'}>
            <FaStop className="me-2" />
            Stop
          </Button>
          <Button variant="outline-secondary" onClick={() => void loadStatus()}>
            <FaSyncAlt className="me-2" />
            Refresh
          </Button>
          <Button variant="outline-primary" onClick={handleDownloadLogs} disabled={!logFiles.length}>
            <FaDownload className="me-2" />
            Download logs
          </Button>
          <Button variant="outline-danger" onClick={() => void handleClearLogs()}>
            <FaTrash className="me-2" />
            Clear logs/
          </Button>
        </div>
      </div>

      {loadingList ? (
        <div className="empty-state d-flex align-items-center gap-3">
          <Spinner animation="border" size="sm" /> Loading scenarios…
        </div>
      ) : (
        <div className="two-column">
          <div className="surface-panel card-body">
            <div className="section-title"><h4>Pick a config</h4></div>
            <Form.Select value={selectedConfig} onChange={(e) => setSelectedConfig(e.target.value)}>
              {configs.map((cfg) => (
                <option key={cfg.name} value={cfg.name}>
                  {cfg.name}{cfg.uses_skills ? ' — agents active' : ' — stub agents'}
                </option>
              ))}
            </Form.Select>
            {configDetail ? (
              <div className="metric-list compact-list mt-3">
                <div className="metric-item stat-row"><span>Manufacturer</span><strong>{configDetail.manufacturer ?? '—'}</strong></div>
                <div className="metric-item stat-row"><span>Retailers</span><strong>{configDetail.retailers?.join(', ') || '—'}</strong></div>
                <div className="metric-item stat-row"><span>Providers</span><strong>{configDetail.providers?.join(', ') || '—'}</strong></div>
                <div className="metric-item stat-row"><span>Drives Claude skills</span><strong>{configDetail.uses_skills ? 'Yes (real LLM calls)' : 'No (stub agents)'}</strong></div>
              </div>
            ) : null}
          </div>

          <div className="surface-panel card-body">
            <div className="section-title"><h4>Pick a scenario</h4></div>
            <Form.Select value={selectedScenario} onChange={(e) => setSelectedScenario(e.target.value)}>
              {scenarios.map((sc) => (
                <option key={sc.name} value={sc.name}>{sc.name} — {sc.scenario_name ?? 'unnamed'}</option>
              ))}
            </Form.Select>
            <Form.Group className="mt-3">
              <Form.Label>Days to simulate</Form.Label>
              <Form.Control type="number" min={1} max={60} value={days} onChange={(e) => setDays(Number(e.target.value) || 1)} />
            </Form.Group>
            {scenarioDetail?.events?.length ? (
              <div className="metric-list compact-list mt-3">
                {scenarioDetail.events.map((event, idx) => (
                  <div className="metric-item" key={idx}>
                    <div className="stat-row">
                      <strong>{event.name ?? `event ${idx + 1}`}</strong>
                      <span className="badge badge-neutral">Day {event.start_day}–{event.end_day}</span>
                    </div>
                    <div className="text-muted mt-1">{event.description ?? 'No description.'}</div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="surface-panel card-body">
            <div className="section-title"><h4>Choose model &amp; config</h4></div>
            <Form.Group>
              <Form.Label>Claude model</Form.Label>
              <Form.Select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
                {AVAILABLE_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>{m.label}</option>
                ))}
              </Form.Select>
              {AVAILABLE_MODELS.find((m) => m.id === selectedModel) && (
                <div className="text-muted small mt-1">
                  {AVAILABLE_MODELS.find((m) => m.id === selectedModel)?.description}
                </div>
              )}
            </Form.Group>
            <Form.Group className="mt-3">
              <Form.Check
                type="switch"
                id="thinking-switch"
                label="Enable extended thinking"
                checked={thinkingEnabled}
                disabled={fastMode}
                onChange={(e) => setThinkingEnabled(e.target.checked)}
              />
              <div className="text-muted small mt-1">
                {thinkingEnabled
                  ? 'Extended thinking enabled — agents will spend more time reasoning'
                  : 'Extended thinking disabled — faster execution'}
              </div>
            </Form.Group>
            <Form.Group className="mt-3">
              <Form.Check
                type="switch"
                id="fast-mode-switch"
                label="Fast mode (scripted agents)"
                checked={fastMode}
                onChange={(e) => {
                  setFastMode(e.target.checked);
                  if (e.target.checked) setThinkingEnabled(false);
                }}
              />
              <div className="text-muted small mt-1">
                {fastMode
                  ? 'Fast mode ON — deterministic scripted agents replace Claude (~60× faster, no API cost)'
                  : 'Fast mode OFF — Claude LLM agents make real decisions (slower, uses API tokens)'}
              </div>
            </Form.Group>
            <Form.Group className="mt-3">
              <Form.Check
                type="switch"
                id="parallel-agents-switch"
                label="Parallel agents"
                checked={parallelAgents}
                onChange={(e) => setParallelAgents(e.target.checked)}
              />
              <div className="text-muted small mt-1">
                {parallelAgents
                  ? 'Parallel ON — all agents run at the same time (faster, but each acts on pre-fetched state and may miss same-turn peer writes)'
                  : 'Parallel OFF — agents run sequentially: retailer → manufacturer → provider (correct causal ordering, manufacturer sees retailer orders placed this turn)'}
              </div>
            </Form.Group>
            <div className="metric-list compact-list mt-3">
              <div className="metric-item stat-row">
                <span>Selected model</span>
                <strong className="mono">{fastMode ? 'scripted (no LLM)' : selectedModel}</strong>
              </div>
              <div className="metric-item stat-row">
                <span>Thinking mode</span>
                <strong>{fastMode ? 'N/A' : thinkingEnabled ? 'Enabled' : 'Disabled'}</strong>
              </div>
              <div className="metric-item stat-row">
                <span>Fast mode</span>
                <strong>{fastMode ? 'ON — scripted agents' : 'OFF — LLM agents'}</strong>
              </div>
              <div className="metric-item stat-row">
                <span>Agent execution</span>
                <strong>{parallelAgents ? 'Parallel' : 'Sequential (retailer → mfr → provider)'}</strong>
              </div>
            </div>
          </div>

          {scenarioDetail && (currentConfig || true) && (
            <div className="surface-panel card-body">
              <div className="section-title"><h4>Scenario recommendations</h4></div>
              <p className="text-muted small mb-4">
                This scenario recommends specific assembly and cost configuration. Click apply to use these values, or continue with current settings.
              </p>

              {scenarioDetail.recommended_assembly && (
                <div className="mb-4 p-3 bg-light rounded">
                  <div className="d-flex justify-content-between align-items-center mb-3 gap-3">
                    <div>
                      <h6 className="mb-2">Assembly Capacity</h6>
                      {currentConfig && (
                        <div className="text-muted small">
                          <div>Current: {currentConfig.assembly_lines} line{currentConfig.assembly_lines !== 1 ? 's' : ''} × {currentConfig.workers_per_line} worker{currentConfig.workers_per_line !== 1 ? 's' : ''} × {currentConfig.shift_hours}h</div>
                          <div>Recommended: {scenarioDetail.recommended_assembly.assembly_lines} line{scenarioDetail.recommended_assembly.assembly_lines !== 1 ? 's' : ''} × {scenarioDetail.recommended_assembly.workers_per_line} worker{scenarioDetail.recommended_assembly.workers_per_line !== 1 ? 's' : ''} × {scenarioDetail.recommended_assembly.shift_hours}h</div>
                        </div>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {(() => {
                        const isSame = !!(currentConfig &&
                          currentConfig.assembly_lines === scenarioDetail.recommended_assembly!.assembly_lines &&
                          currentConfig.workers_per_line === scenarioDetail.recommended_assembly!.workers_per_line &&
                          currentConfig.shift_hours === scenarioDetail.recommended_assembly!.shift_hours);
                        return (
                          <Button
                            variant="primary"
                            size="sm"
                            disabled={isSame}
                            title={isSame ? 'Current assembly configuration matches recommendation' : ''}
                            onClick={async () => {
                              try {
                                const result = await configAPI.applyScenarioAssembly(scenarioDetail.recommended_assembly);
                                setCurrentConfig(result.data);
                                setNotice('Applied recommended assembly configuration');
                                setTimeout(() => setNotice(null), 3000);
                              } catch (err) {
                                setError(getErrorMessage(err, 'Failed to apply assembly configuration'));
                              }
                            }}
                          >
                            Apply recommended
                          </Button>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              )}

              {scenarioDetail.recommended_costs && (
                <div className="p-3 bg-light rounded">
                  <div className="d-flex justify-content-between align-items-center gap-3">
                    <div>
                      <h6 className="mb-2">Costs</h6>
                      {currentConfig && (
                        <div className="text-muted small">
                          <div>Current: ${currentConfig.cost_per_assembly_line}/line, ${currentConfig.cost_per_worker_per_hour}/hr, max {currentConfig.max_workers_per_line}/line</div>
                          <div>Recommended: ${scenarioDetail.recommended_costs.cost_per_assembly_line}/line, ${scenarioDetail.recommended_costs.cost_per_worker_per_hour}/hr, max {scenarioDetail.recommended_costs.max_workers_per_line}/line</div>
                        </div>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {(() => {
                        const isSame = !!(currentConfig &&
                          currentConfig.cost_per_assembly_line === scenarioDetail.recommended_costs!.cost_per_assembly_line &&
                          currentConfig.cost_per_worker_per_hour === scenarioDetail.recommended_costs!.cost_per_worker_per_hour &&
                          currentConfig.max_workers_per_line === scenarioDetail.recommended_costs!.max_workers_per_line);
                        return (
                          <Button
                            variant="primary"
                            size="sm"
                            disabled={isSame}
                            title={isSame ? 'Current cost configuration matches recommendation' : ''}
                            onClick={async () => {
                              try {
                                const result = await configAPI.applyScenarioCosts(scenarioDetail.recommended_costs);
                                setCurrentConfig(result.data);
                                setNotice('Applied recommended cost configuration');
                                setTimeout(() => setNotice(null), 3000);
                              } catch (err) {
                                setError(getErrorMessage(err, 'Failed to apply cost configuration'));
                              }
                            }}
                          >
                            Apply recommended
                          </Button>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="card mt-3">
        <div className="card-header d-flex justify-content-between align-items-center gap-3 flex-wrap">
          <span className="d-flex align-items-center gap-2">
            <FaBolt /> Current run
          </span>
          {run ? (
            <span className="d-flex align-items-center gap-3">
              <Badge bg={statusVariant(run.status)}>{run.status.toUpperCase()}</Badge>
              <span className="text-muted mono">Day {run.current_day} / {run.days}</span>
            </span>
          ) : <span className="text-muted">No run launched yet</span>}
        </div>
        <div className="card-body">
          {run ? (
            <>
              <div className="metric-list compact-list">
                <div className="metric-item stat-row"><span>Run ID</span><strong className="mono">{run.run_id}</strong></div>
                <div className="metric-item stat-row"><span>Config</span><strong className="mono">{run.config}</strong></div>
                <div className="metric-item stat-row"><span>Scenario</span><strong className="mono">{run.scenario}</strong></div>
                <div className="metric-item stat-row"><span>Started</span><strong>{new Date(run.started_at).toLocaleString()}</strong></div>
                {run.finished_at ? (
                  <div className="metric-item stat-row"><span>Finished</span><strong>{new Date(run.finished_at).toLocaleString()}</strong></div>
                ) : null}
                {run.exit_code != null ? (
                  <div className="metric-item stat-row"><span>Exit code</span><strong>{run.exit_code}</strong></div>
                ) : null}
              </div>

              <div className="mt-3">
                <ProgressBar
                  now={progress}
                  label={`${progress}%`}
                  animated={run.status === 'running'}
                  variant={statusVariant(run.status)}
                />
              </div>

              <div className="d-flex justify-content-between align-items-center mt-3">
                <h5 className="mb-0">Engine stdout (last {STDOUT_TAIL_LINES} lines)</h5>
                <Form.Check
                  type="switch"
                  id="auto-follow-switch"
                  label="Auto-follow"
                  checked={autoFollow}
                  onChange={(e) => setAutoFollow(e.target.checked)}
                />
              </div>
              <pre
                ref={logBoxRef}
                className="mono mt-2 p-3"
                style={{ background: '#0d1117', color: '#d6deeb', maxHeight: 320, overflow: 'auto', borderRadius: 8 }}
              >
                {stdoutTail.join('\n') || '(no output yet)'}
              </pre>
            </>
          ) : (
            <div className="empty-state">Pick a config + scenario and press Start to launch a run.</div>
          )}
        </div>
      </div>

      <div className="card mt-3">
        <div className="card-header d-flex justify-content-between align-items-center gap-3 flex-wrap">
          <span>Agent &amp; engine logs ({logFiles.length} files in <code>logs/</code>)</span>
          <Form.Select
            style={{ maxWidth: 360 }}
            value={selectedLog ?? ''}
            onChange={(e) => setSelectedLog(e.target.value || null)}
          >
            <option value="">— pick a log file —</option>
            {logFiles.map((file) => (
              <option key={file.name} value={file.name}>
                {file.name} ({formatBytes(file.size)})
              </option>
            ))}
          </Form.Select>
        </div>
        <div className="card-body">
          {selectedLog && logContent ? (
            <pre
              className="mono p-3"
              style={{ background: '#0d1117', color: '#d6deeb', maxHeight: 420, overflow: 'auto', borderRadius: 8 }}
            >
              {logContent.content || '(file is empty)'}
            </pre>
          ) : (
            <div className="empty-state">
              Engine writes <code>day-NNN-{'<agent>'}.log</code>, <code>day-NNN-api-calls.jsonl</code>, and
              <code> day-NNN-bash-calls.jsonl</code>. Once a run starts, the files appear here automatically.
            </div>
          )}
        </div>
      </div>

      {/* ── Inventory + Demand charts ─── */}
      <div className="data-grid mt-3">
        <div className="chart-container">
          {inventoryChart ? (
            <ResponsivePlot
              data={[
                { x: inventoryChart.days, y: inventoryChart.providerStock, type: 'scatter', mode: 'lines+markers', name: 'Provider stock' },
                { x: inventoryChart.days, y: inventoryChart.mfg, type: 'scatter', mode: 'lines+markers', name: 'Manufacturer inventory' },
                { x: inventoryChart.days, y: inventoryChart.retailStock, type: 'scatter', mode: 'lines+markers', name: 'Retailer stock' },
              ]}
              layout={{
                title: { text: 'Inventory across the chain' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Units in hand (sum)' } },
                margin: { t: 56, r: 24, b: 56, l: 56 },
              }}
              minHeight={300}
            />
          ) : (
            <div className="empty-state">Metrics chart will populate after the first day completes.</div>
          )}
        </div>
        <div className="chart-container">
          {demandChart ? (
            <ResponsivePlot
              data={[
                { x: demandChart.days, y: demandChart.placed, type: 'bar', name: 'Placed', marker: { color: '#d18a1a' } },
                { x: demandChart.days, y: demandChart.fulfilled, type: 'bar', name: 'Fulfilled', marker: { color: '#2f7d4a' } },
                { x: demandChart.days, y: demandChart.backordered, type: 'bar', name: 'Backordered', marker: { color: '#b6463b' } },
              ]}
              layout={{
                barmode: 'group',
                title: { text: 'Daily customer demand outcomes' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Customer orders' } },
                margin: { t: 56, r: 24, b: 56, l: 56 },
              }}
              minHeight={300}
            />
          ) : (
            <div className="empty-state">Demand chart waits for the first metrics snapshot.</div>
          )}
        </div>
      </div>

      {/* ── Capacity charts ─── */}
      <div className="data-grid mt-3">
        <div className="chart-container">
          {capacityChart ? (
            <ResponsivePlot
              data={[
                { x: capacityChart.days, y: capacityChart.lines, type: 'scatter', mode: 'lines+markers', name: 'Assembly lines', marker: { color: '#0066cc' } },
                { x: capacityChart.days, y: capacityChart.workers, type: 'scatter', mode: 'lines+markers', name: 'Workers per line', marker: { color: '#ff6600' } },
              ]}
              layout={{
                title: { text: 'Assembly capacity expansion' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Count' } },
                margin: { t: 56, r: 24, b: 56, l: 56 },
              }}
              minHeight={300}
            />
          ) : (
            <div className="empty-state">Capacity evolution chart waits for the first metrics snapshot.</div>
          )}
        </div>
        <div className="chart-container">
          {capacityChart ? (
            <ResponsivePlot
              data={[
                { x: capacityChart.days, y: capacityChart.dailyHours, type: 'scatter', mode: 'lines+markers', name: 'Daily assembly hours', marker: { color: '#228B22' } },
              ]}
              layout={{
                title: { text: 'Total daily assembly capacity' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Hours' } },
                margin: { t: 56, r: 24, b: 56, l: 56 },
              }}
              minHeight={300}
            />
          ) : (
            <div className="empty-state">Capacity hours chart waits for the first metrics snapshot.</div>
          )}
        </div>
      </div>

      {/* ── Financial charts ─── */}
      <div className="data-grid mt-3">
        <div className="chart-container">
          {financialChart ? (
            <ResponsivePlot
              data={[
                { x: financialChart.days, y: financialChart.costs, type: 'scatter', mode: 'lines+markers', name: 'Total costs', marker: { color: '#dc3545' } },
                { x: financialChart.days, y: financialChart.revenue, type: 'scatter', mode: 'lines+markers', name: 'Total revenue', marker: { color: '#28a745' } },
              ]}
              layout={{
                title: { text: 'Financial performance' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Amount ($)' } },
                margin: { t: 56, r: 24, b: 56, l: 56 },
              }}
              minHeight={300}
            />
          ) : (
            <div className="empty-state">Financial chart waits for the first metrics snapshot.</div>
          )}
        </div>
        <div className="chart-container">
          {financialChart ? (
            <ResponsivePlot
              data={[
                { x: financialChart.days, y: financialChart.profit, type: 'scatter', mode: 'lines+markers', name: 'Net profit', marker: { color: financialChart.profit.some((p) => p < 0) ? '#ffc107' : '#0dcaf0' } },
              ]}
              layout={{
                title: { text: 'Net profit evolution' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Profit ($)' } },
                margin: { t: 56, r: 24, b: 56, l: 56 },
              }}
              minHeight={300}
            />
          ) : (
            <div className="empty-state">Profit chart waits for the first metrics snapshot.</div>
          )}
        </div>
      </div>

      {/* ── Price charts ─── */}
      <div className="data-grid mt-3">
        <div className="chart-container">
          {printerPriceChart ? (
            <ResponsivePlot
              data={printerPriceChart.traces}
              layout={{
                title: { text: 'Printer prices (wholesale vs retail)' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Price ($)' } },
                legend: { orientation: 'h', y: -0.25 },
                margin: { t: 56, r: 24, b: 80, l: 56 },
              }}
              minHeight={320}
            />
          ) : (
            <div className="empty-state">Printer price chart shows manufacturer wholesale and retailer retail after the first day.</div>
          )}
        </div>
        <div className="chart-container">
          {materialPriceChart ? (
            <ResponsivePlot
              data={materialPriceChart.traces}
              layout={{
                title: { text: 'Material prices (provider components)' },
                xaxis: { title: { text: 'Simulated day' } },
                yaxis: { title: { text: 'Price ($)' } },
                legend: { orientation: 'h', y: -0.25 },
                margin: { t: 56, r: 24, b: 80, l: 56 },
              }}
              minHeight={320}
            />
          ) : (
            <div className="empty-state">Material price chart shows provider component prices after the first day.</div>
          )}
        </div>
      </div>

      {/* ── Events timeline (full width, numeric axis so all events render correctly) ─── */}
      <div className="chart-container mt-3">
        {eventsOverlay ? (
          <ResponsivePlot
            data={[
              {
                // Dummy trace to anchor the numeric x-axis to the full scenario range
                x: [0.5, eventsOverlay.maxScenarioDay + 0.5],
                y: [null, null],
                type: 'scatter',
                mode: 'none' as const,
                showlegend: false,
              },
            ]}
            layout={{
              title: { text: 'Scenario events timeline' },
              xaxis: {
                title: { text: 'Simulated day' },
                range: [0.5, eventsOverlay.maxScenarioDay + 0.5],
              },
              yaxis: {
                title: { text: '' },
                tickvals: eventsOverlay.yLabels.map((_, i) => i),
                ticktext: eventsOverlay.yLabels,
                range: [-0.6, eventsOverlay.eventCount - 0.4],
              },
              shapes: eventsOverlay.shapes,
              annotations: eventsOverlay.annotations,
              margin: { t: 56, r: 24, b: 56, l: 120 },
              plot_bgcolor: '#f8f9fa',
            }}
            minHeight={Math.max(200, eventsOverlay.eventCount * 50 + 80)}
          />
        ) : (
          <div className="empty-state">
            Events timeline shows scenario event windows once a scenario is selected.
            {!scenarioDetail?.events?.length ? ' The selected scenario has no named events.' : ''}
          </div>
        )}
      </div>

      <div className="card mt-3">
        <div className="card-header">Log directory contents</div>
        <div className="card-body p-0">
          {logFiles.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Size</th>
                  <th>Last modified</th>
                </tr>
              </thead>
              <tbody>
                {logFiles.map((file) => (
                  <tr key={file.name} style={{ cursor: 'pointer' }} onClick={() => setSelectedLog(file.name)}>
                    <td className="mono">{file.name}</td>
                    <td>{formatBytes(file.size)}</td>
                    <td>{new Date(file.modified).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">No logs yet — start a scenario to populate the directory.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Scenarios;
