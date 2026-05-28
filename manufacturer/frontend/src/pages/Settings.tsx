import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaCog, FaDownload, FaPlus, FaSave, FaTrash, FaUndo } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { configAPI, exportAPI, getErrorMessage, materialsAPI, simulationAPI } from '../services/api';
import type { BOMEntry, Product, SimulationConfig } from '../types';
import { announceSimulationUpdate, onSimulationUpdate } from '../utils/simulationEvents';
import LoadingSpinner from '../components/LoadingSpinner';

const Settings: React.FC = () => {
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [printers, setPrinters] = useState<Product[]>([]);
  const [materials, setMaterials] = useState<Product[]>([]);
  const [bomEntries, setBomEntries] = useState<BOMEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const [formData, setFormData] = useState({
    warehouse_capacity: '8400',
    assembly_lines: '1',
    workers_per_line: '1',
    shift_hours: '8',
    demand_distribution_mean: '5',
    demand_distribution_variance: '2',
    internal_demand_enabled: false,
    cost_per_assembly_line: '50000',
    cost_per_worker_per_hour: '50',
    max_workers_per_line: '10',
  });
  const [printerForm, setPrinterForm] = useState({ name: '', assembly_hours: '1' });
  const [materialForm, setMaterialForm] = useState({ name: '' });
  const [bomForm, setBomForm] = useState({ finished_product_id: '', material_id: '', quantity: '1' });

  const loadSetup = async () => {
    try {
      setLoading(true);
      const [configRes, printersRes, materialsRes, bomRes] = await Promise.all([
        configAPI.getConfig(),
        configAPI.getPrinterModels(),
        materialsAPI.getMaterials(),
        materialsAPI.getBOM(),
      ]);
      setConfig(configRes.data);
      setPrinters(printersRes.data);
      setMaterials(materialsRes.data);
      setBomEntries(bomRes.data);
      setFormData({
        warehouse_capacity: String(configRes.data.warehouse_capacity),
        assembly_lines: String(configRes.data.assembly_lines),
        workers_per_line: String(configRes.data.workers_per_line),
        shift_hours: String(configRes.data.shift_hours),
        demand_distribution_mean: String(configRes.data.demand_distribution_mean),
        demand_distribution_variance: String(configRes.data.demand_distribution_variance),
        internal_demand_enabled: configRes.data.internal_demand_enabled ?? true,
        cost_per_assembly_line: String(configRes.data.cost_per_assembly_line),
        cost_per_worker_per_hour: String(configRes.data.cost_per_worker_per_hour),
        max_workers_per_line: String(configRes.data.max_workers_per_line),
      });
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load simulation configuration.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadSetup();
    const clear = onSimulationUpdate(() => {
      void loadSetup();
    });

    return clear;
  }, []);

  const productMap = useMemo(() => {
    const map = new Map<string, string>();
    printers.forEach((printer) => map.set(printer.id, printer.name));
    materials.forEach((material) => map.set(material.id, material.name));
    return map;
  }, [materials, printers]);

  const effectiveHours = Number(formData.assembly_lines || 0) * Number(formData.workers_per_line || 0) * Number(formData.shift_hours || 0);

  const restoreCurrentValues = () => {
    if (!config) {
      return;
    }

    setFormData({
      warehouse_capacity: String(config.warehouse_capacity),
      assembly_lines: String(config.assembly_lines),
      workers_per_line: String(config.workers_per_line),
      shift_hours: String(config.shift_hours),
      demand_distribution_mean: String(config.demand_distribution_mean),
      demand_distribution_variance: String(config.demand_distribution_variance),
      internal_demand_enabled: config.internal_demand_enabled ?? true,
      cost_per_assembly_line: String(config.cost_per_assembly_line),
      cost_per_worker_per_hour: String(config.cost_per_worker_per_hour),
      max_workers_per_line: String(config.max_workers_per_line),
    });
  };

  const saveConfig = async () => {
    try {
      setSaving(true);
      await configAPI.updateConfig({
        warehouse_capacity: Number(formData.warehouse_capacity),
        assembly_lines: Number(formData.assembly_lines),
        workers_per_line: Number(formData.workers_per_line),
        shift_hours: Number(formData.shift_hours),
        demand_distribution_mean: Number(formData.demand_distribution_mean),
        demand_distribution_variance: Number(formData.demand_distribution_variance),
        internal_demand_enabled: formData.internal_demand_enabled,
        cost_per_assembly_line: Number(formData.cost_per_assembly_line),
        cost_per_worker_per_hour: Number(formData.cost_per_worker_per_hour),
        max_workers_per_line: Number(formData.max_workers_per_line),
      });
      setMessage('Configuration saved. Capacity, warehouse limits, and costs are updated.');
      announceSimulationUpdate();
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to save the simulation configuration.'));
    } finally {
      setSaving(false);
    }
  };

  const createPrinter = async () => {
    try {
      await configAPI.createPrinterModel({ name: printerForm.name, assembly_hours: Number(printerForm.assembly_hours) });
      setPrinterForm({ name: '', assembly_hours: '1' });
      setMessage('Printer model added.');
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create the printer model.'));
    }
  };

  const createMaterial = async () => {
    try {
      await materialsAPI.createMaterial({ name: materialForm.name });
      setMaterialForm({ name: '' });
      setMessage('Material added.');
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create the material.'));
    }
  };

  const createBomEntry = async () => {
    try {
      await materialsAPI.createBOM({
        finished_product_id: bomForm.finished_product_id,
        material_id: bomForm.material_id,
        quantity: Number(bomForm.quantity),
      });
      setBomForm({ finished_product_id: '', material_id: '', quantity: '1' });
      setMessage('BOM entry added.');
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to add the BOM entry.'));
    }
  };

  const deletePrinter = async (printerId: string) => {
    try {
      await configAPI.deletePrinterModel(printerId);
      setMessage('Printer model removed.');
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete printer model.'));
    }
  };

  const deleteBomEntry = async (bomId: string) => {
    try {
      await materialsAPI.deleteBOM(bomId);
      setMessage('BOM entry removed.');
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete the BOM entry.'));
    }
  };

  const resetSimulation = async () => {
    if (!window.confirm('Reset the simulation to the starter profile? Orders, purchase orders, events, and inventory levels will be restored to the initial seeded scenario.')) {
      return;
    }

    try {
      await simulationAPI.reset();
      setMessage('Simulation reset to the starter profile.');
      announceSimulationUpdate();
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to reset the simulation.'));
    }
  };

  const resetToEmpty = async () => {
    if (!window.confirm('Clear the simulation to empty state? All products, suppliers, materials, BOM, and orders will be deleted.')) {
      return;
    }

    try {
      await simulationAPI.resetToEmpty();
      setMessage('Simulation cleared to empty state.');
      announceSimulationUpdate();
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to clear the simulation.'));
    }
  };

  const resetToDefaultConfig = async () => {
    if (!window.confirm('Reset to default prefilled demo configuration? All orders and events will be cleared, but products, suppliers, and materials will be restored.')) {
      return;
    }

    try {
      await simulationAPI.resetToDefaultConfig();
      setMessage('Simulation reset to default prefilled demo configuration.');
      announceSimulationUpdate();
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to reset to default configuration.'));
    }
  };

  const handleExport = async () => {
    try {
      const response = await exportAPI.exportFullState();
      const blob = new Blob([JSON.stringify(response.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `simulation-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setMessage('Backup downloaded successfully.');
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to export the simulator state.'));
    }
  };

  const handleImportFullState = async () => {
    if (!importFile) {
      return;
    }

    try {
      setImporting(true);
      const fileContent = await importFile.text();
      const payload = JSON.parse(fileContent) as unknown;
      const response = await exportAPI.importFullState(payload);
      setMessage(response.data.message);
      setImportFile(null);
      if (importInputRef.current) {
        importInputRef.current.value = '';
      }
      announceSimulationUpdate();
      await loadSetup();
    } catch (err) {
      if (err instanceof SyntaxError) {
        setError('The selected file is not valid JSON.');
      } else {
        setError(getErrorMessage(err, 'Failed to import the simulator state.'));
      }
    } finally {
      setImporting(false);
    }
  };

  if (loading) {
    return <LoadingSpinner label="Loading configuration and master data..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Configuration</div>
          <h1>Define how the factory works</h1>
          <p>Set warehouse limits, shape daily demand, define shared assembly capacity, and maintain the product and material master data that drives the simulation.</p>
        </div>
      </div>

      <PageGuide
        title="Configuration"
        controls="This is the control room for simulation rules. Warehouse capacity, workforce structure, demand settings, printer models, materials, and BOM definitions all live here."
        next="Configuration changes affect every future simulation day. Increasing capacity can relieve the assembly queue, while tighter warehouse limits can cause more rejected purchase-order receipts."
        tip="Use the full-state import control to restore a previously exported scenario. The reset action still restores the starter profile when you want to return to the seeded baseline."
      />

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <Card className="mb-4">
        <Card.Header><FaCog className="me-2" />Simulation parameters</Card.Header>
        <Card.Body>
          <div className="two-column">
            <Form.Group className="mb-3">
              <Form.Label>Warehouse capacity</Form.Label>
              <Form.Control type="number" min="1" value={formData.warehouse_capacity} onChange={(event) => setFormData({ ...formData, warehouse_capacity: event.target.value })} />
              <Form.Text>Total storage units available for raw-material inventory.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Assembly lines</Form.Label>
              <Form.Control type="number" min="1" step="1" value={formData.assembly_lines} onChange={(event) => setFormData({ ...formData, assembly_lines: event.target.value })} />
              <Form.Text>Parallel lines contributing to the shared capacity pool.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Workers per line</Form.Label>
              <Form.Control type="number" min="1" step="1" value={formData.workers_per_line} onChange={(event) => setFormData({ ...formData, workers_per_line: event.target.value })} />
              <Form.Text>Operators available on each line during a shift.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Shift hours</Form.Label>
              <Form.Control type="number" min="0.5" step="0.5" value={formData.shift_hours} onChange={(event) => setFormData({ ...formData, shift_hours: event.target.value })} />
              <Form.Text>Hours worked per day by each worker.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Internal demand mean</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.demand_distribution_mean} onChange={(event) => setFormData({ ...formData, demand_distribution_mean: event.target.value })} />
              <Form.Text>Average ManufacturingOrders generated internally per day (standalone mode only).</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Internal demand variance</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.demand_distribution_variance} onChange={(event) => setFormData({ ...formData, demand_distribution_variance: event.target.value })} />
              <Form.Text>How much internal daily demand fluctuates around the mean.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3 d-flex flex-column justify-content-start">
              <Form.Label>Internal demand generator</Form.Label>
              <Form.Check
                type="switch"
                id="internal-demand-switch"
                label={formData.internal_demand_enabled ? 'Enabled' : 'Disabled'}
                checked={formData.internal_demand_enabled}
                onChange={(e) => setFormData({ ...formData, internal_demand_enabled: e.target.checked })}
              />
              <Form.Text>
                Generates random <strong>ManufacturingOrders</strong> directly inside the manufacturer each day
                (standalone/Week 5 mode). Keep off in multi-service mode — demand enters through the retailer
                instead. To configure customer orders injected into the retailer on manual advances, use the
                <strong> Retailers</strong> page.
              </Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Cost per assembly line ($)</Form.Label>
              <Form.Control type="number" min="0" step="1000" value={formData.cost_per_assembly_line} onChange={(event) => setFormData({ ...formData, cost_per_assembly_line: event.target.value })} />
              <Form.Text>Fixed cost incurred when opening a new assembly line.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Cost per worker per hour ($)</Form.Label>
              <Form.Control type="number" min="0" step="10" value={formData.cost_per_worker_per_hour} onChange={(event) => setFormData({ ...formData, cost_per_worker_per_hour: event.target.value })} />
              <Form.Text>Hourly wage cost when hiring a worker.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Max workers per line</Form.Label>
              <Form.Control type="number" min="1" step="1" value={formData.max_workers_per_line} onChange={(event) => setFormData({ ...formData, max_workers_per_line: event.target.value })} />
              <Form.Text>Maximum workers allowed per assembly line.</Form.Text>
            </Form.Group>
          </div>

          <div className="metric-item emphasis-item mb-4">
            <div className="stat-row">
              <span>Derived daily assembly hours</span>
              <strong>{effectiveHours.toFixed(1)}</strong>
            </div>
            <div className="formula-line">
              {formData.assembly_lines} lines × {formData.workers_per_line} workers/line × {Number(formData.shift_hours || 0).toFixed(1)} worker hours = {effectiveHours.toFixed(1)} shared hours/day
            </div>
            <div className="text-muted mt-2">The legacy daily-assembly-hours value is still exposed for compatibility, but this workforce model is now the primary way to manage capacity.</div>
          </div>

          <div className="status-grid">
            <div className="metric-item">
              <strong>Manufacturing statuses</strong>
              <div className="text-muted mt-2">Awaiting Release: demand exists but has not entered assembly.</div>
              <div className="text-muted mt-1">Queued for Production: order is released and waiting to consume shared capacity.</div>
              <div className="text-muted mt-1">Awaiting Release but Blocked by Material Shortage: the planner tried to release the order, but materials were missing immediately.</div>
              <div className="text-muted mt-1">Queued for Production but Blocked by Material Shortage: the order had already been accepted, but production later detected a shortage.</div>
              <div className="text-muted mt-1">Completed: work finished on a simulation day.</div>
              <div className="text-muted mt-1">Rejected: planner declined the order without deleting its history.</div>
            </div>
            <div className="metric-item">
              <strong>Purchase-order statuses</strong>
              <div className="text-muted mt-2">In Transit: supplier has been issued the PO and delivery is pending.</div>
              <div className="text-muted mt-1">Received: the warehouse had enough space and inventory was increased.</div>
              <div className="text-muted mt-1">Rejected: warehouse receipt would have exceeded capacity on delivery day.</div>
            </div>
          </div>

          <div className="action-buttons mt-4">
            <Button variant="primary" onClick={saveConfig} disabled={saving}><FaSave className="me-2" />{saving ? 'Saving...' : 'Save configuration'}</Button>
            <Button variant="outline-secondary" onClick={restoreCurrentValues}><FaUndo className="me-2" />Restore current values</Button>
          </div>

          <div className="mt-4 pt-3 border-top">
            <p className="text-muted mb-3"><strong>Reset options:</strong></p>

            <div className="mb-3 p-3 bg-light rounded">
              <div className="d-flex justify-content-between align-items-start">
                <div className="flex-grow-1">
                  <h6 className="mb-2">Reset to default config</h6>
                  <p className="text-muted small mb-2">
                    <strong>Restores the standard demo scenario:</strong>
                  </p>
                  <ul className="text-muted small mb-0">
                    <li>Recreates 3 standard printers (Basic300, Pro450, Elite700)</li>
                    <li>Recreates 6 materials and 6 suppliers</li>
                    <li>Recreates complete bill of materials</li>
                    <li>Resets all configuration to defaults</li>
                    <li>Clears all orders and events</li>
                  </ul>
                </div>
                <Button variant="warning" onClick={resetToDefaultConfig} className="ms-3 flex-shrink-0">
                  <FaUndo className="me-2" />Reset
                </Button>
              </div>
            </div>

            <div className="mb-3 p-3 bg-light rounded">
              <div className="d-flex justify-content-between align-items-start">
                <div className="flex-grow-1">
                  <h6 className="mb-2">Reset to starter profile</h6>
                  <p className="text-muted small mb-2">
                    <strong>Clears transactional data, restores missing defaults:</strong>
                  </p>
                  <ul className="text-muted small mb-0">
                    <li>Keeps all custom products, suppliers you added</li>
                    <li>Recreates any deleted default materials</li>
                    <li>Clears all orders, purchase orders, and events</li>
                    <li>Resets inventory to initial quantities</li>
                    <li>Resets configuration (costs, capacity, etc.) to defaults</li>
                    <li>Use this for a clean slate while keeping your custom additions</li>
                  </ul>
                </div>
                <Button variant="outline-danger" onClick={resetSimulation} className="ms-3 flex-shrink-0">
                  <FaUndo className="me-2" />Reset
                </Button>
              </div>
            </div>

            <div className="mb-3 p-3 bg-light rounded">
              <div className="d-flex justify-content-between align-items-start">
                <div className="flex-grow-1">
                  <h6 className="mb-2">Reset to empty</h6>
                  <p className="text-muted small mb-2">
                    <strong>Complete wipe:</strong>
                  </p>
                  <ul className="text-muted small mb-0">
                    <li>Deletes all products, suppliers, materials, bill of materials</li>
                    <li>Deletes all orders, purchase orders, and events</li>
                    <li>Resets all configuration to defaults</li>
                    <li>Leaves you with a completely empty simulation</li>
                    <li>Use this to start building from scratch</li>
                  </ul>
                </div>
                <Button variant="danger" onClick={resetToEmpty} className="ms-3 flex-shrink-0">
                  <FaUndo className="me-2" />Reset
                </Button>
              </div>
            </div>
          </div>
        </Card.Body>
      </Card>

      <Card className="mb-4">
        <Card.Header><FaDownload className="me-2" />Backup simulator state</Card.Header>
        <Card.Body>
          <p className="text-muted">
            Download a complete snapshot of the simulator state including configuration, master data, inventory, orders, financials, wholesale prices, and metric history. Use this to create backups or checkpoints.
          </p>
          <div className="action-buttons">
            <Button variant="primary" onClick={() => void handleExport()}>
              <FaDownload className="me-2" />Download backup
            </Button>
          </div>
        </Card.Body>
      </Card>

      <Card className="mb-4">
        <Card.Header><FaUndo className="me-2" />Restore simulator state</Card.Header>
        <Card.Body>
          <p className="text-muted">
            Import a previously exported backup JSON file to restore the simulator to a saved state. This will reset all current data and load the backup, including configuration, master data, inventory, orders, financials, and metric history.
          </p>
          <Form.Group className="mb-3">
            <Form.Label>Backup JSON file</Form.Label>
            <Form.Control
              ref={importInputRef}
              type="file"
              accept="application/json,.json"
              onChange={(event) => {
                const input = event.target as HTMLInputElement;
                setImportFile(input.files?.[0] ?? null);
              }}
            />
            <Form.Text>
              Select a backup file previously downloaded from the Backup section above.
            </Form.Text>
          </Form.Group>
          <div className="action-buttons">
            <Button variant="primary" onClick={handleImportFullState} disabled={!importFile || importing}>
              <FaUndo className="me-2" />
              {importing ? 'Restoring backup...' : 'Restore from backup'}
            </Button>
          </div>
        </Card.Body>
      </Card>

      <div className="three-column">
        <Card>
          <Card.Header><FaPlus className="me-2" />Printer models</Card.Header>
          <Card.Body>
            <Form.Group className="mb-3">
              <Form.Label>Model name</Form.Label>
              <Form.Control value={printerForm.name} onChange={(event) => setPrinterForm({ ...printerForm, name: event.target.value })} />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Assembly hours per unit</Form.Label>
              <Form.Control type="number" step="0.5" value={printerForm.assembly_hours} onChange={(event) => setPrinterForm({ ...printerForm, assembly_hours: event.target.value })} />
            </Form.Group>
            <Button variant="primary" onClick={createPrinter} disabled={!printerForm.name}>Add printer model</Button>
            <div className="list-stack mt-4">
              {printers.map((printer) => (
                <div className="metric-item" key={printer.id}>
                  <div className="stat-row">
                    <strong>{printer.name}</strong>
                    <Button variant="outline-secondary" size="sm" onClick={() => void deletePrinter(printer.id)}>
                      <FaTrash />
                    </Button>
                  </div>
                  <div className="text-muted mt-2">{Number(printer.assembly_hours ?? 0).toFixed(1)} hours per unit</div>
                </div>
              ))}
            </div>
          </Card.Body>
        </Card>

        <Card>
          <Card.Header><FaPlus className="me-2" />Materials</Card.Header>
          <Card.Body>
            <Form.Group className="mb-3">
              <Form.Label>Material name</Form.Label>
              <Form.Control value={materialForm.name} onChange={(event) => setMaterialForm({ name: event.target.value })} />
            </Form.Group>
            <Button variant="primary" onClick={createMaterial} disabled={!materialForm.name}>Add material</Button>
            <div className="list-stack mt-4">
              {materials.map((material) => (
                <div className="metric-item" key={material.id}>
                  <strong>{material.name}</strong>
                </div>
              ))}
            </div>
          </Card.Body>
        </Card>

        <Card>
          <Card.Header><FaPlus className="me-2" />Bill of materials</Card.Header>
          <Card.Body>
            <Form.Group className="mb-3">
              <Form.Label>Printer model</Form.Label>
              <Form.Select value={bomForm.finished_product_id} onChange={(event) => setBomForm({ ...bomForm, finished_product_id: event.target.value })}>
                <option value="">Select a printer</option>
                {printers.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Material</Form.Label>
              <Form.Select value={bomForm.material_id} onChange={(event) => setBomForm({ ...bomForm, material_id: event.target.value })}>
                <option value="">Select a material</option>
                {materials.map((material) => <option key={material.id} value={material.id}>{material.name}</option>)}
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Quantity per finished unit</Form.Label>
              <Form.Control type="number" step="0.01" value={bomForm.quantity} onChange={(event) => setBomForm({ ...bomForm, quantity: event.target.value })} />
            </Form.Group>
            <Button variant="primary" onClick={createBomEntry} disabled={!bomForm.finished_product_id || !bomForm.material_id}>Add BOM entry</Button>
          </Card.Body>
        </Card>
      </div>

      <div className="card">
        <div className="card-header">Current BOM map</div>
        <div className="card-body p-0">
          {bomEntries.length ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Printer</th>
                  <th>Material</th>
                  <th>Quantity per unit</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bomEntries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{productMap.get(entry.finished_product_id) ?? entry.finished_product_id}</td>
                    <td>{productMap.get(entry.material_id) ?? entry.material_id}</td>
                    <td>{Number(entry.quantity).toFixed(2)}</td>
                    <td>
                      <Button variant="outline-secondary" size="sm" onClick={() => void deleteBomEntry(entry.id)}>
                        <FaTrash className="me-2" />Delete
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div className="empty-state">Add BOM entries so assembly knows which materials each printer consumes.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Settings;
