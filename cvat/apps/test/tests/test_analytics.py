# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import asyncio
from unittest.mock import MagicMock, patch
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from cvat.apps.engine.models import (
    Data,
    Job,
    Label,
    LabeledImage,
    LabeledShape,
    Segment,
    ShapeType,
    Task,
)
from cvat.apps.test.services import AnalyticsService
from cvat.apps.test.websocket_routing import ConnectionGroupManager, broadcast_analytics_update


class AnalyticsServiceTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create Task Data
        self.data = Data.objects.create(size=10)

        # Create Task
        self.task = Task.objects.create(
            name="Analytics Test Task",
            data=self.data,
        )

        # Create Segment and Job
        self.segment = Segment.objects.create(
            task=self.task,
            start_frame=0,
            stop_frame=9,
        )
        self.job = Job.objects.create(segment=self.segment)

        # Create Labels
        self.label_car = Label.objects.create(
            task=self.task,
            name="car",
            color="#ff0000",
        )
        self.label_person = Label.objects.create(
            task=self.task,
            name="person",
            color="#00ff00",
        )

    def test_class_wise_counts_aggregation(self):
        # Scenario:
        # Frame 0: 2 cars, 1 person
        # Frame 1: 1 car
        # Frame 2: 1 person
        # Frames 3..9: unannotated
        LabeledShape.objects.create(
            job=self.job,
            label=self.label_car,
            frame=0,
            type=ShapeType.RECTANGLE,
            points=[10, 10, 50, 50],
        )
        LabeledShape.objects.create(
            job=self.job,
            label=self.label_car,
            frame=0,
            type=ShapeType.RECTANGLE,
            points=[60, 60, 90, 90],
        )
        LabeledShape.objects.create(
            job=self.job,
            label=self.label_person,
            frame=0,
            type=ShapeType.RECTANGLE,
            points=[100, 100, 120, 150],
        )

        LabeledShape.objects.create(
            job=self.job,
            label=self.label_car,
            frame=1,
            type=ShapeType.RECTANGLE,
            points=[20, 20, 40, 40],
        )

        LabeledImage.objects.create(
            job=self.job,
            label=self.label_person,
            frame=2,
        )

        result = AnalyticsService.get_class_wise_counts(task_id=self.task.id)

        self.assertIn("summary", result)
        self.assertIn("classes", result)

        summary = result["summary"]
        self.assertEqual(summary["total_images"], 10)
        self.assertEqual(summary["annotated_images"], 3)  # Frames 0, 1, 2
        self.assertEqual(summary["unannotated_images"], 7)  # Frames 3..9
        self.assertEqual(summary["total_annotations"], 5)  # 4 shapes + 1 tag

        classes_map = {c["label_name"]: c for c in result["classes"]}

        # 'car' should be in 2 distinct images (frames 0 and 1) with 3 total shapes
        self.assertEqual(classes_map["car"]["image_count"], 2)
        self.assertEqual(classes_map["car"]["annotation_count"], 3)
        self.assertEqual(classes_map["car"]["percentage_of_total_images"], 20.0)

        # 'person' should be in 2 distinct images (frames 0 and 2) with 2 total annotations
        self.assertEqual(classes_map["person"]["image_count"], 2)
        self.assertEqual(classes_map["person"]["annotation_count"], 2)
        self.assertEqual(classes_map["person"]["percentage_of_total_images"], 20.0)

    def test_class_wise_counts_api_view(self):
        url = reverse("class-wise-counts")

        # Missing params -> 400
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-existent task -> 404
        resp = self.client.get(f"{url}?task_id=999999")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # Valid task
        resp = self.client.get(f"{url}?task_id={self.task.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("classes", resp.data)
        self.assertIn("summary", resp.data)

    def test_simulate_annotation_update_api_view(self):
        url = reverse("simulate-update")
        resp = self.client.post(url, {"task_id": self.task.id}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "broadcast_sent")


class WebSocketConnectionManagerTestCase(TestCase):
    def test_connection_group_manager(self):
        async def run_test():
            manager = ConnectionGroupManager()
            q1 = asyncio.Queue()
            q2 = asyncio.Queue()

            room1 = await manager.register(task_id=1, job_id=None, queue=q1)
            room2 = await manager.register(task_id=1, job_id=None, queue=q2)

            self.assertEqual(room1, "task_1")
            self.assertEqual(len(manager._rooms["task_1"]), 2)

            await manager.broadcast_to_room("task_1", {"msg": "hello"})

            msg1 = await q1.get()
            msg2 = await q2.get()
            self.assertIn("hello", msg1)
            self.assertIn("hello", msg2)

            await manager.unregister(room1, q1)
            self.assertEqual(len(manager._rooms["task_1"]), 1)
            await manager.unregister(room1, q2)
            self.assertNotIn("task_1", manager._rooms)

        asyncio.run(run_test())
