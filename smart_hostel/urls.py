from django.views.generic import TemplateView
from django.urls import path
from hostel import views

urlpatterns = [
    path('', TemplateView.as_view(template_name='hostel/index.html'), name='frontend'),
    path('api/health/', views.health),
    path('api/auth/register/', views.register_student),
    path('api/auth/login/', views.login),
    path('api/auth/me/', views.me),
    path('api/auth/password/', views.change_password),
    path('api/rooms/', views.rooms),
    path('api/categories/', views.categories),
    path('api/complaints/', views.complaints),
    path('api/complaints/summary/', views.complaint_summary),
    path('api/complaints/<int:complaint_id>/', views.complaint_detail),
    path('api/complaints/<int:complaint_id>/photos/', views.add_photo),
    path('api/complaints/<int:complaint_id>/photos/<int:photo_id>/', views.download_photo),
    path('api/complaints/<int:complaint_id>/assign/', views.assign),
    path('api/complaints/<int:complaint_id>/status/', views.update_status),
    path('api/complaints/<int:complaint_id>/feedback/', views.feedback),
    path('api/admin/dashboard/', views.dashboard),
    path('api/admin/rooms/', views.create_room),
    path('api/admin/categories/', views.create_category),
    path('api/admin/staff/', views.staff_collection),
    path('api/admin/staff/create/', views.create_staff),
    path('api/admin/staff/<int:staff_id>/', views.staff_member),
    path('api/admin/staff/<int:staff_id>/reset-password/', views.reset_staff_password),
    path('api/admin/students/', views.students),
    path('api/admin/escalate/', views.escalate),
    path('api/staff/workload/', views.workload),
]
