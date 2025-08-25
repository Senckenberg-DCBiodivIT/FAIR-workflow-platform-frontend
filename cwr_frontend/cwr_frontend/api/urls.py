# urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('workflows', views.SubmitWorkflowView.as_view(), name='submit-workflow-api'),
    path('workflows/<str:workflow_id>', views.WorkflowStatusView.as_view(), name='workflow-status-api'),
    path('workflows/<str:workflow_id>/download', views.WorkflowDownloadView.as_view(), name='workflow-download-api'),
    
]
