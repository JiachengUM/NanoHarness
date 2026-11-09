import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

function findPrinciplesFile(filename: string): string {
  const distPath = join(__dirname, filename)

  try {
    readFileSync(distPath, 'utf-8')
    return distPath
  } catch {
    console.log('原则文件在dist中未找到:', distPath)
  }

  const srcPath = __dirname.replace(/[/\\]dist[/\\]/, '/src/')
  const fallbackPath = join(srcPath, filename)

  try {
    readFileSync(fallbackPath, 'utf-8')
    return fallbackPath
  } catch {
    console.log('原则文件在src中未找到:', fallbackPath)
  }

  throw new Error(
    `原则文件未找到: ${distPath}\n` +
      `也未在源码目录找到: ${fallbackPath}\n` +
      `请确保 ${filename} 存在于 principles 目录中。`,
  )
}

export async function loadWritingPrinciples(): Promise<string> {
  const filePath = findPrinciplesFile('writing.md')
  return readFileSync(filePath, 'utf-8')
}

export async function loadAuditPrinciples(): Promise<string> {
  const filePath = findPrinciplesFile('audit.md')
  return readFileSync(filePath, 'utf-8')
}

export async function loadCompositeSkill(): Promise<string> {
  const filePath = findPrinciplesFile('composite-skill.md')
  return readFileSync(filePath, 'utf-8')
}

export async function loadAuditSupplements(): Promise<string> {
  try {
    const filePath = findPrinciplesFile('audit-supplements.md')
    return readFileSync(filePath, 'utf-8')
  } catch {
    return ''
  }
}

/**
 * 加载关键约束（精简版，用于生成和审核阶段强制执行）
 */
export async function loadKeyConstraints(): Promise<string> {
  try {
    const filePath = findPrinciplesFile('key-constraints.md')
    return readFileSync(filePath, 'utf-8')
  } catch {
    // 如果文件不存在，返回空字符串，不阻塞流程
    console.warn('关键约束文件未找到，将使用完整原则')
    return ''
  }
}
