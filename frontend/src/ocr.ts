import type { Worker } from 'tesseract.js'

let workerPromise: Promise<Worker> | null = null

/** Движок распознавания грузится только при первом фото срока (~7 МБ), дальше берётся из кеша. */
async function getWorker(onProgress?: (p: number) => void): Promise<Worker> {
  if (!workerPromise) {
    workerPromise = (async () => {
      const { createWorker, OEM, PSM } = await import('tesseract.js')
      const worker = await createWorker('eng', OEM.LSTM_ONLY, {
        workerPath: '/ocr/worker.min.js',
        corePath: '/ocr/',
        langPath: '/ocr/',
        gzip: true,
        logger: m => { if (m.status === 'recognizing text') onProgress?.(m.progress) },
      })
      // Нужны только цифры, разделители и буквы слов «EXP/ГОДЕН ДО» и названий месяцев.
      await worker.setParameters({ tessedit_pageseg_mode: PSM.SPARSE_TEXT })
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
async function prepare(file: Blob): Promise<HTMLCanvasElement> {
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
  ctx.putImageData(img, 0, 0)
  return canvas
}

export async function recognizeText(file: Blob, onProgress?: (p: number) => void): Promise<string> {
  const [worker, canvas] = await Promise.all([getWorker(onProgress), prepare(file)])
  const { data } = await worker.recognize(canvas)
  return data.text
}
