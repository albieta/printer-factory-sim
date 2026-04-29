import React from 'react';

interface LoadingSpinnerProps {
  label?: string;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  label = 'Loading factory data...',
}) => {
  return (
    <div className="loading-shell" role="status" aria-live="polite">
      <div className="loading-spinner">
        <div className="spinner" />
      </div>
      <p className="loading-label">{label}</p>
    </div>
  );
};

export default LoadingSpinner;
