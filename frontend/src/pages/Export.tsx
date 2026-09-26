import { useQuery } from '@tanstack/react-query'
import { Copy, Download, Share2 } from 'lucide-react'
import { useState } from 'react'
import { fetchText } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { Empty, Spinner, useToast } from '../components/ui'
import { plural } from '../format'

export function Export() {
  const fam = useFamilyPath()
  const { me, familyId } = useAuth()
  const toast = useToast()
  const [inStock, setInStock] = useState(false)
  const { data: text, isLoading, error } = useQuery({
    queryKey: ['export', fam(''), inStock],
    queryFn: () => fetchText(fam(`/export.txt${inStock ? '?in_stock=true' : ''}`)),
  })
  const count = text ? text.split('\n').filter(Boolean).length : 0
  const familyName = me?.families.find(f => f.id === familyId)?.name ?? 'аптечка'
  // Латиница в имени: часть браузеров молча заменяет кириллическое имя blob-файла на «download».
  const filename = `cureme-lekarstva-${new Date().toLocaleDateString('sv-SE')}.txt`
  const file = () => new File([text ?? ''], filename, { type: 'text/plain;charset=utf-8' })

  const download = () => {
    const url = URL.createObjectURL(file())
    const a = document.createElement('a')
    a.href = url
    a.setAttribute('download', filename)
    document.body.append(a)
    a.click()
    setTimeout(() => { a.remove(); URL.revokeObjectURL(url) }, 1000)
  }
  const canShareFile = typeof navigator.canShare === 'function' && navigator.canShare({ files: [file()] })
  const share = async () => {
    try { await navigator.share({ files: [file()], title: filename }) } catch { /* отменили */ }
  }

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <div className="page-head">
        <div>
          <h1>Экспорт</h1>
          <p className="sub">Список лекарств текстовым файлом: название и дозировка, по одному на строку.</p>
        </div>
      </div>

      <section className="card stack">
        <div className="segmented" role="tablist">
          <button type="button" role="tab" aria-selected={!inStock} className={!inStock ? 'on' : ''} onClick={() => setInStock(false)}>Вся аптечка</button>
          <button type="button" role="tab" aria-selected={inStock} className={inStock ? 'on' : ''} onClick={() => setInStock(true)}>Только в наличии</button>
        </div>

        {isLoading ? <div className="center" style={{ minHeight: 120 }}><Spinner /></div>
          : error ? <div className="alert error">{(error as Error).message}</div>
          : count === 0 ? <Empty icon="📄" title="Список пуст" text={inStock ? 'Сейчас в наличии ничего нет.' : 'Добавьте лекарства в аптечку.'} />
          : (
            <>
              <div className="row between">
                <span className="small muted">{count} {plural(count, 'лекарство', 'лекарства', 'лекарств')}</span>
                <span className="small faint">{familyName}</span>
              </div>
              <pre className="export-preview">{text}</pre>
              <div className="row wrap">
                <button className="btn primary grow" onClick={download}><Download size={18} />Скачать .txt</button>
                {canShareFile && <button className="btn" onClick={share}><Share2 size={18} />Отправить</button>}
                <button className="btn ghost" onClick={() => navigator.clipboard.writeText(text!).then(() => toast('Список скопирован'))}><Copy size={18} />Копировать</button>
              </div>
            </>
          )}
      </section>
    </div>
  )
}
