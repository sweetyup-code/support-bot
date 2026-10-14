from config import load_config

_cfg = load_config()
BASE_URL      = _cfg["base_url"]
LIST_URL_OPEN = _cfg["list_url_open"]

# --- список заявок ---
TICKET_ROWS    = ".el-table__body tr.el-table__row"
ROW_ID_LINK    = ".common-value a"                          # текст: CRN-08656, href со ссылкой
ROW_POST_COUNT = ".ticket-list-column-title__post-count"    # "(8)"
ROW_UNREAD_CLS = "ticket-list__column-unread"
LIST_READY     = ".ticket-topbar-actions__refresh-button"   # есть и в пустом списке
# НЕ нажимать: .plugin__close_tickets ("Закрыть все"), .icon-new-tab, .hde-info-btn

# --- чат ---
CHAT_MESSAGE   = ".ticket-conversation__message"
MSG_HTML       = ".ticket-conversation__message-html"
MSG_TEXT       = ".ticket-conversation__message-text"       # запасной вариант
MSG_META       = ".ticket-conversation__message-meta"
CLS_CLIENT     = "ticket-conversation__message_user"
CLS_STAFF      = "ticket-conversation__message_staff"
CLS_COMMENT    = "ticket-conversation__message_comment"     # служебные записи, пропускаем
MY_USER_ID     = _cfg["operator_id"]                                    # твой id оператора
BOT_USER_ID    = "-1"                                       # "Система" (виртуальный помощник)

# --- редактор и кнопки ---
INPUT_BOX      = ".ticket-editor .ck-editor__editable"
BTN_SEND       = ".ticket-editor__add-post-dropdown .el-button-group > button:first-child"
BTN_BACK       = ".ticket-topbar-actions__back-button"
BTN_REFRESH    = ".ticket-topbar-actions__refresh-button"

# --- шаблоны из чата ---
BTN_TEMPLATES   = "button:has(i.icon-book)"
TEMPLATES_BOX   = ".kb-templates"
TEMPLATE_SEARCH = ".kb-templates__search-input input"
TEMPLATE_ITEMS  = ".kb-templates__item"
TEMPLATE_NAME   = ".el-popover__reference span"