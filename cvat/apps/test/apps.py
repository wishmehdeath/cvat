# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

from django.apps import AppConfig


class TestConfig(AppConfig):
    name = "cvat.apps.test"
    label = "cvat_test"
    verbose_name = "CVAT Real-Time Analytics Test Module"

    def ready(self):
        # Register signals and annotation mutation hooks
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
