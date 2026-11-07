import logging
import os
import signal
import subprocess
import sys
from threading import Event
import time

from django.core.management.base import BaseCommand, CommandError
from apps.core.backups import create_backup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Запустить сайт и ежедневные приватные резервные копии. Локально: --local --port 8000.'

    def add_arguments(self, parser):
        parser.add_argument('--local', action='store_true')
        parser.add_argument('--port', type=int)

    def handle(self, *args, **options):
        port = options['port'] or int(os.getenv('PORT', '8000'))
        command = ([sys.executable, 'manage.py', 'runserver', f'127.0.0.1:{port}', '--noreload'] if options['local'] else
            [sys.executable, '-m', 'gunicorn', 'config.wsgi:application', '--bind', f'0.0.0.0:{port}', '--workers', '2', '--timeout', '45'])
        stop = Event()
        process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        previous = {}
        def shutdown(signum, frame):
            stop.set()
            if process.poll() is None:
                process.terminate()
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, shutdown)
        requested_stop = False
        try:
            last_check = 0
            while process.poll() is None and not stop.is_set():
                if time.monotonic() - last_check >= 300:
                    try:
                        create_backup()
                    except Exception as exc:
                        logger.error('Automatic backup failed (%s); existing backups retained.', type(exc).__name__)
                    last_check = time.monotonic()
                stop.wait(1)
        finally:
            requested_stop = stop.is_set()
            shutdown(None, None)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if process.returncode and not requested_stop:
            raise CommandError('Сервер завершился с ошибкой.')
