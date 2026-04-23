from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
# Make sure to import your views! (Adjust the import path if your views are in a different app folder)
from .views import AnalyzeLeafView, ScanHistoryView, UserProfileView, RegisterView, VerifyOTPView, PendingScansView, SubmitReviewView, AgronomistDashboardView, SavePushTokenView, LiveWeatherView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # --- NEW: JWT LOGIN ENDPOINTS ---
    path('api/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # --- YOUR EXISTING APP ENDPOINTS ---
    path('api/analyze-leaf/', AnalyzeLeafView.as_view(), name='analyze_leaf'),
    path('api/scan-history/', ScanHistoryView.as_view(), name='scan_history'),
    path('api/profile/', UserProfileView.as_view(), name='user_profile'),
    path('api/register/', RegisterView.as_view(), name='register'),
    path('api/verify-otp/', VerifyOTPView.as_view(), name='verify_otp'),
    path('api/pending-scans/', PendingScansView.as_view(), name='pending_scans'),
    path('api/review-scan/<int:scan_id>/', SubmitReviewView.as_view(), name='review_scan'),
    path('api/expert/dashboard/', AgronomistDashboardView.as_view(), name='expert_dashboard'),
    path('api/save-push-token/', SavePushTokenView.as_view(), name='save_push_token'),
    path('api/weather/', LiveWeatherView.as_view(), name='live_weather'),
]