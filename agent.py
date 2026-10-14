"""
Агент поддержки.

Логика:
- Каждые 15 сек бот смотрит на список "Открыто".
- Верхняя заявка — та, с которой работаем.
- Если это та же заявка, что уже обрабатываем — проверяем команду пользователя.
- Если новая:
    - auto/suggest: вставляем шаблон, показываем кнопки, ждём
    - escalate: ничего не делаем, помечаем разобранной
- Разобранные заявки не трогаем.
- Как только верхняя заявка сменилась — сразу берём новую.
"""
import queue
import time
import traceback

from browser import AppLab, needs_reply, UIError
from matcher import Matcher
from notifier import notify as system_notify
import subprocess
from paths import CHROME_EXE, CHROME_PROFILE
from config import load_config
import os
import queue
import subprocess
import time
import traceback

from browser import AppLab, needs_reply, UIError
from matcher import Matcher
from notifier import notify as system_notify
from paths import APP_DIR


CHECK_INTERVAL = 15
PAUSE_ON_ERROR = 5


class Agent:
    def __init__(self, dry_run: bool = True, event_queue: queue.Queue = None):
        self.dry_run = dry_run
        self.events = event_queue or queue.Queue()
        self._stop = False
        self._pause = False
        self.stats = {"total": 0, "auto": 0, "suggest": 0, "escalate": 0}

        self._processed: set[str] = set()
        self._current_id = None
        self._current_href = None
        self._current_template_title = None
        self._user_command = None

    # ------------------------------------------------------------------
    def stop(self):
        self._stop = True

    def pause(self):
        self._pause = True

    def resume(self):
        self._pause = False

    def send_command(self, cmd: str):
        """cmd = 'send' | 'next'"""
        self._user_command = cmd

    # ------------------------------------------------------------------
    def _emit(self, typ, **kwargs):
        self.events.put({"type": typ, **kwargs})

    def _log(self, text):
        self._emit("log", text=text)
        print(text)

    def _notify(self, ticket_id, action, message, href=""):
        # в GUI
        self._emit("notification",
                   ticket=ticket_id, action=action, message=message, href=href)
        # системное уведомление Windows
        print(f"[DEBUG agent] notifier.notify({ticket_id}, {href}, {action}, ...)")
        try:
            system_notify(ticket_id, href, action, message)
        except Exception as e:
            self._log(f"  notifier error: {e}")
            print(f"[DEBUG agent] notifier EXCEPTION: {e}")

    def _push_stats(self):
        self._emit("stats", **self.stats)

    def _clear_buttons(self):
        self._emit("clear_buttons")

    def _show_buttons(self, can_send: bool):
        self._emit("show_buttons", can_send=can_send)

    # ------------------------------------------------------------------
    def run(self):
        self._log("Загружаю matcher...")
        try:
            matcher = Matcher()
        except Exception as e:
            self._log(f"ОШИБКА загрузки matcher: {e}")
            self._log(traceback.format_exc())
            return

        self._log("Запускаю Chrome бота...")
        self._start_chrome()

        self._log("Подключаюсь к Chrome...")
        try:
            app = AppLab(dry_run=self.dry_run)
        except Exception as e:
            self._log(f"ОШИБКА подключения: {e}")
            self._log(traceback.format_exc())
            return

        self._log("Бот готов.")
        self._push_stats()

        while not self._stop:
            if self._pause:
                time.sleep(1)
                continue
            try:
                self._tick(app, matcher)
            except Exception as e:
                self._log(f"ОШИБКА в цикле: {e}")
                self._log(traceback.format_exc())
                time.sleep(PAUSE_ON_ERROR)

        self._log("Бот остановлен.")
        try:
            app.close()
        except Exception:
            pass

    def _start_chrome(self):
        """Запускает Chrome бота через start_chrome.bat, если порт 9222 не слушается."""
        import urllib.request

        # 1. Проверяем, вдруг Chrome уже запущен
        try:
            urllib.request.urlopen("http://localhost:9222/json/version", timeout=1)
            self._log("  Chrome уже запущен, использую существующий.")
            return
        except Exception:
            pass

        # 2. Ищем .bat
        bat_path = os.path.join(APP_DIR, "start_chrome.bat")
        if not os.path.exists(bat_path):
            self._log(f"  ОШИБКА: не найден {bat_path}")
            return

        # 3. Запускаем .bat
        try:
            subprocess.Popen(
                [bat_path],
                shell=True,
                cwd=APP_DIR,
            )
            self._log(f"  Запущен {bat_path}")
            time.sleep(6)   # даём Chrome время поднять порт
        except Exception as e:
            self._log(f"  ОШИБКА запуска .bat: {e}")
    # ------------------------------------------------------------------
    def _tick(self, app, matcher):
        try:
            app.open_list()
            tickets = app.list_tickets()
        except UIError as e:
            self._log(f"Список не открылся: {e}")
            time.sleep(PAUSE_ON_ERROR)
            return

        if not tickets:
            self._log("Список пуст, жду 30 сек...")
            time.sleep(30)
            return

        top = tickets[0]
        top_id = top["id"]

        # Если работаем с текущей заявкой и она всё ещё в списке
        if self._current_id is not None and top_id == self._current_id:
            # обработать команду (Отправить/Дальше)
            self._handle_command(app)
            # после "Дальше" current_id сброшен — переходим к следующему тику
            if self._current_id is not None:
                # текущая всё ещё активна, ждём дальше
                time.sleep(CHECK_INTERVAL)
                return
            # иначе проваливаемся — ищем следующую

        # Если текущая заявка исчезла из топа (закрыта или ушла вниз)
        if self._current_id is not None and top_id != self._current_id:
            self._log(f"Верхняя заявка сменилась: {self._current_id} → {top_id}")
            self._current_id = None
            self._current_href = None
            self._current_template_title = None
            self._clear_buttons()

        # Ищем следующую неразобранную заявку
        target = None
        for cand in tickets:
            if cand["id"] not in self._processed:
                target = cand
                break

        if target is None:
            self._log(f"Все {len(tickets)} заявок разобраны, жду 30 сек...")
            time.sleep(30)
            return

        self._process_new(app, matcher, target)
        time.sleep(CHECK_INTERVAL)

    # ------------------------------------------------------------------
    def _handle_command(self, app):
        if self._user_command is None:
            return
        cmd = self._user_command
        self._user_command = None

        if cmd == "send":
            self._do_send(app, self._current_id)
            self._clear_buttons()
            self._current_template_title = None
        elif cmd == "next":
            self._log(f"  ты нажал 'Дальше' по {self._current_id} — иду к следующей")
            self._clear_buttons()
            self._current_template_title = None
            self._current_id = None
            self._current_href = None
    # ------------------------------------------------------------------
    def _process_new(self, app, matcher, t):
        self._current_id = t["id"]
        self._current_href = t["href"]
        self._current_template_title = None
        self._user_command = None
        self._log(f"--- Заявка {t['id']} ({t['posts']}) ---")

        try:
            app.open_ticket(t["href"])
            msgs = app.read_chat()
        except UIError as e:
            self._log(f"  не открылась/не прочиталась: {e}")
            self._processed.add(t["id"])
            return

        should_reply, _ = needs_reply(msgs)
        if not should_reply:
            self._log("  последним писал оператор — пропускаю")
            self._processed.add(t["id"])
            return

        try:
            result = matcher.match(msgs)
        except Exception as e:
            self._log(f"  ошибка матчера: {e}")
            self._processed.add(t["id"])
            return

        # ВАЖНО: помечаем заявку разобранной СРАЗУ, до любых действий.
        # Это гарантирует, что бот не вернётся к ней, даже если сменится
        # верхняя заявка или что-то упадёт.
        self._processed.add(t["id"])

        self.stats["total"] += 1

        if result.action in ("auto", "suggest"):
            if result.action == "auto":
                self.stats["auto"] += 1
            else:
                self.stats["suggest"] += 1

            tid = result.template_id
            title = matcher.tpl_by_id[tid]["title"]

            try:
                app.insert_chat_template(title)
                self._current_template_title = title
                self._log(f"  {result.action.upper()}: вставил «{title}», жду решения")
                msg = (
                    f"шаблон «{title}»\nклиент: {result.summary}"
                    if result.action == "auto"
                    else f"⚠ шаблон «{title}» — проверь внимательно\nклиент: {result.summary}"
                )
                self._notify(t["id"], result.action, msg, href=t["href"])
                self._show_buttons(can_send=True)
            except UIError as e:
                self._log(f"  не удалось вставить шаблон: {e}")
                self._notify(t["id"], "escalate",
                             f"шаблон «{title}» не вставился\nклиент: {result.summary}",
                             href=t["href"])
                self._current_template_title = None

        else:
            self.stats["escalate"] += 1
            self._log(f"  ESCALATE: {result.reason}")
            self._notify(t["id"], "escalate", result.headline, href=t["href"])
            self._show_buttons(can_send=False)

        self._push_stats()

    # ------------------------------------------------------------------
    def _do_send(self, app, ticket_id):
        try:
            self._log(f"  → отправляю по {ticket_id}...")
            app.open_list()
            tickets = app.list_tickets()
            href = next((x["href"] for x in tickets if x["id"] == ticket_id), None)
            if not href:
                self._log(f"  заявка {ticket_id} не найдена")
                self._processed.add(ticket_id)
                return
            app.open_ticket(href)
            if not app.editor_text():
                self._log("  редактор пуст — нечего отправлять")
                return
            app.send()
            self._log(f"  ✓ отправлено в {ticket_id}")
        except Exception as e:
            self._log(f"  ошибка отправки: {e}")