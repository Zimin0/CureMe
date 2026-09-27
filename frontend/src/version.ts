// Подставляются при сборке (см. buildInfo.ts).
declare const __APP_VERSION__: string
declare const __APP_COMMIT__: string

export const APP_VERSION = __APP_VERSION__
export const APP_COMMIT = __APP_COMMIT__

/** «Версия 1.0.0 · a1b2c3d» — коммит показываем, если он известен. */
export function versionLabel(version = APP_VERSION, commit = APP_COMMIT): string {
  return commit ? `Версия ${version} · ${commit}` : `Версия ${version}`
}
