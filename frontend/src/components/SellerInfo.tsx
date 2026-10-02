import { SELLER, SHOW_SELLER_ID } from '../seller'

/** Реквизиты исполнителя и контакты: нужны публичной странице тарифа и проверке платёжного сервиса. */
export function SellerInfo() {
  return (
    <section className="card stack" aria-label="Реквизиты исполнителя">
      <h2>Исполнитель и контакты</h2>
      <p>{SELLER.name}{SHOW_SELLER_ID ? `, ${SELLER.status}` : ''}.</p>
      {SHOW_SELLER_ID && <p>ИНН: {SELLER.inn}</p>}
      <p>Сайт: {SELLER.site}</p>
      <p>Электронная почта для обращений, вопросов по оплате и возвратов: <a href={`mailto:${SELLER.email}`}>{SELLER.email}</a></p>
      <p className="muted small">Обращения рассматриваются в течение тридцати календарных дней, если для требования не установлен более короткий срок.</p>
    </section>
  )
}
