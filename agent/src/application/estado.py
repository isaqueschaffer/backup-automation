"""Estado compartilhado entre a thread do backup e a do ping (mesmo processo)."""
backup_em_andamento = False
backup_inicio = None  # time.monotonic() do início do backup em andamento


def backup_ha_min():
    """Minutos desde o início do backup em andamento (None se não há)."""
    import time
    if not backup_em_andamento or backup_inicio is None:
        return None
    return int((time.monotonic() - backup_inicio) // 60)
