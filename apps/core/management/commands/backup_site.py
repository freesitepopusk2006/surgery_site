from django.core.management.base import BaseCommand, CommandError
from apps.core.backups import create_backup


class Command(BaseCommand):
    help = 'Полная приватная копия SQLite, заявок, пользователей и media. По умолчанию не чаще раза в сутки.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true')

    def handle(self, *args, **options):
        try:
            path = create_backup(force=options['force'])
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(str(path) if path else 'Резервная копия уже создаётся другим процессом.')
