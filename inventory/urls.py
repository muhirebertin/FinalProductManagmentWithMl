# inventory/urls.py
from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('materials/', views.material_list, name='material_list'),
    path('products/', views.product_list, name='product_list'),
    path('materials/add/', views.material_create, name='material_create'),
    path('materials/<int:pk>/edit/', views.material_update, name='material_update'),
    path('materials/<int:pk>/delete/', views.material_delete, name='material_delete'),
    path('materials/<int:pk>/', views.material_detail, name='material_detail'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/add/', views.product_create, name='product_create'),
    path('products/<int:pk>/edit/', views.product_update, name='product_update'),
    path('products/<int:pk>/delete/', views.product_delete, name='product_delete'),
]