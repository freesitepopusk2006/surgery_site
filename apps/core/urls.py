from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('prices/', views.prices_view, name='prices'),
    path('patients/', views.patients_view, name='patients'),
    path('patients/<str:slug>/', views.patient_page_detail_view, name='patient_page_detail'),
    path('pages/<str:slug>/', views.site_page_view, name='site_page'),
    path('privacy/', views.site_page_view, {'slug': 'privacy'}, name='privacy'),
    path('booking/', views.booking_view, name='booking'),
    path('booking/slots/', views.appointment_slots_view, name='appointment_slots'),
    path('booking/reserve/', views.appointment_booking_view, name='appointment_booking'),
    path('robots.txt', views.robots_view, name='robots'),
    path('sitemap.xml', views.sitemap_view, name='sitemap'),
]
