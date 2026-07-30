/**
 * Reference module proving the TypeScript/ESLint/Vitest CI lane.
 * The real review console (React/Next.js) is built at CP23; this file has no UI.
 */

export interface ServiceInfo {
  name: string;
  version: string;
}

/** Returns a formatted banner for a service — trivial logic, exists to be tested. */
export function formatServiceBanner(info: ServiceInfo): string {
  return `Chartwright · ${info.name} v${info.version}`;
}
