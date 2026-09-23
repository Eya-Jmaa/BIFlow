"use client";

import { useMemo, useRef, useState } from "react";
import { Calendar, Hash, MapPin, Table2, Tag } from "lucide-react";

import { Badge, Eyebrow } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

/**
 * Interactive semantic model graph.
 *
 * Nodes are tables and the dimensions/measures bound to them; edges are the
 * relationships the profiler statistically validated. Pan and zoom are handled
 * directly rather than with a graph library — at this size a layout engine
 * would cost more than it saves, and a deterministic layout means the model
 * looks the same every time you open it.
 */

export type Dimension = {
  name: string;
  table_name: string;
  column_name: string;
  dim_type: string;
  grain: string | null;
  description: string | null;
};

export type Measure = {
  name: string;
  table_name: string;
  column_name: string;
  aggregation: string;
  unit: string | null;
  description: string | null;
};

export type Relationship = {
  source_table: string;
  source_column: string;
  target_table: string;
  target_column: string;
  cardinality: string;
  confidence: number;
  validated: boolean;
  overlap_ratio: number | null;
};

type Node = {
  id: string;
  x: number;
  y: number;
  dimensions: Dimension[];
  measures: Measure[];
};

const NODE_WIDTH = 220;
const DIM_ICON: Record<string, typeof Tag> = {
  datetime: Calendar,
  geo: MapPin,
  categorical: Tag,
};

export function EntityGraph({
  dimensions,
  measures,
  relationships,
  className,
}: {
  dimensions: Dimension[];
  measures: Measure[];
  relationships: Relationship[];
  className?: string;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selected, setSelected] = useState<string | null>(null);
  const dragging = useRef<{ x: number; y: number } | null>(null);

  const nodes = useMemo<Node[]>(() => {
    const tables = [...new Set([...dimensions, ...measures].map((item) => item.table_name))];
    // Deterministic grid: the same model always lays out identically.
    const columns = Math.min(3, Math.max(1, Math.ceil(Math.sqrt(tables.length))));
    return tables.map((table, index) => ({
      id: table,
      x: (index % columns) * (NODE_WIDTH + 90),
      y: Math.floor(index / columns) * 260,
      dimensions: dimensions.filter((item) => item.table_name === table),
      measures: measures.filter((item) => item.table_name === table),
    }));
  }, [dimensions, measures]);

  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const active = selected ? nodeById.get(selected) : null;

  const onPointerDown = (event: React.PointerEvent) => {
    dragging.current = { x: event.clientX - pan.x, y: event.clientY - pan.y };
    (event.target as Element).setPointerCapture?.(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent) => {
    if (!dragging.current) return;
    setPan({ x: event.clientX - dragging.current.x, y: event.clientY - dragging.current.y });
  };
  const onPointerUp = () => {
    dragging.current = null;
  };

  return (
    <div className={cn("relative", className)}>
      {/* Controls */}
      <div className="absolute top-3 right-3 z-10 flex items-center gap-1 rounded-lg border border-line bg-surface/90 p-1 shadow-card backdrop-blur">
        <GraphButton onClick={() => setZoom((value) => Math.max(0.5, value - 0.15))} label="Zoom out">
          −
        </GraphButton>
        <span className="tnum w-10 text-center text-[0.625rem] text-ink-faint">
          {Math.round(zoom * 100)}%
        </span>
        <GraphButton onClick={() => setZoom((value) => Math.min(1.6, value + 0.15))} label="Zoom in">
          +
        </GraphButton>
        <GraphButton
          onClick={() => {
            setZoom(1);
            setPan({ x: 0, y: 0 });
          }}
          label="Reset view"
        >
          ⟲
        </GraphButton>
      </div>

      <div
        className="relative h-[26rem] cursor-grab overflow-hidden rounded-card border border-line bg-sunken/40 active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        {/* Graph-paper backdrop, so pan has a visible frame of reference. */}
        <div
          className="absolute inset-0 opacity-60"
          style={{
            backgroundImage:
              "radial-gradient(circle, var(--color-line-strong) 1px, transparent 1px)",
            backgroundSize: "22px 22px",
            backgroundPosition: `${pan.x}px ${pan.y}px`,
          }}
          aria-hidden
        />

        <div
          className={cn(
            "absolute origin-top-left transition-transform duration-[--duration-fast] ease-[--ease-out-soft]",
            // A lone entity in the top corner reads as a layout bug; with only
            // a handful of nodes there is room to centre them instead.
            nodes.length <= 2 ? "inset-0 grid place-content-center p-8" : "p-8",
          )}
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          {/* Edges */}
          <svg className="pointer-events-none absolute inset-0 size-full overflow-visible" aria-hidden>
            {relationships.map((relationship, index) => {
              const from = nodeById.get(relationship.source_table);
              const to = nodeById.get(relationship.target_table);
              if (!from || !to) return null;
              const x1 = from.x + NODE_WIDTH;
              const y1 = from.y + 40;
              const x2 = to.x;
              const y2 = to.y + 40;
              const mid = (x1 + x2) / 2;
              return (
                <g key={index}>
                  <path
                    d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
                    fill="none"
                    stroke="var(--color-brand)"
                    strokeWidth={1.5}
                    strokeOpacity={relationship.validated ? 0.6 : 0.25}
                    strokeDasharray={relationship.validated ? undefined : "4 4"}
                  />
                  <text
                    x={mid}
                    y={(y1 + y2) / 2 - 6}
                    textAnchor="middle"
                    className="fill-[var(--color-ink-faint)] text-[9px]"
                  >
                    {relationship.cardinality.replace(/_/g, "-")}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Nodes */}
          {nodes.map((node) => {
            const isActive = node.id === selected;
            return (
              <button
                key={node.id}
                onClick={(event) => {
                  event.stopPropagation();
                  setSelected(isActive ? null : node.id);
                }}
                style={
                  nodes.length <= 2
                    ? { width: NODE_WIDTH }
                    : { left: node.x, top: node.y, width: NODE_WIDTH }
                }
                className={cn(
                  "rounded-card border bg-surface p-0 text-left shadow-card",
                  nodes.length > 2 && "absolute",
                  "transition-[box-shadow,border-color,transform] duration-[--duration-fast] ease-[--ease-out-soft]",
                  "hover:-translate-y-0.5 hover:shadow-lift",
                  isActive ? "border-brand ring-2 ring-brand/20" : "border-line",
                )}
              >
                <div className="flex items-center gap-2 border-b border-line px-3 py-2">
                  <Table2 className="size-3.5 shrink-0 text-brand" aria-hidden />
                  <span className="truncate font-mono text-[0.6875rem] font-medium text-ink">
                    {node.id}
                  </span>
                </div>
                <div className="space-y-0.5 p-2">
                  {node.dimensions.slice(0, 4).map((dimension) => {
                    const Icon = DIM_ICON[dimension.dim_type] ?? Tag;
                    return (
                      <div
                        key={dimension.name}
                        className="flex items-center gap-1.5 rounded px-1.5 py-1 text-[0.6875rem] text-ink-soft"
                      >
                        <Icon className="size-3 shrink-0 text-info" aria-hidden />
                        <span className="truncate font-mono">{dimension.column_name}</span>
                      </div>
                    );
                  })}
                  {node.measures.slice(0, 4).map((measure) => (
                    <div
                      key={measure.name}
                      className="flex items-center gap-1.5 rounded px-1.5 py-1 text-[0.6875rem] text-ink-soft"
                    >
                      <Hash className="size-3 shrink-0 text-good" aria-hidden />
                      <span className="truncate font-mono">{measure.column_name}</span>
                      <span className="ml-auto shrink-0 text-[0.5625rem] text-ink-faint">
                        {measure.aggregation}
                      </span>
                    </div>
                  ))}
                  {node.dimensions.length + node.measures.length > 8 && (
                    <p className="px-1.5 pt-1 text-[0.625rem] text-ink-faint">
                      +{node.dimensions.length + node.measures.length - 8} more
                    </p>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {relationships.length === 0 && nodes.length === 1 && (
          <p className="pointer-events-none absolute right-3 bottom-3 max-w-xs rounded-lg border border-line bg-surface/90 px-3 py-2 text-[0.6875rem] leading-snug text-ink-muted backdrop-blur">
            One table, so there are no relationships to validate. Upload related tables and the
            profiler will look for joins by value overlap.
          </p>
        )}
      </div>

      {/* Inspector */}
      {active && (
        <div className="bf-fade-up mt-3 rounded-card border border-line bg-surface p-4 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-mono text-[0.8125rem] font-semibold text-ink">{active.id}</h3>
            <Badge tone="neutral">
              {active.dimensions.length} dimensions · {active.measures.length} measures
            </Badge>
          </div>
          <div className="mt-3 grid gap-5 sm:grid-cols-2">
            <div>
              <Eyebrow>Dimensions</Eyebrow>
              <ul className="mt-1.5 space-y-1">
                {active.dimensions.map((dimension) => (
                  <li key={dimension.name} className="flex items-center gap-2 text-[0.75rem]">
                    <span className="truncate font-mono text-ink-soft">{dimension.column_name}</span>
                    <Badge tone="info">{dimension.dim_type}</Badge>
                    {dimension.grain && (
                      <span className="text-[0.625rem] text-ink-faint">{dimension.grain}</span>
                    )}
                  </li>
                ))}
                {active.dimensions.length === 0 && (
                  <li className="text-[0.75rem] text-ink-faint">None bound.</li>
                )}
              </ul>
            </div>
            <div>
              <Eyebrow>Measures</Eyebrow>
              <ul className="mt-1.5 space-y-1">
                {active.measures.map((measure) => (
                  <li key={measure.name} className="flex items-center gap-2 text-[0.75rem]">
                    <span className="truncate font-mono text-ink-soft">{measure.column_name}</span>
                    <Badge tone="good">{measure.aggregation}</Badge>
                    {measure.unit && (
                      <span className="text-[0.625rem] text-ink-faint">{measure.unit}</span>
                    )}
                  </li>
                ))}
                {active.measures.length === 0 && (
                  <li className="text-[0.75rem] text-ink-faint">None bound.</li>
                )}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function GraphButton({
  children,
  onClick,
  label,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="grid size-6 place-items-center rounded text-[0.75rem] text-ink-muted transition-colors duration-[--duration-fast] hover:bg-sunken hover:text-ink"
    >
      {children}
    </button>
  );
}
