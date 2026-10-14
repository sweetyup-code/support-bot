"""
Матчер шаблонов. Использует обученный classifier.pkl + правила поверх.
Возвращает action + template_id + confidence + короткое summary для GUI.
ВАЖНО: правила используют только шаблоны из чата (source: chat), не kb.
"""
import json
import re
from dataclasses import dataclass
from typing import Literal

import joblib
import numpy as np
from sentence_transformers import SentenceTransformer

from paths import find_json, MODEL_CACHE_DIR

TEMPLATES_FILE = find_json("templates_final.json")
CLASSIFIER_FILE = find_json("classifier.pkl")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

TOP_K = 5
NEVER_THRESH   = 0.30
AUTO_THRESH    = 0.50
SUGGEST_THRESH = 0.50
MAX_CLIENT_MSGS = 3

FILE_RE = re.compile(r"^\S+\.(jpe?g|png|mp4|pdf|gif|mov|heic)$", re.I)

MONEY_TRIGGERS = [
    "верн", "возврат", "деньг", "оплат", "заплат", "переплат",
    "списал", "списание", "рефанд", "refund",
]
THANKS_TRIGGERS = [
    "спасибо", "благодар", "заработал", "всё хорошо", "все хорошо",
]
RKN_TRIGGERS = [
    "когда заработа", "когда почин", "когда восстанов",
    "сколько ждать", "когда будет работать", "когда исправ",
]
GREETING_ONLY = {
    "/start", "start", "привет", "здравствуйте",
    "здравствуй", "добрый день", "добрый вечер", "доброе утро",
}

# какие шаблоны есть в панели чата (source == "chat")
def _is_chat_template(tpl: dict) -> bool:
    return tpl.get("source") == "chat"


Action = Literal[
    "auto",
    "suggest",
    "escalate_never",
    "escalate_low",
    "escalate_file",
]


@dataclass
class MatchResult:
    template_id: str | None
    action: Action
    confidence: float
    reason: str
    summary: str
    headline: str


def mask(s: str) -> str:
    s = re.sub(r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}", "<ID>", s, flags=re.I)
    s = re.sub(r"https?://\S+", "<URL>", s)
    s = re.sub(r"@\w+", "<NICK>", s)
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<EMAIL>", s)
    s = re.sub(r"\+?\d[\d\s()-]{8,}\d", "<PHONE>", s)
    return s


def short_summary(text: str, max_words: int = 6) -> str:
    text = text.replace("\n", " ").strip()
    text = re.sub(r"^/start\s*", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "(пусто)"
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


class Matcher:
    def __init__(self):
        print("Загружаю шаблоны...")
        self.templates = json.load(open(TEMPLATES_FILE, encoding="utf-8"))
        self.tpl_by_id = {t["id"]: t for t in self.templates}

        print("Загружаю classifier.pkl...")
        data = joblib.load(CLASSIFIER_FILE)
        self.clf = data["clf"]

        print(f"Загружаю модель {MODEL_NAME}...")
        self.model = SentenceTransformer(MODEL_NAME, cache_folder=MODEL_CACHE_DIR)

        print("Матчер готов.")

    @staticmethod
    def _get(m, key):
        return getattr(m, key) if hasattr(m, key) else m[key]

    def _context(self, messages: list) -> tuple[str, bool]:
        parts = []
        has_file = False
        for m in reversed(messages):
            role = self._get(m, "role")
            text = self._get(m, "text")
            if role in ("comment", "bot"):
                continue
            if role == "me":
                break
            if role == "client":
                t = text.strip()
                if FILE_RE.match(t):
                    has_file = True
                    parts.append("[файл]")
                    break
                parts.append(mask(t)[:300])
                if len(parts) >= MAX_CLIENT_MSGS:
                    break
        return "\n".join(reversed(parts)), has_file

    def _last_client_msg(self, messages: list) -> str:
        for m in reversed(messages):
            role = self._get(m, "role")
            text = self._get(m, "text")
            if role == "client":
                return text.strip().lower()
        return ""

    def _pick_chat_template(self, candidates: list[str]) -> str | None:
        """Из списка id возвращает первый, который есть в панели чата."""
        for tid in candidates:
            tpl = self.tpl_by_id.get(tid)
            if tpl and _is_chat_template(tpl):
                return tid
        return None

    def match(self, messages: list) -> MatchResult:
        ctx, has_file = self._context(messages)
        last_lower = self._last_client_msg(messages)
        last_display = ""
        for m in reversed(messages):
            if self._get(m, "role") == "client":
                last_display = self._get(m, "text").strip()
                break

        summary = short_summary(last_display)

        # ----- файл -----
        if has_file:
            return MatchResult(
                None, "escalate_file", 1.0,
                "клиент прислал файл — нужно посмотреть глазами",
                summary,
                f"нужен оператор, не могу решить без вас\n"
                f"клиент: {summary}\n"
                f"файл от клиента — посмотри глазами",
            )

        if not ctx.strip():
            return MatchResult(
                None, "escalate_low", 0.0,
                "нет сообщений клиента",
                "(пусто)",
                "нужен оператор, не могу решить без вас\n"
                "в чате нет сообщений клиента",
            )

        # ----- деньги -----
        if any(w in last_lower for w in MONEY_TRIGGERS):
            return MatchResult(
                None, "escalate_never", 1.0,
                "клиент написал про деньги/возврат — нужен оператор",
                summary,
                f"нужен оператор, не могу решить без вас\n"
                f"клиент: {summary}\n"
                f"тема: деньги / возврат",
            )

        # ----- благодарность -----
        if any(w in last_lower for w in THANKS_TRIGGERS):
            tid = self._pick_chat_template(["t07", "t06", "kb236", "kb235"])
            if tid:
                title = self.tpl_by_id[tid]["title"]
                return MatchResult(
                    tid, "suggest", 0.80,
                    "клиент доволен — предложить отзыв",
                    summary,
                    f"решил проблему так → «{title}»\n"
                    f"клиент: {summary}\n"
                    f"(предложить отзыв за 7 дней)",
                )

        # ----- РКН -----
        if any(w in last_lower for w in RKN_TRIGGERS):
            tid = self._pick_chat_template(["t16", "t19", "t05"])
            if tid:
                title = self.tpl_by_id[tid]["title"]
                return MatchResult(
                    tid, "suggest", 0.85,
                    "вопрос про сроки — показать шаблон",
                    summary,
                    f"решил проблему так → «{title}»\n"
                    f"клиент: {summary}\n"
                    f"(проверь, может РКН — там свой шаблон)",
                )

        # ----- приветствие без сути -----
        stripped = last_lower.strip().strip("!.?, ")
        if stripped in GREETING_ONLY:
            tid = self._pick_chat_template(["t00", "t01"])
            if tid:
                title = self.tpl_by_id[tid]["title"]
                return MatchResult(
                    tid, "auto", 1.0,
                    "клиент поздоровался без сути — спросить вопрос",
                    summary,
                    f"решил проблему так → «{title}»\n"
                    f"клиент: {summary}\n"
                    f"(спросить, какой вопрос)",
                )

        # ----- классификатор -----
        vec = self.model.encode([ctx], convert_to_numpy=True)
        vec = vec / np.linalg.norm(vec, axis=1, keepdims=True)
        proba = self.clf.predict_proba(vec)[0]
        classes = self.clf.classes_

        order = np.argsort(-proba)[:TOP_K]
        top = [(classes[j], float(proba[j])) for j in order]

        # never
        for tid, conf in top:
            if self.tpl_by_id[tid].get("level") == "never" and conf > NEVER_THRESH:
                title = self.tpl_by_id[tid]["title"]
                return MatchResult(
                    tid, "escalate_never", conf,
                    f"предсказан never-шаблон {tid} ({title})",
                    summary,
                    f"нужен оператор, не могу решить без вас\n"
                    f"клиент: {summary}\n"
                    f"похоже на «{title}» — не могу решать сам",
                )

        # auto — только chat-шаблоны
        auto_candidates = [
            (tid, c) for tid, c in top
            if self.tpl_by_id[tid].get("level") == "auto"
            and _is_chat_template(self.tpl_by_id[tid])
            and c > AUTO_THRESH
        ]
        if auto_candidates:
            auto_candidates.sort(key=lambda x: -x[1])
            tid, conf = auto_candidates[0]
            title = self.tpl_by_id[tid]["title"]
            return MatchResult(
                tid, "auto", conf,
                f"auto-шаблон {tid} ({title})",
                summary,
                f"решил проблему так → «{title}»\n"
                f"клиент: {summary}",
            )

        # suggest — только chat-шаблоны
        for tid, conf in top:
            tpl = self.tpl_by_id[tid]
            if (
                tpl.get("level") == "suggest"
                and _is_chat_template(tpl)
                and conf > SUGGEST_THRESH
            ):
                title = tpl["title"]
                return MatchResult(
                    tid, "suggest", conf,
                    f"suggest-шаблон {tid} ({title})",
                    summary,
                    f"решил проблему так → «{title}»\n"
                    f"клиент: {summary}\n"
                    f"(проверь внимательно!)",
                )

        # эскалация
        return MatchResult(
            None, "escalate_low", top[0][1],
            f"низкая уверенность ({top[0][1]:.2f}) — нужен оператор",
            summary,
            f"нужен оператор, не могу решить без вас\n"
            f"клиент: {summary}\n"
            f"не уверен в шаблоне ({top[0][1]:.2f})",
        )