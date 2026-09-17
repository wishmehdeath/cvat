// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

import React from 'react';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    ArcElement,
    Title,
    Tooltip,
    Legend,
    ChartOptions,
} from 'chart.js';
import { Bar, Doughnut } from 'react-chartjs-2';
import { ClassAnalyticsItem, AnalyticsSummary } from './types';

// Register ChartJS plugins
ChartJS.register(
    CategoryScale,
    LinearScale,
    BarElement,
    ArcElement,
    Title,
    Tooltip,
    Legend,
);

interface ClassCountChartsProps {
    classes: ClassAnalyticsItem[];
    summary: AnalyticsSummary;
}

export const ClassCountBarChart: React.FC<ClassCountChartsProps> = ({ classes }) => {
    const labels = classes.map((c) => c.label_name);
    const imageCounts = classes.map((c) => c.image_count);
    const annotationCounts = classes.map((c) => c.annotation_count);
    const backgroundColors = classes.map((c) => c.color || '#1890ff');

    const data = {
        labels,
        datasets: [
            {
                label: 'Distinct Images Containing Class',
                data: imageCounts,
                backgroundColor: backgroundColors.map((c) => `${c}dd`),
                borderColor: backgroundColors,
                borderWidth: 1.5,
                borderRadius: 4,
            },
            {
                label: 'Total Object Annotations',
                data: annotationCounts,
                backgroundColor: 'rgba(120, 144, 156, 0.35)',
                borderColor: 'rgba(120, 144, 156, 0.8)',
                borderWidth: 1,
                borderRadius: 4,
            },
        ],
    };

    const options: ChartOptions<'bar'> = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'top' as const,
                labels: {
                    boxWidth: 14,
                    usePointStyle: true,
                    font: { size: 12 },
                },
            },
            tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.85)',
                padding: 10,
                cornerRadius: 6,
                callbacks: {
                    afterLabel: (context) => {
                        const item = classes[context.dataIndex];
                        if (!item) return '';
                        return context.datasetIndex === 0
                            ? `Coverage: ${item.percentage_of_total_images}% of dataset`
                            : `Avg per image: ${item.image_count > 0 ? (item.annotation_count / item.image_count).toFixed(1) : 0}`;
                    },
                },
            },
        },
        scales: {
            x: {
                grid: { display: false },
                ticks: {
                    font: { weight: 500 },
                    maxRotation: 45,
                    minRotation: 0,
                },
            },
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(200, 200, 200, 0.2)' },
                ticks: {
                    stepSize: 1,
                    precision: 0,
                },
            },
        },
    };

    return (
        <div style={{ height: '340px', width: '100%', position: 'relative' }}>
            <Bar data={data} options={options} />
        </div>
    );
};

export const ClassDistributionDoughnut: React.FC<ClassCountChartsProps> = ({ classes }) => {
    const activeClasses = classes.filter((c) => c.image_count > 0);

    const labels = activeClasses.length > 0
        ? activeClasses.map((c) => c.label_name)
        : ['No annotations yet'];

    const dataPoints = activeClasses.length > 0
        ? activeClasses.map((c) => c.image_count)
        : [1];

    const backgroundColors = activeClasses.length > 0
        ? activeClasses.map((c) => c.color || '#1890ff')
        : ['#e0e0e0'];

    const data = {
        labels,
        datasets: [
            {
                data: dataPoints,
                backgroundColor: backgroundColors,
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 6,
            },
        ],
    };

    const options: ChartOptions<'doughnut'> = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'right' as const,
                labels: {
                    boxWidth: 12,
                    font: { size: 11 },
                },
            },
            tooltip: {
                callbacks: {
                    label: (context) => {
                        const total = context.dataset.data.reduce((a, b) => Number(a) + Number(b), 0);
                        const val = Number(context.raw);
                        const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '0';
                        return ` ${context.label}: ${val} images (${pct}%)`;
                    },
                },
            },
        },
        cutout: '62%',
    };

    return (
        <div style={{ height: '340px', width: '100%', position: 'relative' }}>
            <Doughnut data={data} options={options} />
        </div>
    );
};
