"""Выписка «для врача»: какие лекарства и когда принимал человек, в PDF и Excel.

Данные собирает collect(), а render_pdf() и render_xlsx() только раскладывают их по страницам,
поэтому оба файла всегда показывают одно и то же.

PDF рисует fpdf2 (чистый Python, без системных библиотек), кириллицу даёт шрифт DejaVu Sans,
который лежит рядом в fonts/. Excel пишет openpyxl: даты в нём настоящие, их можно сортировать.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Family, Intake, Medicine, User
from .services import load_medicines, stock_of

FONTS = Path(__file__).parent / "fonts"
BRAND = "Капсулка"

DISCLAIMER = (
    "Выписка составлена пользователем в приложении «Капсулка» по его собственным отметкам о приёме. "
    "Это не медицинский документ и не назначение: сведения не проверялись врачом или фармацевтом "
    "и могут быть неполными. Решения о лечении принимает врач."
)
NO_COMMENTS_NOTE = "Комментарии к приёму видит только их автор, поэтому в выписке по другому участнику их нет."

STATUS = {"ok": "есть", "low": "заканчивается", "out": "закончилось", "expiring": "скоро истекает", "expired": "есть просроченное"}


@dataclass
class IntakeRow:
    taken_at: datetime          # местное время, без часового пояса (так его понимает Excel)
    medicine: str
    dosage: str
    amount: float
    unit: str
    comment: str


@dataclass
class SummaryRow:
    medicine: str
    dosage: str
    form: str
    active_ingredient: str
    times: int
    total: float
    unit: str
    first: datetime
    last: datetime


@dataclass
class CabinetRow:
    medicine: str
    dosage: str
    form: str
    active_ingredient: str
    left: float
    unit: str
    nearest_expiry: date | None
    status: str


@dataclass
class Report:
    family: str
    patient: str
    date_from: date
    date_to: date
    tz: str
    generated_at: datetime
    with_comments: bool
    intakes: list[IntakeRow] = field(default_factory=list)
    summary: list[SummaryRow] = field(default_factory=list)
    cabinet: list[CabinetRow] | None = None

    @property
    def period(self) -> str:
        return f"{self.date_from:%d.%m.%Y} — {self.date_to:%d.%m.%Y}"

    def filename(self, ext: str) -> tuple[str, str]:
        """(латинское имя на всякий случай, человеческое имя по-русски)."""
        stamp = f"{self.date_from:%Y-%m-%d}_{self.date_to:%Y-%m-%d}"
        return f"kapsulka-dlya-vracha-{stamp}.{ext}", f"Для врача — {self.patient} {self.period}.{ext}"


def collect(
    db: Session, fam: Family, viewer: User, patient: User,
    date_from: date, date_to: date, tz: ZoneInfo, cabinet: bool = False,
) -> Report:
    start = datetime.combine(date_from, time.min, tz).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tz).astimezone(timezone.utc)
    intakes = list(db.scalars(
        select(Intake)
        .where(Intake.family_id == fam.id, Intake.user_id == patient.id, Intake.taken_at >= start, Intake.taken_at < end)
        .order_by(Intake.taken_at, Intake.id)
    ))
    meds = {m.id: m for m in load_medicines(db, fam.id)}
    # Комментарий — личная заметка автора (как и в истории на сайте): чужие не показываем.
    with_comments = viewer.id == patient.id

    def local(dt: datetime) -> datetime:
        if dt.tzinfo is None:  # SQLite отдаёт время без пояса, хранится оно в UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).replace(tzinfo=None, microsecond=0)

    report = Report(
        family=fam.name, patient=patient.name, date_from=date_from, date_to=date_to, tz=tz.key,
        generated_at=local(datetime.now(timezone.utc)), with_comments=with_comments,
    )
    groups: dict[tuple, SummaryRow] = {}
    for i in intakes:
        med: Medicine | None = meds.get(i.medicine_id) if i.medicine_id else None
        dosage = (med.dosage if med else None) or ""
        at = local(i.taken_at)
        report.intakes.append(IntakeRow(at, i.medicine_name, dosage, i.amount, i.unit, i.comment if with_comments else ""))
        key = (i.medicine_id or i.medicine_name, i.unit)
        row = groups.get(key)
        if row is None:
            groups[key] = SummaryRow(
                i.medicine_name, dosage, (med.form if med else None) or "",
                (med.active_ingredient if med else None) or "", 1, i.amount, i.unit, at, at,
            )
        else:
            row.times += 1
            row.total += i.amount
            row.last = at
    report.summary = sorted(groups.values(), key=lambda r: r.medicine.lower())
    if cabinet:
        report.cabinet = []
        for med in meds.values():
            s = stock_of(med)
            report.cabinet.append(CabinetRow(
                med.name, med.dosage or "", med.form or "", med.active_ingredient or "",
                s.total, med.unit, s.nearest_expiry, STATUS.get(s.status, s.status),
            ))
    return report


def num(x: float) -> str:
    """1.0 → «1», 0.5 → «0,5»: так пишут в России."""
    return f"{x:g}".replace(".", ",")


def _dt(x: datetime) -> str:
    return f"{x:%d.%m.%Y %H:%M}"


# --- PDF -----------------------------------------------------------------------

def render_pdf(r: Report) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    class Doc(FPDF):
        def footer(self):
            self.set_y(-14)
            self.set_font("DejaVu", size=7)
            self.set_text_color(110)
            self.cell(0, 4, f"{BRAND} · выписка для пациента, не медицинский документ", align="L")
            self.cell(0, 4, f"стр. {self.page_no()} из {{nb}}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf = Doc(format="A4")
    pdf.set_title(f"Для врача — {r.patient}")
    pdf.set_author(BRAND)
    pdf.set_creator(BRAND)
    pdf.add_font("DejaVu", "", FONTS / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", FONTS / "DejaVuSans-Bold.ttf")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    head = FontFace(emphasis="BOLD", fill_color=(234, 240, 238))

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 9, "Приём лекарств — выписка для врача", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", size=10)
    for label, value in [
        ("Пациент", r.patient), ("Период", r.period),
        ("Сформировано", f"{_dt(r.generated_at)} ({r.tz})"),
    ]:
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(36, 6, label)
        pdf.set_font("DejaVu", size=10)
        pdf.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("DejaVu", size=8)
    pdf.set_text_color(90)
    pdf.set_fill_color(250, 244, 230)
    pdf.multi_cell(0, 4.2, DISCLAIMER, fill=True, padding=2, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)

    def section(title: str, note: str = ""):
        if pdf.will_page_break(40):  # заголовок не остаётся внизу страницы без таблицы
            pdf.add_page()
        else:
            pdf.ln(4)
        pdf.set_font("DejaVu", "B", 12)
        pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        if note:
            pdf.set_font("DejaVu", size=8)
            pdf.set_text_color(100)
            pdf.multi_cell(0, 4, note, new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0)
        pdf.ln(1)
        pdf.set_font("DejaVu", size=8.5)

    def table(widths, headings, rows, align=None):
        with pdf.table(col_widths=widths, headings_style=head, line_height=4.6, padding=1.2,
                       text_align=align or "LEFT", first_row_as_headings=True) as t:
            t.row(headings)
            for row in rows:
                t.row([str(c) for c in row])

    section("Что принималось", "Сводка по каждому лекарству за период.")
    if r.summary:
        table(
            (40, 22, 32, 10, 18, 30, 30),
            ["Лекарство", "Дозировка", "Действующее вещество", "Раз", "Всего", "Первый приём", "Последний приём"],
            [[s.medicine, s.dosage, s.active_ingredient, s.times, f"{num(s.total)} {s.unit}",
              _dt(s.first), _dt(s.last)] for s in r.summary],
        )
    else:
        pdf.cell(0, 6, "За этот период отметок о приёме нет.", new_x="LMARGIN", new_y="NEXT")

    if r.intakes:
        section("Журнал приёма", "" if r.with_comments else NO_COMMENTS_NOTE)
        if r.with_comments:
            table((32, 54, 20, 76), ["Когда", "Лекарство", "Сколько", "Комментарий"],
                  [[_dt(i.taken_at), f"{i.medicine} {i.dosage}".strip(), f"{num(i.amount)} {i.unit}", i.comment]
                   for i in r.intakes])
        else:
            table((34, 110, 38), ["Когда", "Лекарство", "Сколько"],
                  [[_dt(i.taken_at), f"{i.medicine} {i.dosage}".strip(), f"{num(i.amount)} {i.unit}"]
                   for i in r.intakes])

    if r.cabinet is not None:
        section(f"Лекарства в аптечке «{r.family}»", "Что есть дома сейчас, по данным приложения.")
        if r.cabinet:
            table((56, 24, 36, 22, 22, 22),
                  ["Лекарство", "Дозировка", "Действующее вещество", "Осталось", "Годен до", "Статус"],
                  [[c.medicine, c.dosage, c.active_ingredient, f"{num(c.left)} {c.unit}",
                    f"{c.nearest_expiry:%d.%m.%Y}" if c.nearest_expiry else "", c.status] for c in r.cabinet])
        else:
            pdf.cell(0, 6, "Аптечка пуста.", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# --- Excel ---------------------------------------------------------------------

def render_xlsx(r: Report) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="EAF0EE")
    wrap = Alignment(wrap_text=True, vertical="top")
    DT, D = "DD.MM.YYYY HH:MM", "DD.MM.YYYY"

    def sheet(ws, title, headings, widths, rows, formats=None, note=""):
        ws.title = title
        ws.append([f"Приём лекарств — выписка для врача. Пациент: {r.patient}. Период: {r.period}."])
        ws["A1"].font = Font(bold=True, size=12)
        ws.append([DISCLAIMER])
        ws["A2"].font = Font(italic=True, size=9, color="666666")
        ws.append([note])
        ws["A3"].font = Font(italic=True, size=9, color="666666")
        ws.append(headings)
        for i, w in enumerate(widths[:len(headings)], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
            cell = ws.cell(row=4, column=i)
            cell.font, cell.fill = bold, fill
        for row in rows:
            ws.append(row)
        for col, fmt in (formats or {}).items():
            for (cell,) in ws.iter_rows(min_row=5, min_col=col, max_col=col):
                cell.number_format = fmt
        for row in ws.iter_rows(min_row=5):
            for cell in row:
                cell.alignment = wrap
        ws.freeze_panes = "A5"
        if rows:
            ws.auto_filter.ref = f"A4:{get_column_letter(len(headings))}{4 + len(rows)}"

    sheet(
        wb.active, "Сводка",
        ["Лекарство", "Дозировка", "Форма", "Действующее вещество", "Раз", "Всего", "Ед.", "Первый приём", "Последний приём"],
        [30, 14, 14, 26, 7, 9, 8, 18, 18],
        [[s.medicine, s.dosage, s.form, s.active_ingredient, s.times, s.total, s.unit, s.first, s.last] for s in r.summary],
        {8: DT, 9: DT},
    )
    headings = ["Когда", "Лекарство", "Дозировка", "Сколько", "Ед."] + (["Комментарий"] if r.with_comments else [])
    sheet(
        wb.create_sheet(), "Журнал приёма", headings, [18, 30, 14, 9, 8, 50],
        [[i.taken_at, i.medicine, i.dosage, i.amount, i.unit] + ([i.comment] if r.with_comments else []) for i in r.intakes],
        {1: DT}, note="" if r.with_comments else NO_COMMENTS_NOTE,
    )
    if r.cabinet is not None:
        sheet(
            wb.create_sheet(), "Аптечка",
            ["Лекарство", "Дозировка", "Форма", "Действующее вещество", "Осталось", "Ед.", "Годен до", "Статус"],
            [30, 14, 14, 26, 10, 8, 12, 18],
            [[c.medicine, c.dosage, c.form, c.active_ingredient, c.left, c.unit, c.nearest_expiry, c.status] for c in r.cabinet],
            {7: D},
        )
    wb.properties.creator = BRAND
    wb.properties.title = f"Для врача — {r.patient}"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
