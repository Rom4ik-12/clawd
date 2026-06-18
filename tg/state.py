"""
tg/state.py — Глобальное состояние агента (что сейчас делает)
"""
_current_action = "Онлайн"


def get_action() -> str:
    return _current_action


def set_action(action: str):
    global _current_action
    _current_action = action
