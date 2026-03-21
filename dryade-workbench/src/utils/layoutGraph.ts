// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
/**
 * Shared Kahn's topological layout algorithm.
 *
 * Used by MiniGraph (horizontal), WorkflowCanvas auto-layout (vertical),
 * and useWorkflowState plan loading (vertical).
 */

export interface LayoutConfig {
  direction: 'horizontal' | 'vertical';
  nodeWidth: number;
  nodeHeight: number;
  hSpacing: number;
  vSpacing: number;
  startX: number;
  startY: number;
}

export interface LayoutEdge {
  from?: string;
  to?: string;
  source?: string;
  target?: string;
}

/**
 * Position nodes using Kahn's topological sort.
 *
 * - `horizontal`: levels are columns (left-to-right) — compact previews
 * - `vertical`: levels are rows (top-to-bottom) — workflow editor
 */
export function layoutGraph(
  nodeIds: string[],
  edges: LayoutEdge[],
  config: LayoutConfig,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  if (nodeIds.length === 0) return positions;

  // Build adjacency + in-degree
  const inDegree = new Map<string, number>();
  const adjacency = new Map<string, string[]>();

  nodeIds.forEach((id) => {
    inDegree.set(id, 0);
    adjacency.set(id, []);
  });

  edges.forEach((e) => {
    const from = e.from || e.source;
    const to = e.to || e.target;
    if (from && to && adjacency.has(from) && inDegree.has(to)) {
      adjacency.get(from)?.push(to);
      inDegree.set(to, (inDegree.get(to) || 0) + 1);
    }
  });

  // Kahn's algorithm — assign levels
  const levels: string[][] = [];
  const queue: string[] = [];

  inDegree.forEach((deg, id) => {
    if (deg === 0) queue.push(id);
  });

  while (queue.length > 0) {
    const currentLevel = [...queue];
    levels.push(currentLevel);
    queue.length = 0;

    for (const nodeId of currentLevel) {
      for (const neighbor of adjacency.get(nodeId) || []) {
        const newDeg = (inDegree.get(neighbor) || 1) - 1;
        inDegree.set(neighbor, newDeg);
        if (newDeg === 0) queue.push(neighbor);
      }
    }
  }

  // Handle remaining nodes (cycles or disconnected)
  const placed = new Set(levels.flat());
  const remaining = nodeIds.filter((id) => !placed.has(id));
  if (remaining.length > 0) {
    levels.push(remaining);
  }

  // Position nodes
  const { direction, nodeWidth, nodeHeight, hSpacing, vSpacing, startX, startY } = config;
  const maxLevelSize = levels.reduce((max, l) => Math.max(max, l.length), 0);

  if (direction === 'horizontal') {
    // Levels = columns, left-to-right
    // Stagger single-node levels vertically so linear chains don't produce flat lines
    const allSingle = maxLevelSize === 1;
    let xOffset = startX;
    let staggerIndex = 0;

    levels.forEach((level) => {
      if (level.length === 1 && allSingle) {
        // Zigzag: alternate between two Y positions for visual separation
        const yA = startY;
        const yB = startY + nodeHeight + vSpacing;
        positions.set(level[0], { x: xOffset, y: staggerIndex % 2 === 0 ? yA : yB });
        staggerIndex++;
      } else if (level.length === 1) {
        // Single node in a mixed graph — center vertically relative to max level
        const totalHeight = maxLevelSize * (nodeHeight + vSpacing);
        const yOffset = startY + Math.max(0, (totalHeight - (nodeHeight + vSpacing)) / 2);
        positions.set(level[0], { x: xOffset, y: yOffset });
      } else {
        // Multiple nodes — spread them vertically, centered on max level height
        const levelHeight = level.length * (nodeHeight + vSpacing);
        const totalHeight = maxLevelSize * (nodeHeight + vSpacing);
        let yOffset = startY + Math.max(0, (totalHeight - levelHeight) / 2);

        level.forEach((nodeId) => {
          positions.set(nodeId, { x: xOffset, y: yOffset });
          yOffset += nodeHeight + vSpacing;
        });
      }

      xOffset += nodeWidth + hSpacing;
    });
  } else {
    // Levels = rows, top-to-bottom
    let yOffset = startY;
    levels.forEach((level) => {
      const levelWidth = level.length * (nodeWidth + hSpacing);
      const totalWidth = maxLevelSize * (nodeWidth + hSpacing);
      let xOffset = startX + Math.max(0, (totalWidth - levelWidth) / 2);

      level.forEach((nodeId) => {
        positions.set(nodeId, { x: xOffset, y: yOffset });
        xOffset += nodeWidth + hSpacing;
      });

      yOffset += nodeHeight + vSpacing;
    });
  }

  // Post-processing pass: center merge nodes between their actual parents.
  // Without this, merge nodes (in-degree >= 2) are centered relative to
  // maxLevelSize, which is incorrect when parents span different levels
  // or occupy non-adjacent positions within a level.
  const parentMap = new Map<string, string[]>();
  edges.forEach((e) => {
    const from = e.from || e.source;
    const to = e.to || e.target;
    if (from && to) {
      if (!parentMap.has(to)) parentMap.set(to, []);
      parentMap.get(to)!.push(from);
    }
  });

  parentMap.forEach((parents, nodeId) => {
    if (parents.length < 2) return;
    const parentPositions = parents
      .map((pid) => positions.get(pid))
      .filter((p): p is { x: number; y: number } => p !== undefined);
    if (parentPositions.length < 2) return;

    const pos = positions.get(nodeId);
    if (!pos) return;

    if (direction === 'horizontal') {
      // Center Y between parent Y positions
      const avgY = parentPositions.reduce((sum, p) => sum + p.y, 0) / parentPositions.length;
      pos.y = avgY;
    } else {
      // Center X between parent X positions
      const avgX = parentPositions.reduce((sum, p) => sum + p.x, 0) / parentPositions.length;
      pos.x = avgX;
    }
  });

  return positions;
}
