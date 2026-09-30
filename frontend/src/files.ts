export function saveFile(file: File) {
  const url = URL.createObjectURL(file)
  const a = document.createElement('a')
  a.href = url
  a.setAttribute('download', file.name)
  document.body.append(a)
  a.click()
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url) }, 1000)
}
export const canShare = (file: File) => typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] })
export async function shareFile(file: File) {
  try { await navigator.share({ files: [file], title: file.name }) } catch { /* отменили */ }
}
