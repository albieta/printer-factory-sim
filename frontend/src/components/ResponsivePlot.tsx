import React from 'react';
import Plot from 'react-plotly.js';
import type { Config, Data, Layout } from 'plotly.js';

interface ResponsivePlotProps {
  data: Data[];
  layout?: Partial<Layout>;
  config?: Partial<Config>;
  minHeight?: number;
}

const ResponsivePlot: React.FC<ResponsivePlotProps> = ({
  data,
  layout,
  config,
  minHeight = 320,
}) => {
  const mergedMargin = {
    t: 56,
    r: 24,
    b: 56,
    l: 56,
    ...(layout?.margin ?? {}),
  };

  const mergedLayout: Partial<Layout> = {
    autosize: true,
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    title: {
      x: 0,
      xanchor: 'left',
      font: { size: 18 },
      ...(layout?.title ?? {}),
    },
    ...layout,
    margin: mergedMargin,
  };

  return (
    <div className="responsive-plot" style={{ minHeight }}>
      <Plot
        data={data}
        layout={mergedLayout}
        config={{
          displayModeBar: false,
          responsive: true,
          ...config,
        }}
        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
};

export default ResponsivePlot;
