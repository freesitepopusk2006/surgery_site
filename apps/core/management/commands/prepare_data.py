from pathlib import Path
from shutil import copy2

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Prepare writable data storage; preserve the existing bundled database and media on first startup.'

    def handle(self, *args, **options):
        database = settings.DATABASES['default']
        legacy_db = settings.BASE_DIR / 'db.sqlite3'
        if database['ENGINE'] == 'django.db.backends.sqlite3':
            target = Path(database['NAME'])
            if not target.exists() and legacy_db.exists() and target.resolve() != legacy_db.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                copy2(legacy_db, target)
                self.stdout.write('Existing database copied to writable data storage. Original preserved.')
        legacy_media = settings.BASE_DIR / 'media'
        target_media = Path(settings.MEDIA_ROOT)
        if legacy_media.exists() and legacy_media.resolve() != target_media.resolve():
            for source in legacy_media.rglob('*'):
                if source.is_file():
                    target = target_media / source.relative_to(legacy_media)
                    if not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        copy2(source, target)
        self.stdout.write(self.style.SUCCESS('Writable data storage is ready.'))
