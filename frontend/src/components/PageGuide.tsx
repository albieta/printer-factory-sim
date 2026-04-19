import React from 'react';

interface PageGuideProps {
  title: string;
  controls: string;
  next: string;
  tip?: React.ReactNode;
  tipLabel?: string;
}

const PageGuide: React.FC<PageGuideProps> = ({ title, controls, next, tip, tipLabel = 'Why it matters' }) => {
  return (
    <details className="page-guide" aria-label={`${title} guidance`}>
      <summary className="page-guide-summary">
        <div>
          <div className="section-kicker">Screen guide</div>
          <strong>{title}</strong>
        </div>
        <span className="page-guide-summary-action">Show explanation</span>
      </summary>
      <div className="page-guide-content">
        <div className="page-guide-block">
          <div className="page-guide-label">What this screen controls</div>
          <p>{controls}</p>
        </div>
        <div className="page-guide-block">
          <div className="page-guide-label">What it changes next</div>
          <p>{next}</p>
        </div>
        {tip ? (
          <div className="page-guide-tip">
            <strong>{tipLabel}:</strong>
            <div>{tip}</div>
          </div>
        ) : null}
      </div>
    </details>
  );
};

export default PageGuide;
