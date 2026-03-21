// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { layoutGraph, type LayoutConfig } from '../utils/layoutGraph';

const HORIZONTAL: LayoutConfig = {
  direction: 'horizontal',
  nodeWidth: 220,
  nodeHeight: 120,
  hSpacing: 100,
  vSpacing: 60,
  startX: 100,
  startY: 80,
};

const VERTICAL: LayoutConfig = {
  direction: 'vertical',
  nodeWidth: 220,
  nodeHeight: 120,
  hSpacing: 100,
  vSpacing: 60,
  startX: 100,
  startY: 80,
};

describe('layoutGraph', () => {
  it('places linear chain A→B→C in separate columns with zigzag Y', () => {
    const positions = layoutGraph(
      ['A', 'B', 'C'],
      [{ from: 'A', to: 'B' }, { from: 'B', to: 'C' }],
      HORIZONTAL,
    );
    const xA = positions.get('A')!.x;
    const xB = positions.get('B')!.x;
    const xC = positions.get('C')!.x;

    // Each in a different column, left to right
    expect(xA).toBeLessThan(xB);
    expect(xB).toBeLessThan(xC);

    // Zigzag: A and C on same row, B on a different row (alternating)
    expect(positions.get('A')!.y).toBe(positions.get('C')!.y);
    expect(positions.get('A')!.y).not.toBe(positions.get('B')!.y);
  });

  it('places branching nodes A→[B,C]→D in correct levels with B,C on same column', () => {
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { from: 'A', to: 'B' },
        { from: 'A', to: 'C' },
        { from: 'B', to: 'D' },
        { from: 'C', to: 'D' },
      ],
      HORIZONTAL,
    );

    // A is first column
    const xA = positions.get('A')!.x;
    // B and C are second column (same x, different y)
    const xB = positions.get('B')!.x;
    const xC = positions.get('C')!.x;
    // D is third column
    const xD = positions.get('D')!.x;

    expect(xB).toBe(xC); // Same column
    expect(xA).toBeLessThan(xB); // A before B/C
    expect(xB).toBeLessThan(xD); // B/C before D

    // B and C must have different y (not overlapping)
    expect(positions.get('B')!.y).not.toBe(positions.get('C')!.y);
  });

  it('handles fan-out: A→[B,C,D] places B,C,D in same column', () => {
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { from: 'A', to: 'B' },
        { from: 'A', to: 'C' },
        { from: 'A', to: 'D' },
      ],
      HORIZONTAL,
    );

    const xB = positions.get('B')!.x;
    const xC = positions.get('C')!.x;
    const xD = positions.get('D')!.x;

    // All three in same column
    expect(xB).toBe(xC);
    expect(xC).toBe(xD);

    // All three at different y positions (no overlap)
    const ys = [positions.get('B')!.y, positions.get('C')!.y, positions.get('D')!.y];
    expect(new Set(ys).size).toBe(3);

    // Minimum vertical spacing between nodes
    ys.sort((a, b) => a - b);
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(HORIZONTAL.nodeHeight + HORIZONTAL.vSpacing);
  });

  it('no nodes overlap in complex diamond graph', () => {
    // Start → [A, B] → [C] → [D, E] → End
    const positions = layoutGraph(
      ['start', 'A', 'B', 'C', 'D', 'E', 'end'],
      [
        { from: 'start', to: 'A' },
        { from: 'start', to: 'B' },
        { from: 'A', to: 'C' },
        { from: 'B', to: 'C' },
        { from: 'C', to: 'D' },
        { from: 'C', to: 'E' },
        { from: 'D', to: 'end' },
        { from: 'E', to: 'end' },
      ],
      HORIZONTAL,
    );

    // Check no two nodes occupy the same position
    const posArray = Array.from(positions.entries());
    for (let i = 0; i < posArray.length; i++) {
      for (let j = i + 1; j < posArray.length; j++) {
        const [idA, posA] = posArray[i];
        const [idB, posB] = posArray[j];
        const samePos = posA.x === posB.x && posA.y === posB.y;
        expect(samePos).toBe(false);
      }
    }

    // Check nodes in same column don't overlap vertically
    const byColumn = new Map<number, Array<{ id: string; y: number }>>();
    posArray.forEach(([id, pos]) => {
      if (!byColumn.has(pos.x)) byColumn.set(pos.x, []);
      byColumn.get(pos.x)!.push({ id, y: pos.y });
    });

    byColumn.forEach((nodes) => {
      if (nodes.length < 2) return;
      nodes.sort((a, b) => a.y - b.y);
      for (let i = 1; i < nodes.length; i++) {
        const gap = nodes[i].y - nodes[i - 1].y;
        expect(gap).toBeGreaterThanOrEqual(HORIZONTAL.nodeHeight);
      }
    });
  });

  it('handles source/target edge format', () => {
    const positions = layoutGraph(
      ['A', 'B', 'C'],
      [{ source: 'A', target: 'B' }, { source: 'A', target: 'C' }],
      HORIZONTAL,
    );

    // B and C should be in same column (both children of A)
    expect(positions.get('B')!.x).toBe(positions.get('C')!.x);
    expect(positions.get('B')!.y).not.toBe(positions.get('C')!.y);
  });

  it('handles empty graph', () => {
    const positions = layoutGraph([], [], HORIZONTAL);
    expect(positions.size).toBe(0);
  });

  it('handles disconnected nodes', () => {
    const positions = layoutGraph(['A', 'B', 'C'], [], HORIZONTAL);
    // All roots → all in level 0 → same column, different y
    expect(positions.get('A')!.x).toBe(positions.get('B')!.x);
    expect(positions.get('A')!.y).not.toBe(positions.get('B')!.y);
  });

  // --- Diamond centering tests ---

  it('diamond merge D centers vertically between parents B and C (horizontal)', () => {
    // A -> [B, C] -> D
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { from: 'A', to: 'B' },
        { from: 'A', to: 'C' },
        { from: 'B', to: 'D' },
        { from: 'C', to: 'D' },
      ],
      HORIZONTAL,
    );

    const yB = positions.get('B')!.y;
    const yC = positions.get('C')!.y;
    const yD = positions.get('D')!.y;

    // D should be centered between B and C
    expect(yD).toBe((yB + yC) / 2);
  });

  it('diamond merge D centers horizontally between parents B and C (vertical)', () => {
    // A -> [B, C] -> D in vertical mode
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { from: 'A', to: 'B' },
        { from: 'A', to: 'C' },
        { from: 'B', to: 'D' },
        { from: 'C', to: 'D' },
      ],
      VERTICAL,
    );

    const xB = positions.get('B')!.x;
    const xC = positions.get('C')!.x;
    const xD = positions.get('D')!.x;

    // D should be centered between B and C
    expect(xD).toBe((xB + xC) / 2);
  });

  it('triple fan-in: D centers between all 3 parents A, B, C (horizontal)', () => {
    // A, B, C all merge into D
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { from: 'A', to: 'D' },
        { from: 'B', to: 'D' },
        { from: 'C', to: 'D' },
      ],
      HORIZONTAL,
    );

    const yA = positions.get('A')!.y;
    const yB = positions.get('B')!.y;
    const yC = positions.get('C')!.y;
    const yD = positions.get('D')!.y;

    // D should be the average of all 3 parents
    expect(yD).toBe((yA + yB + yC) / 3);
  });

  it('nested diamond: both merge nodes D and G center correctly (horizontal)', () => {
    // A -> [B, C] -> D -> [E, F] -> G
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D', 'E', 'F', 'G'],
      [
        { from: 'A', to: 'B' },
        { from: 'A', to: 'C' },
        { from: 'B', to: 'D' },
        { from: 'C', to: 'D' },
        { from: 'D', to: 'E' },
        { from: 'D', to: 'F' },
        { from: 'E', to: 'G' },
        { from: 'F', to: 'G' },
      ],
      HORIZONTAL,
    );

    const yB = positions.get('B')!.y;
    const yC = positions.get('C')!.y;
    const yD = positions.get('D')!.y;
    const yE = positions.get('E')!.y;
    const yF = positions.get('F')!.y;
    const yG = positions.get('G')!.y;

    // D centers between B and C
    expect(yD).toBe((yB + yC) / 2);
    // G centers between E and F
    expect(yG).toBe((yE + yF) / 2);
  });

  it('asymmetric fan-in with source/target edge format (horizontal)', () => {
    // A -> D, B -> D, C -> D where A, B, C are all roots at different y positions
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { source: 'A', target: 'D' },
        { source: 'B', target: 'D' },
        { source: 'C', target: 'D' },
      ],
      HORIZONTAL,
    );

    const yA = positions.get('A')!.y;
    const yB = positions.get('B')!.y;
    const yC = positions.get('C')!.y;
    const yD = positions.get('D')!.y;

    // D should be centered between all 3 parents
    expect(yD).toBe((yA + yB + yC) / 3);
  });

  it('cross-level merge: D centers between parents at different levels (horizontal)', () => {
    // A -> B -> D, C -> D
    // A and C are at level 0, B is at level 1, D is at level 2
    // D's parents are B (level 1) and C (level 0) — at very different Y positions
    // D should center between B.y and C.y
    const positions = layoutGraph(
      ['A', 'B', 'C', 'D'],
      [
        { from: 'A', to: 'B' },
        { from: 'B', to: 'D' },
        { from: 'C', to: 'D' },
      ],
      HORIZONTAL,
    );

    const yB = positions.get('B')!.y;
    const yC = positions.get('C')!.y;
    const yD = positions.get('D')!.y;

    // D should be centered between its actual parents B and C
    expect(yD).toBe((yB + yC) / 2);
  });
});
