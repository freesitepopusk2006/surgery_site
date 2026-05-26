import re
from pathlib import Path
from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.core.models import PatientCategory, PatientPage, PatientPageSection


PART_RE = re.compile(
    r'\n\s*(\d+)\s+part\s+-\s+"([^"]+)":\s+"(.*?)"\s*,?\s*(?=\n\s*\d+\s+part\s+-|\Z)',
    re.DOTALL,
)


class Command(BaseCommand):
    help = 'Imports patient pages from parsed text files into admin-editable models.'

    def add_arguments(self, parser):
        parser.add_argument('data_dir', help='Path to the parse/data directory.')
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Replace existing sections for imported pages.',
        )

    def handle(self, *args, **options):
        data_dir = Path(options['data_dir'])
        index_path = data_dir / 'index.txt'

        if not index_path.exists():
            raise CommandError(f'index.txt not found: {index_path}')

        rows = self._read_index(index_path)
        if not rows:
            raise CommandError('No pages found in index.txt.')

        stats = {'categories': 0, 'pages': 0, 'sections': 0, 'skipped': 0}

        with transaction.atomic():
            for order, row in enumerate(rows, start=1):
                file_path = data_dir / row['relative_path']
                if not file_path.exists():
                    stats['skipped'] += 1
                    self.stdout.write(self.style.WARNING(f'Skipped missing file: {file_path}'))
                    continue

                parsed = self._parse_page(file_path)
                category, category_created = PatientCategory.objects.get_or_create(
                    title=row['category'],
                    defaults={
                        'slug': self._unique_slug(PatientCategory, row['category'], row['category']),
                        'order': self._category_order(row['category']),
                        'is_published': True,
                    },
                )
                if not category_created:
                    category.order = self._category_order(row['category'])
                    category.is_published = True
                    category.save(update_fields=['order', 'is_published'])
                if category_created:
                    stats['categories'] += 1

                page_slug = row['slug'] or self._unique_slug(PatientPage, parsed['title'], parsed['title'])
                page, _ = PatientPage.objects.update_or_create(
                    slug=page_slug,
                    defaults={
                        'category': category,
                        'title': parsed['title'],
                        'description': parsed['description'],
                        'order': order,
                        'is_published': True,
                        'source_url': row['source_url'],
                    },
                )
                stats['pages'] += 1

                if options['replace']:
                    page.sections.all().delete()

                for section_order, section in enumerate(parsed['sections'], start=1):
                    PatientPageSection.objects.update_or_create(
                        page=page,
                        order=section_order,
                        defaults={
                            'title': section['title'],
                            'content': self._normalize_content(section['content']),
                        },
                    )
                    stats['sections'] += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Import finished: {pages} pages, {sections} sections, {categories} new categories, {skipped} skipped.'
                .format(**stats)
            )
        )

    def _read_index(self, index_path):
        rows = []
        for line in self._read_text(index_path).splitlines():
            if not line.startswith('OK | '):
                continue

            parts = [part.strip() for part in line.split('|')]
            if len(parts) < 5:
                continue

            source_url = parts[3]
            rows.append({
                'category': parts[1],
                'source_url': source_url,
                'slug': self._slug_from_url(source_url),
                'relative_path': Path(parts[4]),
            })
        return rows

    def _parse_page(self, file_path):
        text = self._read_text(file_path)
        title_match = re.search(r'^Title:\s*(.+)$', text, re.MULTILINE)
        description_match = re.search(r'Desription:\s+"(.*?)"\s*\n\s*1\s+part\s+-', text, re.DOTALL)

        if not title_match:
            raise CommandError(f'Title not found in {file_path}')

        sections = [
            {'title': match.group(2).strip(), 'content': match.group(3).strip()}
            for match in PART_RE.finditer(text)
        ]

        return {
            'title': title_match.group(1).strip(),
            'description': description_match.group(1).strip() if description_match else '',
            'sections': sections,
        }

    def _normalize_content(self, content):
        lines = []
        for line in content.replace('\r\n', '\n').split('\n'):
            stripped = line.strip()
            if not stripped:
                lines.append('')
                continue

            if len(stripped) < 180 and stripped.endswith(';'):
                stripped = stripped[:-1].rstrip() + '.'
            elif len(stripped) < 180 and stripped[-1] not in '.!?:»")':
                stripped = stripped + '.'

            lines.append(stripped)

        return '\n'.join(lines).strip()

    def _read_text(self, path):
        for encoding in ('utf-8-sig', 'utf-8', 'cp1251'):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise CommandError(f'Could not read text file: {path}')

    def _slug_from_url(self, url):
        path = urlparse(url).path.strip('/')
        return path.split('/')[-1] if path else ''

    def _unique_slug(self, model, value, fallback):
        base = slugify(value, allow_unicode=True) or slugify(fallback, allow_unicode=True) or 'page'
        slug = base
        counter = 2
        while model.objects.filter(slug=slug).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug

    def _category_order(self, title):
        order = {
            'Памятки пациенту': 10,
            'Катаракта, замена хрусталика, факоэмульсификация': 20,
            'Диабетическая ретинопатия': 30,
            'Возрастная макулярная дегенерация (Макулодистрофия)': 40,
            'Глаукома': 50,
            'Искусственный хрусталик (Интраокулярные линзы)': 60,
            'Интравитреальные инъекции': 70,
            'Интересное': 80,
        }
        return order.get(title, 100)
