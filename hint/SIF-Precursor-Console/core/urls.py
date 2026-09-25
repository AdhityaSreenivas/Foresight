from django.urls import path

from .views import (
    home,
    register_view,
    login_view,
    logout_view,
    analyze_report,
    upload_reports,
    history_view,
    pattern_analytics_view,
)


urlpatterns = [

    path(
        "",
        home,
        name="home"
    ),

    path(
        "register/",
        register_view,
        name="register"
    ),

    path(
        "login/",
        login_view,
        name="login"
    ),

    path(
        "logout/",
        logout_view,
        name="logout"
    ),

    path(
        "analyze/",
        analyze_report,
        name="analyze_report"
    ),

    path(
        "upload-reports/",
        upload_reports,
        name="upload_reports"
    ),

    path(
        "history/",
        history_view,
        name="history"
    ),

    path(
        "analytics/",
        pattern_analytics_view,
        name="analytics"
    ),
]
