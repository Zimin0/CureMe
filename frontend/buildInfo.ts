import { execSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// Версия приложения вшивается в сборку фронтенда: номер — из файла VERSION в корне репозитория,
// коммит — из CUREME_COMMIT (его передаёт деплой) или из локального git.
function gitCommit(): string {
  try {
    return execSync('git rev-parse --short=7 HEAD', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  } catch {
    return '' // в Docker-сборке нет .git, там коммит приходит через CUREME_COMMIT
  }
}

export function buildDefines() {
  const version = readFileSync(fileURLToPath(new URL('../VERSION', import.meta.url)), 'utf8').trim()
  const commit = (process.env.CUREME_COMMIT || gitCommit()).slice(0, 7)
  return {
    __APP_VERSION__: JSON.stringify(version),
    __APP_COMMIT__: JSON.stringify(commit),
  }
}
