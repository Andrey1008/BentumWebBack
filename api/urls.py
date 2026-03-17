from django.urls import path
from .views import save_data, dashboard, logout, theme, get_schedule, get_literature, get_news
from .profile_views import update_profile, update_avatar, update_banner
from .support_views import submit_support_request, test_telegram_connection, test_new_user_notification, send_new_user_notification
from .user_views import get_all_users, get_users_stats, create_user, ban_user, unban_user
from .admin_views import appoint_administrator, remove_administrator, get_administrators, get_administration_history
from .ban_views import get_ban_info
from . import media_views

urlpatterns = [
    path("api/save_data", save_data),
    path("api/dashboard", dashboard),
    path("api/logout", logout),
    path("api/theme", theme),
    path("api/schedule", get_schedule),
    path("api/literature", get_literature),
    path("api/news", get_news),
    path("api/profile/update", update_profile),
    path("api/profile/avatar", update_avatar),
    path("api/profile/banner", update_banner),
    path("api/ban/info", get_ban_info),
    # Support endpoints
    path("api/support/submit", submit_support_request),
    path("api/support/test", test_telegram_connection),
    path("api/support/test-user-notification", test_new_user_notification),
    path("api/support/send-user-notification", send_new_user_notification),
    # Admin user management endpoints
    path("api/admin/users", get_all_users),
    path("api/admin/users/stats", get_users_stats),
    path("api/admin/users/create", create_user),
    path("api/admin/users/ban", ban_user),
    path("api/admin/users/unban", unban_user),
    # Admin management endpoints
    path("api/admin/administrators/appoint", appoint_administrator),
    path("api/admin/administrators/remove", remove_administrator),
    path("api/admin/administrators", get_administrators),
    path("api/admin/administrators/history", get_administration_history),
    # Media upload endpoints
    path("api/media/upload", media_views.upload_media),
    path("api/media/set-active", media_views.set_active_media),
    path("api/media/get", media_views.get_user_media),
    path("api/media/delete/<int:media_id>", media_views.delete_media),
]
