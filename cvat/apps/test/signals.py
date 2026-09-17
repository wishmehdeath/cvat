# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import logging
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from cvat.apps.engine.models import (
    Job,
    LabeledImage,
    LabeledShape,
    LabeledTrack,
    TrackedShape,
)
from cvat.apps.engine.plugins import add_plugin

from .websocket_routing import broadcast_analytics_update

logger = logging.getLogger("cvat.apps.test.signals")


def _trigger_update_for_job(job_id: int):
    try:
        job = Job.objects.select_related("segment__task").get(pk=job_id)
        task_id = job.segment.task_id
        broadcast_analytics_update(task_id=task_id, job_id=job_id)
    except Exception as e:
        logger.debug(f"Could not trigger WebSocket broadcast for job {job_id}: {e}")


@receiver([post_save, post_delete], sender=LabeledShape)
def on_labeled_shape_changed(sender, instance, **kwargs):
    if instance.job_id:
        _trigger_update_for_job(instance.job_id)


@receiver([post_save, post_delete], sender=LabeledImage)
def on_labeled_image_changed(sender, instance, **kwargs):
    if instance.job_id:
        _trigger_update_for_job(instance.job_id)


@receiver([post_save, post_delete], sender=LabeledTrack)
def on_labeled_track_changed(sender, instance, **kwargs):
    if instance.job_id:
        _trigger_update_for_job(instance.job_id)


@receiver([post_save, post_delete], sender=TrackedShape)
def on_tracked_shape_changed(sender, instance, **kwargs):
    try:
        job_id = instance.track.job_id
        if job_id:
            _trigger_update_for_job(job_id)
    except Exception:
        pass


# Register CVAT plugin hook for batch patch_job_data updates
def after_patch_job_data_hook(pk, *args, **kwargs):
    _trigger_update_for_job(pk)


try:
    add_plugin("patch_job_data", after_patch_job_data_hook, "after", exc_ok=True)
except Exception as e:
    logger.debug(f"Could not register patch_job_data plugin hook: {e}")
