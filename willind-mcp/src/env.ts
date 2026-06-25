import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { config as loadEnv } from 'dotenv'

const here = dirname(fileURLToPath(import.meta.url))

for (const envPath of [
  resolve(here, '..', '.env'),
  resolve(here, '..', '..', '..', '.env'),
]) {
  if (existsSync(envPath)) loadEnv({ path: envPath, override: false })
}
