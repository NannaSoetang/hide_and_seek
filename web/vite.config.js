import { defineConfig } from 'vite'
import { resolve } from 'node:path'

export default defineConfig({
  base: './',
  root: resolve(process.cwd(), 'web'),
  publicDir: resolve(process.cwd(), 'web/public'),
  build: {
    rollupOptions: {
      input: {
        main: resolve(process.cwd(), 'web/index.html'),
        print: resolve(process.cwd(), 'web/print.html'),
        whereAmI: resolve(process.cwd(), 'web/where-am-i.html'),
        guide: resolve(process.cwd(), 'web/guide.html'),
      },
    },
    outDir: resolve(process.cwd(), 'dist'),
    emptyOutDir: true,
  },
})
