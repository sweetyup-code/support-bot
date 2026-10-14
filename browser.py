import random
import time
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

import ui_selectors as S

TIMEOUT_MS = 15_000


class UIError(Exception):
    """Элемент не найден или страница в неожиданном состоянии."""


@dataclass
class Message:
    role: str            # client / bot / me / operator / comment / unknown
    text: str
    meta: str            # "Имя 10.10.2026 18:31"
    post_id: str | None
    user_id: str | None


def human_pause(a: float = 1.0, b: float = 3.0) -> None:
    time.sleep(random.uniform(a, b))


def detect_role(cls: str, user_id: str | None) -> str:
    if S.CLS_COMMENT in cls:
        return "comment"
    if S.CLS_CLIENT in cls:
        return "client"
    if S.CLS_STAFF in cls:
        if user_id == S.BOT_USER_ID:
            return "bot"
        return "me" if user_id == S.MY_USER_ID else "operator"
    return "unknown"


def needs_reply(messages: list[Message]) -> tuple[bool, str | None]:
    """Нужно ли отвечать: последним среди клиента и операторов писал клиент.
    Сообщения бота и служебные записи игнорируются.
    Возвращает (нужно_ответить, post_id последнего сообщения клиента)."""
    for m in reversed(messages):
        if m.role in ("client", "me", "operator"):
            return (m.role == "client", m.post_id if m.role == "client" else None)
    return (False, None)


class AppLab:
    def __init__(self, cdp_url: str = "http://localhost:9222", dry_run: bool = True):
        self.dry_run = dry_run          # True: send() ничего не отправляет
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.connect_over_cdp(cdp_url)
        self.page: Page = self._pick_page()
        self.page.set_default_timeout(TIMEOUT_MS)

    def _pick_page(self) -> Page:
        pages = [pg for ctx in self._browser.contexts for pg in ctx.pages
                 if "helpdeskeddy" in pg.url]
        if not pages:
            raise UIError("Не найдена вкладка с helpdeskeddy в Chrome бота")
        for pg in pages:
            if "/ticket/" in pg.url:
                return pg
        return pages[0]

    def close(self) -> None:
        self._pw.stop()

    # ---------- навигация ----------
    def _goto(self, url: str, wait_selector: str) -> None:
        for attempt in range(1, 4):
            try:
                self.page.goto(url, wait_until="commit", timeout=45_000)
                self.page.wait_for_selector(wait_selector, timeout=45_000)
                return
            except PWTimeout:
                if attempt == 3:
                    raise UIError(f"Не загрузилось: {url}")
                time.sleep(2 * attempt)

    def open_list(self) -> None:
        """Список 'открыто'. Заменяет и 'нажать вкладку', и 'обновить страницу'."""
        self._goto(S.LIST_URL_OPEN, S.LIST_READY)
        try:
            self.page.locator(S.TICKET_ROWS).first.wait_for(timeout=5_000)
        except PWTimeout:
            pass    # список пуст, это нормально

    # ---------- список заявок ----------
    def list_tickets(self) -> list[dict]:
        rows = self.page.locator(S.TICKET_ROWS)
        out = []
        for i in range(rows.count()):
            r = rows.nth(i)
            link = r.locator(S.ROW_ID_LINK).first
            cnt = r.locator(S.ROW_POST_COUNT)
            out.append({
                "id": link.inner_text().strip(),
                "href": link.get_attribute("href"),
                "posts": cnt.inner_text().strip() if cnt.count() else "",
                "unread": S.ROW_UNREAD_CLS in (r.get_attribute("class") or ""),
            })
        return out

    def open_ticket(self, href: str) -> None:
        url = href if href.startswith("http") else S.BASE_URL + href
        self._goto(url, S.CHAT_MESSAGE)
        self.page.locator(S.INPUT_BOX).first.wait_for()

    def is_ticket_open(self, ticket_id: str) -> bool:
        """Проверяет, есть ли заявка в списке 'Открыто' (не закрыта ли)."""
        self.open_list()
        tickets = self.list_tickets()
        return any(t["id"] == ticket_id for t in tickets)

    # ---------- чат ----------
    def read_chat(self) -> list[Message]:
        raw = self.page.evaluate("""(s) => [...document.querySelectorAll(s.msg)].map(m => {
            const t = m.querySelector(s.html) || m.querySelector(s.text);
            const meta = m.querySelector(s.meta);
            return {cls: m.className, uid: m.getAttribute('data-user-id'),
                    pid: m.getAttribute('data-post-id'),
                    text: t ? t.innerText.trim() : '',
                    meta: meta ? meta.innerText.trim().replace(/\\s+/g, ' ') : ''};
        })""", {"msg": S.CHAT_MESSAGE, "html": S.MSG_HTML,
                "text": S.MSG_TEXT, "meta": S.MSG_META})
        return [Message(detect_role(m["cls"], m["uid"]), m["text"], m["meta"],
                        m["pid"], m["uid"]) for m in raw]

    # ---------- редактор ----------
    def editor_text(self) -> str:
        """Читает текст из CKEditor через его API. Устойчиво к анимациям."""
        return self.page.evaluate("""(sel) => {
            const el = document.querySelector(sel);
            if (!el) return '';
            if (el.ckeditorInstance) {
                const data = el.ckeditorInstance.getData();
                // вырезаем HTML-теги и декодируем сущности
                const div = document.createElement('div');
                div.innerHTML = data;
                return (div.textContent || '').trim();
            }
            return (el.textContent || '').trim();
        }""", S.INPUT_BOX)

    def clear_editor(self) -> None:
        ed = self.page.locator(S.INPUT_BOX).first
        ed.click()
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Delete")

    def insert_text(self, text: str) -> None:
        """Вставляет произвольный текст. Переносы строк → <br> (одной операцией)."""
        self.clear_editor()
        # insertText с \n внутри сохраняет переносы как <br>, не создавая пустых <p>
        self.page.keyboard.insert_text(text.replace("\r", ""))
        self.page.wait_for_timeout(200)
        if not self.editor_text():
            raise UIError("Текст не попал в редактор")

        # ---------- шаблоны из чата ----------
    def _open_templates_panel(self) -> None:
        """Открывает панель шаблонов, если она ещё не открыта."""
        if self.page.locator(S.TEMPLATES_BOX).count() > 0:
            return
        self.page.locator(S.BTN_TEMPLATES).first.click()
        self.page.wait_for_selector(S.TEMPLATES_BOX, timeout=5_000)
        # ждём, пока Vue отрисует сами items
        self.page.wait_for_selector(S.TEMPLATE_ITEMS, timeout=5_000)
        self.page.wait_for_timeout(200)   # маленькая пауза на отрисовку popover-ов

    def _close_templates_panel(self) -> None:
        """Закрывает панель, чтобы следующий вызов _open_templates_panel сработал."""
        if self.page.locator(S.TEMPLATES_BOX).count() > 0:
            self.page.locator(S.BTN_TEMPLATES).first.click()
            self.page.wait_for_timeout(300)

    def list_chat_templates(self) -> list[dict]:
        """Открывает панель и читает шаблоны. Возвращает [{name, title, text}, ...]."""
        self._open_templates_panel()
        raw = self.page.evaluate("""() => {
            const box = document.querySelector('.kb-templates');
            if (!box) return [];
            return [...box.querySelectorAll('.kb-templates__item')].map(it => {
                const ref = it.querySelector('.el-popover__reference');
                let name = '';
                if (ref) {
                    const spans = ref.querySelectorAll(':scope > span');
                    if (spans.length) name = spans[spans.length - 1].innerText.trim();
                }
                const pop = it.querySelector('.el-popover--plain');
                let title = '';
                let text = '';
                if (pop) {
                    const t = pop.querySelector('.el-popover__title');
                    title = t ? t.innerText.trim() : '';
                    const clone = pop.cloneNode(true);
                    const tc = clone.querySelector('.el-popover__title');
                    if (tc) tc.remove();
                    text = clone.innerText.trim();
                }
                return {name, title, text};
            }).filter(t => t.name);
        }""")
        seen = set()
        out = []
        for t in raw:
            if t["name"] in seen:
                continue
            seen.add(t["name"])
            out.append(t)
        return out

    def insert_chat_template(self, title: str) -> None:
        """Открывает панель, кликает по item с точным именем. Не отправляет."""
        self._open_templates_panel()

        escaped = title.replace("'", "\\'")
        item = self.page.locator(
            f".kb-templates__item:has(.el-popover__reference span:text-is('{escaped}'))"
        ).first

        item.wait_for(state="visible", timeout=5_000)
        item.click()
        # ждём, пока текст появится в редакторе — до 3 сек
        for _ in range(15):
            self.page.wait_for_timeout(200)
            if self.editor_text():
                return
        raise UIError(f"Шаблон '{title}' не вставился в редактор")

    # ---------- отправка ----------
    def send(self) -> bool:
        """Нажимает 'Добавить ответ'. В dry_run ничего не делает."""
        if self.dry_run:
            return False
        if not self.editor_text():
            raise UIError("Пустой редактор, отправлять нечего")
        self.page.locator(S.BTN_SEND).click()
        try:
            self.page.wait_for_function(
                """(sel) => !document.querySelector(sel).innerText.trim()""",
                arg=S.INPUT_BOX, timeout=10_000)
        except PWTimeout:
            raise UIError("После отправки редактор не очистился")
        human_pause(1.0, 2.0)
        return True