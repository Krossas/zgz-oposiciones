"""
services/scheduler.py — Programación de tareas automáticas.

Usa APScheduler para ejecutar el scraping de forma periódica sin
que el usuario tenga que pulsar "Actualizar datos" manualmente.

Configuración por defecto:
  - Scraping completo: cada domingo a las 3:00 AM
  - Frecuencia configurable desde config.py

Por qué APScheduler y no cron del sistema:
  - No requiere acceso al sistema operativo (funciona en cualquier OS)
  - Se arranca y para junto con la aplicación Flask
  - El historial de ejecuciones queda en la BD igual que el scraping manual
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron         import CronTrigger
from apscheduler.events                import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from app.config import Config

logger    = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Europe/Madrid")


def iniciar_scheduler():
    """
    Arranca el scheduler con las tareas programadas.
    Se llama una sola vez al iniciar la aplicación.
    """
    # Importación diferida para evitar importaciones circulares
    from app.services.oferta_service import iniciar_scraping

    # ── Tarea: scraping semanal ───────────────────────────────────────────────
    # Se ejecuta cada domingo a las 3:00 AM (hora de Madrid)
    # A esa hora el servidor del Ayuntamiento tiene menos carga
    scheduler.add_job(
        func    = _tarea_scraping_automatico,
        trigger = CronTrigger(
            day_of_week = Config.SCHEDULER_DIA,
            hour        = Config.SCHEDULER_HORA,
            minute      = 0,
        ),
        id              = "scraping_semanal",
        name            = "Scraping semanal automático",
        replace_existing = True,
        misfire_grace_time = 3600,   # Si el servidor estaba apagado, ejecutar si el retraso es < 1h
    )

    # Escuchar eventos del scheduler para registrarlos en el log
    scheduler.add_listener(_listener_eventos, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    scheduler.start()

    proxima = scheduler.get_job("scraping_semanal").next_run_time
    logger.info(
        "Scheduler iniciado. Próximo scraping automático: %s",
        proxima.strftime("%d/%m/%Y %H:%M") if proxima else "desconocido"
    )


def parar_scheduler():
    """Para el scheduler de forma limpia al cerrar la aplicación."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler parado")


def obtener_info_scheduler() -> dict:
    """
    Devuelve información sobre el estado del scheduler y la próxima ejecución.
    Usado por la API para mostrarlo en el panel de Log.
    """
    if not scheduler.running:
        return {"activo": False}

    job    = scheduler.get_job("scraping_semanal")
    proxima = job.next_run_time if job else None

    return {
        "activo":             True,
        "proxima_ejecucion":  proxima.isoformat() if proxima else None,
        "dia_semana":         Config.SCHEDULER_DIA,
        "hora":               Config.SCHEDULER_HORA,
    }


def _tarea_scraping_automatico():
    """
    Función que ejecuta APScheduler periódicamente.
    Lanza el scraping si no hay uno ya en curso.
    """
    logger.info("Scheduler: lanzando scraping automático programado")
    from app.services.oferta_service import iniciar_scraping
    iniciado = iniciar_scraping()
    if not iniciado:
        logger.warning("Scheduler: no se pudo iniciar el scraping (ya hay uno en curso)")


def _listener_eventos(evento):
    """Recibe notificaciones de APScheduler cuando una tarea termina o falla."""
    if evento.exception:
        logger.error("Scheduler: la tarea %s falló: %s", evento.job_id, evento.exception)
    else:
        logger.info("Scheduler: la tarea %s completada correctamente", evento.job_id)
