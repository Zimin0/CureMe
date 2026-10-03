import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Bell, CalendarClock, Check, FileText, History, Layers, Pill, ScanLine, Search, ShieldCheck, Sparkles, Users,
} from 'lucide-react'
import { api } from '../api'
import { LegalLinks } from './Legal'

type Access = { closed: boolean; trial_days?: number; price_month?: number | null; price_year?: number | null }

const FEATURES = [
  { icon: ScanLine, title: 'Добавление сканом', text: 'Наведите камеру на код упаковки: название, срок годности и серия подставятся сами.' },
  { icon: Pill, title: 'Сроки годности', text: 'Видно, что скоро испортится, а что уже пора выбросить. Остатки считаются по таблеткам.' },
  { icon: Users, title: 'Вся семья в одной аптечке', text: 'Родные видят общую аптечку со своих телефонов. У каждого свои избранные лекарства.' },
  { icon: Search, title: 'Что есть дома от…', text: 'Введите, что беспокоит, и посмотрите, что из ваших лекарств указано в инструкции для такого случая.' },
] as const

const PLUS = [
  { icon: CalendarClock, title: 'Расписание приёма', text: 'Назначения врача по часам и дням. Отметили приём в один тап.' },
  { icon: Bell, title: 'Напоминания', text: 'Письмо, когда лекарство заканчивается или подходит срок годности.' },
  { icon: History, title: 'Вся история приёма', text: 'Кто и что принимал, без ограничения в 30 дней.' },
  { icon: FileText, title: 'Файл для врача', text: 'Список лекарств и история в PDF и Excel, чтобы показать на приёме.' },
  { icon: Layers, title: 'Несколько аптечек', text: 'Дача, машина, бабушка: у каждой своя аптечка.' },
  { icon: Sparkles, title: 'Без ограничений бесплатного тарифа', text: 'Больше участников и лекарств в аптечке.' },
]

function Phone({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="lp-phone" role="img" aria-label={label}>
      <div className="lp-phone-notch" />
      <div className="lp-phone-screen">{children}</div>
    </div>
  )
}

function MockExpiry() {
  return (
    <Phone label="Пример экрана: лекарства и сроки годности">
      <div className="lp-mock-title">Срок годности</div>
      {[['Мазь', 'истёк 3 дня назад', 'bad'], ['Сироп', 'ещё 12 дней', 'warn'], ['Витамины', 'до марта 2027', 'ok']].map(([n, d, k]) => (
        <div key={n} className="lp-mock-row"><Pill size={16} /><div className="grow"><b>{n}</b><span>{d}</span></div><i className={`dot ${k}`} /></div>
      ))}
    </Phone>
  )
}

function MockSchedule() {
  return (
    <Phone label="Пример экрана: расписание приёма">
      <div className="lp-mock-title">Сегодня <span className="lp-plus-chip"><Sparkles size={10} /> Плюс</span></div>
      {[['08:00', 'Витамин D', true], ['14:00', 'Витамин C', false], ['21:00', 'Витамин C', false]].map(([t, n, done]) => (
        <div key={String(t)} className="lp-mock-row"><b className="lp-time">{t}</b><div className="grow"><b>{n}</b></div>{done ? <Check size={16} className="lp-ok" /> : <span className="lp-take">Принял</span>}</div>
      ))}
    </Phone>
  )
}

export function Landing() {
  const access = useQuery({ queryKey: ['access'], queryFn: () => api<Access>('/auth/access'), staleTime: 60_000 })
  const closed = access.data?.closed ?? false
  const trial = access.data?.trial_days ?? 0
  const { price_month: pm, price_year: py } = access.data ?? {}
  const cta = closed ? '/login' : '/register'
  const ctaText = closed ? 'Войти' : 'Попробовать бесплатно'
  const price = [pm ? `${pm} ₽ в месяц` : null, py ? `${py} ₽ в год` : null].filter(Boolean).join(' или ')

  return (
    <div className="lp">
      <header className="lp-top">
        <div className="brand"><img src="/icon.svg" alt="" />Капсулка</div>
        <Link className="btn ghost sm" to="/login">Войти</Link>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-text">
          <h1>Домашняя аптечка, в которой всё под контролем</h1>
          <p>Капсулка помнит, какие лекарства есть у вас дома, когда истекает срок и сколько осталось. Вся семья смотрит в одну аптечку с телефона.</p>
          <div className="lp-cta">
            <Link className="btn primary lp-btn" to={cta}>{ctaText}</Link>
            {!closed && trial > 0 && <span className="lp-note"><Sparkles size={14} /> {trial} {trial === 1 ? 'день' : trial < 5 ? 'дня' : 'дней'} Капсулки Плюс, пробный период</span>}
          </div>
          <p className="lp-small">Без карты. Регистрация по почте за минуту.</p>
        </div>
        <div className="lp-hero-art"><MockExpiry /></div>
      </section>

      <section className="lp-section">
        <h2>Что умеет Капсулка</h2>
        <div className="lp-grid">
          {FEATURES.map(f => (
            <div key={f.title} className="lp-card">
              <div className="lp-ico"><f.icon size={22} /></div>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="lp-plus">
        <div className="lp-plus-head">
          <span className="lp-plus-chip big"><Sparkles size={14} /> Капсулка Плюс</span>
          <h2>Когда аптечкой пользуется вся семья</h2>
          <p>Плюс добавляет то, что экономит время и нервы: расписание, напоминания и файл для врача. Один Плюс действует на все ваши аптечки, до 5 своих.</p>
        </div>
        <div className="lp-plus-body">
          <div className="lp-hero-art"><MockSchedule /></div>
          <ul className="lp-plus-list">
            {PLUS.map(f => (
              <li key={f.title}><div className="lp-ico plus"><f.icon size={20} /></div><div><b>{f.title}</b><span>{f.text}</span></div></li>
            ))}
          </ul>
        </div>
        <div className="lp-plus-cta">
          {!closed && trial > 0
            ? <p><b>Пробный период Плюса: {trial} {trial === 1 ? 'день' : trial < 5 ? 'дня' : 'дней'} бесплатно.</b> Он включится сам после подтверждения почты. Потом аккаунт вернётся на бесплатный тариф, деньги не списываются.</p>
            : <p>Основные функции Капсулки бесплатны. Плюс нужен, если хочется большего.</p>}
          {price && <p className="lp-small">Стоимость Плюса: {price}. Цена указана для сведения и не является публичной офертой.</p>}
          <p className="lp-small"><Link to="/plus">Тариф, стоимость и условия оплаты</Link></p>
          <Link className="btn primary lp-btn" to={cta}>{ctaText}</Link>
        </div>
      </section>

      <section className="lp-section lp-free">
        <ShieldCheck size={28} />
        <div>
          <h2>Бесплатно останется главное</h2>
          <p>Сканирование упаковок, сроки годности, остатки, фото, подбор «Что есть дома от…» и приглашение родных не требуют Плюса. В бесплатной версии до 3 человек в семье и 60 лекарств в аптечке.</p>
        </div>
      </section>

      <section className="lp-final">
        <h2>Наведите порядок в аптечке сегодня</h2>
        <Link className="btn primary lp-btn" to={cta}>{ctaText}</Link>
      </section>

      <footer className="lp-foot">
        <p className="lp-small">Капсулка помогает вести учёт лекарств и не заменяет консультацию врача. Перед применением лекарств читайте инструкцию и советуйтесь со специалистом.</p>
        <LegalLinks />
        <nav className="legal-links small" aria-label="Тариф">
          <Link to="/plus">Капсулка Плюс: тариф и оплата</Link>
          <Link to="/offer">Публичная оферта</Link>
        </nav>
      </footer>
    </div>
  )
}
