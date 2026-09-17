// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

export interface ClassAnalyticsItem {
    label_id: number;
    label_name: string;
    color: string;
    type: string;
    image_count: number;
    annotation_count: number;
    percentage_of_total_images: number;
    percentage_of_annotated_images: number;
}

export interface AnalyticsSummary {
    total_images: number;
    annotated_images: number;
    unannotated_images: number;
    total_classes: number;
    active_classes: number;
    total_annotations: number;
    completion_rate: number;
}

export interface TargetEntity {
    scope: 'task' | 'job' | 'project';
    task_id?: number;
    job_id?: number;
    project_id?: number;
    task_name?: string;
    project_name?: string;
    segment_start?: number;
    segment_stop?: number;
}

export interface AnalyticsResponse {
    target: TargetEntity;
    summary: AnalyticsSummary;
    classes: ClassAnalyticsItem[];
    timestamp: string;
}

export type ConnectionStatus = 'connected' | 'connecting' | 'reconnecting' | 'polling_fallback' | 'disconnected';
