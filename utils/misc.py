from datetime import datetime


def iso_format(dt):
    """Форматирование datetime в ISO строку"""
    return dt.isoformat(timespec="seconds")