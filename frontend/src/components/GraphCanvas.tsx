import { useEffect, useRef, useCallback } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import type { Core, EventObject } from 'cytoscape';
import type { GraphElement, ViewMode } from '../types/paper';

interface GraphCanvasProps {
  elements: GraphElement[];
  viewMode: ViewMode;
  onNodeClick: (nodeId: string) => void;
  selectedNodeId: string | null;
}

const stylesheet = [
  {
    selector: 'node',
    style: {
      'background-color': '#6366f1',
      'label': 'data(label)',
      'font-size': '10px',
      'text-wrap': 'ellipsis',
      'text-max-width': '120px',
      'width': 'mapData(citationCount, 0, 150000, 30, 80)',
      'height': 'mapData(citationCount, 0, 150000, 30, 80)',
      'color': '#1f2937',
      'text-valign': 'bottom',
      'text-margin-y': 5,
    },
  },
  {
    selector: 'node[?isSeed]',
    style: {
      'background-color': '#dc2626',
      'border-width': 3,
      'border-color': '#991b1b',
    },
  },
  {
    selector: 'node:selected',
    style: {
      'background-color': '#22c55e',
      'border-width': 3,
      'border-color': '#15803d',
    },
  },
  {
    selector: 'edge',
    style: {
      'width': 2,
      'line-color': '#9ca3af',
      'curve-style': 'straight',
      'target-arrow-color': '#9ca3af',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
    },
  },
];

export function GraphCanvas({ elements, viewMode, onNodeClick, selectedNodeId }: GraphCanvasProps) {
  const cyRef = useRef<Core | null>(null);

  const handleNodeClick = useCallback((evt: EventObject) => {
    const nodeId = evt.target.id();
    onNodeClick(nodeId);
  }, [onNodeClick]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.on('tap', 'node', handleNodeClick);

    return () => {
      cy.off('tap', 'node', handleNodeClick);
    };
  }, [handleNodeClick]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !selectedNodeId) return;

    cy.batch(() => {
      cy.nodes().unselect();
      const node = cy.getElementById(selectedNodeId);
      if (node.length > 0) {
        node.select();
      }
    });
  }, [selectedNodeId]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    const handleZoom = () => {
      const zoom = cy.zoom();
      cy.batch(() => {
        if (zoom < 0.7) {
          cy.style().selector('node').style('label', '').update();
        } else {
          cy.style().selector('node').style('label', 'data(label)').update();
        }
      });
    };

    cy.on('zoom', handleZoom);
    return () => {
      cy.off('zoom', handleZoom);
    };
  }, []);

  const getLayout = () => {
    if (viewMode === 'pre') {
      return {
        name: 'preset',
        fit: true,
        padding: 50,
      };
    }
    return {
      name: 'breadthfirst',
      directed: true,
      roots: elements.filter(el => 'data' in el && 'isSeed' in el.data && el.data.isSeed).map(el => (el as GraphElement & { data: { id: string } }).data.id),
      spacingFactor: 1.5,
      padding: 50,
    };
  };

  return (
    <CytoscapeComponent
      elements={elements}
      style={{ width: '100%', height: '100%' }}
      layout={getLayout()}
      stylesheet={stylesheet}
      cy={(cy: Core) => {
        cyRef.current = cy;
      }}
      pixelRatio={1}
      hideEdgesOnViewport={true}
    />
  );
}
