# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cvat.apps.engine.models import Job, Task
from .services import AnalyticsService
from .websocket_routing import broadcast_analytics_update


class ClassWiseImageCountView(APIView):
    """
    API endpoint for retrieving class-wise image counts and dataset annotation metrics.
    Aggregates annotations from LabeledImage, LabeledShape, and TrackedShape.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Retrieve class-wise image counts and annotation metrics",
        description=(
            "Calculates the distinct image/frame count for each class label within a task, job, or project, "
            "as well as annotation totals and dataset coverage percentages."
        ),
        parameters=[
            OpenApiParameter(
                name="task_id",
                type=int,
                required=False,
                description="Filter analytics by specific Task ID",
            ),
            OpenApiParameter(
                name="job_id",
                type=int,
                required=False,
                description="Filter analytics by specific Job ID",
            ),
            OpenApiParameter(
                name="project_id",
                type=int,
                required=False,
                description="Filter analytics by Project ID",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Class-wise analytics data"),
            400: OpenApiResponse(description="Missing required filter parameters"),
            404: OpenApiResponse(description="Target task, job, or project not found"),
        },
    )
    def get(self, request, *args, **kwargs):
        task_id = request.query_params.get("task_id")
        job_id = request.query_params.get("job_id")
        project_id = request.query_params.get("project_id")

        task_id = int(task_id) if task_id and task_id.isdigit() else None
        job_id = int(job_id) if job_id and job_id.isdigit() else None
        project_id = int(project_id) if project_id and project_id.isdigit() else None

        data = AnalyticsService.get_class_wise_counts(
            task_id=task_id,
            job_id=job_id,
            project_id=project_id,
        )
        return Response(data, status=status.HTTP_200_OK)


class AnalyticsOverviewView(APIView):
    """
    API view providing a high-level list of tasks with quick access to their class-wise counts.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        tasks = Task.objects.select_related("data", "project").all().order_by("-id")[:20]
        summary_list = []
        for task in tasks:
            summary_list.append({
                "task_id": task.id,
                "task_name": task.name,
                "project_id": task.project_id,
                "total_frames": task.data.size if (task.data and task.data.size) else 0,
                "status": task.status,
                "analytics_url": f"/api/test/analytics/class-counts/?task_id={task.id}",
                "websocket_url": f"/ws/test/analytics/?task_id={task.id}",
            })
        return Response({"tasks": summary_list}, status=status.HTTP_200_OK)


class SimulateAnnotationUpdateView(APIView):
    """
    Utility endpoint to trigger a simulated annotation change event and broadcast
    real-time class-wise count updates to all connected WebSocket clients.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        task_id = request.data.get("task_id") or request.query_params.get("task_id")
        job_id = request.data.get("job_id") or request.query_params.get("job_id")

        task_id = int(task_id) if task_id and str(task_id).isdigit() else None
        job_id = int(job_id) if job_id and str(job_id).isdigit() else None

        if not task_id and not job_id:
            return Response(
                {"error": "Please provide 'task_id' or 'job_id'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Broadcast update to WebSocket clients
        count = broadcast_analytics_update(task_id=task_id, job_id=job_id)

        # Fetch latest metrics
        latest_data = AnalyticsService.get_class_wise_counts(task_id=task_id, job_id=job_id)

        return Response(
            {
                "status": "broadcast_sent",
                "connected_clients_notified": count,
                "latest_analytics": latest_data,
            },
            status=status.HTTP_200_OK,
        )
