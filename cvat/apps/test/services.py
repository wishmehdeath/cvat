# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

from collections import defaultdict
from itertools import chain
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from django.db.models import Count, Q
from rest_framework.exceptions import NotFound, ValidationError

from cvat.apps.engine.models import (
    Job,
    Label,
    LabeledImage,
    LabeledShape,
    LabeledTrack,
    Project,
    Task,
    TrackedShape,
)


class AnalyticsService:
    """
    Analytics service responsible for extracting annotation data across CVAT
    annotation entities (LabeledShape, LabeledImage, TrackedShape via LabeledTrack)
    and aggregating class-wise image counts and distribution metrics.
    """

    @staticmethod
    def get_class_wise_counts(
        *,
        task_id: Optional[int] = None,
        job_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculates class-wise unique image counts and annotation totals.

        An image (or video frame) can contain multiple instances of the same label
        (e.g., 4 bounding boxes for 'person' on frame 10).
        This method correctly calculates:
          - image_count: Number of DISTINCT images/frames containing label L.
          - annotation_count: Total individual annotations with label L.
          - total_images: Total frames in dataset/job segment.
          - annotated_images: Distinct images having at least one annotation.
          - unannotated_images: Images without any annotations.
        """
        if not any([task_id, job_id, project_id]):
            raise ValidationError("Either 'task_id', 'job_id', or 'project_id' parameter must be provided.")

        jobs_filter = Q()
        tracked_shapes_filter = Q()
        total_frames = 0
        target_entity = {}

        if job_id:
            try:
                job = Job.objects.select_related("segment__task", "segment__task__data").get(pk=job_id)
            except Job.DoesNotExist:
                raise NotFound(f"Job {job_id} does not exist.")

            task = job.segment.task
            jobs_filter = Q(job=job)
            tracked_shapes_filter = Q(track__job=job)
            total_frames = max(0, job.segment.stop_frame - job.segment.start_frame + 1)
            target_entity = {
                "scope": "job",
                "job_id": job.id,
                "task_id": task.id,
                "task_name": task.name,
                "segment_start": job.segment.start_frame,
                "segment_stop": job.segment.stop_frame,
            }
            labels_qs = Label.objects.filter(Q(task=task) | Q(project=task.project_id))

        elif task_id:
            try:
                task = Task.objects.select_related("data", "project").get(pk=task_id)
            except Task.DoesNotExist:
                raise NotFound(f"Task {task_id} does not exist.")

            jobs_filter = Q(job__segment__task=task)
            tracked_shapes_filter = Q(track__job__segment__task=task)
            total_frames = task.data.size if (task.data and task.data.size) else 0
            target_entity = {
                "scope": "task",
                "task_id": task.id,
                "task_name": task.name,
                "project_id": task.project_id,
            }
            labels_qs = Label.objects.filter(Q(task=task) | Q(project=task.project_id))

        elif project_id:
            try:
                project = Project.objects.get(pk=project_id)
            except Project.DoesNotExist:
                raise NotFound(f"Project {project_id} does not exist.")

            jobs_filter = Q(job__segment__task__project=project)
            tracked_shapes_filter = Q(track__job__segment__task__project=project)
            tasks = Task.objects.filter(project=project).select_related("data")
            total_frames = sum((t.data.size for t in tasks if t.data and t.data.size), 0)
            target_entity = {
                "scope": "project",
                "project_id": project.id,
                "project_name": project.name,
            }
            labels_qs = Label.objects.filter(project=project)

        # 1. Map all labels
        labels_map = {
            label.id: {
                "id": label.id,
                "name": label.name,
                "color": label.color or "#1890ff",
                "type": label.type,
            }
            for label in labels_qs
        }

        # 2. Extract distinct (label_id, frame) pairs across shapes, images, and tracks
        # Shapes:
        shape_pairs = (
            LabeledShape.objects.filter(jobs_filter)
            .values_list("label_id", "frame")
            .distinct()
        )
        shape_counts = (
            LabeledShape.objects.filter(jobs_filter)
            .values("label_id")
            .annotate(total=Count("id"))
        )
        shape_count_dict = {item["label_id"]: item["total"] for item in shape_counts}

        # Images (tag annotations):
        image_pairs = (
            LabeledImage.objects.filter(jobs_filter)
            .values_list("label_id", "frame")
            .distinct()
        )
        image_counts = (
            LabeledImage.objects.filter(jobs_filter)
            .values("label_id")
            .annotate(total=Count("id"))
        )
        image_count_dict = {item["label_id"]: item["total"] for item in image_counts}

        # Tracks (TrackedShape):
        track_pairs = (
            TrackedShape.objects.filter(tracked_shapes_filter)
            .values_list("track__label_id", "frame")
            .distinct()
        )
        track_counts = (
            TrackedShape.objects.filter(tracked_shapes_filter)
            .values("track__label_id")
            .annotate(total=Count("id"))
        )
        track_count_dict = {item["track__label_id"]: item["total"] for item in track_counts}

        # Aggregate unique frames per label
        label_frames = defaultdict(set)
        all_annotated_frames = set()

        for label_id, frame in chain(shape_pairs, image_pairs, track_pairs):
            if label_id in labels_map:
                label_frames[label_id].add(frame)
                all_annotated_frames.add(frame)

        annotated_images_count = len(all_annotated_frames)
        # If total_frames was 0 or uninitialized, fallback to annotated frames count
        effective_total_images = max(total_frames, annotated_images_count)
        unannotated_images_count = max(0, effective_total_images - annotated_images_count)

        classes_analytics: List[Dict[str, Any]] = []
        for label_id, label_info in labels_map.items():
            distinct_frames = label_frames.get(label_id, set())
            img_count = len(distinct_frames)
            total_annotations = (
                shape_count_dict.get(label_id, 0)
                + image_count_dict.get(label_id, 0)
                + track_count_dict.get(label_id, 0)
            )

            pct_of_total = (
                round((img_count / effective_total_images) * 100, 2)
                if effective_total_images > 0
                else 0.0
            )
            pct_of_annotated = (
                round((img_count / annotated_images_count) * 100, 2)
                if annotated_images_count > 0
                else 0.0
            )

            classes_analytics.append({
                "label_id": label_id,
                "label_name": label_info["name"],
                "color": label_info["color"],
                "type": label_info["type"],
                "image_count": img_count,
                "annotation_count": total_annotations,
                "percentage_of_total_images": pct_of_total,
                "percentage_of_annotated_images": pct_of_annotated,
            })

        # Sort classes descending by image_count
        classes_analytics.sort(key=lambda x: x["image_count"], reverse=True)

        return {
            "target": target_entity,
            "summary": {
                "total_images": effective_total_images,
                "annotated_images": annotated_images_count,
                "unannotated_images": unannotated_images_count,
                "total_classes": len(labels_map),
                "active_classes": sum(1 for c in classes_analytics if c["image_count"] > 0),
                "total_annotations": sum(c["annotation_count"] for c in classes_analytics),
                "completion_rate": (
                    round((annotated_images_count / effective_total_images) * 100, 2)
                    if effective_total_images > 0
                    else 0.0
                ),
            },
            "classes": classes_analytics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
