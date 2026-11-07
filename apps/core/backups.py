"""Private, complete SQLite snapshots with media and verified recovery to a new directory."""
import hashlib
from contextlib import closing
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
from tempfile import TemporaryDirectory
import time
from zipfile import ZipFile, ZIP_DEFLATED

from django.conf import settings
from django.utils import timezone


def digest(data):
    return hashlib.sha256(data).hexdigest()


def create_backup(*, force=False):
    if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.sqlite3':
        raise ValueError('Полный архив поддерживает SQLite. Для PostgreSQL настройте отдельный pg_dump и копирование media.')
    database = Path(settings.DATABASES['default']['NAME'])
    if not database.is_file():
        raise ValueError('Рабочая база не найдена.')
    root = settings.DATA_DIR / 'backups'
    root.mkdir(parents=True, exist_ok=True)
    archives = sorted(root.glob('site-full-*.zip'), key=lambda path: path.stat().st_mtime, reverse=True)
    if not force and archives and time.time() - archives[0].stat().st_mtime < 86400:
        return archives[0]
    lock = root / '.backup.lock'
    if lock.exists() and time.time() - lock.stat().st_mtime > 3600:
        lock.unlink(missing_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return None
    os.close(descriptor)
    target = root / f'site-full-{timezone.now():%Y%m%dT%H%M%S}-{time.time_ns()}.zip'
    partial = target.with_suffix('.partial')
    try:
        with TemporaryDirectory(dir=root) as temporary:
            snapshot = Path(temporary) / 'db.sqlite3'
            with closing(sqlite3.connect(f'{database.resolve().as_uri()}?mode=ro', uri=True)) as source, closing(sqlite3.connect(snapshot)) as destination:
                source.backup(destination, pages=256)
                if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Проверка целостности базы не пройдена.')
            manifest = {'format': 1, 'created_at': timezone.now().isoformat(), 'files': {}}
            with ZipFile(partial, 'w', ZIP_DEFLATED) as archive:
                files = [('db.sqlite3', snapshot)]
                media = Path(settings.MEDIA_ROOT).resolve()
                if media.is_dir():
                    files += [('media/' + path.relative_to(media).as_posix(), path) for path in media.rglob('*')
                        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(media)]
                for name, path in files:
                    data = path.read_bytes()
                    manifest['files'][name] = digest(data)
                    archive.writestr(name, data)
                archive.writestr('manifest.json', json.dumps(manifest))
            os.replace(partial, target)
        # Rotate only this feature's generated archives, never unrelated backups.
        for old in sorted(root.glob('site-full-*.zip'), key=lambda path: path.stat().st_mtime, reverse=True)[7:]:
            old.unlink()
        return target
    finally:
        partial.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def verify_or_restore(archive_path, destination=None):
    target = Path(destination).resolve() if destination else None
    if target and target.exists() and any(target.iterdir()):
        raise ValueError('Восстановление разрешено только в новую или пустую папку. Рабочая база не перезаписывается.')
    with ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 1 or 'db.sqlite3' not in manifest.get('files', {}):
            raise ValueError('Неподдерживаемый формат резервной копии.')
        names = manifest['files']
        if set(archive.namelist()) != set(names) | {'manifest.json'} or len(archive.namelist()) != len(names) + 1:
            raise ValueError('Состав архива отличается от манифеста.')
        for name, checksum in names.items():
            path = PurePosixPath(name)
            if '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or not (name == 'db.sqlite3' or name.startswith('media/')):
                raise ValueError('Недопустимый путь в архиве.')
            if digest(archive.read(name)) != checksum:
                raise ValueError('Контрольная сумма файла не совпала.')
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / 'db.sqlite3'
            database.write_bytes(archive.read('db.sqlite3'))
            with closing(sqlite3.connect(database)) as connection:
                if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Резервная база повреждена.')
        if target:
            target.mkdir(parents=True, exist_ok=True)
            for name in names:
                path = target / name
                if not path.resolve().is_relative_to(target):
                    raise ValueError('Недопустимый путь восстановления.')
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('xb') as output:
                    output.write(archive.read(name))
        return {'files': len(names), 'created_at': manifest['created_at'], 'restored': bool(target)}
