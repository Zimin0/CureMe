import { useMutation, useQuery } from '@tanstack/react-query'
import { FormEvent, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, Family, Me } from '../api'
import { useAuth } from '../auth'
import { DeleteAccountButton } from '../components/DeleteAccount'
import { PageLoader, useToast } from '../components/ui'
import { OPERATOR } from '../legal'
import { LegalLinks } from './Legal'

type TokenOut = { access_token: string; user: Me }

function AuthShell({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card stack lg">
        <div className="stack" style={{ gap: 6, textAlign: 'center' }}>
          <div className="brand"><img src="/icon.svg" alt="" />Капсулка</div>
          <h1 style={{ fontSize: 24 }}>{title}</h1>
          <p className="muted">{sub}</p>
        </div>
        <div className="card stack">{children}</div>
        <LegalLinks />
      </div>
    </div>
  )
}

/** Закрыт ли сайт для всех, кроме участников теста (переключается в админке). */
function useSiteClosed() {
  const q = useQuery({ queryKey: ['access'], queryFn: () => api<{ closed: boolean }>('/auth/access'), staleTime: 60_000 })
  return q.data?.closed ?? false
}

/** Объяснение для закрытого режима: что происходит и куда писать, в том числе чтобы удалить свои данные. */
function ClosedNote() {
  return (
    <div className="alert info">
      <span>
        Капсулка пока открыта только для тестирования. Вопросы, предложения и просьбы удалить свои данные
        присылайте на <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a> ({OPERATOR.name}).
      </span>
    </div>
  )
}

export function Login() {
  const closed = useSiteClosed()
  const { signIn } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const m = useMutation({
    mutationFn: () => api<TokenOut>('/auth/login', { body: { email, password } }),
    onSuccess: d => { signIn(d.access_token, d.user); nav(params.get('next') ?? '/') },
  })
  const submit = (e: FormEvent) => { e.preventDefault(); m.mutate() }
  return (
    <AuthShell title={closed ? 'Сайт в разработке' : 'С возвращением'} sub="Лекарства всей семьи в одном месте">
      {closed && <ClosedNote />}
      {closed && <div className="divider">вход для участников теста</div>}
      <form className="stack" onSubmit={submit}>
        <label className="field"><span>Почта</span>
          <input className="input" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} />
        </label>
        <label className="field"><span>Пароль</span>
          <input className="input" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
        </label>
        {m.error && <div className="alert error">{m.error.message}</div>}
        <button className="btn primary block" disabled={m.isPending}>{m.isPending ? 'Входим…' : 'Войти'}</button>
      </form>
      {!closed && <div className="divider">нет аккаунта?</div>}
      {!closed && <Link className="btn ghost block" to={`/register${params.get('next') ? `?next=${encodeURIComponent(params.get('next')!)}` : ''}`}>Зарегистрироваться</Link>}
    </AuthShell>
  )
}

export function Register() {
  const closed = useSiteClosed()
  if (closed) {
    return (
      <AuthShell title="Сайт в разработке" sub="Регистрация пока закрыта">
        <ClosedNote />
        <Link className="btn ghost block" to="/login">Вход для участников теста</Link>
      </AuthShell>
    )
  }
  return <RegisterForm />
}

function RegisterForm() {
  const { signIn } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const invite = params.get('invite') ?? ''
  const [form, setForm] = useState({ name: '', email: '', password: '', invite_code: invite })
  const [agreed, setAgreed] = useState({ consent: false, terms: false })
  const inviteInfo = useQuery({
    queryKey: ['invite', form.invite_code],
    queryFn: () => api<{ family_name: string; members: number }>(`/invites/${form.invite_code.trim()}`),
    enabled: form.invite_code.trim().length >= 6,
    retry: false,
  })
  const m = useMutation({
    mutationFn: () => api<TokenOut>('/auth/register', { body: { ...form, invite_code: form.invite_code.trim() || null, consent: agreed.consent } }),
    onSuccess: d => { signIn(d.access_token, d.user); nav('/') },
  })
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value })
  return (
    <AuthShell
      title={inviteInfo.data ? `Вступить в «${inviteInfo.data.family_name}»` : 'Новый аккаунт'}
      sub={inviteInfo.data ? 'После регистрации вы увидите общую аптечку семьи' : 'Мы создадим аптечку для вашей семьи'}
    >
      <form className="stack" onSubmit={e => { e.preventDefault(); m.mutate() }}>
        <label className="field"><span>Как вас зовут</span>
          <input className="input" required autoComplete="given-name" value={form.name} onChange={set('name')} placeholder="Например, Мама" />
        </label>
        <label className="field"><span>Почта</span>
          <input className="input" type="email" required autoComplete="email" value={form.email} onChange={set('email')} />
        </label>
        <label className="field"><span>Пароль</span>
          <input className="input" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set('password')} />
          <span className="hint">Не короче 8 символов</span>
        </label>
        <label className="field"><span>Код приглашения в семью</span>
          <input className="input" value={form.invite_code} onChange={set('invite_code')} placeholder="Необязательно" style={{ textTransform: 'uppercase' }} />
          {inviteInfo.isError && <span className="hint" style={{ color: 'var(--danger)' }}>Такого кода нет</span>}
          {!form.invite_code && <span className="hint">Если вас позвали в семью, введите код из приглашения</span>}
        </label>
        <ConsentChecks value={agreed} onChange={setAgreed} />
        {m.error && <div className="alert error">{m.error.message}</div>}
        <button className="btn primary block" disabled={m.isPending}>{m.isPending ? 'Создаём…' : 'Создать аккаунт'}</button>
      </form>
      <div className="divider">уже есть аккаунт?</div>
      <Link className="btn ghost block" to="/login">Войти</Link>
    </AuthShell>
  )
}

/** Ссылка-приглашение /join/:code — работает и для новых, и для уже вошедших. */
export function Join() {
  const closed = useSiteClosed()
  const { code = '' } = useParams()
  const { me, refresh, setFamilyId } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const info = useQuery({
    queryKey: ['invite', code],
    queryFn: () => api<{ family_name: string; members: number }>(`/invites/${code}`),
    retry: false,
  })
  const join = useMutation({
    mutationFn: () => api<Family>('/families/join', { body: { code } }),
    onSuccess: async f => { await refresh(); setFamilyId(f.id); toast(`Вы в семье «${f.name}»`); nav('/') },
  })
  if (info.isLoading) return <PageLoader />
  if (info.isError) {
    return <AuthShell title="Приглашение не найдено" sub="Возможно, код обновили. Попросите новую ссылку."><Link className="btn primary block" to="/">На главную</Link></AuthShell>
  }
  const fam = info.data!
  return (
    <AuthShell title={`Приглашение в «${fam.family_name}»`} sub={`В семье уже ${fam.members} чел. Вы получите доступ к общей аптечке.`}>
      {me ? (
        <>
          {join.error && <div className="alert error">{join.error.message}</div>}
          <button className="btn primary block" onClick={() => join.mutate()} disabled={join.isPending}>Вступить как {me.name}</button>
        </>
      ) : (
        <>
          {closed ? <ClosedNote /> : <Link className="btn primary block" to={`/register?invite=${code}`}>Создать аккаунт и вступить</Link>}
          <Link className="btn ghost block" to={`/login?next=/join/${code}`}>У меня уже есть аккаунт</Link>
        </>
      )}
    </AuthShell>
  )
}

type Agreed = { consent: boolean; terms: boolean }

/**
 * Две отдельные галочки, обе пустые по умолчанию: согласие на обработку данных по 152-ФЗ
 * нельзя смешивать с другими документами и нельзя ставить за человека.
 */
function ConsentChecks({ value, onChange }: { value: Agreed; onChange: (v: Agreed) => void }) {
  return (
    <div className="stack" style={{ gap: 10 }}>
      <label className="check">
        <input type="checkbox" required checked={value.consent} onChange={e => onChange({ ...value, consent: e.target.checked })} />
        <span>Даю <Link to="/consent" target="_blank">согласие на обработку персональных данных</Link>, включая сведения о здоровье</span>
      </label>
      <label className="check">
        <input type="checkbox" required checked={value.terms} onChange={e => onChange({ ...value, terms: e.target.checked })} />
        <span>Принимаю <Link to="/terms" target="_blank">пользовательское соглашение</Link> и понимаю, что Капсулка не заменяет врача</span>
      </label>
    </div>
  )
}

/** Для тех, кто зарегистрировался до появления согласия или когда его текст поменялся. */
export function ConsentGate() {
  const { refresh, signOut } = useAuth()
  const [agreed, setAgreed] = useState({ consent: false, terms: false })
  const m = useMutation({
    mutationFn: () => api<Me>('/auth/consent', { body: { consent: true } }),
    onSuccess: () => refresh(),
  })
  return (
    <AuthShell title="Нужно ваше согласие" sub="Мы обновили документы: теперь согласие на обработку данных оформляется отдельно, как требует закон">
      <form className="stack" onSubmit={e => { e.preventDefault(); m.mutate() }}>
        <ConsentChecks value={agreed} onChange={setAgreed} />
        {m.error && <div className="alert error">{m.error.message}</div>}
        <button className="btn primary block" disabled={m.isPending}>Продолжить</button>
      </form>
      <div className="divider">не согласны?</div>
      <DeleteAccountButton className="btn ghost block" />
      <button className="btn ghost block" onClick={signOut}>Выйти</button>
    </AuthShell>
  )
}

/** Вошёл человек, которого нет среди участников теста: аптечка закрыта, но данные можно удалить. */
export function ClosedGate() {
  const { signOut } = useAuth()
  return (
    <AuthShell title="Сайт в разработке" sub="Ваш аккаунт сохранён, но пока сайт открыт только участникам теста">
      <ClosedNote />
      <DeleteAccountButton className="btn ghost block" />
      <button className="btn ghost block" onClick={signOut}>Выйти</button>
    </AuthShell>
  )
}
