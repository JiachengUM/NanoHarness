import { readdir } from 'node:fs/promises'
import { extname, join, dirname, basename, relative } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import type { FastifyInstance, FastifyPluginAsync } from 'fastify'

type FastifyPlugin = FastifyPluginAsync

export interface RegisterRoutesOptions {
  prefix?: string
}

export interface TagDefinition {
  name: string
  description: string
}

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

function fileToTag(routesDir: string, filePath: string): TagDefinition {
  const rel = relative(routesDir, filePath)
  const parts = rel.replace(/\\/g, '/').split('/')
  const name = parts.length > 1 ? parts.slice(0, -1).join(' / ') : basename(parts[0], extname(parts[0]))
  return { name, description: `${name} 模块` }
}

async function collectRouteFiles(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true })
  const files: string[] = []

  for (const entry of entries) {
    const fullPath = join(dir, entry.name)

    if (entry.isDirectory()) {
      files.push(...(await collectRouteFiles(fullPath)))
      continue
    }

    const extension = extname(entry.name)
    const isRouteFile = ['.ts', '.js', '.cjs', '.mjs', '.cts', '.mts'].includes(extension)
    const isDeclaration = entry.name.endsWith('.d.ts')
    const isIndex = entry.name === 'index.ts' || entry.name === 'index.js'

    if (isRouteFile && !isDeclaration && !isIndex) {
      files.push(fullPath)
    }
  }

  return files
}

function extractPlugins(routeModule: unknown): FastifyPlugin[] {
  const plugins = new Set<FastifyPlugin>()

  if (typeof routeModule === 'function') {
    plugins.add(routeModule as FastifyPlugin)
  }

  if (routeModule && typeof routeModule === 'object') {
    const maybeModule = routeModule as Record<string, unknown>

    if (typeof maybeModule.default === 'function') {
      plugins.add(maybeModule.default as FastifyPlugin)
    }

    for (const [name, value] of Object.entries(maybeModule)) {
      if (name === 'default') {
        continue
      }

      const isRouteLikeName = /route(s)?$/i.test(name)
      if (isRouteLikeName && typeof value === 'function') {
        plugins.add(value as FastifyPlugin)
      }
    }
  }

  return Array.from(plugins)
}

function withTag(plugin: FastifyPlugin, tag: string): FastifyPlugin {
  const wrapped: FastifyPluginAsync = async (app, opts) => {
    app.addHook('onRoute', (routeOptions) => {
      if (!routeOptions.schema) {
        routeOptions.schema = {}
      }
      if (!routeOptions.schema.tags) {
        routeOptions.schema.tags = [tag]
      }
    })
    return plugin(app, opts)
  }
  return wrapped
}

export async function registerRoutes(
  app: FastifyInstance,
  options: RegisterRoutesOptions = {},
): Promise<TagDefinition[]> {
  const routesDir = join(__dirname, 'routes')
  const routeFiles = await collectRouteFiles(routesDir)
  const tags: TagDefinition[] = []

  for (const routeFile of routeFiles) {
    const tag = fileToTag(routesDir, routeFile)
    tags.push(tag)

    const fileUrl = pathToFileURL(routeFile).href
    const routeModule: unknown = await import(fileUrl)
    const plugins = extractPlugins(routeModule)

    if (plugins.length === 0) {
      app.log.warn({ routeFile }, 'No route plugin export found, skipped.')
      continue
    }

    for (const plugin of plugins) {
      // 读取路由文件中的 prefix 导出，如果存在则使用
      const routePrefix = (routeModule as any).prefix ?? ''
      const fullPrefix = (options.prefix ?? '/api') + routePrefix
      await app.register(withTag(plugin, tag.name), { prefix: fullPrefix })
    }
  }

  return tags
}
