import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, MoveResult } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { plural } from '../format'
import { Sheet, useToast } from './ui'

const cards = (n: number) => `${n} ${plural(n, 'лекарство', 'лекарства', 'лекарств')}`

function useAfterMove(onDone: () => void) {
  const { refresh } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  return {
    done: async (text: string) => {
      await refresh()
      qc.invalidateQueries({ queryKey: ['medicines'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
      qc.invalidateQueries({ queryKey: ['plan'] })
      toast(text)
      onDone()
    },
    fail: (e: Error) => toast(e.message, 'error'),
  }
}

/** Перенос выбранных лекарств в другую аптечку семьи (R17). Одинаковые по штрихкоду сливаются в одну карточку. */
export function MoveSheet({ ids, onClose, onDone }: { ids: number[]; onClose: () => void; onDone: () => void }) {
  const { me, familyId } = useAuth()
  const fam = useFamilyPath()
  const targets = (me?.families ?? []).filter(f => f.id !== familyId && f.status !== 'frozen')
  const [to, setTo] = useState<number | ''>(targets[0]?.id ?? '')
  const after = useAfterMove(onDone)
  const move = useMutation({
    mutationFn: () => api<MoveResult>(fam('/medicines/move'), { body: { to_family_id: to, medicine_ids: ids } }),
    onSuccess: r => after.done(`Перенесено: ${cards(r.moved)}${r.merged ? `, из них слито с такими же: ${r.merged}` : ''}`),
    onError: after.fail,
  })
  return (
    <Sheet title="Перенести в другую аптечку" onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); if (to !== '') move.mutate() }}>
        <p className="muted small">Выбрано: {cards(ids.length)}. Упаковки, приёмы и расписание переезжают вместе с лекарством. Если в той аптечке уже есть такое же лекарство с тем же штрихкодом, карточки сольются в одну.</p>
        {targets.length === 0
          ? <p role="note" className="alert info">Других активных аптечек в семье нет. Создайте новую на странице «Семья» или разделите эту.</p>
          : (
            <label className="field"><span>Куда перенести</span>
              <select className="input" value={to} onChange={e => setTo(Number(e.target.value))}>
                {targets.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
            </label>
          )}
        <button className="btn primary block" disabled={move.isPending || to === ''}>Перенести</button>
      </form>
    </Sheet>
  )
}

/** Выбранные лекарства уходят в новую аптечку семьи (R18). Новая аптечка занимает слот: в бесплатной версии аптечек столько, сколько людей. */
export function SplitSheet({ ids, onClose, onDone }: { ids: number[]; onClose: () => void; onDone: () => void }) {
  const fam = useFamilyPath()
  const [name, setName] = useState('')
  const after = useAfterMove(onDone)
  const split = useMutation({
    mutationFn: () => api<MoveResult>(fam('/split'), { body: { name: name.trim(), medicine_ids: ids } }),
    onSuccess: r => after.done(`Новая аптечка «${name.trim()}»: ${cards(r.moved)}`),
    // 402 (нет места под новую аптечку) сам открывает шторку Плюса.
    onError: (e: Error & { status?: number }) => { if (e.status !== 402) after.fail(e) },
  })
  return (
    <Sheet title="Новая аптечка из выбранного" onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); if (name.trim()) split.mutate() }}>
        <p className="muted small">Выбрано: {cards(ids.length)}. Они уйдут из этой аптечки в новую; доступ к ней получит вся семья.</p>
        <label className="field"><span>Название новой аптечки</span>
          <input className="input" required maxLength={100} placeholder="Например: Дача" value={name} onChange={e => setName(e.target.value)} />
        </label>
        <button className="btn primary block" disabled={split.isPending || !name.trim()}>Создать и перенести</button>
      </form>
    </Sheet>
  )
}
