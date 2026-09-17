# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""
ASGI config for CVAT project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from django.core.handlers.asgi import ASGIHandler

import cvat.utils.remote_debugger as debug

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cvat.settings.development")

django_application = get_asgi_application()

if debug.is_debugging_enabled():

    class DebuggerApp(ASGIHandler):
        """
        Support for VS code debugger
        """

        def __init__(self) -> None:
            super().__init__()
            self.__debugger = debug.RemoteDebugger()

        async def handle(self, *args, **kwargs):
            self.__debugger.attach_current_thread()
            return await super().handle(*args, **kwargs)

    django_application = DebuggerApp()


async def application(scope, receive, send):
    """
    CVAT unified ASGI 3.0 router supporting both standard Django HTTP requests
    and real-time WebSocket connections.
    """
    if scope["type"] == "websocket":
        path = scope.get("path", "")
        if path.startswith("/ws/test/analytics") or path.startswith("/ws/analytics"):
            from cvat.apps.test.websocket_routing import websocket_analytics_handler
            await websocket_analytics_handler(scope, receive, send)
            return

        # Fallback rejection for unknown websocket paths
        await send({"type": "websocket.close", "code": 4404})
        return

    # HTTP requests pass through to Django ASGI application
    await django_application(scope, receive, send)

