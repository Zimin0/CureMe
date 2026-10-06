import { SELLER, SHOW_SELLER_ID } from '../seller'

/** Реквизиты исполнителя и контакты: нужны публичной странице тарифа и проверке платёжного сервиса. Свёрнуты в самом низу страницы, текст остаётся в разметке и открывается по клику. */
export function SellerInfo() {
  return (
    <details className="card collapse" aria-label="Реквизиты исполнителя">
      <summary><h2>Исполнитель и контакты</h2></summary>
      <div className="stack collapse-body">
      <p>{SELLER.name}{SHOW_SELLER_ID ? `, ${SELLER.status}` : ''}.</p>
      {SHOW_SELLER_ID && <p>ИНН: {SELLER.inn}</p>}
      <p>Сайт: {SELLER.site}</p>
      <p>Телефон: <a href={`tel:${SELLER.phone.replace(/[^+\d]/g, '')}`}>{SELLER.phone}</a></p>
      <p>Электронная почта для обращений, вопросов по оплате и возвратов: <a href={`mailto:${SELLER.email}`}>{SELLER.email}</a></p>
      <p className="muted small">Обращения рассматриваются в течение тридцати календарных дней, если для требования не установлен более короткий срок.</p>
      </div>
    </details>
  )
}
