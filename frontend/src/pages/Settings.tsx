import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaCog, FaPlus, FaSave, FaTrash, FaUndo } from 'react-icons/fa';
import PageGuide from '../components/PageGuide';
import { configAPI, getErrorMessage, materialsAPI, simulationAPI } from '../services/api';
import type { BOMEntry, Product, SimulationConfig } from '../types';
import { announceSimulationUpdate } from '../utils/simulationEvents';
import LoadingSpinner from '../components/LoadingSpinner';

const Settings: React.FC = () => {
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [printers, setPrinters] = useState<Product[]>([]);
  const [materials, setMaterials] = useState<Product[]>([]);
  const [bomEntries, setBomEntries] = useState<BOMEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState({
    warehouse_capacity: '2200',
    assembly_lines: '1',
    workers_per_line: '1',
    shift_hours: '8',
    demand_distribution_mean: '5',
    demand_distribution_variance: '2',
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
      });
      setMessage('Configuration saved. Capacity and warehouse limits are updated.');
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
        tip="The reset action now restores the full starter profile, including seeded inventory and the corrected warehouse capacity, so the simulation starts from a valid non-negative scenario."
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
              <Form.Label>Demand mean</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.demand_distribution_mean} onChange={(event) => setFormData({ ...formData, demand_distribution_mean: event.target.value })} />
              <Form.Text>Average new order quantity generated per simulation day.</Form.Text>
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Demand variance</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.demand_distribution_variance} onChange={(event) => setFormData({ ...formData, demand_distribution_variance: event.target.value })} />
              <Form.Text>How much daily demand fluctuates around the mean.</Form.Text>
            </Form.Group>
          </div>

          <div className="metric-item emphasis-item mb-4">
            <div className="stat-row">
              <span>Derived daily assembly hours</span>
              <strong>{effectiveHours.toFixed(1)}</strong>
            </div>
            <div className="formula-line">
              {formData.assembly_lines} lines × {formData.workers_per_line} workers × {Number(formData.shift_hours || 0).toFixed(1)} hours = {effectiveHours.toFixed(1)} shared hours/day
            </div>
            <div className="text-muted mt-2">The legacy daily-assembly-hours value is still exposed for compatibility, but this workforce model is now the primary way to manage capacity.</div>
          </div>

          <div className="status-grid">
            <div className="metric-item">
              <strong>Manufacturing statuses</strong>
              <div className="text-muted mt-2">Awaiting Release: demand exists but has not entered assembly.</div>
              <div className="text-muted mt-1">Queued for Production: order is released and waiting to consume shared capacity.</div>
              <div className="text-muted mt-1">Blocked by Material Shortage: inventory is not sufficient to proceed.</div>
              <div className="text-muted mt-1">Completed: work finished on a simulation day.</div>
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
            <Button variant="danger" onClick={resetSimulation}><FaUndo className="me-2" />Reset to starter profile</Button>
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
