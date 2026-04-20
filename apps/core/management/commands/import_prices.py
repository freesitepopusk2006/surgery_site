import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core.models import PriceItem


HEADER_ALIASES = {
    'title': {'title', 'name', 'service', 'service_name', 'услуга', 'название', 'название услуги', 'наименование'},
    'description': {'description', 'desc', 'описание'},
    'price_text': {'price', 'price_text', 'cost', 'цена', 'стоимость', 'цена / подпись цены'},
    'order': {'order', 'sort', 'position', 'порядок', 'сортировка'},
    'is_active': {'is_active', 'active', 'published', 'активно', 'показывать', 'опубликовано'},
}

TRUE_VALUES = {'1', 'true', 'yes', 'y', 'да', 'истина', 'активно', 'показывать'}
FALSE_VALUES = {'0', 'false', 'no', 'n', 'нет', 'ложь', 'неактивно', 'скрыть'}


class Command(BaseCommand):
    help = 'Imports services and prices from a CSV file into the PriceItem model.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', help='Path to a CSV file with services and prices.')
        parser.add_argument(
            '--deactivate-missing',
            action='store_true',
            help='Deactivate existing prices that are not present in the imported file.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate and show import statistics without saving changes.',
        )

    def handle(self, *args, **options):
        csv_path = Path(options['csv_file'])
        if not csv_path.exists():
            raise CommandError(f'File not found: {csv_path}')
        if csv_path.suffix.lower() != '.csv':
            raise CommandError('Only CSV files are supported. Save your table as .csv and run the command again.')

        rows = self._read_rows(csv_path)
        if not rows:
            raise CommandError('CSV file is empty.')

        imported_titles = set()
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'deactivated': 0}

        with transaction.atomic():
            for index, row in enumerate(rows, start=2):
                data = self._normalize_row(row)
                title = data.get('title', '').strip()

                if not title:
                    stats['skipped'] += 1
                    self.stdout.write(self.style.WARNING(f'Row {index}: skipped because title is empty.'))
                    continue

                imported_titles.add(title)
                defaults = {
                    'description': data.get('description', '').strip(),
                    'price_text': data.get('price_text', '').strip(),
                    'order': self._parse_order(data.get('order'), index),
                    'is_active': self._parse_bool(data.get('is_active'), default=True),
                }

                _, created = PriceItem.objects.update_or_create(title=title, defaults=defaults)
                stats['created' if created else 'updated'] += 1

            if options['deactivate_missing'] and imported_titles:
                stats['deactivated'] = PriceItem.objects.exclude(title__in=imported_titles).update(is_active=False)

            if options['dry_run']:
                transaction.set_rollback(True)

        suffix = ' (dry run, nothing saved)' if options['dry_run'] else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Import finished%s: %s created, %s updated, %s skipped, %s deactivated.'
                % (suffix, stats['created'], stats['updated'], stats['skipped'], stats['deactivated'])
            )
        )

    def _read_rows(self, csv_path):
        content = self._read_text(csv_path)
        sample = content[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;')
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(content.splitlines(), dialect=dialect)
        if not reader.fieldnames:
            return []

        return list(reader)

    def _read_text(self, csv_path):
        for encoding in ('utf-8-sig', 'cp1251'):
            try:
                return csv_path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue

        raise CommandError('Could not read CSV file. Please save it as UTF-8 or Windows-1251 CSV.')

    def _normalize_row(self, row):
        normalized = {}
        for source_key, value in row.items():
            if source_key is None:
                continue

            key = source_key.strip().lower()
            for target_key, aliases in HEADER_ALIASES.items():
                if key in aliases:
                    normalized[target_key] = value or ''
                    break

        return normalized

    def _parse_order(self, raw_value, row_index):
        if raw_value in (None, ''):
            return row_index

        try:
            return int(str(raw_value).strip())
        except ValueError:
            return row_index

    def _parse_bool(self, raw_value, default):
        if raw_value in (None, ''):
            return default

        value = str(raw_value).strip().lower()
        if value in TRUE_VALUES:
            return True
        if value in FALSE_VALUES:
            return False
        return default
