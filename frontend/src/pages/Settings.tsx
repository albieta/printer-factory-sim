import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Form, Table } from 'react-bootstrap';
import { FaCog, FaPlus, FaSave, FaTrash, FaUndo } from 'react-icons/fa';
import { configAPI, getErrorMessage, materialsAPI, simulationAPI } from '../services/api';
import type { BOMEntry, Product, SimulationConfig } from '../types';
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
    warehouse_capacity: '1000',
    daily_assembly_hours: '8',
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
        daily_assembly_hours: String(configRes.data.daily_assembly_hours),
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

  const saveConfig = async () => {
    try {
      setSaving(true);
      await configAPI.updateConfig({
        warehouse_capacity: Number(formData.warehouse_capacity),
        daily_assembly_hours: Number(formData.daily_assembly_hours),
        demand_distribution_mean: Number(formData.demand_distribution_mean),
        demand_distribution_variance: Number(formData.demand_distribution_variance),
      });
      setMessage('Simulation configuration saved.');
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
    if (!window.confirm('Reset the simulation state? Orders, purchase orders, events, and inventory levels will be cleared.')) {
      return;
    }

    try {
      await simulationAPI.reset();
      setMessage('Simulation reset successfully.');
      await loadSetup();
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to reset the simulation.'));
    }
  };

  if (loading) {
    return <LoadingSpinner label="Loading setup and configuration..." />;
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="section-kicker">Setup</div>
          <h1>Configuration studio</h1>
          <p>Shape the simulation inputs, define your factory catalog, and wire bill-of-materials rules that production uses every day.</p>
        </div>
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <Card className="mb-4">
        <Card.Header><FaCog className="me-2" />Simulation parameters</Card.Header>
        <Card.Body>
          <div className="two-column">
            <Form.Group className="mb-3">
              <Form.Label>Warehouse capacity</Form.Label>
              <Form.Control type="number" value={formData.warehouse_capacity} onChange={(event) => setFormData({ ...formData, warehouse_capacity: event.target.value })} />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Daily assembly hours</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.daily_assembly_hours} onChange={(event) => setFormData({ ...formData, daily_assembly_hours: event.target.value })} />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Demand mean</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.demand_distribution_mean} onChange={(event) => setFormData({ ...formData, demand_distribution_mean: event.target.value })} />
            </Form.Group>
            <Form.Group className="mb-3">
              <Form.Label>Demand variance</Form.Label>
              <Form.Control type="number" step="0.5" value={formData.demand_distribution_variance} onChange={(event) => setFormData({ ...formData, demand_distribution_variance: event.target.value })} />
            </Form.Group>
          </div>
          <div className="action-buttons">
            <Button variant="primary" onClick={saveConfig} disabled={saving}><FaSave className="me-2" />{saving ? 'Saving...' : 'Save configuration'}</Button>
            <Button variant="outline-secondary" onClick={() => config && setFormData({
              warehouse_capacity: String(config.warehouse_capacity),
              daily_assembly_hours: String(config.daily_assembly_hours),
              demand_distribution_mean: String(config.demand_distribution_mean),
              demand_distribution_variance: String(config.demand_distribution_variance),
            })}><FaUndo className="me-2" />Restore current values</Button>
            <Button variant="danger" onClick={resetSimulation}><FaUndo className="me-2" />Reset simulation state</Button>
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
                  <div className="text-muted mono mt-2">{material.id}</div>
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
                  <th>Entry ID</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bomEntries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{productMap.get(entry.finished_product_id) ?? entry.finished_product_id}</td>
                    <td>{productMap.get(entry.material_id) ?? entry.material_id}</td>
                    <td>{Number(entry.quantity).toFixed(2)}</td>
                    <td><span className="mono">{entry.id}</span></td>
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
            <div className="empty-state">Add BOM entries so production knows which materials each printer consumes.</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Settings;
