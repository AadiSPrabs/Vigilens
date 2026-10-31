import type { Audit, Finding, Person, Zone } from "./types";

export function personLabel(person: Person, index: number) {
  return `Person ${index + 1}`;
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
