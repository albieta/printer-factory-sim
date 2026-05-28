import type { Data } from 'plotly.js';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Form, Table, Spinner } from 'react-bootstrap';
import { FaDownload } from 'react-icons/fa';
import html2canvas from 'html2canvas';
import JSZip from 'jszip';
import PageGuide from '../components/PageGuide';
import ResponsivePlot from '../components/ResponsivePlot';
import { eventsAPI, exportAPI, getErrorMessage, scenariosAPI } from '../services/api';
import type { Event, MetricsSnapshot, ScenarioSummary } from '../types';
import { describeEventDetails, formatEventType, formatTimestamp } from '../utils/formatters';
import LoadingSpinner from '../components/LoadingSpinner';
import { onSimulationUpdate } from '../utils/simulationEvents';

// ── helpers ──────────────────────────────────────────────────────────────────

const EmptyChart: React.FC<{ label: string }> = ({ label }) => (
  <div className="empty-state" style={{ minHeight: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    {label}
  </div>
);

const SectionHeader: React.FC<{ title: string; subtitle: string; onDownload?: () => void; isDownloading?: boolean; hasData?: boolean }> = ({ title, subtitle, onDownload, isDownloading, hasData = true }) => (
  <div className="mt-5 mb-3 d-flex justify-content-between align-items-start gap-3">
    <div>
      <div className="section-kicker">{title}</div>
      <p className="text-muted mb-0">{subtitle}</p>
    </div>
    {onDownload && hasData && (
      <Button
        variant="outline-secondary"
        size="sm"
        onClick={onDownload}
        disabled={isDownloading}
        className="flex-shrink-0"
      >
        {isDownloading ? (
          <>
            <Spinner animation="border" size="sm" className="me-2" />
            Downloading...
          </>
        ) : (
          <>
            <FaDownload className="me-2" />
            Download charts
          </>
        )}
      </Button>
    )}
  </div>
);

// ── component ────────────────────────────────────────────────────────────────

const Reports: React.FC = () => {
  const [events, setEvents] = useState<Event[]>([]);
  const [metrics, setMetrics] = useState<MetricsSnapshot[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [eventFilter, setEventFilter] = useState('all');
  const [downloadingSection, setDownloadingSection] = useState<string | null>(null);

  // Chart refs for downloading
  const commonInventoryChartRef = useRef<HTMLDivElement | null>(null);
  const commonPricesChartRef = useRef<HTMLDivElement | null>(null);
  const commonEventsChartRef = useRef<HTMLDivElement | null>(null);
  const retailerDemandChartRef = useRef<HTMLDivElement | null>(null);
  const retailerStockChartRef = useRef<HTMLDivElement | null>(null);
  const mfgCapacityChartRef = useRef<HTMLDivElement | null>(null);
  const mfgHoursChartRef = useRef<HTMLDivElement | null>(null);
  const mfgQueuedHoursChartRef = useRef<HTMLDivElement | null>(null);
  const mfgQueueLoadChartRef = useRef<HTMLDivElement | null>(null);
  const mfgFinancialChartRef = useRef<HTMLDivElement | null>(null);
  const mfgProfitChartRef = useRef<HTMLDivElement | null>(null);
  const mfgOrdersChartRef = useRef<HTMLDivElement | null>(null);
  const mfgDailyFinancialsChartRef = useRef<HTMLDivElement | null>(null);
  const mfgInventoryChartRef = useRef<HTMLDivElement | null>(null);
  const supplierPriceChartRef = useRef<HTMLDivElement | null>(null);
  const supplierStockChartRef = useRef<HTMLDivElement | null>(null);

  const loadEvents = useCallback(async () => {
    try {
      const response = await eventsAPI.getEvents({ limit: 500 });
      setEvents(response.data);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load event analytics.'));
    }
  }, []);

  const loadMetrics = useCallback(async () => {
    try {
      const response = await scenariosAPI.metrics(200);
      setMetrics(response.data.snapshots);
    } catch {
      // non-fatal — metrics may not exist yet
    }
  }, []);

  const loadScenarios = useCallback(async () => {
    try {
      const response = await scenariosAPI.list();
      setScenarios(response.data.scenarios);
    } catch {
      // non-fatal
    }
  }, []);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(() => { void loadMetrics(); }, 3000);
  }, [loadMetrics]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  useEffect(() => {
    Promise.all([loadEvents(), loadMetrics(), loadScenarios()]).finally(() => setLoading(false));
    const clear = onSimulationUpdate(() => {
      void loadEvents();
      void loadMetrics();
    });
    return () => { clear(); stopPolling(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll metrics while a scenario run is active; stop when it ends.
  useEffect(() => {
    const checkRun = async () => {
      try {
        const res = await scenariosAPI.status();
        const status = res.data.run?.status;
        if (status === 'running' || status === 'stopping') {
          startPolling();
        } else {
          stopPolling();
        }
      } catch {
        stopPolling();
      }
    };
    void checkRun();
    const timer = setInterval(() => { void checkRun(); }, 5000);
    return () => clearInterval(timer);
  }, [startPolling, stopPolling]);

  // ── chart derivations ─────────────────────────────────────────────────────

  // Deduplicate metrics by day, keeping the one with most complete data
  const uniqueMetrics = useMemo(() => {
    const seen = new Map<number, MetricsSnapshot>();
    metrics.forEach((m) => {
      const day = m.day ?? 0;
      const existing = seen.get(day);

      // Score completeness: prefer non-manual scenarios, then most complete data
      const score = (metric: MetricsSnapshot) => {
        let points = 0;

        // Strongly prefer non-manual scenarios (they have events and are intentional)
        if (metric.scenario && metric.scenario !== 'manual') points += 10000;

        // Retailer demand (most important for charts)
        const retailers = metric.retailers ?? [];
        const placedToday = retailers.reduce((acc, r) => acc + (r.customer_orders?.placed_today ?? 0), 0);
        const fulfilledToday = retailers.reduce((acc, r) => acc + (r.customer_orders?.fulfilled_today ?? 0), 0);
        const backordered = retailers.reduce((acc, r) => acc + (r.customer_orders?.backordered_today ?? 0), 0);

        // Count which demand fields have data (even if zero in some cases, having the field matters)
        // We also check the sum as a tiebreaker
        const totalDemand = placedToday + fulfilledToday + backordered;
        if (totalDemand > 0 || placedToday >= 0) points += 1000 + totalDemand;

        // Only use secondary data if no retailer data
        if (totalDemand === 0) {
          if (metric.manufacturer?.queued_assembly_hours != null && metric.manufacturer.queued_assembly_hours > 0) points += 5;
          if (metric.manufacturer?.daily_financials?.costs != null && metric.manufacturer.daily_financials.costs > 0) points += 5;
        }

        return points;
      };

      if (!existing || score(m) > score(existing)) {
        seen.set(day, m);
      }
    });
    return Array.from(seen.values()).sort((a, b) => (a.day ?? 0) - (b.day ?? 0));
  }, [metrics]);

  const dayLabels = useMemo(() => uniqueMetrics.map((m) => `D${m.day}`), [uniqueMetrics]);

  // COMMON — aggregate inventory per service
  const inventoryChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const mfg = uniqueMetrics.map((m) => Object.values(m.manufacturer.inventory ?? {}).reduce((a, b) => a + Number(b || 0), 0));
    const retailStock = uniqueMetrics.map((m) => m.retailers.reduce((acc, r) => acc + Object.values(r.stock ?? {}).reduce((a, b) => a + Number(b || 0), 0), 0));
    const providerStock = uniqueMetrics.map((m) => m.providers.reduce((acc, p) => acc + Object.values(p.stock ?? {}).reduce((a, b) => a + Number(b || 0), 0), 0));
    return { mfg, retailStock, providerStock };
  }, [uniqueMetrics]);

  // COMMON — printer prices: wholesale + retail per model
  const printerPriceChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const traces: Data[] = [];
    const productNames = new Set<string>();
    uniqueMetrics.forEach((m) => Object.keys(m.manufacturer?.prices ?? {}).forEach((k) => productNames.add(k)));
    productNames.forEach((product) => {
      const vals = uniqueMetrics.map((m) => { const p = m.manufacturer?.prices?.[product]; return p != null ? Number(p) : null; });
      if (vals.some((v) => v != null)) {
        traces.push({ x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers', name: `Wholesale: ${product}`, line: { dash: 'solid' }, connectgaps: true } as Data);
      }
    });
    uniqueMetrics[0]?.retailers.forEach((retailer, ri) => {
      const rNames = new Set<string>();
      uniqueMetrics.forEach((m) => Object.keys(m.retailers[ri]?.prices ?? {}).forEach((k) => rNames.add(k)));
      rNames.forEach((product) => {
        const vals = uniqueMetrics.map((m) => { const p = m.retailers[ri]?.prices?.[product]; return p != null ? Number(p) : null; });
        if (vals.some((v) => v != null)) {
          traces.push({ x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers', name: `${retailer.name}: ${product}`, line: { dash: 'dot' }, connectgaps: true } as Data);
        }
      });
    });
    return traces.length ? traces : null;
  }, [uniqueMetrics, dayLabels]);

  // COMMON — scenario events overlay with day-by-day timeline
  const eventsOverlay = useMemo(() => {
    // Build a timeline for each day that has been run
    if (!uniqueMetrics.length) return null;

    const maxDay = Math.max(...uniqueMetrics.map((m) => m.day ?? 0), 0);
    const lastScenarioName = uniqueMetrics[0]?.scenario;
    const scenarioDetail = lastScenarioName && lastScenarioName !== 'manual'
      ? scenarios.find((s) => s.scenario_name === lastScenarioName || s.name.replace('.json', '') === lastScenarioName)
      : null;
    const events = scenarioDetail?.events ?? [];

    // Create unique event combination rows (consolidate duplicate events)
    const eventCombinations = new Map<string, { label: string; events: Array<any> }>();
    for (let day = 0; day <= maxDay; day++) {
      const dayEvents = events.filter((ev) =>
        ev && ev.start_day != null && ev.start_day <= day && (ev.end_day ?? ev.start_day) >= day
      );
      const key = dayEvents.length > 0
        ? dayEvents.map((ev) => ev.name ?? 'event').sort().join('|')
        : '';
      if (!eventCombinations.has(key)) {
        const label = dayEvents.length > 0
          ? dayEvents.map((ev) => ev.name ?? `event`).join(', ')
          : `Day ${day}`;
        eventCombinations.set(key, { label, events: dayEvents });
      }
    }

    // Build day rows from unique combinations
    const dayRows: Array<{ day: number; label: string; events: Array<any> }> = [];
    let rowIndex = 0;
    const eventToRowIndex = new Map<string, number>();
    for (const [key, { label, events: evts }] of eventCombinations) {
      if (evts.length > 0) {
        eventToRowIndex.set(key, rowIndex);
        dayRows.push({ day: rowIndex, label, events: evts });
        rowIndex++;
      }
    }

    // Build shapes and annotations from events, skipping any that don't fit in the current day range
    const shapes = events
      .filter((ev) => ev.start_day != null && ev.end_day != null)
      .map((ev, i) => {
        const yIndex = dayRows.findIndex((dr) => dr.events.includes(ev));
        if (yIndex < 0) return null; // Event not in any day row, skip it
        return {
          type: 'rect' as const, xref: 'x' as const, yref: 'y' as const,
          x0: ev.start_day, x1: ev.end_day, y0: yIndex - 0.4, y1: yIndex + 0.4,
          fillcolor: `hsl(${(i * 67) % 360}, 60%, 55%)`, opacity: 0.75, line: { width: 0 },
        };
      })
      .filter((shape) => shape != null);

    const annotations = events
      .filter((ev) => ev.start_day != null)
      .map((ev, i) => {
        const yIndex = dayRows.findIndex((dr) => dr.events.includes(ev));
        if (yIndex < 0) return null; // Event not in any day row, skip it
        return {
          x: ev.start_day ?? 0, y: yIndex, text: ev.name ?? `event ${i + 1}`,
          xanchor: 'left' as const, showarrow: false, font: { color: '#fff', size: 11 },
        };
      })
      .filter((ann) => ann != null);

    const yLabels = dayRows.map((dr) => dr.label);
    return { shapes, annotations, yLabels, eventCount: dayRows.length, maxDay };
  }, [uniqueMetrics, scenarios]);

  // RETAILER — daily customer demand
  const demandChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const placed = uniqueMetrics.map((m) => (m.retailers ?? []).reduce((acc, r) => acc + (r.customer_orders?.placed_today ?? 0), 0));
    const fulfilled = uniqueMetrics.map((m) => (m.retailers ?? []).reduce((acc, r) => acc + (r.customer_orders?.fulfilled_today ?? 0), 0));
    const backordered = uniqueMetrics.map((m) => (m.retailers ?? []).reduce((acc, r) => acc + (r.customer_orders?.backordered_today ?? 0), 0));
    return { placed, fulfilled, backordered };
  }, [uniqueMetrics]);

  // RETAILER — stock per product
  const retailerStockChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const traces: Data[] = [];
    const modelNames = new Set<string>();
    uniqueMetrics.forEach((m) => m.retailers.forEach((r) => Object.keys(r.stock ?? {}).forEach((k) => modelNames.add(k))));
    modelNames.forEach((model) => {
      const vals = uniqueMetrics.map((m) => m.retailers.reduce((acc, r) => acc + (r.stock?.[model] ?? 0), 0));
      traces.push({ x: dayLabels, y: vals, type: 'scatter', mode: 'lines+markers', name: model, connectgaps: true } as Data);
    });
    return traces.length ? traces : null;
  }, [uniqueMetrics, dayLabels]);

  // MANUFACTURER — assembly capacity
  const capacityChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const lines = uniqueMetrics.map((m) => m.manufacturer?.capacity?.assembly_lines ?? 1);
    const workers = uniqueMetrics.map((m) => m.manufacturer?.capacity?.workers_per_line ?? 1);
    const dailyHours = uniqueMetrics.map((m) => m.manufacturer?.capacity?.daily_assembly_hours ?? 8);
    return { lines, workers, dailyHours };
  }, [uniqueMetrics]);

  // MANUFACTURER — queued assembly hours evolution
  const queuedHoursChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const queuedHours = uniqueMetrics.map((m) => m.manufacturer?.queued_assembly_hours ?? 0);
    const dailyCapacity = uniqueMetrics.map((m) => m.manufacturer?.capacity?.daily_assembly_hours ?? 8);
    return { queuedHours, dailyCapacity };
  }, [uniqueMetrics]);

  // MANUFACTURER — queue load percentage evolution
  const queueLoadChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    return uniqueMetrics.map((m) => m.manufacturer?.queue_load_percentage ?? 0);
  }, [uniqueMetrics]);

  // MANUFACTURER — financials
  const financialChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const costs = uniqueMetrics.map((m) => m.manufacturer?.financials?.total_costs ?? 0);
    const revenue = uniqueMetrics.map((m) => m.manufacturer?.financials?.total_revenue ?? 0);
    const profit = uniqueMetrics.map((m) => m.manufacturer?.financials?.net_profit ?? 0);
    return { costs, revenue, profit };
  }, [uniqueMetrics]);

  // MANUFACTURER — daily sales order activity
  const mfgOrdersChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const sot = (m: MetricsSnapshot) => m.manufacturer?.sales_orders_today ?? {};
    return {
      placed: uniqueMetrics.map((m) => sot(m).placed ?? 0),
      in_progress: uniqueMetrics.map((m) => sot(m).in_progress ?? 0),
      shipped: uniqueMetrics.map((m) => sot(m).shipped ?? 0),
      rejected: uniqueMetrics.map((m) => sot(m).rejected ?? 0),
    };
  }, [uniqueMetrics]);

  // MANUFACTURER — daily financials
  const dailyFinancialsChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const df = (m: MetricsSnapshot) => m.manufacturer?.daily_financials ?? {};
    return {
      revenue: uniqueMetrics.map((m) => df(m).revenue ?? 0),
      costs: uniqueMetrics.map((m) => df(m).costs ?? 0),
      net_profit: uniqueMetrics.map((m) => df(m).net_profit ?? 0),
    };
  }, [uniqueMetrics]);

  // MANUFACTURER — inventory per material
  const mfgInventoryChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const traces: Data[] = [];
    const materialNames = new Set<string>();
    uniqueMetrics.forEach((m) => Object.keys(m.manufacturer?.inventory ?? {}).forEach((k) => materialNames.add(k)));
    materialNames.forEach((material) => {
      const vals = uniqueMetrics.map((m) => m.manufacturer?.inventory?.[material] ?? null);
      if (vals.some((v) => v != null)) {
        traces.push({ x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers', name: material, connectgaps: true } as Data);
      }
    });
    return traces.length ? traces : null;
  }, [uniqueMetrics, dayLabels]);

  // SUPPLIER — material prices (cheapest tier)
  const materialPriceChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const traces: Data[] = [];
    const providerProductNames = new Set<string>();
    uniqueMetrics.forEach((m) => m.providers.forEach((p) => Object.keys(p.prices ?? {}).forEach((k) => providerProductNames.add(k))));
    uniqueMetrics[0]?.providers.forEach((provider, pi) => {
      providerProductNames.forEach((product) => {
        const vals = uniqueMetrics.map((m) => {
          const tiers = m.providers[pi]?.prices?.[product];
          if (!tiers || typeof tiers !== 'object') return null;
          const tierVals = Object.values(tiers).map(Number).filter((v) => !isNaN(v));
          return tierVals.length ? Math.min(...tierVals) : null;
        });
        if (vals.some((v) => v != null)) {
          traces.push({ x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers', name: `${provider.name}: ${product}`, line: { dash: 'dashdot' }, connectgaps: true } as Data);
        }
      });
    });
    return traces.length ? traces : null;
  }, [uniqueMetrics, dayLabels]);

  // SUPPLIER — stock per component
  const supplierStockChart = useMemo(() => {
    if (!uniqueMetrics.length) return null;
    const traces: Data[] = [];
    const componentNames = new Set<string>();
    uniqueMetrics.forEach((m) => m.providers.forEach((p) => Object.keys(p.stock ?? {}).forEach((k) => componentNames.add(k))));
    uniqueMetrics[0]?.providers.forEach((provider, pi) => {
      componentNames.forEach((component) => {
        const vals = uniqueMetrics.map((m) => m.providers[pi]?.stock?.[component] ?? null);
        if (vals.some((v) => v != null)) {
          traces.push({ x: dayLabels, y: vals as number[], type: 'scatter', mode: 'lines+markers', name: `${provider.name}: ${component}`, connectgaps: true } as Data);
        }
      });
    });
    return traces.length ? traces : null;
  }, [uniqueMetrics, dayLabels]);

  // ── event log (existing) ──────────────────────────────────────────────────

  const filteredEvents = useMemo(
    () => events.filter((event) => eventFilter === 'all' || event.event_type === eventFilter),
    [eventFilter, events],
  );

  // ── chart download handler ────────────────────────────────────────────────

  const downloadChartsAsZip = useCallback(
    async (section: 'common' | 'retailer' | 'manufacturer' | 'supplier') => {
      setDownloadingSection(section);
      try {
        const zip = new JSZip();
        const chartRefs: Array<{ ref: React.RefObject<HTMLDivElement | null>; name: string }> = [];

        if (section === 'common') {
          chartRefs.push(
            { ref: commonInventoryChartRef, name: 'Inventory across the chain' },
            { ref: commonPricesChartRef, name: 'Printer prices (wholesale vs retail)' },
            { ref: commonEventsChartRef, name: 'Scenario events timeline' }
          );
        } else if (section === 'retailer') {
          chartRefs.push(
            { ref: retailerDemandChartRef, name: 'Daily customer demand outcomes' },
            { ref: retailerStockChartRef, name: 'Retailer stock per product' }
          );
        } else if (section === 'manufacturer') {
          chartRefs.push(
            { ref: mfgCapacityChartRef, name: 'Assembly capacity expansion' },
            { ref: mfgHoursChartRef, name: 'Total daily assembly capacity' },
            { ref: mfgQueuedHoursChartRef, name: 'Queued assembly hours evolution' },
            { ref: mfgQueueLoadChartRef, name: 'Queue load percentage evolution' },
            { ref: mfgFinancialChartRef, name: 'Financial performance' },
            { ref: mfgProfitChartRef, name: 'Net profit evolution' },
            { ref: mfgOrdersChartRef, name: 'Daily order activity (MFG + sales orders)' },
            { ref: mfgDailyFinancialsChartRef, name: 'Daily income, costs & profit' },
            { ref: mfgInventoryChartRef, name: 'Manufacturer raw material inventory per component' }
          );
        } else if (section === 'supplier') {
          chartRefs.push(
            { ref: supplierPriceChartRef, name: 'Material prices (provider components)' },
            { ref: supplierStockChartRef, name: 'Supplier stock per component' }
          );
        }

        let chartCount = 0;
        for (const { ref, name } of chartRefs) {
          if (ref.current) {
            const canvas = await html2canvas(ref.current, {
              backgroundColor: '#ffffff',
              scale: 2,
              allowTaint: true,
              useCORS: true,
            });
            const imgData = canvas.toDataURL('image/png');
            const base64Data = imgData.replace(/^data:image\/png;base64,/, '');
            zip.file(`${chartCount + 1}_${name.replace(/[\/\?:]/g, '_')}.png`, base64Data, { base64: true });
            chartCount += 1;
          }
        }

        if (chartCount === 0) {
          setError(`No data available in ${section} section.`);
          setDownloadingSection(null);
          return;
        }

        const content = await zip.generateAsync({ type: 'blob' });
        const url = URL.createObjectURL(content);
        const a = document.createElement('a');
        a.href = url;
        a.download = `analytics-${section}-charts-${new Date().toISOString().slice(0, 10)}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        setError(null);
      } catch (err) {
        setError(getErrorMessage(err, `Failed to download ${section} charts.`));
      } finally {
        setDownloadingSection(null);
      }
    },
    []
  );

  // ── export handler ────────────────────────────────────────────────────────

  const handleExport = async (type: 'full' | 'inventory' | 'events') => {
    try {
      const response = type === 'full' ? await exportAPI.exportFullState() : type === 'inventory' ? await exportAPI.exportInventory() : await exportAPI.exportEvents();
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${type}_export_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to export report data.'));
    }
  };

  if (loading) return <LoadingSpinner label="Loading analytics..." />;

  const hasMetrics = metrics.length > 0;
  const noMetricsMsg = 'No data yet — advance the day or run a scenario to populate charts.';

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Analytics</div>
          <h1>Explain what happened across the flow</h1>
          <p>Charts update automatically when you advance the day or run a scenario. Grouped by supply chain layer — Common covers the full chain, then Retailer, Manufacturer, and Supplier each have their own section.</p>
        </div>
      </div>

      <PageGuide
        title="Analytics"
        controls="Charts are sourced from the metrics log. They update on every Advance All or scenario run. Resetting the simulation clears the chart history."
        next="Use the event log at the bottom for line-by-line audit detail — which order was blocked, which PO was rejected, and when."
        tip="Stock-per-product charts let you spot which specific material or model is running low, independently of the aggregate totals."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="action-bar">
        <div>
          <div className="section-kicker">Data exports</div>
          <h3 className="mb-1">Export specialized snapshots</h3>
          <p className="text-muted mb-0">Export inventory snapshot or event history as JSON. For full state backups, use the Backup feature in Configuration.</p>
        </div>
        <div className="action-buttons">
          <Button variant="success" onClick={() => void handleExport('inventory')}><FaDownload className="me-2" />Inventory</Button>
          <Button variant="warning" onClick={() => void handleExport('events')}><FaDownload className="me-2" />Events</Button>
        </div>
      </div>

      {/* ── COMMON ─────────────────────────────────────────────────────────── */}
      <SectionHeader
        title="Common"
        subtitle="Full-chain views spanning all three services."
        onDownload={() => void downloadChartsAsZip('common')}
        isDownloading={downloadingSection === 'common'}
        hasData={hasMetrics}
      />

      <div className="chart-container mb-3" ref={commonInventoryChartRef}>
        {hasMetrics && inventoryChart ? (
          <ResponsivePlot
            data={[
              { x: dayLabels, y: inventoryChart.providerStock, type: 'scatter', mode: 'lines+markers', name: 'Provider stock' },
              { x: dayLabels, y: inventoryChart.mfg, type: 'scatter', mode: 'lines+markers', name: 'Manufacturer materials' },
              { x: dayLabels, y: inventoryChart.retailStock, type: 'scatter', mode: 'lines+markers', name: 'Retailer stock' },
            ]}
            layout={{ title: { text: 'Inventory across the chain' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Units in hand (sum)' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
            minHeight={300}
          />
        ) : <EmptyChart label={noMetricsMsg} />}
      </div>

      <div className="data-grid mb-3">
        <div className="chart-container" ref={commonPricesChartRef}>
          {hasMetrics && printerPriceChart ? (
            <ResponsivePlot
              data={printerPriceChart}
              layout={{ title: { text: 'Printer prices (wholesale vs retail)' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Price ($)' } }, legend: { orientation: 'h', y: -0.25 }, margin: { t: 56, r: 24, b: 80, l: 56 } }}
              minHeight={320}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={commonEventsChartRef}>
          {eventsOverlay ? (
            <ResponsivePlot
              data={[{ x: [0.5, eventsOverlay.maxDay + 0.5], y: [null, null], type: 'scatter', mode: 'none' as const, showlegend: false }]}
              layout={{
                title: { text: 'Simulation timeline — Days and scenario events' },
                xaxis: { title: { text: 'Simulated day' }, range: [0.5, eventsOverlay.maxDay + 0.5] },
                yaxis: { title: { text: '' }, tickvals: eventsOverlay.yLabels.map((_, i) => i), ticktext: eventsOverlay.yLabels, range: [-0.6, eventsOverlay.eventCount - 0.4] },
                shapes: eventsOverlay.shapes,
                annotations: eventsOverlay.annotations,
                margin: { t: 56, r: 24, b: 56, l: 120 },
                plot_bgcolor: '#f8f9fa',
              }}
              minHeight={Math.max(200, eventsOverlay.eventCount * 50 + 80)}
            />
          ) : <EmptyChart label="Simulation timeline — Run a scenario or advance days to populate." />}
        </div>
      </div>

      {/* ── RETAILER ───────────────────────────────────────────────────────── */}
      <SectionHeader
        title="Retailer"
        subtitle="Customer demand flow and retailer stock by product."
        onDownload={() => void downloadChartsAsZip('retailer')}
        isDownloading={downloadingSection === 'retailer'}
        hasData={hasMetrics}
      />

      <div className="data-grid mb-3">
        <div className="chart-container" ref={retailerDemandChartRef}>
          {hasMetrics && demandChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: demandChart.placed, type: 'bar', name: 'Placed', marker: { color: '#d18a1a' } },
                { x: dayLabels, y: demandChart.fulfilled, type: 'bar', name: 'Fulfilled', marker: { color: '#2f7d4a' } },
                { x: dayLabels, y: demandChart.backordered, type: 'bar', name: 'Backordered', marker: { color: '#b6463b' } },
              ]}
              layout={{ barmode: 'group', title: { text: 'Daily customer demand outcomes' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Customer orders' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={retailerStockChartRef}>
          {hasMetrics && retailerStockChart ? (
            <ResponsivePlot
              data={retailerStockChart}
              layout={{ title: { text: 'Retailer stock per product' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Units on hand' } }, legend: { orientation: 'h', y: -0.25 }, margin: { t: 56, r: 24, b: 80, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>
      </div>

      {/* ── MANUFACTURER ───────────────────────────────────────────────────── */}
      <SectionHeader
        title="Manufacturer"
        subtitle="Assembly capacity, financials, and raw material inventory over time."
        onDownload={() => void downloadChartsAsZip('manufacturer')}
        isDownloading={downloadingSection === 'manufacturer'}
        hasData={hasMetrics}
      />

      <div className="data-grid mb-3">
        <div className="chart-container" ref={mfgCapacityChartRef}>
          {hasMetrics && capacityChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: capacityChart.lines, type: 'scatter', mode: 'lines+markers', name: 'Assembly lines', marker: { color: '#0066cc' } },
                { x: dayLabels, y: capacityChart.workers, type: 'scatter', mode: 'lines+markers', name: 'Workers per line', marker: { color: '#ff6600' } },
              ]}
              layout={{ title: { text: 'Assembly capacity expansion' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Count' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={mfgHoursChartRef}>
          {hasMetrics && capacityChart ? (
            <ResponsivePlot
              data={[{ x: dayLabels, y: capacityChart.dailyHours, type: 'scatter', mode: 'lines+markers', name: 'Daily assembly hours', marker: { color: '#228B22' } }]}
              layout={{ title: { text: 'Total daily assembly capacity' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Hours' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>
      </div>

      <div className="data-grid mb-3">
        <div className="chart-container" ref={mfgQueuedHoursChartRef}>
          {hasMetrics && queuedHoursChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: queuedHoursChart.queuedHours, type: 'scatter', mode: 'lines+markers', name: 'Queued hours', marker: { color: '#ff9900' } },
                { x: dayLabels, y: queuedHoursChart.dailyCapacity, type: 'scatter', mode: 'lines', name: 'Daily capacity', line: { color: '#cccccc', dash: 'dash' } },
              ]}
              layout={{ title: { text: 'Queued assembly hours evolution' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Hours' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={mfgQueueLoadChartRef}>
          {hasMetrics && queueLoadChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: queueLoadChart, type: 'scatter', mode: 'lines+markers', name: 'Queue load %', marker: { color: '#ff6b6b' } },
                { x: dayLabels, y: Array(dayLabels.length).fill(100), type: 'scatter', mode: 'lines', name: 'Capacity limit', line: { color: '#cccccc', dash: 'dash' } },
              ]}
              layout={{ title: { text: 'Queue load percentage evolution' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Load %' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>
      </div>

      <div className="data-grid mb-3">
        <div className="chart-container" ref={mfgFinancialChartRef}>
          {hasMetrics && financialChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: financialChart.costs, type: 'scatter', mode: 'lines+markers', name: 'Total costs', marker: { color: '#dc3545' } },
                { x: dayLabels, y: financialChart.revenue, type: 'scatter', mode: 'lines+markers', name: 'Total revenue', marker: { color: '#28a745' } },
              ]}
              layout={{ title: { text: 'Financial performance' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Amount ($)' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={mfgProfitChartRef}>
          {hasMetrics && financialChart ? (
            <ResponsivePlot
              data={[{ x: dayLabels, y: financialChart.profit, type: 'scatter', mode: 'lines+markers', name: 'Net profit', marker: { color: financialChart.profit.some((p) => p < 0) ? '#ffc107' : '#0dcaf0' } }]}
              layout={{ title: { text: 'Net profit evolution' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Profit ($)' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>
      </div>

      <div className="data-grid mb-3">
        <div className="chart-container" ref={mfgOrdersChartRef}>
          {hasMetrics && mfgOrdersChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: mfgOrdersChart.placed, type: 'bar', name: 'New (MFG + SO)', marker: { color: '#0066cc' } },
                { x: dayLabels, y: mfgOrdersChart.in_progress, type: 'bar', name: 'Accepted', marker: { color: '#28a745' } },
                { x: dayLabels, y: mfgOrdersChart.shipped, type: 'bar', name: 'Shipped', marker: { color: '#17a2b8' } },
                { x: dayLabels, y: mfgOrdersChart.rejected, type: 'bar', name: 'Deleted/Blocked', marker: { color: '#dc3545' } },
              ]}
              layout={{ barmode: 'group', title: { text: 'Daily order activity (MFG + sales orders)' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Orders' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={mfgDailyFinancialsChartRef}>
          {hasMetrics && dailyFinancialsChart ? (
            <ResponsivePlot
              data={[
                { x: dayLabels, y: dailyFinancialsChart.revenue, type: 'bar', name: 'Income', marker: { color: '#28a745' } },
                { x: dayLabels, y: dailyFinancialsChart.costs, type: 'bar', name: 'Costs', marker: { color: '#dc3545' } },
                { x: dayLabels, y: dailyFinancialsChart.net_profit, type: 'bar', name: 'Net profit', marker: { color: '#0dcaf0' } },
              ]}
              layout={{ barmode: 'group', title: { text: 'Daily income, costs & profit' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Amount ($)' } }, margin: { t: 56, r: 24, b: 56, l: 56 } }}
              minHeight={300}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>
      </div>

      <div className="chart-container mb-3" ref={mfgInventoryChartRef}>
        {hasMetrics && mfgInventoryChart ? (
          <ResponsivePlot
            data={mfgInventoryChart}
            layout={{ title: { text: 'Manufacturer raw material inventory per component' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Units in stock' } }, legend: { orientation: 'h', y: -0.2 }, margin: { t: 56, r: 24, b: 80, l: 56 } }}
            minHeight={320}
          />
        ) : <EmptyChart label={noMetricsMsg} />}
      </div>

      {/* ── SUPPLIER ───────────────────────────────────────────────────────── */}
      <SectionHeader
        title="Supplier"
        subtitle="Provider component pricing and stock levels over time."
        onDownload={() => void downloadChartsAsZip('supplier')}
        isDownloading={downloadingSection === 'supplier'}
        hasData={hasMetrics}
      />

      <div className="data-grid mb-3">
        <div className="chart-container" ref={supplierPriceChartRef}>
          {hasMetrics && materialPriceChart ? (
            <ResponsivePlot
              data={materialPriceChart}
              layout={{ title: { text: 'Material prices (provider components)' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Price ($)' } }, legend: { orientation: 'h', y: -0.25 }, margin: { t: 56, r: 24, b: 80, l: 56 } }}
              minHeight={320}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>

        <div className="chart-container" ref={supplierStockChartRef}>
          {hasMetrics && supplierStockChart ? (
            <ResponsivePlot
              data={supplierStockChart}
              layout={{ title: { text: 'Supplier stock per component' }, xaxis: { title: { text: 'Simulated day' } }, yaxis: { title: { text: 'Units in stock' } }, legend: { orientation: 'h', y: -0.25 }, margin: { t: 56, r: 24, b: 80, l: 56 } }}
              minHeight={320}
            />
          ) : <EmptyChart label={noMetricsMsg} />}
        </div>
      </div>

      {/* ── Event log ──────────────────────────────────────────────────────── */}
      <div className="card mt-3">
        <div className="card-header d-flex justify-content-between align-items-center gap-3 flex-wrap">
          <span>Event log</span>
          <Form.Select style={{ maxWidth: 260 }} value={eventFilter} onChange={(event) => setEventFilter(event.target.value)}>
            <option value="all">All events</option>
            <option value="ORDER_CREATED">Order created</option>
            <option value="ORDER_RELEASED">Order released</option>
            <option value="ORDER_UNBLOCKED_MATERIALS">Order unblocked</option>
            <option value="ORDER_REJECTED">Order rejected</option>
            <option value="ORDER_COMPLETED">Order completed</option>
            <option value="ORDER_BLOCKED_MATERIALS">Order blocked by materials</option>
            <option value="PO_CREATED">Purchase order created</option>
            <option value="PO_DELIVERED">Purchase order delivered</option>
            <option value="PO_REJECTED_CAPACITY">Purchase order rejected</option>
            <option value="MATERIAL_CONSUMED">Material consumed</option>
            <option value="DAY_ADVANCED">Day advanced</option>
          </Form.Select>
        </div>
        <div className="card-body p-0">
          {filteredEvents.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Simulation Date</th>
                  <th>Recorded At</th>
                  <th>Summary</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.slice(0, 120).map((event) => (
                  <tr key={event.id}>
                    <td><span className="badge badge-neutral">{formatEventType(event.event_type)}</span></td>
                    <td>{event.sim_date}</td>
                    <td>{formatTimestamp(event.timestamp)}</td>
                    <td><div className="event-summary">{describeEventDetails(event.details)}</div></td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">No events recorded for this filter yet.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Reports;
