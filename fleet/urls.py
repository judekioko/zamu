from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('signup/', views.signup, name='signup'),
    path('vehicles/add/', views.vehicle_form, name='vehicle_add'),
    path('vehicles/<int:pk>/', views.vehicle_detail, name='vehicle'),
    path('vehicles/<int:pk>/edit/', views.vehicle_form, name='vehicle_edit'),
    path('vehicles/<int:pk>/paid/', views.quick_paid, name='quick_paid'),
    path('vehicles/<int:pk>/off/', views.mark_off, name='mark_off'),
    path('vehicles/<int:pk>/move/', views.move_vehicle, name='move'),
    path('vehicles/<int:pk>/expense/', views.add_expense, name='add_expense'),
    path('remittance/<int:pk>/delete/', views.delete_remittance, name='delete_remittance'),
    path('expense/<int:pk>/delete/', views.delete_expense, name='delete_expense'),
    path('report/', views.report, name='report'),
]
