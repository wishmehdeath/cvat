// Copyright (C) CVAT.ai Corporation
//
// SPDX-License-Identifier: MIT

import { useState, useEffect, useRef, useCallback } from 'react';
import { AnalyticsResponse, ConnectionStatus } from './types';

interface UseRealtimeAnalyticsProps {
    taskId?: number;
    jobId?: number;
    projectId?: number;
}

interface UseRealtimeAnalyticsResult {
    data: AnalyticsResponse | null;
    loading: boolean;
    error: string | null;
    connectionStatus: ConnectionStatus;
    lastUpdated: Date | null;
    reconnect: () => void;
    refresh: () => void;
    simulateUpdate: () => Promise<void>;
}

export function useRealtimeAnalytics({
    taskId,
    jobId,
    projectId,
}: UseRealtimeAnalyticsProps): UseRealtimeAnalyticsResult {
    const [data, setData] = useState<AnalyticsResponse | null>(null);
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connecting');
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectAttemptsRef = useRef<number>(0);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const isUnmountedRef = useRef<boolean>(false);

    const maxReconnectAttempts = 5;

    const buildQueryString = useCallback(() => {
        const params = new URLSearchParams();
        if (jobId) params.append('job_id', String(jobId));
        else if (taskId) params.append('task_id', String(taskId));
        else if (projectId) params.append('project_id', String(projectId));
        return params.toString();
    }, [taskId, jobId, projectId]);

    const fetchViaHttp = useCallback(async () => {
        const query = buildQueryString();
        if (!query) return;

        try {
            const resp = await fetch(`/api/test/analytics/class-counts/?${query}`, {
                headers: { Accept: 'application/json' },
            });
            if (!resp.ok) {
                throw new Error(`HTTP error ${resp.status}`);
            }
            const json: AnalyticsResponse = await resp.json();
            if (!isUnmountedRef.current) {
                setData(json);
                setLastUpdated(new Date());
                setError(null);
                setLoading(false);
            }
        } catch (err: unknown) {
            if (!isUnmountedRef.current) {
                const msg = err instanceof Error ? err.message : 'Failed to fetch analytics data';
                setError(msg);
                setLoading(false);
            }
        }
    }, [buildQueryString]);

    const startPollingFallback = useCallback(() => {
        if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
        setConnectionStatus('polling_fallback');
        fetchViaHttp();
        pollingTimerRef.current = setInterval(fetchViaHttp, 5000);
    }, [fetchViaHttp]);

    const connectWebSocket = useCallback(() => {
        const query = buildQueryString();
        if (!query) return;

        if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
        if (pingTimerRef.current) clearInterval(pingTimerRef.current);
        if (wsRef.current) {
            try {
                wsRef.current.close();
            } catch {
                // ignore
            }
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/ws/test/analytics/?${query}`;

        setConnectionStatus('connecting');

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                if (isUnmountedRef.current) return;
                setConnectionStatus('connected');
                setError(null);
                reconnectAttemptsRef.current = 0;

                // Cancel polling if active
                if (pollingTimerRef.current) {
                    clearInterval(pollingTimerRef.current);
                    pollingTimerRef.current = null;
                }

                // Setup heartbeat
                pingTimerRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ action: 'ping', timestamp: Date.now() }));
                    }
                }, 25000);
            };

            ws.onmessage = (event) => {
                if (isUnmountedRef.current) return;
                try {
                    const message = JSON.parse(event.data);
                    if (message.event === 'INITIAL_DATA' || message.event === 'CLASS_COUNTS_UPDATED') {
                        setData(message.data);
                        setLastUpdated(new Date());
                        setLoading(false);
                    }
                } catch (e) {
                    console.error('Error parsing WebSocket message:', e);
                }
            };

            ws.onerror = () => {
                if (isUnmountedRef.current) return;
                // Will trigger onclose handler for reconnection logic
            };

            ws.onclose = (event) => {
                if (isUnmountedRef.current) return;
                if (pingTimerRef.current) clearInterval(pingTimerRef.current);

                if (reconnectAttemptsRef.current < maxReconnectAttempts) {
                    const delay = Math.min(1000 * (2 ** reconnectAttemptsRef.current), 15000);
                    reconnectAttemptsRef.current += 1;
                    setConnectionStatus('reconnecting');
                    reconnectTimerRef.current = setTimeout(connectWebSocket, delay);
                } else {
                    // Fallback to polling if WebSockets cannot connect
                    startPollingFallback();
                }
            };
        } catch (e) {
            startPollingFallback();
        }
    }, [buildQueryString, startPollingFallback]);

    useEffect(() => {
        isUnmountedRef.current = false;
        // Perform initial HTTP fetch to display data instantly while WS establishes
        fetchViaHttp();
        connectWebSocket();

        return () => {
            isUnmountedRef.current = true;
            if (wsRef.current) wsRef.current.close();
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            if (pingTimerRef.current) clearInterval(pingTimerRef.current);
            if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
        };
    }, [connectWebSocket, fetchViaHttp]);

    const refresh = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ action: 'refresh' }));
        } else {
            fetchViaHttp();
        }
    }, [fetchViaHttp]);

    const simulateUpdate = useCallback(async () => {
        const body: Record<string, number> = {};
        if (jobId) body.job_id = jobId;
        else if (taskId) body.task_id = taskId;

        await fetch('/api/test/analytics/simulate-update/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    }, [taskId, jobId]);

    return {
        data,
        loading,
        error,
        connectionStatus,
        lastUpdated,
        reconnect: connectWebSocket,
        refresh,
        simulateUpdate,
    };
}
