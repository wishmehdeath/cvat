// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

import React, { useState } from 'react';
import {
    Row,
    Col,
    Card,
    Statistic,
    Progress,
    Table,
    Tag,
    Button,
    Space,
    Typography,
    Alert,
    Tooltip,
    Input,
} from 'antd';
import {
    ReloadOutlined,
    ThunderboltOutlined,
    CheckCircleOutlined,
    ExclamationCircleOutlined,
    SyncOutlined,
    DisconnectOutlined,
    SearchOutlined,
} from '@ant-design/icons';
import { useRealtimeAnalytics } from './use-realtime-analytics';
import { ClassCountBarChart, ClassDistributionDoughnut } from './class-count-charts';
import { ClassAnalyticsItem } from './types';
import './styles.scss';

const { Title, Text } = Typography;

interface Props {
    taskId?: number;
    jobId?: number;
    projectId?: number;
}

export const RealtimeAnalyticsDashboard: React.FC<Props> = ({
    taskId,
    jobId,
    projectId,
}) => {
    const {
        data,
        loading,
        error,
        connectionStatus,
        lastUpdated,
        reconnect,
        refresh,
        simulateUpdate,
    } = useRealtimeAnalytics({ taskId, jobId, projectId });

    const [isSimulating, setIsSimulating] = useState(false);
    const [searchText, setSearchText] = useState('');

    const handleSimulate = async () => {
        try {
            setIsSimulating(true);
            await simulateUpdate();
        } finally {
            setIsSimulating(false);
        }
    };

    const renderConnectionBadge = () => {
        switch (connectionStatus) {
            case 'connected':
                return (
                    <Tag color='success' icon={<CheckCircleOutlined />}>
                        <span className='pulse-dot connected' />
                        Live WebSocket
                    </Tag>
                );
            case 'connecting':
            case 'reconnecting':
                return (
                    <Tag color='warning' icon={<SyncOutlined spin />}>
                        <span className='pulse-dot connecting' />
                        Reconnecting...
                    </Tag>
                );
            case 'polling_fallback':
                return (
                    <Tag color='processing' icon={<SyncOutlined spin />}>
                        <span className='pulse-dot polling_fallback' />
                        Polling Fallback (5s)
                    </Tag>
                );
            default:
                return (
                    <Tag color='error' icon={<DisconnectOutlined />}>
                        <span className='pulse-dot disconnected' />
                        Disconnected
                    </Tag>
                );
        }
    };

    const filteredClasses = (data?.classes || []).filter((c) =>
        c.label_name.toLowerCase().includes(searchText.toLowerCase()),
    );

    const columns = [
        {
            title: 'Class / Label',
            dataIndex: 'label_name',
            key: 'label_name',
            render: (text: string, record: ClassAnalyticsItem) => (
                <Space>
                    <span
                        className='color-badge'
                        style={{ backgroundColor: record.color || '#1890ff' }}
                    />
                    <Text strong>{text}</Text>
                    <Tag>{record.type}</Tag>
                </Space>
            ),
        },
        {
            title: 'Distinct Images',
            dataIndex: 'image_count',
            key: 'image_count',
            sorter: (a: ClassAnalyticsItem, b: ClassAnalyticsItem) => a.image_count - b.image_count,
            render: (count: number) => <Text strong style={{ color: '#1890ff' }}>{count}</Text>,
        },
        {
            title: 'Total Annotations',
            dataIndex: 'annotation_count',
            key: 'annotation_count',
            sorter: (a: ClassAnalyticsItem, b: ClassAnalyticsItem) => a.annotation_count - b.annotation_count,
        },
        {
            title: '% of Dataset Images',
            dataIndex: 'percentage_of_total_images',
            key: 'percentage_of_total_images',
            sorter: (a: ClassAnalyticsItem, b: ClassAnalyticsItem) =>
                a.percentage_of_total_images - b.percentage_of_total_images,
            render: (pct: number) => (
                <div style={{ width: 140 }}>
                    <Progress percent={pct} size='small' strokeColor='#1890ff' />
                </div>
            ),
        },
        {
            title: '% of Annotated Images',
            dataIndex: 'percentage_of_annotated_images',
            key: 'percentage_of_annotated_images',
            sorter: (a: ClassAnalyticsItem, b: ClassAnalyticsItem) =>
                a.percentage_of_annotated_images - b.percentage_of_annotated_images,
            render: (pct: number) => (
                <div style={{ width: 140 }}>
                    <Progress percent={pct} size='small' strokeColor='#52c41a' />
                </div>
            ),
        },
    ];

    return (
        <div className='realtime-analytics-container'>
            {/* Header section */}
            <div className='header-card'>
                <div className='title-section'>
                    <div>
                        <Title level={3} style={{ marginBottom: 4 }}>
                            Real-Time Class Analytics
                        </Title>
                        <Space size='middle'>
                            <Text type='secondary'>
                                Scope: {data?.target?.scope ? data.target.scope.toUpperCase() : 'TARGET'}
                                {data?.target?.task_name ? ` • ${data.target.task_name}` : ''}
                                {taskId ? ` (Task #${taskId})` : ''}
                                {jobId ? ` (Job #${jobId})` : ''}
                            </Text>
                            {lastUpdated && (
                                <Text type='secondary' style={{ fontSize: 12 }}>
                                    Updated: {lastUpdated.toLocaleTimeString()}
                                </Text>
                            )}
                        </Space>
                    </div>

                    <div className='badge-group'>
                        {renderConnectionBadge()}
                        <Tooltip title='Simulate an annotation change to test instant WebSocket push'>
                            <Button
                                type='primary'
                                ghost
                                icon={<ThunderboltOutlined />}
                                loading={isSimulating}
                                onClick={handleSimulate}
                            >
                                Simulate Live Update
                            </Button>
                        </Tooltip>
                        <Tooltip title='Refresh analytics data'>
                            <Button icon={<ReloadOutlined />} onClick={refresh} />
                        </Tooltip>
                        {connectionStatus === 'disconnected' && (
                            <Button type='primary' onClick={reconnect}>
                                Reconnect
                            </Button>
                        )}
                    </div>
                </div>
            </div>

            {error && (
                <Alert
                    message='Analytics Warning'
                    description={error}
                    type='warning'
                    showIcon
                    closable
                    style={{ marginBottom: 20 }}
                />
            )}

            {/* KPI Cards */}
            <Row gutter={[16, 16]} className='kpi-row'>
                <Col xs={24} sm={12} md={6}>
                    <Card>
                        <Statistic
                            title='Total Dataset Images'
                            value={data?.summary?.total_images ?? 0}
                            valueStyle={{ color: '#262626' }}
                        />
                        <Text type='secondary' style={{ fontSize: 12 }}>Frames in job / dataset</Text>
                    </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                    <Card>
                        <Statistic
                            title='Annotated Images'
                            value={data?.summary?.annotated_images ?? 0}
                            valueStyle={{ color: '#52c41a' }}
                            suffix={
                                <Text type='secondary' style={{ fontSize: 13 }}>
                                    ({data?.summary?.completion_rate ?? 0}%)
                                </Text>
                            }
                        />
                        <Progress
                            percent={data?.summary?.completion_rate ?? 0}
                            showInfo={false}
                            strokeColor='#52c41a'
                            size='small'
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                    <Card>
                        <Statistic
                            title='Unannotated Images'
                            value={data?.summary?.unannotated_images ?? 0}
                            valueStyle={{ color: '#faad14' }}
                        />
                        <Text type='secondary' style={{ fontSize: 12 }}>Awaiting annotations</Text>
                    </Card>
                </Col>
                <Col xs={24} sm={12} md={6}>
                    <Card>
                        <Statistic
                            title='Total Object Annotations'
                            value={data?.summary?.total_annotations ?? 0}
                            valueStyle={{ color: '#1890ff' }}
                            suffix={
                                <Text type='secondary' style={{ fontSize: 13 }}>
                                    across {data?.summary?.active_classes ?? 0}/{data?.summary?.total_classes ?? 0} classes
                                </Text>
                            }
                        />
                        <Text type='secondary' style={{ fontSize: 12 }}>Shapes & tags aggregated</Text>
                    </Card>
                </Col>
            </Row>

            {/* Visual Charts */}
            <Row gutter={[16, 16]} className='charts-row'>
                <Col xs={24} lg={15}>
                    <Card
                        title='Class-Wise Image Counts'
                        extra={<Text type='secondary'>Number of distinct images with each class</Text>}
                    >
                        {data && <ClassCountBarChart classes={data.classes} summary={data.summary} />}
                    </Card>
                </Col>
                <Col xs={24} lg={9}>
                    <Card
                        title='Class Distribution Share'
                        extra={<Text type='secondary'>Proportion by unique images</Text>}
                    >
                        {data && <ClassDistributionDoughnut classes={data.classes} summary={data.summary} />}
                    </Card>
                </Col>
            </Row>

            {/* Class Breakdown Table */}
            <Card
                className='table-card'
                title='Detailed Class-Wise Analytics Breakdown'
                extra={
                    <Input
                        placeholder='Search class name...'
                        prefix={<SearchOutlined />}
                        value={searchText}
                        onChange={(e) => setSearchText(e.target.value)}
                        style={{ width: 220 }}
                        allowClear
                    />
                }
            >
                <Table
                    columns={columns}
                    dataSource={filteredClasses}
                    rowKey='label_id'
                    loading={loading}
                    pagination={{ pageSize: 8, showSizeChanger: true }}
                />
            </Card>
        </div>
    );
};
