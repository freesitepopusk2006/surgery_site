import hashlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from datetime import timedelta
from zipfile import ZipFile, ZIP_DEFLATED

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .backups import create_backup, verify_or_restore
from .models import AdminLoginThrottle


class LoginProtectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.create_superuser(username='operations-admin', password='test-only-password')

    def test_repeated_failed_login_is_paused_without_blocking_public_site(self):
        for _ in range(5):
            self.assertEqual(self.client.post('/admin/login/', {'username':'operations-admin','password':'wrong'}).status_code,200)
        response = self.client.post('/admin/login/', {'username':'operations-admin','password':'test-only-password'})
        self.assertEqual(response.status_code,429)
        self.assertGreater(int(response['Retry-After']),0)
        self.assertEqual(self.client.get('/').status_code,200)
        attempt=AdminLoginThrottle.objects.get()
        attempt.window_start=timezone.now()-timedelta(minutes=16)
        attempt.save()
        self.assertEqual(self.client.post('/admin/login/', {'username':'operations-admin','password':'test-only-password'}).status_code,302)
        self.assertFalse(AdminLoginThrottle.objects.exists())

    def test_oversized_booking_is_rejected_before_csrf_parses_it(self):
        client=Client(enforce_csrf_checks=True)
        response=client.post(reverse('core:appointment_booking'),{'name':'x'*9000})
        self.assertEqual(response.status_code,413)
        self.assertFalse(response.json()['ok'])

    def test_csrf_failure_does_not_count_as_a_password_guess(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/admin/login/', {'username':'operations-admin','password':'wrong'}).status_code,403)
        self.assertFalse(AdminLoginThrottle.objects.exists())


class BackupTests(SimpleTestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.database=self.root/'db.sqlite3'
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute('CREATE TABLE bookings (name TEXT, status TEXT)')
            connection.execute('INSERT INTO bookings VALUES (?,?)',('Synthetic visitor','confirmed'))
            connection.commit()
        self.media=self.root/'media'
        self.media.mkdir()
        (self.media/'sample.txt').write_text('Uploaded original',encoding='utf-8')
        self.override=override_settings(DATA_DIR=self.root,MEDIA_ROOT=self.media,
            DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':self.database}})
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_full_backup_restores_database_and_media_without_overwriting_source(self):
        archive=create_backup(force=True)
        target=self.root/'recovery'
        result=verify_or_restore(archive,target)
        self.assertTrue(result['restored'])
        with closing(sqlite3.connect(target/'db.sqlite3')) as connection:
            self.assertEqual(connection.execute('SELECT name,status FROM bookings').fetchone(),('Synthetic visitor','confirmed'))
        self.assertEqual((target/'media/sample.txt').read_text(),'Uploaded original')
        with self.assertRaises(ValueError):
            verify_or_restore(archive,self.root)

    def test_daily_check_does_not_create_duplicate_archives(self):
        first=create_backup(force=True)
        self.assertEqual(create_backup(),first)
        self.assertEqual(len(list((self.root/'backups').glob('site-full-*.zip'))),1)
        self.assertFalse(verify_or_restore(first)['restored'])

    def test_tampered_archive_is_rejected_before_any_files_are_restored(self):
        archive=create_backup(force=True)
        with ZipFile(archive) as source:
            files={name:source.read(name) for name in source.namelist()}
        files['media/sample.txt']=b'Changed content'
        damaged=self.root/'damaged.zip'
        with ZipFile(damaged,'w',ZIP_DEFLATED) as target:
            for name,data in files.items(): target.writestr(name,data)
        destination=self.root/'must-not-exist'
        with self.assertRaises(ValueError): verify_or_restore(damaged,destination)
        self.assertFalse(destination.exists())

    def test_path_traversal_is_rejected_even_with_a_matching_checksum(self):
        data=b'forbidden'
        archive=self.root/'unsafe.zip'
        manifest={'format':1,'created_at':'test','files':{'db.sqlite3':hashlib.sha256(self.database.read_bytes()).hexdigest(),
            'media/../../escape.txt':hashlib.sha256(data).hexdigest()}}
        with ZipFile(archive,'w') as output:
            output.write(self.database,'db.sqlite3')
            output.writestr('media/../../escape.txt',data)
            output.writestr('manifest.json',json.dumps(manifest))
        with self.assertRaises(ValueError): verify_or_restore(archive,self.root/'recovery')
