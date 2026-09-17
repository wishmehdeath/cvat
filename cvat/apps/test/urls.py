# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

from django.urls import path
from .views import (
    ClassWiseImageCountView,
    AnalyticsOverviewView,
    SimulateAnnotationUpdateView,
)

urlpatterns = [
    path("test/analytics/class-counts/", ClassWiseImageCountView.as_view(), name="class-wise-counts"),
    path("test/analytics/overview/", AnalyticsOverviewView.as_view(), name="analytics-overview"),
    path("test/analytics/simulate-update/", SimulateAnnotationUpdateView.as_view(), name="simulate-update"),
]
