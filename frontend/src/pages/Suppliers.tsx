import React, { useState, useEffect } from 'react';
import { Table, Card, Alert } from 'react-bootstrap';
import { suppliersAPI } from '../services/api';
import type { Supplier } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';

const Suppliers: React.FC = () => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSuppliers = async () => {
    try {
      setLoading(true);
      const response = await suppliersAPI.getSuppliers();
      setSuppliers(response.data);
      setError(null);
    } catch (err: any) {
      setError('Failed to load suppliers');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSuppliers();
  }, []);

  if (loading) return <LoadingSpinner />;

  return (
    <div>
      <div className="page-header">
        <h1>Supplier Management</h1>
        <p>Manage your raw material suppliers and pricing</p>
      </div>

      {error && <Alert variant="danger">{error}</Alert>}

      <div className="card">
        <div className="card-header">Suppliers</div>
        <div className="card-body p-0">
          {suppliers.length > 0 ? (
            <Table responsive hover>
              <thead>
                <tr>
                  <th>Supplier Name</th>
                  <th>Product ID</th>
                  <th>Unit Cost</th>
                  <th>Lead Time (Days)</th>
                  <th>Quantity Breaks</th>
                </tr>
              </thead>
              <tbody>
                {suppliers.map((supplier) => (
                  <tr key={supplier.id}>
                    <td><strong>{supplier.name}</strong></td>
                    <td><code>{supplier.product_id.substring(0, 12)}...</code></td>
                    <td>${supplier.unit_cost.toFixed(2)}</td>
                    <td>{supplier.lead_time_days} days</td>
                    <td>
                      {supplier.quantity_breaks && supplier.quantity_breaks.length > 0 ? (
                        <div>
                          {supplier.quantity_breaks.map((qb, idx) => (
                            <span key={idx} className="badge bg-info me-1">
                              {qb.qty}+ @ ${qb.price.toFixed(2)}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted">No tiered pricing</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <div style={{ padding: '60px', textAlign: 'center', color: '#757575' }}>
              <p>No suppliers found. Add suppliers to start purchasing materials.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Suppliers;
