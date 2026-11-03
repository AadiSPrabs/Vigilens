import type { Audit, Finding, Person, Zone } from "./types";

export function personLabel(person: Person, index: number) {
  return `Person ${index + 1}`;
}

export type PersonMapping = { id: string; label: string; mapped: boolean };

// Maps each backend person id to the label drawn on its stage outline. The label travels with the record that
// carries both the id and the polygon, so the report and the stage cannot disagree. A person is unmapped when
// its id is duplicated or its outline is not a usable polygon: it then gets no number and no attestations.
export function personMappings(persons: Person[]): Map<string, PersonMapping> {
  const counts = new Map<string, number>();
  for (const p of persons) counts.set(p.id, (counts.get(p.id) ?? 0) + 1);
  const out = new Map<string, PersonMapping>();
  persons.forEach((p, index) => {
    const poly = Array.isArray(p.polygon) ? p.polygon : [];
    const usable = poly.length >= 3 && poly.every((q) => Number.isFinite(q.x) && Number.isFinite(q.y) && q.x >= 0 && q.x <= 1 && q.y >= 0 && q.y <= 1);
    const mapped = usable && counts.get(p.id) === 1;
    out.set(p.id, { id: p.id, mapped, label: mapped ? personLabel(p, index) : "Unmapped person" });
  });
  return out;
}

export function zoneNameFor(zones: Zone[], id: string | null) {
  if (!id) return "No zone shown";
  return zones.find((z) => z.id === id)?.name ?? "No zone shown";
}

export function formatClock(date: Date) {
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function formatFixtureTime(iso: string | null) {
  if (!iso) return "unknown";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "unknown";
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
}

export function allFindings(audit: Audit): { person: Person; personIndex: number; finding: Finding }[] {
  return audit.persons.flatMap((person, personIndex) =>
    person.findings.map((finding) => ({ person, personIndex, finding })),
  );
}

export function pluralize(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}
