import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .models import BookingRequest, SiteSettings

logger = logging.getLogger(__name__)


def notify_booking(booking):
    site = SiteSettings.objects.order_by('pk').first()
    if not site or not site.notification_email or not settings.RESEND_API_KEY or not settings.DEFAULT_FROM_EMAIL:
        booking.notification_status = BookingRequest.Notification.UNCONFIGURED
        booking.notification_error = 'Укажите почту получателя, RESEND_API_KEY и DEFAULT_FROM_EMAIL.'
    else:
        payload = json.dumps({
            'from': settings.DEFAULT_FROM_EMAIL,
            'to': [site.notification_email],
            'subject': f'Новая заявка на приём #{booking.pk}',
            'text': f'Заявка #{booking.pk}\nИмя: {booking.name}\nТелефон: {booking.phone}\n'
                    'Заявка сохранена в разделе «Заявки на приём» в админке сайта.',
        }).encode('utf-8')
        request = Request('https://api.resend.com/emails', data=payload, method='POST', headers={
            'Authorization': f'Bearer {settings.RESEND_API_KEY}',
            'Content-Type': 'application/json',
            'User-Agent': 'SurgerySite/1.0',
            'Idempotency-Key': f'booking/{booking.pk}',
        })
        try:
            with urlopen(request, timeout=6) as response:
                if not 200 <= response.status < 300:
                    raise URLError('Unexpected status')
                result = json.loads(response.read(16384))
                if not result.get('id'):
                    raise ValueError('Missing message ID')
            booking.notification_status = BookingRequest.Notification.SENT
            booking.notification_error = ''
        except (HTTPError, URLError, OSError, ValueError):
            logger.warning('Booking notification failed for request #%s', booking.pk)
            booking.notification_status = BookingRequest.Notification.FAILED
            booking.notification_error = 'Почтовый сервис не подтвердил отправку. Проверьте настройки и повторите.'
    booking.save(update_fields=['notification_status', 'notification_error'])
    return booking.notification_status
