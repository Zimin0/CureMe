import { useMutation, useQuery } from '@tanstack/react-query'
import { MailCheck } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, InviteInfo, Me } from '../api'
import { CooldownNote, JoinError, useJoinFamily } from '../join'
import { useAuth } from '../auth'
import { DeleteAccountButton } from '../components/DeleteAccount'
import { PageLoader, useToast } from '../components/ui'
import { OPERATOR } from '../legal'
import { safeNext } from '../redirect'
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
  const q = useQuery({ queryKey: ['access'], queryFn: () => api<{ closed: boolean; debug?: boolean }>('/auth/access'), staleTime: 60_000 })
  return q.data?.closed ?? false
}

/** Объяснение для закрытого режима: что происходит и куда писать, в том числе чтобы удалить свои данные. */
function ClosedNote() {
  return (
    <div className="alert info">
      <span>
        Капсулка пока открыта только для тестирования. Вопросы, предложения и просьбы удалить свои данные
        присылайте на <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>.
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
    onSuccess: d => { signIn(d.access_token, d.user); nav(safeNext(params.get('next'))) },
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
        <Link className="muted small" style={{ textAlign: 'center' }} to="/reset-password">Забыли пароль?</Link>
      </form>
      {!closed && <div className="divider">нет аккаунта?</div>}
      {!closed && <Link className="btn ghost block" to={`/register${params.get('next') ? `?next=${encodeURIComponent(params.get('next')!)}` : ''}`}>Зарегистрироваться</Link>}
    </AuthShell>
  )
}

/** Восстановление пароля: сначала почта, потом код из письма и новый пароль. В письме нет ссылки, только код. */
export function ResetPassword() {
  const nav = useNavigate()
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [step, setStep] = useState<'ask' | 'confirm'>('ask')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const ask = useMutation({
    mutationFn: () => api('/auth/password-reset/request', { body: { email } }),
    onSuccess: () => setStep('confirm'),
  })
  const confirm = useMutation({
    mutationFn: () => api('/auth/password-reset/confirm', { body: { email, code, password } }),
    onSuccess: () => { toast('Пароль изменён, войдите с новым'); nav('/login') },
  })
  return (
    <AuthShell title="Восстановление пароля" sub={step === 'ask' ? 'Пришлём код на почту' : 'Введите код из письма и новый пароль'}>
      {step === 'ask' ? (
        <form className="stack" onSubmit={e => { e.preventDefault(); ask.mutate() }}>
          <label className="field"><span>Почта</span>
            <input className="input" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} />
          </label>
          {ask.error && <div className="alert error">{ask.error.message}</div>}
          <button className="btn primary block" disabled={ask.isPending}>{ask.isPending ? 'Отправляем…' : 'Прислать код'}</button>
        </form>
      ) : (
        <form className="stack" onSubmit={e => { e.preventDefault(); confirm.mutate() }}>
          <div className="alert info"><MailCheck size={18} style={{ flexShrink: 0 }} /><span>Если аккаунт с почтой <b>{email}</b> есть, мы отправили на неё код. Он действует 30 минут. Проверьте папку «Спам».</span></div>
          <label className="field"><span>Код из письма</span>
            <input value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={8} placeholder="00000000"
              style={{ fontSize: 24, letterSpacing: 6, textAlign: 'center' }}
              onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 8))} />
          </label>
          <label className="field"><span>Новый пароль</span>
            <input className="input" type="password" required minLength={12} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
            <span className="hint">Не короче 12 символов (администратору 16). Лучше фраза из нескольких слов</span>
          </label>
          {confirm.error && <div className="alert error">{confirm.error.message}</div>}
          <button className="btn primary block" disabled={code.length !== 8 || confirm.isPending}>{confirm.isPending ? 'Меняем…' : 'Сменить пароль'}</button>
          <button type="button" className="btn ghost block" onClick={() => { setStep('ask'); setCode('') }}>Отправить код ещё раз</button>
        </form>
      )}
      <Link className="btn ghost block" to="/login">Назад ко входу</Link>
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
    queryFn: () => api<InviteInfo>(`/invites/${form.invite_code.trim()}`),
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
          <input className="input" type="password" required minLength={12} autoComplete="new-password" value={form.password} onChange={set('password')} />
          <span className="hint">Не короче 12 символов. Лучше фраза из нескольких слов: её легко помнить и трудно подобрать</span>
        </label>
        <label className="field"><span>Код приглашения в семью</span>
          <input className="input" value={form.invite_code} onChange={set('invite_code')} placeholder="Необязательно" style={{ textTransform: 'uppercase' }} />
          {inviteInfo.isError && <span className="hint" style={{ color: 'var(--danger)' }}>Такого кода нет</span>}
          {!form.invite_code && <span className="hint">Если вас позвали в семью, введите код из приглашения</span>}
          {inviteInfo.data?.full && <span className="hint" style={{ color: 'var(--danger)' }}>{FULL_TEXT} Или сотрите код, и мы создадим вашу аптечку.</span>}
        </label>
        <ConsentChecks value={agreed} onChange={setAgreed} />
        {m.error && <div className="alert error">{m.error.message}</div>}
        <button className="btn primary block" disabled={m.isPending || !!inviteInfo.data?.full}>{m.isPending ? 'Создаём…' : 'Создать аккаунт'}</button>
      </form>
      <div className="divider">уже есть аккаунт?</div>
      <Link className="btn ghost block" to="/login">Войти</Link>
    </AuthShell>
  )
}

const FULL_TEXT = 'В семье уже столько участников, сколько позволяет бесплатная версия. Попросите владельца подключить Капсулку Плюс.'

/** Ссылка-приглашение /join/:code — работает и для новых, и для уже вошедших. */
export function Join() {
  const closed = useSiteClosed()
  const { code = '' } = useParams()
  const { me, refresh, setFamilyId } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const info = useQuery({
    queryKey: ['invite', code],
    queryFn: () => api<InviteInfo>(`/invites/${code}`),
    retry: false,
  })
  const join = useJoinFamily(code, async f => { await refresh(); setFamilyId(f.id); toast(`Вы в семье «${f.name}»`); nav('/') })
  if (info.isLoading) return <PageLoader />
  if (info.isError) {
    return <AuthShell title="Приглашение не найдено" sub="Приглашение одноразовое и действует 24 часа, прежние многоразовые ссылки больше не работают. Попросите владельца семьи создать новую."><Link className="btn primary block" to="/">На главную</Link></AuthShell>
  }
  const fam = info.data!
  if (fam.full) {
    return (
      <AuthShell title={`В «${fam.family_name}» нет мест`} sub={FULL_TEXT}>
        <Link className="btn primary block" to="/">На главную</Link>
      </AuthShell>
    )
  }
  return (
    <AuthShell title={`Приглашение в «${fam.family_name}»`} sub={`${fam.owner_name ? `${fam.owner_name} зовёт вас в общую аптечку` : 'Вас зовут в общую аптечку'}. Вы получите доступ ко всем аптечкам семьи.`}>
      {me ? (
        <>
          <CooldownNote />
          <JoinError j={join} />
          <button className="btn primary block" onClick={join.join} disabled={join.pending}>Вступить как {me.name}</button>
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

/** Аккаунт создан, но почта ещё не подтверждена: ждём код из письма. */
export function VerifyGate() {
  const { me, refresh, signOut } = useAuth()
  const [sent, setSent] = useState(false)
  const [code, setCode] = useState('')
  const resend = useMutation({
    mutationFn: () => api('/auth/verify-email/resend', { method: 'POST' }),
    onSuccess: () => { setSent(true); setCode('') },
  })
  const confirm = useMutation({
    mutationFn: () => api('/auth/verify-email', { body: { code } }),
    onSuccess: () => refresh(),
  })
  const submit = (e: FormEvent) => { e.preventDefault(); setSent(false); confirm.mutate() }
  return (
    <AuthShell title="Проверьте почту" sub="Осталось подтвердить, что почта ваша">
      <div className="alert info">
        <MailCheck size={18} style={{ flexShrink: 0 }} />
        <span>Мы отправили письмо с кодом на <b>{me?.email}</b>. Введите код из него, и аптечка откроется.</span>
      </div>
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span>Код из письма</span>
          <input value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000"
            style={{ fontSize: 24, letterSpacing: 8, textAlign: 'center' }}
            onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} />
        </label>
        {confirm.error && <div className="alert error">{confirm.error.message}</div>}
        <button className="btn primary block" disabled={code.length !== 6 || confirm.isPending}>
          {confirm.isPending ? 'Проверяем…' : 'Подтвердить'}
        </button>
      </form>
      <p className="muted small">Письма нет? Проверьте папку «Спам» или отправьте его ещё раз. Код из прошлого письма после этого перестанет работать.</p>
      {sent && !resend.isPending && <div className="alert ok">Отправили новое письмо</div>}
      {resend.error && <div className="alert error">{resend.error.message}</div>}
      <button className="btn ghost block" disabled={resend.isPending} onClick={() => resend.mutate()}>
        {resend.isPending ? 'Отправляем…' : 'Отправить письмо ещё раз'}
      </button>
      <div className="divider">ошиблись в адресе?</div>
      <p className="muted small">Удалите этот аккаунт и зарегистрируйтесь заново с правильной почтой.</p>
      <DeleteAccountButton className="btn ghost block" />
      <button className="btn ghost block" onClick={signOut}>Выйти</button>
    </AuthShell>
  )
}
