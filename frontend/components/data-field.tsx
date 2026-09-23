"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";

/**
 * An ambient field of points and connections behind the hero.
 *
 * Deliberately almost invisible at rest: the data visualisation is the hero,
 * and a busy animated backdrop competes with it. Points drift very slowly;
 * edges only appear between near neighbours, and brighten slightly near the
 * pointer. Nothing here encodes data — it is texture, so it carries no labels
 * and no numbers that could be mistaken for a reading.
 *
 * Costs: one canvas, ~50 points, capped at 2× DPR, paused when off-screen and
 * disabled outright under `prefers-reduced-motion`.
 */
export function DataField({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    let visible = true;
    let width = 0;
    let height = 0;

    const pointer = { x: -9999, y: -9999 };
    type Point = { x: number; y: number; vx: number; vy: number };
    let points: Point[] = [];

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = rect.width;
      height = rect.height;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      context.setTransform(dpr, 0, 0, dpr, 0, 0);

      // Density scales with area so a wide monitor is not denser than a laptop.
      const count = Math.min(56, Math.max(18, Math.round((width * height) / 22000)));
      points = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.12,
        vy: (Math.random() - 0.5) * 0.12,
      }));
    };

    const readTheme = () => {
      const styles = getComputedStyle(document.documentElement);
      return {
        dot: styles.getPropertyValue("--color-ink-faint").trim() || "#99a0b8",
        edge: styles.getPropertyValue("--color-brand").trim() || "#4f46e5",
      };
    };
    let theme = readTheme();

    const draw = () => {
      context.clearRect(0, 0, width, height);
      const linkDistance = 118;

      for (const point of points) {
        point.x += point.vx;
        point.y += point.vy;
        if (point.x < 0 || point.x > width) point.vx *= -1;
        if (point.y < 0 || point.y > height) point.vy *= -1;
      }

      // Edges first, so points sit on top of them.
      for (let i = 0; i < points.length; i += 1) {
        for (let j = i + 1; j < points.length; j += 1) {
          const dx = points[i].x - points[j].x;
          const dy = points[i].y - points[j].y;
          const distance = Math.hypot(dx, dy);
          if (distance > linkDistance) continue;

          const midX = (points[i].x + points[j].x) / 2;
          const midY = (points[i].y + points[j].y) / 2;
          const toPointer = Math.hypot(midX - pointer.x, midY - pointer.y);
          // Base opacity is barely there; proximity to the pointer lifts it a little.
          const proximity = Math.max(0, 1 - toPointer / 220);
          const alpha = (1 - distance / linkDistance) * (0.05 + proximity * 0.22);

          context.strokeStyle = theme.edge;
          context.globalAlpha = alpha;
          context.lineWidth = 1;
          context.beginPath();
          context.moveTo(points[i].x, points[i].y);
          context.lineTo(points[j].x, points[j].y);
          context.stroke();
        }
      }

      for (const point of points) {
        const toPointer = Math.hypot(point.x - pointer.x, point.y - pointer.y);
        const proximity = Math.max(0, 1 - toPointer / 180);
        context.globalAlpha = 0.16 + proximity * 0.4;
        context.fillStyle = proximity > 0.25 ? theme.edge : theme.dot;
        context.beginPath();
        context.arc(point.x, point.y, 1.1 + proximity * 1.2, 0, Math.PI * 2);
        context.fill();
      }

      context.globalAlpha = 1;
      if (visible && !reduced.matches) frame = requestAnimationFrame(draw);
    };

    const onPointer = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = event.clientX - rect.left;
      pointer.y = event.clientY - rect.top;
    };
    const onLeave = () => {
      pointer.x = -9999;
      pointer.y = -9999;
    };

    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting;
        if (visible && !reduced.matches) {
          cancelAnimationFrame(frame);
          frame = requestAnimationFrame(draw);
        }
      },
      { threshold: 0 },
    );
    observer.observe(canvas);

    const themeObserver = new MutationObserver(() => {
      theme = readTheme();
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    resize();
    draw(); // One static frame, so reduced-motion users still see the texture.

    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", onPointer);
    window.addEventListener("pointerleave", onLeave);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      themeObserver.disconnect();
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={cn("pointer-events-none absolute inset-0 size-full", className)}
    />
  );
}
