import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { api, TrustedStatus } from '../api'
import { PageLoader } from '../components/ui'
import { OPERATOR } from '../legal'
import { LegalLinks } from './Legal'

interface Info { user_name: string; status: TrustedStatus }

/**
 * Страница доверенного человека по ссылке из письма (без входа): он сам соглашается, отказывается или отписывается.
 * Токен стоит в адресе после «#», поэтому не попадает в логи сервера.
 */
export function Trusted() {
  const token = useLocation().hash.replace(/^#/, '')
  const qc = useQueryClient()
  const key = ['trusted', token]
  const q = useQuery({ queryKey: key, queryFn: () => api<Info>('/trusted/lookup', { body: { token } }), enabled: !!token, retry: false })
  const act = useMutation({
    mutationFn: (what: 'confirm' | 'decline') => api<Info>(`/trusted/${what}`, { body: { token } }),
    onSuccess: d => qc.setQueryData(key, d),
  })
  if (token && q.isLoading) return <PageLoader />
  const info = q.data
  const done = act.isSuccess ? act.data : null
  const status = done?.status ?? info?.status

  return (
    <div className="auth-wrap">
      <div className="auth-card stack lg">
        <div className="stack" style={{ gap: 6, textAlign: 'center' }}>
          <div className="brand"><img src="/icon.svg" alt="" />Капсулка</div>
          <h1 style={{ fontSize: 24 }}>Доверенный человек</h1>
        </div>
        <div className="card stack" data-testid="trusted-card">
          {!info ? (
            <div className="alert error">
              {!token ? 'В ссылке нет кода. Откройте её из письма целиком.' : (q.error?.message ?? 'Ссылка недействительна.')}
            </div>
          ) : status === 'pending' ? (
            <>
              <p><b>{info.user_name}</b> указал(а) вас доверенным человеком в Капсулке, домашней аптечке.</p>
              <p className="muted small">
                Если {info.user_name} не отметит плановый приём лекарства, мы отправим вам на почту короткое письмо, чтобы вы могли
                связаться. По умолчанию в письме нет названия лекарства.
              </p>
              <div className="alert info">
                <span className="small">
                  Нажимая «Согласен(на)», вы разрешаете Капсулке использовать вашу почту и имя, которые ввёл(а) {info.user_name},
                  только для этих писем. Письма приходят, пока вы не отпишетесь по ссылке в любом из них. Имя и почта хранятся, пока
                  {info.user_name} не уберёт вас из списка (или не удалит аккаунт), либо до вашего запроса на удаление.
                  Оператор: {OPERATOR.name}. Полный текст: <a href="/consent-trusted">согласие доверенного лица</a> и{' '}
                  <a href="/privacy">Политика</a>; вопросы и запросы на удаление: <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>.
                </span>
              </div>
              <button className="btn primary block" disabled={act.isPending} onClick={() => act.mutate('confirm')}>Согласен(на) получать письма</button>
              <button className="btn ghost block" disabled={act.isPending} onClick={() => act.mutate('decline')}>Не согласен(на)</button>
            </>
          ) : status === 'confirmed' ? (
            <>
              <h2>Вы согласились</h2>
              <p className="muted small">Если {info.user_name} не отметит плановый приём, мы напишем вам. Это автоматическое письмо, оно не означает, что что-то случилось.</p>
              <button className="btn ghost block" disabled={act.isPending} onClick={() => act.mutate('decline')}>Отписаться</button>
            </>
          ) : (
            <>
              <h2>{status === 'declined' ? 'Вы отказались' : 'Вы отписались'}</h2>
              <p className="muted small">Писем от Капсулки по этому поводу вам больше не будет. Спасибо, что ответили.</p>
            </>
          )}
          {act.isError && <div className="alert error">{act.error.message}</div>}
        </div>
        <LegalLinks />
      </div>
    </div>
  )
}
