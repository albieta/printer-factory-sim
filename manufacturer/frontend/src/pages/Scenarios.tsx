import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Badge, Button, Form, ProgressBar, Spinner, Table } from 'react-bootstrap';
import { FaBolt, FaPlay, FaStop, FaSyncAlt, FaTrash } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { getErrorMessage, scenariosAPI } from '../services/api';
import type {
  ConfigSummary,
  LogContents,
  LogFile,
  MetricsSnapshot,
  ScenarioRunRecord,
  ScenarioSummary,
} from '../types';
import { announceSimulationUpdate } from '../utils/simulationEvents';

const POLL_INTERVAL_MS = 2000;
const STDOUT_TAIL_LINES = 200;

const statusVariant = (status?: string): string => {
  switch (status) {
    case 'running':
      return 'info';
    case 'stopping':
      return 'warning';
    case 'completed':
      return 'success';
    case 'failed':
      return 'danger';
    default:
      return 'secondary';
  }
};

const formatBytes = (size: number): string => {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
};

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
  const [selectedConfig, setSelectedConfig] = useState<string>('');
  const [selectedScenario, setSelectedScenario] = useState<string>('');
  const [days, setDays] = useState<number>(5);
  const [autoFollow, setAutoFollow] = useState(true);
  const logBoxRef = useRef<HTMLPreElement | null>(null);

  // ── Loaders ─────────────────────────────────────────────────────────────

  const loadLibraries = useCallback(async () => {
    try {
      const response = await scenariosAPI.list();
      setScenarios(response.data.scenarios);
      setConfigs(response.data.configs);
      if (!selectedConfig && response.data.configs.length) {
        const stub = response.data.configs.find((c) => c.name === 'sim-stub.json');
        setSelectedConfig((stub ?? response.data.configs[0]).name);
      }
      if (!selectedScenario && response.data.scenarios.length) {
        const smoke = response.data.scenarios.find((s) => s.name === 'smoke-test.json');
        setSelectedScenario((smoke ?? response.data.scenarios[0]).name);
      }
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load scenarios.'));
    } finally {
      setLoadingList(false);
    }
  }, [selectedConfig, selectedScenario]);

  const loadStatus = useCallback(async () => {
    try {
      const response = await scenariosAPI.status();
      setRun(response.data.run);
    } catch (err) {
      // surface but keep polling
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
      // non-fatal — log directory may be empty
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
      // non-fatal — file may not exist yet
    }
  }, []);

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    void loadLibraries();
    void loadStatus();
    void loadLogFiles();
    void loadMetrics();
  }, [loadLibraries, loadStatus, loadLogFiles, loadMetrics]);

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
    const days = metrics.map((m) => `D${m.day}`);
    const mfg = metrics.map((m) => Object.values(m.manufacturer.inventory ?? {}).reduce((a, b) => a + Number(b || 0), 0));
    const retailStock = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + Object.values(r.stock ?? {}).reduce((a, b) => a + Number(b || 0), 0), 0),
    );
    const providerStock = metrics.map((m) =>
      m.providers.reduce((acc, p) => acc + Object.values(p.stock ?? {}).reduce((a, b) => a + Number(b || 0), 0), 0),
    );
    return { days, mfg, retailStock, providerStock };
  }, [metrics]);

  const demandChart = useMemo(() => {
    if (!metrics.length) return null;
    const days = metrics.map((m) => `D${m.day}`);
    const placed = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + (r.customer_orders?.placed_today ?? 0), 0),
    );
    const fulfilled = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + (r.customer_orders?.fulfilled_today ?? 0), 0),
    );
    const backordered = metrics.map((m) =>
      m.retailers.reduce((acc, r) => acc + (r.customer_orders?.backordered_today ?? 0), 0),
    );
    return { days, placed, fulfilled, backordered };
  }, [metrics]);

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
