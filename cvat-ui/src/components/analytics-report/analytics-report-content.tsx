// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

import React from 'react';
import { useSelector } from 'react-redux';

import config from 'config';
import { Project, Task, Job } from 'cvat-core-wrapper';
import { CombinedState } from 'reducers';
import PaidFeaturePlaceholder from 'components/paid-feature-placeholder/paid-feature-placeholder';
import { TimePeriod } from '.';

interface Props {
    resource: Project | Task | Job;
    timePeriod: TimePeriod | null;
}

import { RealtimeAnalyticsDashboard } from 'components/realtime-analytics';

function AnalyticsReportContent({ resource }: { resource?: Project | Task | Job }): JSX.Element {
    let taskId: number | undefined;
    let jobId: number | undefined;
    let projectId: number | undefined;

    if (resource instanceof Task) {
        taskId = resource.id;
    } else if (resource instanceof Job) {
        jobId = resource.id;
    } else if (resource instanceof Project) {
        projectId = resource.id;
    }

    return (
        <RealtimeAnalyticsDashboard
            taskId={taskId}
            jobId={jobId}
            projectId={projectId}
        />
    );
}

function AnalyticsReportContentWrap(props: Readonly<Props>): JSX.Element {
    const overrides = useSelector(
        (state: CombinedState) => state.plugins.overridableComponents.analyticsReportPage.content,
    );

    if (overrides.length) {
        const [Component] = overrides.slice(-1);
        return <Component {...props} />;
    }

    return <AnalyticsReportContent resource={props.resource} />;
}

export default React.memo(AnalyticsReportContentWrap);
