import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Badge, Button, Form, ProgressBar, Spinner, Table } from 'react-bootstrap';
import { FaBolt, FaDownload, FaPlay, FaStop, FaSyncAlt, FaTrash } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { configAPI, getErrorMessage, scenariosAPI } from '../services/api';
import type {
  ConfigSummary,
  LogContents,
  LogFile,
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

type ModelOption = {
  id: string;
  label: string;
  description: string;
  provider: 'claude' | 'gemini';
};

const AVAILABLE_MODELS: ModelOption[] = [
  { id: 'claude-opus-4-7',           label: 'Claude Opus 4.7',          description: 'Most capable, slower, expensive',                           provider: 'claude' },
  { id: 'claude-sonnet-4-6',         label: 'Claude Sonnet 4.6',        description: 'Balanced performance and cost',                             provider: 'claude' },
  { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5',         description: 'Fast and cost-effective',                                   provider: 'claude' },
  { id: 'gemini-3.1-flash-lite',     label: 'Gemini 3.1 Flash Lite',    description: 'Google free tier: 15 RPM / 250K TPM / 500 RPD — skills cached', provider: 'gemini' },
];

const isGeminiModel = (id: string): boolean => id.toLowerCase().startsWith('gemini');

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

  // ── Initial load ─────────────────────────────────────────────────────────
  useEffect(() => {
    void loadLibraries();
    void loadStatus();
    void loadLogFiles();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Polling while a run is active ────────────────────────────────────────
  useEffect(() => {
    if (!run || run.status !== 'running') return;
    const id = window.setInterval(() => {
      void loadStatus();
      void loadLogFiles();
      if (selectedLog) void loadLogContent(selectedLog);
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [run, loadStatus, loadLogFiles, loadLogContent, selectedLog]);

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
      announceSimulationUpdate();
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
              <Form.Label>Agent model</Form.Label>
              <Form.Select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
                <optgroup label="Anthropic Claude (via local CLI)">
                  {AVAILABLE_MODELS.filter((m) => m.provider === 'claude').map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Google Gemini (free-tier API)">
                  {AVAILABLE_MODELS.filter((m) => m.provider === 'gemini').map((m) => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </optgroup>
              </Form.Select>
              {AVAILABLE_MODELS.find((m) => m.id === selectedModel) && (
                <div className="text-muted small mt-1">
                  {AVAILABLE_MODELS.find((m) => m.id === selectedModel)?.description}
                </div>
              )}
              {isGeminiModel(selectedModel) && (
                <Alert variant="info" className="small mt-2 mb-0 py-2 px-3">
                  Gemini agents read <code>GOOGLE_API_KEY</code> from <code>.env</code> at the
                  repo root. Skill files are uploaded as cached content so they only count
                  toward token cost once per process. Free-tier caps (15 RPM / 500 RPD) are
                  enforced engine-side — the engine will block briefly if a window fills up.
                </Alert>
              )}
            </Form.Group>
            <Form.Group className="mt-3">
              <Form.Check
                type="switch"
                id="thinking-switch"
                label="Enable extended thinking"
                checked={thinkingEnabled && !isGeminiModel(selectedModel)}
                disabled={fastMode || isGeminiModel(selectedModel)}
                onChange={(e) => setThinkingEnabled(e.target.checked)}
              />
              <div className="text-muted small mt-1">
                {isGeminiModel(selectedModel)
                  ? 'Extended thinking is a Claude-only setting (Gemini agents always run single-shot)'
                  : thinkingEnabled
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
                <span>Provider</span>
                <strong>
                  {fastMode
                    ? 'None (scripted)'
                    : isGeminiModel(selectedModel)
                      ? 'Google Gemini'
                      : 'Anthropic Claude'}
                </strong>
              </div>
              <div className="metric-item stat-row">
                <span>Thinking mode</span>
                <strong>
                  {fastMode || isGeminiModel(selectedModel)
                    ? 'N/A'
                    : thinkingEnabled ? 'Enabled' : 'Disabled'}
                </strong>
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
                          <div>Current: ${currentConfig.cost_per_assembly_line}/line opening, ${currentConfig.cost_per_assembly_line_per_day}/line daily, ${currentConfig.cost_per_worker_per_hour}/hr, max {currentConfig.max_workers_per_line}/line</div>
                          <div>Recommended: ${scenarioDetail.recommended_costs.cost_per_assembly_line}/line opening, ${scenarioDetail.recommended_costs.cost_per_assembly_line_per_day || 'N/A'}/line daily, ${scenarioDetail.recommended_costs.cost_per_worker_per_hour}/hr, max {scenarioDetail.recommended_costs.max_workers_per_line}/line</div>
                        </div>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {(() => {
                        const isSame = !!(currentConfig &&
                          currentConfig.cost_per_assembly_line === scenarioDetail.recommended_costs!.cost_per_assembly_line &&
                          currentConfig.cost_per_assembly_line_per_day === scenarioDetail.recommended_costs!.cost_per_assembly_line_per_day &&
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
