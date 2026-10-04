import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MapPin, Plus, Trash2 } from 'lucide-react'
import { PointerEvent, useRef, useState } from 'react'
import { api, Medicine, MedicineDetail, Shelf, ShelfPlan } from '../api'
import { useFamilyPath } from '../auth'
import { Sheet, useToast } from './ui'

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

export function usePlan(enabled = true) {
  const fam = useFamilyPath()
  return useQuery({ queryKey: ['shelf-plan', fam('')], queryFn: () => api<ShelfPlan>(fam('/shelf-plan')), enabled })
}

/** Полка, в которую попал центр круга (для подписи «Верхняя полка»). */
export function shelfAt(plan: ShelfPlan | undefined, x: number, y: number): Shelf | undefined {
  const hit = (s: Shelf) => x >= s.x && x <= s.x + s.w && y >= s.y && y <= s.y + s.h
  const hits = plan?.shelves.filter(hit) ?? []
  return hits.find(s => s.kind === 'box') ?? hits[0]
}

interface MapProps {
  plan: ShelfPlan
  place?: { x: number; y: number; r: number } | null
  width?: number | string
  onPoint?: (x: number, y: number) => void
  onShelfDown?: (id: string, e: PointerEvent<SVGGElement>) => void
  selected?: string | null
  labels?: boolean
}

/** Схема аптечки: прямоугольники полок и круг «здесь лежит». Координаты в долях ширины от 0 до 1. */
export function ShelfMap({ plan, place, width = '100%', onPoint, onShelfDown, selected, labels = true }: MapProps) {
  const ref = useRef<SVGSVGElement>(null)
  const h = plan.height
  const toPoint = (e: PointerEvent<SVGSVGElement>) => {
    const r = ref.current!.getBoundingClientRect()
    onPoint?.(clamp((e.clientX - r.left) / r.width, 0, 1), clamp((e.clientY - r.top) / r.height * h, 0, h))
  }
  return (
    <svg ref={ref} viewBox={`0 0 1 ${h}`} style={{ width, display: 'block', touchAction: onPoint ? 'none' : undefined, cursor: onPoint ? 'crosshair' : undefined }}
      role="img" aria-label="Схема аптечки" onPointerDown={onPoint ? toPoint : undefined}>
      <rect x={0.002} y={0.002} width={0.996} height={h - 0.004} rx={0.02} fill="var(--surface-2, #f4f6f5)" stroke="var(--border, #cfd8d5)" strokeWidth={0.004} />
      {[...plan.shelves].sort((a, b) => Number(a.kind === 'box') - Number(b.kind === 'box')).map(s => {
        const box = s.kind === 'box'
        const fs = box ? 0.03 : 0.032
        const shown = s.name.length > (box ? Math.floor(s.w / 0.018) : 40) ? s.name.slice(0, Math.max(3, Math.floor(s.w / 0.018) - 1)) + '…' : s.name
        return (
          <g key={s.id} onPointerDown={onShelfDown ? e => onShelfDown(s.id, e) : undefined} style={{ cursor: onShelfDown ? 'move' : undefined }}>
            <rect x={s.x} y={s.y} width={s.w} height={s.h} rx={box ? 0.02 : 0.012}
              style={{ fill: box ? 'var(--primary-soft, #e3f5f1)' : 'var(--surface, #fff)', stroke: selected === s.id ? 'var(--primary, #0f9d8a)' : box ? 'var(--primary, #0f9d8a)' : 'var(--border, #cfd8d5)' }}
              strokeWidth={selected === s.id ? 0.008 : 0.004} />
            {labels && shown && (box
              ? <text x={s.x + s.w / 2} y={s.y + s.h / 2} fontSize={fs} fontWeight={600} textAnchor="middle" dominantBaseline="central"
                  style={{ fill: 'var(--primary-strong, #0b7f70)', pointerEvents: 'none', userSelect: 'none' }}>{shown}</text>
              : <g style={{ pointerEvents: 'none' }}>
                  <rect x={s.x + 0.012} y={s.y + 0.012} width={Math.min(s.w - 0.024, shown.length * 0.0185 + 0.03)} height={0.05} rx={0.025}
                    style={{ fill: 'var(--surface-2, #f4f6f5)', stroke: 'var(--border, #cfd8d5)' }} strokeWidth={0.003} />
                  <text x={s.x + 0.027} y={s.y + 0.037} fontSize={fs} fontWeight={600} dominantBaseline="central"
                    style={{ fill: 'var(--muted, #6b7a76)', userSelect: 'none' }}>{shown}</text>
                </g>)}
          </g>
        )
      })}
      {place && <circle cx={place.x} cy={place.y} r={place.r} fill="rgba(15,157,138,.25)" strokeWidth={0.008} style={{ stroke: 'var(--primary, #0f9d8a)', pointerEvents: 'none' }} />}
      {place && <circle cx={place.x} cy={place.y} r={0.008} style={{ fill: 'var(--primary, #0f9d8a)', pointerEvents: 'none' }} />}
    </svg>
  )
}

/** Маленькая схема в списке и карточке; без схемы ничего не рисуем. */
export function MiniPlace({ m }: { m: Pick<Medicine, 'place_x' | 'place_y' | 'place_r'> }) {
  return m.place_x != null && m.place_y != null && m.place_r != null ? <MiniPlaceInner m={m} /> : null
}

function MiniPlaceInner({ m }: { m: Pick<Medicine, 'place_x' | 'place_y' | 'place_r'> }) {
  const { data: plan } = usePlan()
  if (!plan) return null
  const shelf = shelfAt(plan, m.place_x!, m.place_y!)
  return (
    <div className="row" style={{ gap: 6, marginTop: 4 }} title={shelf?.name ? `Лежит: ${shelf.name}` : 'Место на схеме'}>
      <div style={{ width: 54, flex: 'none' }}>
        <ShelfMap plan={plan} place={{ x: m.place_x!, y: m.place_y!, r: m.place_r! }} labels={false} />
      </div>
      {shelf?.name && <span className="faint small ellipsis"><MapPin size={11} style={{ verticalAlign: -1 }} /> {shelf.name}</span>}
    </div>
  )
}

/** «Где лежит»: тап по схеме ставит точку, ползунок задаёт радиус. */
export function PlaceSheet({ m, onClose, onSaved, onEditPlan }: {
  m: MedicineDetail; onClose: () => void; onSaved: (d: MedicineDetail) => void; onEditPlan: () => void
}) {
  const fam = useFamilyPath()
  const toast = useToast()
  const { data: plan } = usePlan()
  const [pt, setPt] = useState<{ x: number; y: number; r: number } | null>(
    m.place_x != null && m.place_y != null && m.place_r != null ? { x: m.place_x, y: m.place_y, r: m.place_r } : null,
  )
  const save = useMutation({
    mutationFn: (p: { x: number; y: number; r: number } | null) => api<MedicineDetail>(fam(`/medicines/${m.id}`), {
      method: 'PATCH', body: { place_x: p?.x ?? null, place_y: p?.y ?? null, place_r: p?.r ?? null },
    }),
    onSuccess: d => { onSaved(d); onClose() }, onError: (e: Error) => toast(e.message, 'error'),
  })
  return (
    <Sheet title="Где лежит" onClose={onClose}>
      {!plan ? null : plan.shelves.length === 0 ? (
        <div className="stack">
          <p className="muted">Сначала нарисуйте схему аптечки: полки и ящики. Потом на ней отмечается место каждого лекарства.</p>
          <button className="btn primary block" onClick={onEditPlan}>Нарисовать схему</button>
        </div>
      ) : (
        <div className="stack">
          <p className="muted small">Нажмите на схему там, где лежит «{m.name}», и выберите размер круга.</p>
          <ShelfMap plan={plan} place={pt} onPoint={(x, y) => setPt(p => ({ x, y, r: p?.r ?? 0.08 }))} />
          <label className="small">Размер круга
            <input type="range" min={0.03} max={0.3} step={0.01} disabled={!pt} value={pt?.r ?? 0.08}
              onChange={e => setPt(p => p && { ...p, r: Number(e.target.value) })} style={{ width: '100%' }} />
          </label>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn primary grow" disabled={!pt || save.isPending} onClick={() => save.mutate(pt)}>Сохранить</button>
            {m.place_x != null && <button className="btn ghost" disabled={save.isPending} onClick={() => save.mutate(null)}>Убрать метку</button>}
          </div>
          <button className="btn ghost sm" onClick={onEditPlan}>Изменить схему аптечки</button>
        </div>
      )}
    </Sheet>
  )
}

const PRESET: Shelf[] = [0, 1, 2].map(i => ({ id: `s${i + 1}`, name: `${i + 1}-я полка`, x: 0.04, y: 0.04 + i * 0.31, w: 0.92, h: 0.27 }))

/** Редактор схемы: добавить полку, назвать, перетащить, поменять размер. */
export function PlanEditor({ onClose }: { onClose: () => void }) {
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: plan } = usePlan()
  const [draft, setDraft] = useState<ShelfPlan | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const drag = useRef<{ id: string; dx: number; dy: number } | null>(null)
  const cur = draft ?? plan
  const save = useMutation({
    mutationFn: (p: ShelfPlan) => api<ShelfPlan>(fam('/shelf-plan'), { method: 'PUT', body: p }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['shelf-plan'] }); toast('Схема сохранена'); onClose() },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  if (!cur) return <Sheet title="Схема аптечки" onClose={onClose}><p className="muted">Загрузка…</p></Sheet>
  const edit = (f: (p: ShelfPlan) => ShelfPlan) => setDraft(f(cur))
  const patch = (id: string, c: Partial<Shelf>) => edit(p => ({ ...p, shelves: p.shelves.map(s => s.id === id ? { ...s, ...c } : s) }))
  const shelf = cur.shelves.find(s => s.id === sel)
  const add = (kind: 'shelf' | 'box' = 'shelf') => {
    const id = `s${Date.now().toString(36)}`
    const box = kind === 'box'
    edit(p => ({ ...p, shelves: [...p.shelves, { id, name: '', kind, x: box ? 0.2 : 0.1, y: box ? 0.1 : 0.1, w: box ? 0.28 : 0.4, h: box ? 0.14 : 0.2 }] }))
    setSel(id)
  }
  const down = (id: string, e: PointerEvent<SVGGElement>) => {
    const svg = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
    const s = cur.shelves.find(x => x.id === id)!
    drag.current = { id, dx: (e.clientX - svg.left) / svg.width - s.x, dy: (e.clientY - svg.top) / svg.width - s.y }
    setSel(id)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current
    if (!d) return
    const svg = e.currentTarget.querySelector('svg')!.getBoundingClientRect()
    const s = cur.shelves.find(x => x.id === d.id)!
    patch(d.id, {
      x: clamp((e.clientX - svg.left) / svg.width - d.dx, 0, 1 - s.w),
      y: clamp((e.clientY - svg.top) / svg.width - d.dy, 0, cur.height - s.h),
    })
  }
  return (
    <Sheet title="Схема аптечки" onClose={onClose}>
      <div className="stack">
        <p className="muted small">Нарисуйте шкаф: полки, а на них контейнеры с подписями. Перетаскивайте прямоугольники, размер и название меняются ниже.</p>
        <div onPointerMove={move} onPointerUp={() => { drag.current = null }} style={{ touchAction: 'none' }}>
          <ShelfMap plan={cur} selected={sel} onShelfDown={down} />
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn sm" onClick={() => add('shelf')} disabled={cur.shelves.length >= 30}><Plus size={15} />Полка</button>
          <button className="btn sm" onClick={() => add('box')} disabled={cur.shelves.length >= 30}><Plus size={15} />Контейнер</button>
          {cur.shelves.length === 0 && <button className="btn ghost sm" onClick={() => edit(p => ({ ...p, shelves: PRESET, height: 1 }))}>Шкаф с 3 полками</button>}
        </div>
        {shelf && (
          <div className="stack" style={{ gap: 6 }}>
            <input value={shelf.name} maxLength={60} placeholder={shelf.kind === 'box' ? 'Название, например «Таблетки»' : 'Название, например «Верхняя полка»'} onChange={e => patch(shelf.id, { name: e.target.value })} />
            <label className="small">Ширина
              <input type="range" min={0.1} max={1} step={0.01} value={shelf.w} style={{ width: '100%' }}
                onChange={e => patch(shelf.id, { w: Number(e.target.value), x: clamp(shelf.x, 0, 1 - Number(e.target.value)) })} /></label>
            <label className="small">Высота
              <input type="range" min={0.05} max={cur.height} step={0.01} value={shelf.h} style={{ width: '100%' }}
                onChange={e => patch(shelf.id, { h: Number(e.target.value), y: clamp(shelf.y, 0, cur.height - Number(e.target.value)) })} /></label>
            <button className="btn ghost sm danger" onClick={() => { edit(p => ({ ...p, shelves: p.shelves.filter(s => s.id !== shelf.id) })); setSel(null) }}>
              <Trash2 size={15} />{shelf.kind === 'box' ? 'Удалить контейнер' : 'Удалить полку'}</button>
          </div>
        )}
        <button className="btn primary block" disabled={!draft || save.isPending} onClick={() => save.mutate(cur)}>Сохранить схему</button>
      </div>
    </Sheet>
  )
}
