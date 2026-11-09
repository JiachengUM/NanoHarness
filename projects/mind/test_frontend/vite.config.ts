import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import svgr from 'vite-plugin-svgr'
import { createReadStream, cpSync, existsSync, mkdirSync, statSync } from 'node:fs'
import path from 'node:path'
import type { Plugin } from 'vite'

// ---------------------------------------------------------------------------
// 前端 VAD(Silero onnxruntime-web)运行资源: worklet + onnx 模型 + ort wasm。
// 自托管到 /vad/(dev 经中间件 serve, build 复制进 dist/vad/), 避免弱网下 CDN 加载失败。
// ---------------------------------------------------------------------------
const VAD_ASSET_SOURCES: Array<[src: string, name: string]> = [
  ['node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js', 'vad.worklet.bundle.min.js'],
  ['node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx', 'silero_vad_v5.onnx'],
  ['node_modules/@ricky0123/vad-web/dist/silero_vad_legacy.onnx', 'silero_vad_legacy.onnx'],
  ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm', 'ort-wasm-simd-threaded.wasm'],
  ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.mjs'],
  // .js 扩展名副本: 网关(volcalb)对 .mjs 返回 application/octet-stream, 浏览器动态 import 模块
  // 严格 MIME 检查会拦截; .js 返回 application/javascript, ort 经 wasmPaths.mjs 指向此副本
  ['node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs', 'ort-wasm-simd-threaded.js'],
]

function copyVadAssets(): Plugin {
  const root = process.cwd()
  const copyTo = (outDir: string): void => {
    for (const [src, name] of VAD_ASSET_SOURCES) {
      const from = path.join(root, src)
      if (!existsSync(from)) continue
      const to = path.join(outDir, 'vad', name)
      mkdirSync(path.dirname(to), { recursive: true })
      cpSync(from, to)
    }
  }
  return {
    name: 'copy-vad-assets',
    // configureServer 仅 dev 生效; writeBundle 仅 build 生效, 无需 apply 限定
    // 注意: build 不能用 buildStart(随后会被 emptyOutDir 清掉), 用 writeBundle 在产物写入后复制
    writeBundle() {
      copyTo(path.join(root, 'dist'))
    },
    configureServer(server) {
      // dev: /vad/* 直接读 node_modules 源文件。注意 connect 的 use(path) 会把匹配前缀
      // 从 req.url 中剥掉, 这里 req.url 形如 /silero_vad_v5.onnx(无 /vad/ 前缀)
      server.middlewares.use('/vad/', (req, res, next) => {
        const name = (req.url ?? '').split('?')[0].split('/').pop() ?? ''
        const entry = VAD_ASSET_SOURCES.find(([, n]) => n === name)
        if (!entry) {
          next()
          return
        }
        const file = path.join(root, entry[0])
        if (!existsSync(file)) {
          res.statusCode = 404
          res.end()
          return
        }
        // module 脚本严格 MIME 检查: js/mjs 必须 application/javascript, wasm 必须 application/wasm
        const mime = name.endsWith('.wasm')
          ? 'application/wasm'
          : name.endsWith('.onnx')
            ? 'application/octet-stream'
            : 'application/javascript'
        res.setHeader('Content-Type', mime)
        res.setHeader('Content-Length', statSync(file).size)
        createReadStream(file).pipe(res)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())

  return {
    plugins: [
      react(),
      svgr({ svgrOptions: { icon: true } }),
      copyVadAssets(),
    ],
    resolve: {
      alias: {
        '@': '/src',
      },
    },
    server: {
      host: '0.0.0.0',
      port: 9001,
      proxy: {
        '/api': {
          target: env.VITE_DEFAULT_API_URL,
          changeOrigin: true,
          xfwd: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/v1': {
          target: env.VITE_ADVISOR_API_URL,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/v1/, ''),
        },
        '/platform-api': {
          target: env.VITE_PLATFORM_API_URL,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/platform-api/, ''),
        },
        '/agent-arena-api': {
          target: env.VITE_AGENT_ARENA_API_URL,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/agent-arena-api/, ''),
        },
        '/legacy/api': {
          target: env.VITE_LEGACY_DEFAULT_API_URL || env.VITE_DEFAULT_API_URL,
          changeOrigin: true,
          xfwd: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/legacy\/api/, ''),
        },
        '/legacy/v1': {
          target: env.VITE_LEGACY_ADVISOR_API_URL || env.VITE_ADVISOR_API_URL,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/legacy\/v1/, ''),
        },
        '/legacy/platform-api': {
          target: env.VITE_LEGACY_PLATFORM_API_URL || env.VITE_PLATFORM_API_URL,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/legacy\/platform-api/, ''),
        },
        '/legacy/agent-arena-api': {
          target: env.VITE_LEGACY_AGENT_ARENA_API_URL || env.VITE_AGENT_ARENA_API_URL,
          changeOrigin: true,
          xfwd: true,
          rewrite: (path) => path.replace(/^\/legacy\/agent-arena-api/, ''),
        },
      },
    },
  }
})
