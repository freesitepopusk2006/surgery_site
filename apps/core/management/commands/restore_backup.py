import json
from django.core.management.base import BaseCommand, CommandError
from apps.core.backups import verify_or_restore


class Command(BaseCommand):
    help = 'Проверить полный архив; с --destination восстановить только в пустую папку, сохранив рабочие данные.'

    def add_arguments(self, parser):
        parser.add_argument('archive')
        parser.add_argument('--destination')

    def handle(self, *args, **options):
        try:
            result = verify_or_restore(options['archive'], options['destination'])
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
