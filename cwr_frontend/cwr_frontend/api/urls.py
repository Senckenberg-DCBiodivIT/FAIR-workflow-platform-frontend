# urls.py
from django.urls import path
from . import views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('workflows', views.SubmitWorkflowView.as_view(), name='submit-workflow-api'),
    path('workflows/<str:workflow_id>', views.WorkflowStatusView.as_view(), name='workflow-status-api'),
    path('workflows/<str:workflow_id>/download', views.WorkflowDownloadView.as_view(), name='workflow-download-api'),
    path('schema/', SpectacularAPIView.as_view(), name = 'schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name = 'swagger-ui'),
    
]
