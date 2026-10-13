# employees/urls.py
from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    path('artisans/', views.employee_list, name='employee_list'),
    path('artisans/add/', views.employee_create, name='employee_create'),
    path('artisans/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('artisans/<int:pk>/edit/', views.employee_update, name='employee_update'),
    path('artisans/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    path('leave/<int:leave_id>/status/<str:status>/', views.update_leave_status, name='update_leave_status'),
    path('artisans/<int:employee_id>/contract/add/', views.contract_create, name='contract_create'),
    path('artisans/<int:employee_id>/leave/add/', views.leave_create, name='leave_create'),
]