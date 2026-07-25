import { chromium } from '@playwright/test'
import http from 'node:http'
import { copyFile, mkdir, readFile, stat } from 'node:fs/promises'
import { createReadStream } from 'node:fs'
import { extname, join, resolve } from 'node:path'

const distDir = resolve(process.cwd(), 'dist')
const publicPdfPath = resolve(process.cwd(), 'web/public/print-map.pdf')
const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.geojson': 'application/geo+json; charset=utf-8',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
}

function safePathFromUrl(urlPath) {
  const cleanPath = urlPath.split('?')[0]
  const relativePath = cleanPath === '/' ? 'index.html' : cleanPath.replace(/^\//, '')
  const fullPath = resolve(distDir, relativePath)
  if (!fullPath.startsWith(distDir)) {
    throw new Error('Unsafe path requested')
  }
  return fullPath
}

async function createStaticServer() {
  const server = http.createServer(async (req, res) => {
    try {
      const filePath = safePathFromUrl(req.url || '/')
      const fileInfo = await stat(filePath)
      if (fileInfo.isDirectory()) {
        res.writeHead(404)
        res.end('Not found')
        return
      }
      res.writeHead(200, {
        'Content-Type': mimeTypes[extname(filePath)] || 'application/octet-stream',
      })
      createReadStream(filePath).pipe(res)
    } catch {
      res.writeHead(404)
      res.end('Not found')
    }
  })

  await new Promise((resolvePromise) => server.listen(0, '127.0.0.1', resolvePromise))
  const address = server.address()
  if (!address || typeof address === 'string') {
    throw new Error('Could not determine local server address for PDF build')
  }
  return { server, port: address.port }
}

async function main() {
  const printHtml = join(distDir, 'print.html')
  await readFile(printHtml)
  await mkdir(resolve(process.cwd(), 'web/public'), { recursive: true })

  const { server, port } = await createStaticServer()
  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ viewport: { width: 1200, height: 1600 } })
    await page.goto(`http://127.0.0.1:${port}/print.html`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1000)
    const outputPath = join(distDir, 'print-map.pdf')
    await page.pdf({
      path: outputPath,
      format: 'A4',
      landscape: false,
      printBackground: true,
      preferCSSPageSize: true,
    })
    await copyFile(outputPath, publicPdfPath)
  } finally {
    await browser.close()
    await new Promise((resolvePromise, rejectPromise) => {
      server.close((error) => (error ? rejectPromise(error) : resolvePromise()))
    })
  }
}

await main()
