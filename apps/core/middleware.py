from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import AdminLoginThrottle


class FormProtectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.path.startswith('/booking/'):
            try:
                too_large = int(request.META.get('CONTENT_LENGTH') or 0) > 8192
            except ValueError:
                too_large = True
            if too_large:
                return JsonResponse({'ok': False, 'error': 'Слишком большой запрос.'}, status=413)
        login = request.method == 'POST' and request.path == '/admin/login/'
        if not login:
            return self.get_response(request)
        now = timezone.now()
        cutoff = now - timedelta(minutes=15)
        key = salted_hmac('admin-login', request.META.get('REMOTE_ADDR', ''), secret=settings.SECRET_KEY).hexdigest()
        attempt = AdminLoginThrottle.objects.filter(key=key, window_start__gt=cutoff, failures__gte=5).first()
        if attempt:
            seconds = max(1, int((attempt.window_start + timedelta(minutes=15) - now).total_seconds()))
            response = render(request, 'admin/login_wait.html', {'title': 'Пауза перед входом',
                'retry_minutes': max(1, (seconds + 59) // 60)}, status=429)
            response['Retry-After'] = str(seconds)
            return response
        response = self.get_response(request)
        if response.status_code == 302 and getattr(request, 'user', None) and request.user.is_authenticated:
            AdminLoginThrottle.objects.filter(key=key).delete()
        elif response.status_code == 200:
            AdminLoginThrottle.objects.get_or_create(key=key, defaults={'window_start': now})
            reset = AdminLoginThrottle.objects.filter(key=key, window_start__lte=cutoff).update(failures=1, window_start=now)
            if not reset:
                AdminLoginThrottle.objects.filter(key=key).update(failures=F('failures') + 1)
        return response
