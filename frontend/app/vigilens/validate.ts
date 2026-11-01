import { validateZonePoints } from "./geometry";
import type { Audit, Point, PpeState, Zone } from "./types";

const PPE_VALUES: PpeState[] = ["present", "absent", "unknown"];
const SCHEMA_VERSIONS = ["0.2", "0.2-local-draft"];

export class AuditValidationError extends Error {}

function fail(reason: string): never {
  throw new AuditValidationError(`Audit data is invalid: ${reason}. No results were shown.`);
}

function isUnitPoint(p: unknown): p is Point {
  if (!p || typeof p !== "object") return false;
  const { x, y } = p as Point;
  return Number.isFinite(x) && Number.isFinite(y) && x >= 0 && x <= 1 && y >= 0 && y <= 1;
}

function checkPolygon(points: unknown, label: string) {
  if (!Array.isArray(points) || points.length < 3) fail(`${label} needs at least 3 points`);
  for (const p of points) {
    if (!isUnitPoint(p)) fail(`${label} has a coordinate outside 0 to 1`);
  }
}

export function validateZones(zones: unknown): Zone[] {
  if (!Array.isArray(zones)) fail("zones is missing");
  const seen = new Set<string>();
  for (const z of zones as Zone[]) {
    if (typeof z.id !== "string" || seen.has(z.id)) fail("zone ids must be unique strings");
    seen.add(z.id);
    if (typeof z.name !== "string" || z.name.length < 1 || z.name.length > 200) {
      fail(`zone ${z.id} needs a name of 1 to 200 characters`);
    }
    if (typeof z.hazard !== "boolean") fail(`zone ${z.id} hazard must be true or false`);
    if (!Array.isArray(z.points) || !z.points.every(isUnitPoint)) {
      fail(`zone ${z.id} points must be within 0 to 1`);
    }
    const err = validateZonePoints(z.points);
    if (err) fail(`zone ${z.id}: ${err}`);
  }
  return zones as Zone[];
}

export function validateAudit(audit: Audit): Audit {
  if (!audit || typeof audit !== "object") fail("response is not an object");
  if (typeof audit.audit_id !== "string") fail("audit_id is missing");
  if (!SCHEMA_VERSIONS.includes(audit.schema_version)) fail("unsupported schema_version");
  if (!audit.image || !(audit.image.width > 0) || !(audit.image.height > 0)) {
    fail("image size is missing");
  }
  const zones = validateZones(audit.zones);
  const zoneIds = new Set(zones.map((z) => z.id));
  if (!Array.isArray(audit.persons)) fail("persons is missing");

  const personIds = new Set<string>();
  const findingIds = new Set<string>();
  for (const person of audit.persons) {
    if (typeof person.id !== "string" || personIds.has(person.id)) fail("person ids must be unique");
    personIds.add(person.id);
    checkPolygon(person.polygon, `person ${person.id}`);
    if (!PPE_VALUES.includes(person.helmet) || !PPE_VALUES.includes(person.vest)) {
      fail(`person ${person.id} has an unknown PPE value`);
    }
    if (person.zone_id !== null && !zoneIds.has(person.zone_id)) fail(`person ${person.id} refers to an unknown zone`);
    for (const zid of person.zone_ids ?? []) {
      if (!zoneIds.has(zid)) fail(`person ${person.id} refers to an unknown zone`);
    }
    if (!Array.isArray(person.findings)) fail(`person ${person.id} findings is missing`);
    for (const f of person.findings) {
      if (typeof f.id !== "string" || findingIds.has(f.id)) fail("finding ids must be unique");
      findingIds.add(f.id);
      if (f.zone_id !== null && !zoneIds.has(f.zone_id)) fail(`finding ${f.id} refers to an unknown zone`);
      if (f.severity !== null && typeof f.severity !== "string") fail(`finding ${f.id} severity is invalid`);
    }
  }
  return audit;
}
