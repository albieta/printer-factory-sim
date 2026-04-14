import React, { useState, useEffect } from 'react';
import { Card, Form, Button, Alert, Row, Col } from 'react-bootstrap';
import { FaCog, FaSave, FaUndo } from 'react-icons/fa';
import { configAPI, simulationAPI } from '../services/api';
import type { SimulationConfig } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Settings: React.FC = () => {
  const [config, setConfig] = useState<SimulationConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  const [formData, setFormData] = useState({
    warehouse_capacity: 1000,
    daily_assembly_hours: 8.0,
    demand_distribution_mean: 5.0,
    demand_distribution_variance: 2.0,
  });

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const response = await configAPI.getConfig();
      setConfig(response.data);
      setFormData({
        warehouse_capacity: response.data.warehouse_capacity,
        daily_assembly_hours: response.data.daily_assembly_hours,
        demand_distribution_mean: response.data.demand_distribution_mean,
        demand_distribution_variance: response.data.demand_distribution_variance,
      });
      setError(null);
    } catch (err: any) {
      setError('Failed to load configuration');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  const handleSave = async () => {
    try {
      setSaving(true);
      await configAPI.updateConfig(formData);
      setSuccess('Configuration saved successfully');
      setError(null);
      await fetchConfig();
    } catch (err: any) {
      setError('Failed to save configuration');
      setSuccess(null);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm('Are you sure you want to reset the simulation? This will delete all orders and events.')) {
      return;
    }
    
    if (!window.confirm('This action cannot be undone. Continue?')) {
      return;
    }
    
    try {
      await simulationAPI.reset();
      setSuccess('Simulation reset successfully');
      setError(null);
    } catch (err: any) {
      setError('Failed to reset simulation');
      setSuccess(null);
    }
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
        <p>Configure simulation parameters and system settings</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}
      {success && <Alert variant="success">{success}</Alert>}

      {/* Configuration Form */}
      <Card className="mb-4">
        <Card.Header>
          <strong><FaCog /> Simulation Configuration</strong>
        </Card.Header>
        <Card.Body>
          <Row>
            <Col md={6}>
              <Form.Group className="mb-3">
                <Form.Label>Warehouse Capacity</Form.Label>
                <Form.Control
                  type="number"
                  value={formData.warehouse_capacity}
                  onChange={(e) => setFormData({ ...formData, warehouse_capacity: parseInt(e.target.value) })}
                />
                <Form.Text className="text-muted">
                  Total storage units available in the warehouse
                </Form.Text>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group className="mb-3">
                <Form.Label>Daily Assembly Hours</Form.Label>
                <Form.Control
                  type="number"
                  step="0.5"
                  value={formData.daily_assembly_hours}
                  onChange={(e) => setFormData({ ...formData, daily_assembly_hours: parseFloat(e.target.value) })}
                />
                <Form.Text className="text-muted">
                  Production capacity per day in hours
                </Form.Text>
              </Form.Group>
            </Col>
          </Row>
          <Row>
            <Col md={6}>
              <Form.Group className="mb-3">
                <Form.Label>Demand Distribution Mean</Form.Label>
                <Form.Control
                  type="number"
                  step="0.5"
                  value={formData.demand_distribution_mean}
                  onChange={(e) => setFormData({ ...formData, demand_distribution_mean: parseFloat(e.target.value) })}
                />
                <Form.Text className="text-muted">
                  Average number of orders generated per day
                </Form.Text>
              </Form.Group>
            </Col>
            <Col md={6}>
              <Form.Group className="mb-3">
                <Form.Label>Demand Distribution Variance</Form.Label>
                <Form.Control
                  type="number"
                  step="0.5"
                  value={formData.demand_distribution_variance}
                  onChange={(e) => setFormData({ ...formData, demand_distribution_variance: parseFloat(e.target.value) })}
                />
                <Form.Text className="text-muted">
                  Variance in daily order generation
                </Form.Text>
              </Form.Group>
            </Col>
          </Row>
          <div className="d-flex gap-2">
            <Button 
              variant="primary" 
              onClick={handleSave}
              disabled={saving}
            >
              <FaSave /> {saving ? 'Saving...' : 'Save Configuration'}
            </Button>
            <Button 
              variant="outline-secondary" 
              onClick={() => {
                if (config) {
                  setFormData({
                    warehouse_capacity: config.warehouse_capacity,
                    daily_assembly_hours: config.daily_assembly_hours,
                    demand_distribution_mean: config.demand_distribution_mean,
                    demand_distribution_variance: config.demand_distribution_variance,
                  });
                }
              }}
            >
              <FaUndo /> Reset to Saved
            </Button>
          </div>
        </Card.Body>
      </Card>

      {/* Simulation Control */}
      <Card className="mb-4">
        <Card.Header>
          <strong>Simulation Control</strong>
        </Card.Header>
        <Card.Body>
          <Alert variant="warning">
            <strong>Warning:</strong> Resetting the simulation will delete all manufacturing orders, 
            purchase orders, and events. Inventory will be cleared. This action cannot be undone.
          </Alert>
          <Button 
            variant="danger" 
            onClick={handleReset}
          >
            <FaUndo /> Reset Simulation
          </Button>
        </Card.Body>
      </Card>

      {/* Current Configuration Summary */}
      {config && (
        <Card>
          <Card.Header>
            <strong>Current Configuration Summary</strong>
          </Card.Header>
          <Card.Body>
            <Row>
              <Col md={3}>
                <div className="text-center p-3 bg-light rounded">
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#1976d2' }}>
                    {config.warehouse_capacity.toLocaleString()}
                  </div>
                  <div className="text-muted">Warehouse Capacity</div>
                </div>
              </Col>
              <Col md={3}>
                <div className="text-center p-3 bg-light rounded">
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#4caf50' }}>
                    {config.daily_assembly_hours}h
                  </div>
                  <div className="text-muted">Daily Assembly Hours</div>
                </div>
              </Col>
              <Col md={3}>
                <div className="text-center p-3 bg-light rounded">
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#ff9800' }}>
                    {config.demand_distribution_mean}
                  </div>
                  <div className="text-muted">Avg Daily Orders</div>
                </div>
              </Col>
              <Col md={3}>
                <div className="text-center p-3 bg-light rounded">
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#f44336' }}>
                    ±{config.demand_distribution_variance}
                  </div>
                  <div className="text-muted">Demand Variance</div>
                </div>
              </Col>
            </Row>
          </Card.Body>
        </Card>
      )}
    </div>
  );
};

export default Settings;
