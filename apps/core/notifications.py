import json
import logging
from hashlib import sha256
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import BookingRequest, SiteSettings

logger = logging.getLogger(__name__)


def send_notification(site, subject, text, message_key):
    """Return a safe status; provider responses and credentials stay off admin pages."""
    if not site or not site.notification_email or not settings.RESEND_API_KEY or not settings.DEFAULT_FROM_EMAIL:
        return (BookingRequest.Notification.UNCONFIGURED,
                'Укажите почту получателя, RESEND_API_KEY и DEFAULT_FROM_EMAIL.')
    payload = json.dumps({
        'from': settings.DEFAULT_FROM_EMAIL,
        'to': [site.notification_email],
        'subject': subject,
        'text': text,
    }).encode('utf-8')
    # A changed recipient/sender is a new delivery, while retries remain idempotent.
    route = sha256(f'{settings.DEFAULT_FROM_EMAIL}\n{site.notification_email}'.encode()).hexdigest()[:24]
    request = Request('https://api.resend.com/emails', data=payload, method='POST', headers={
        'Authorization': f'Bearer {settings.RESEND_API_KEY}',
        'Content-Type': 'application/json',
        'User-Agent': 'SurgerySite/1.0',
        'Idempotency-Key': f'{message_key}/{route}',
    })
    try:
        with urlopen(request, timeout=6) as response:
            if not 200 <= response.status < 300:
                raise URLError('Unexpected status')
            result = json.loads(response.read(16384))
            if not isinstance(result, dict) or not isinstance(result.get('id'), str) or not result['id']:
                raise ValueError('Missing message ID')
        return BookingRequest.Notification.SENT, ''
    except HTTPError as exc:
        errors = {
            401: 'Ключ Resend отклонён. Проверьте RESEND_API_KEY на сервере.',
            403: 'Resend запретил отправку. Проверьте отправителя, подтверждение домена и права ключа. '
                 'С onboarding@resend.dev можно отправлять только на почту владельца аккаунта Resend.',
            429: 'Достигнут лимит Resend. Повторите отправку позже.',
        }
        error = errors.get(exc.code, 'Почтовый сервис отклонил отправку. Проверьте его настройки и повторите.')
        logger.warning('Email service rejected notification (HTTP %s)', exc.code)
        return BookingRequest.Notification.FAILED, error
    except (URLError, OSError, ValueError):
        logger.warning('Email service did not confirm notification')
        return (BookingRequest.Notification.FAILED,
                'Почтовый сервис не подтвердил отправку. Проверьте настройки и повторите.')


def send_test_notification(site):
    return send_notification(site, 'Проверка уведомлений сайта',
        'Это тестовое письмо из админки сайта.\n'
        'Уведомления о новых заявках будут приходить на этот адрес.\n'
        'Тест не создаёт заявку и не содержит данных пациентов.', f'test/{uuid4()}')


def notify_booking(booking):
    site = SiteSettings.objects.order_by('pk').first()
    booking.notification_status, booking.notification_error = send_notification(site,
        f'Новая заявка на приём #{booking.pk}',
        f'Заявка #{booking.pk}\nИмя: {booking.name}\nТелефон: {booking.phone}\n'
        'Заявка сохранена в разделе «Заявки на приём» в админке сайта.', f'booking/{booking.pk}')
    booking.save(update_fields=['notification_status', 'notification_error'])
    return booking.notification_status
