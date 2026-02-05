declare module 'react-cytoscapejs' {
  import type { Core, ElementDefinition, Stylesheet, LayoutOptions } from 'cytoscape';
  import type { ComponentType } from 'react';

  interface CytoscapeComponentProps {
    elements: ElementDefinition[];
    style?: React.CSSProperties;
    stylesheet?: Stylesheet[];
    layout?: LayoutOptions;
    cy?: (cy: Core) => void;
    pixelRatio?: number;
    hideEdgesOnViewport?: boolean;
    textureOnViewport?: boolean;
    motionBlur?: boolean;
    motionBlurOpacity?: number;
    wheelSensitivity?: number;
    boxSelectionEnabled?: boolean;
    autoungrabify?: boolean;
    autounselectify?: boolean;
    pan?: { x: number; y: number };
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    zoomingEnabled?: boolean;
    userZoomingEnabled?: boolean;
    panningEnabled?: boolean;
    userPanningEnabled?: boolean;
    autolock?: boolean;
    className?: string;
    id?: string;
  }

  const CytoscapeComponent: ComponentType<CytoscapeComponentProps>;
  export default CytoscapeComponent;
}
