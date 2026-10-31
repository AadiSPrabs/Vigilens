import type { Point } from "./types";

export const MIN_CLICK_DISTANCE = 0.002;
export const MAX_POINTS_PER_ZONE = 100;
export const MAX_ZONES = 20;

export function clientToNormalized(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): Point | null {
  if (rect.width <= 0 || rect.height <= 0) return null;
  const x = (clientX - rect.left) / rect.width;
  const y = (clientY - rect.top) / rect.height;
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return { x, y };
}

function at(points: Point[], i: number): Point {
  return points[i % points.length] as Point;
}

export function polygonArea(points: Point[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = at(points, i);
    const b = at(points, i + 1);
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

function orient(a: Point, b: Point, c: Point): number {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function onSegment(a: Point, b: Point, p: Point): boolean {
  return (
    Math.min(a.x, b.x) <= p.x &&
    p.x <= Math.max(a.x, b.x) &&
    Math.min(a.y, b.y) <= p.y &&
    p.y <= Math.max(a.y, b.y)
  );
}

// Inclusive: segments that merely touch also count as intersecting.
export function segmentsIntersect(p1: Point, p2: Point, q1: Point, q2: Point) {
  const d1 = orient(q1, q2, p1);
  const d2 = orient(q1, q2, p2);
  const d3 = orient(p1, p2, q1);
  const d4 = orient(p1, p2, q2);
  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
    return true;
  }
  if (d1 === 0 && onSegment(q1, q2, p1)) return true;
  if (d2 === 0 && onSegment(q1, q2, p2)) return true;
  if (d3 === 0 && onSegment(p1, p2, q1)) return true;
  if (d4 === 0 && onSegment(p1, p2, q2)) return true;
  return false;
}

// Returns true when any two non-adjacent edges of the closed ring touch.
export function hasSelfIntersection(points: Point[]): boolean {
  const n = points.length;
  for (let i = 0; i < n; i++) {
    const a1 = at(points, i);
    const a2 = at(points, i + 1);
    for (let j = i + 1; j < n; j++) {
      if (j === i || (j + 1) % n === i || j === (i + 1) % n) continue;
      const b1 = at(points, j);
      const b2 = at(points, j + 1);
      if (segmentsIntersect(a1, a2, b1, b2)) return true;
    }
  }
  return false;
}

export function isNearPrevious(points: Point[], p: Point): boolean {
  const last = points[points.length - 1];
  if (!last) return false;
  return Math.hypot(p.x - last.x, p.y - last.y) < MIN_CLICK_DISTANCE;
}

// Checks whether appending p keeps the open chain free of self-touching edges.
export function canAppendPoint(points: Point[], p: Point): string | null {
  if (points.length >= MAX_POINTS_PER_ZONE) {
    return `A zone can have at most ${MAX_POINTS_PER_ZONE} points.`;
  }
  const n = points.length;
  if (n < 2) return null;
  const last = at(points, n - 1);
  for (let i = 0; i < n - 2; i++) {
    if (segmentsIntersect(last, p, at(points, i), at(points, i + 1))) {
      return "That point would make the zone edges cross or touch.";
    }
  }
  return null;
}

export function validateZonePoints(points: Point[]): string | null {
  if (points.length < 3) return "A zone needs at least 3 points.";
  if (points.length > MAX_POINTS_PER_ZONE) return `A zone can have at most ${MAX_POINTS_PER_ZONE} points.`;
  for (let i = 0; i < points.length; i++) {
    const a = at(points, i);
    const b = at(points, i + 1);
    if (Math.hypot(a.x - b.x, a.y - b.y) < 1e-9) return "Repeated points are not allowed.";
  }
  if (polygonArea(points) < 1e-6) return "The zone has no area.";
  if (hasSelfIntersection(points)) return "The zone edges cross or touch.";
  return null;
}
