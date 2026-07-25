import { loadJson } from './shared.js'

export async function loadAdministrativeLayers(configs) {
  const entries = await Promise.all(
    configs.map(async (config) => [config.id, await loadJson(config.dataFile)]),
  )
  return Object.fromEntries(entries)
}
