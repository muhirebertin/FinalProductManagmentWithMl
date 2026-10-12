# employees/urls.py
from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    path('artisans/', views.employee_list, name='employee_list'),
    path('artisans/add/', views.employee_create, name='employee_create'),

    # New Dynamic URLs
    path('artisans/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('artisans/<int:pk>/edit/', views.employee_update, name='employee_update'),
    path('artisans/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
]