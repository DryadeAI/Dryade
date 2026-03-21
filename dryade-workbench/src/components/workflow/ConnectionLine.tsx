// Licensed under the Dryade Source Use License (DSUL). See LICENSE.
import { type Connection } from "@/types/workflow";

interface ConnectionLineProps {
  connection: Connection;
  nodes: Map<string, { x: number; y: number }>;
  isActive?: boolean;
}

const ConnectionLine = ({ connection, nodes, isActive }: ConnectionLineProps) => {
  const fromPos = nodes.get(connection.from);
  const toPos = nodes.get(connection.to);

  if (!fromPos || !toPos) return null;

  const dx = toPos.x - fromPos.x;
  const controlOffset = Math.min(Math.abs(dx) * 0.5, 100);

  const path = `
    M ${fromPos.x + 100} ${fromPos.y}
    C ${fromPos.x + 100 + controlOffset} ${fromPos.y},
      ${toPos.x - 100 - controlOffset} ${toPos.y},
      ${toPos.x - 100} ${toPos.y}
  `;

  return (
    <g>
      {isActive && (
        <path
          d={path}
          fill="none"
          stroke="hsl(var(--primary) / 0.3)"
          strokeWidth={10}
          className="blur-sm"
        />
      )}
      <path
        d={path}
        fill="none"
        stroke={isActive ? "hsl(var(--accent))" : "hsl(var(--primary) / 0.5)"}
        strokeWidth={isActive ? 3 : 2.5}
        strokeLinecap="round"
        className={isActive ? "connection-line-active" : ""}
      />
      {isActive && (
        <circle r={5} fill="hsl(var(--accent))">
          <animateMotion dur="1.5s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </g>
  );
};

export default ConnectionLine;
