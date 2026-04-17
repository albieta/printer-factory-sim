import React from 'react';

interface PageGuideProps {
  title: string;
  controls: string;
  next: string;
  tip?: string;
}

const PageGuide: React.FC<PageGuideProps> = ({ title, controls, next, tip }) => {
  return (
    <section className="page-guide" aria-label={`${title} guidance`}>
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
          <strong>Why it matters:</strong> {tip}
        </div>
      ) : null}
    </section>
  );
};

export default PageGuide;
