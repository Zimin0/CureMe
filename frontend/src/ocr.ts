import type { Worker } from 'tesseract.js'

let workerPromise: Promise<Worker> | null = null
let progressCb: ((p: number) => void) | undefined

/** Движок распознавания грузится только при первом фото срока (~7 МБ), дальше берётся из кеша. */
async function getWorker(): Promise<Worker> {
  if (!workerPromise) {
    workerPromise = (async () => {
      const { createWorker, OEM } = await import('tesseract.js')
      const worker = await createWorker('eng', OEM.LSTM_ONLY, {
        workerPath: '/ocr/worker.min.js',
        corePath: '/ocr/',
        langPath: '/ocr/',
        gzip: true,
        logger: m => { if (m.status === 'recognizing text') progressCb?.(m.progress) },
      })
      return worker
    })()
    workerPromise.catch(() => { workerPromise = null })
  }
  return workerPromise
}

/**
 * Готовим снимок для OCR: крупнее, в оттенках серого и с растянутым контрастом.
 * Срок годности на коробке часто выдавлен или напечатан бледной краской.
 */
async function prepare(file: Blob, binarize = false): Promise<HTMLCanvasElement> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(3, 2000 / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const ctx = canvas.getContext('2d', { willReadFrequently: true })!
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  bitmap.close()
  const img = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const d = img.data
  let min = 255, max = 0
  for (let i = 0; i < d.length; i += 4) {
    const g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]
    d[i] = g
    if (g < min) min = g
    if (g > max) max = g
  }
  const k = 255 / Math.max(1, max - min)
  for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = (d[i] - min) * k
  if (binarize) {
    const t = otsu(d)
    for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = d[i] > t ? 255 : 0
  }
  ctx.putImageData(img, 0, 0)
  return canvas
}

/** Порог Оцу: делит пиксели на «текст» и «фон» так, чтобы две группы различались сильнее всего. */
function otsu(d: Uint8ClampedArray): number {
  const hist = new Array(256).fill(0)
  for (let i = 0; i < d.length; i += 4) hist[d[i] | 0]++
  const total = d.length / 4
  let sum = 0
  for (let i = 0; i < 256; i++) sum += i * hist[i]
  let sumB = 0, wB = 0, best = 0, threshold = 127
  for (let t = 0; t < 256; t++) {
    wB += hist[t]
    if (!wB) continue
    const wF = total - wB
    if (!wF) break
    sumB += t * hist[t]
    const mB = sumB / wB, mF = (sum - sumB) / wF
    const between = wB * wF * (mB - mF) ** 2
    if (between > best) { best = between; threshold = t }
  }
  return threshold
}

/**
 * Распознаёт текст на фото. Если в первом проходе нет того, что нужно (`good`),
 * пробуем ещё раз по чёрно-белой версии снимка и с разбором всей страницы блоками.
 */
export async function recognizeText(file: Blob, onProgress?: (p: number) => void, good?: (text: string) => boolean): Promise<string> {
  const { PSM } = await import('tesseract.js')
  const [worker, canvas] = await Promise.all([getWorker(), prepare(file)])
  const twoPass = !!good
  progressCb = p => onProgress?.(twoPass ? p / 2 : p)
  await worker.setParameters({ tessedit_pageseg_mode: PSM.SPARSE_TEXT })
  const first = (await worker.recognize(canvas)).data.text
  if (!good || good(first)) { onProgress?.(1); return first }

  progressCb = p => onProgress?.(0.5 + p / 2)
  await worker.setParameters({ tessedit_pageseg_mode: PSM.AUTO })
  const second = (await worker.recognize(await prepare(file, true))).data.text
  return `${first}\n${second}`
}
