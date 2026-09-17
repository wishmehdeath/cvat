#!/usr/bin/env python3
# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

"""
CVAT Real-Time Analytics Standalone Zero-Dependency Runner

Runs the complete real-time analytics system (HTTP REST API + RFC 6455 WebSockets + Live UI)
using pure Python 3 without requiring Docker, PostgreSQL, or external pip packages.
"""

import asyncio
import base64
import hashlib
import json
import os
import random
import socket
import struct
import sys
import time
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = 8000

# In-memory dataset simulating CVAT tasks, jobs, labels, and annotations
MOCK_DATASET = {
    "task": {
        "id": 1,
        "name": "Autonomous Highway Dataset (Real-time Demo)",
        "total_frames": 120,
    },
    "labels": [
        {"id": 1, "name": "vehicle", "color": "#1890ff", "type": "rectangle"},
        {"id": 2, "name": "pedestrian", "color": "#52c41a", "type": "rectangle"},
        {"id": 3, "name": "traffic_sign", "color": "#faad14", "type": "polygon"},
        {"id": 4, "name": "cyclist", "color": "#eb2f96", "type": "rectangle"},
        {"id": 5, "name": "road_obstacle", "color": "#722ed1", "type": "tag"},
    ],
    # Frame annotations: frame_number -> list of {label_id, shape_type}
    "annotations": {
        0: [{"label_id": 1}, {"label_id": 1}, {"label_id": 2}],
        1: [{"label_id": 1}, {"label_id": 3}],
        2: [{"label_id": 2}],
        3: [{"label_id": 1}, {"label_id": 4}],
        4: [{"label_id": 1}, {"label_id": 1}, {"label_id": 1}],
        5: [{"label_id": 3}, {"label_id": 5}],
        6: [{"label_id": 1}],
        7: [{"label_id": 2}, {"label_id": 4}],
        8: [{"label_id": 1}],
        9: [{"label_id": 1}, {"label_id": 2}, {"label_id": 3}],
    },
}

# Connected WebSocket clients: set of asyncio.StreamWriter
ws_clients = set()


def calculate_class_wise_analytics():
    """
    Computes class-wise image count metrics:
    - image_count: number of distinct frames containing the label
    - annotation_count: total individual annotations for that label
    """
    total_frames = MOCK_DATASET["task"]["total_frames"]
    labels = MOCK_DATASET["labels"]
    annotations = MOCK_DATASET["annotations"]

    label_to_frames = {l["id"]: set() for l in labels}
    label_to_annotations_count = {l["id"]: 0 for l in labels}
    all_annotated_frames = set()

    for frame, shape_list in annotations.items():
        if shape_list:
            all_annotated_frames.add(frame)
        for shape in shape_list:
            lid = shape["label_id"]
            if lid in label_to_frames:
                label_to_frames[lid].add(frame)
                label_to_annotations_count[lid] += 1

    annotated_count = len(all_annotated_frames)
    unannotated_count = max(0, total_frames - annotated_count)

    classes_list = []
    for l in labels:
        lid = l["id"]
        img_count = len(label_to_frames[lid])
        ann_count = label_to_annotations_count[lid]
        pct_total = round((img_count / total_frames) * 100, 2) if total_frames > 0 else 0
        pct_annotated = round((img_count / annotated_count) * 100, 2) if annotated_count > 0 else 0

        classes_list.append({
            "label_id": lid,
            "label_name": l["name"],
            "color": l["color"],
            "type": l["type"],
            "image_count": img_count,
            "annotation_count": ann_count,
            "percentage_of_total_images": pct_total,
            "percentage_of_annotated_images": pct_annotated,
        })

    classes_list.sort(key=lambda x: x["image_count"], reverse=True)

    return {
        "target": {
            "scope": "task",
            "task_id": MOCK_DATASET["task"]["id"],
            "task_name": MOCK_DATASET["task"]["name"],
        },
        "summary": {
            "total_images": total_frames,
            "annotated_images": annotated_count,
            "unannotated_images": unannotated_count,
            "total_classes": len(labels),
            "active_classes": sum(1 for c in classes_list if c["image_count"] > 0),
            "total_annotations": sum(c["annotation_count"] for c in classes_list),
            "completion_rate": round((annotated_count / total_frames) * 100, 2) if total_frames > 0 else 0,
        },
        "classes": classes_list,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def add_random_annotation():
    """Simulates an annotator drawing shapes on a frame."""
    target_frame = random.randint(0, 25)
    random_label = random.choice(MOCK_DATASET["labels"])
    if target_frame not in MOCK_DATASET["annotations"]:
        MOCK_DATASET["annotations"][target_frame] = []
    MOCK_DATASET["annotations"][target_frame].append({"label_id": random_label["id"]})
    return target_frame, random_label["name"]


def make_websocket_frame(payload_str: str) -> bytes:
    payload_bytes = payload_str.encode("utf-8")
    length = len(payload_bytes)
    frame = bytearray([0x81])  # FIN + Text frame
    if length <= 125:
        frame.append(length)
    elif length <= 65535:
        frame.append(126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", length))
    frame.extend(payload_bytes)
    return bytes(frame)


async def broadcast_ws(payload: dict):
    if not ws_clients:
        return
    msg = make_websocket_frame(json.dumps(payload))
    dead_clients = set()
    for writer in list(ws_clients):
        try:
            writer.write(msg)
            await writer.drain()
        except Exception:
            dead_clients.add(writer)
    ws_clients.difference_update(dead_clients)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CVAT Real-Time Analytics Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --primary: #1890ff;
      --success: #52c41a;
      --warning: #faad14;
      --bg: #f0f2f5;
      --card-bg: #ffffff;
      --text: #1f2937;
      --text-muted: #6b7280;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; }
    .container { max-width: 1200px; margin: 0 auto; }
    
    .header-card {
      background: var(--card-bg);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }
    .header-title h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
    .header-title p { color: var(--text-muted); font-size: 14px; }
    
    .actions-group { display: flex; align-items: center; gap: 12px; }
    
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      background: #e6f7ff;
      color: var(--primary);
    }
    .status-badge.connected { background: #f6ffed; color: var(--success); }
    .status-badge.reconnecting { background: #fffbe6; color: var(--warning); }
    
    .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: currentColor; }
    .pulse { animation: pulse 1.8s infinite; }
    @keyframes pulse { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.3); } 100% { opacity: 1; transform: scale(1); } }
    
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 9px 18px;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
      font-size: 13px;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .btn:hover { opacity: 0.9; transform: translateY(-1px); }
    .btn-secondary { background: #ffffff; color: var(--text); border: 1px solid #d9d9d9; }
    .btn-secondary:hover { border-color: var(--primary); color: var(--primary); }

    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .kpi-card { background: var(--card-bg); padding: 20px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    .kpi-title { font-size: 13px; color: var(--text-muted); font-weight: 500; margin-bottom: 8px; }
    .kpi-value { font-size: 28px; font-weight: 700; color: var(--text); }
    .kpi-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

    .charts-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 24px; }
    @media (max-width: 900px) { .charts-grid { grid-template-columns: 1fr; } }
    
    .chart-card { background: var(--card-bg); padding: 22px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .chart-header h3 { font-size: 16px; font-weight: 600; }
    .chart-container { position: relative; height: 320px; }

    .table-card { background: var(--card-bg); padding: 22px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
    th { text-align: left; padding: 12px 14px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid #f0f0f0; }
    td { padding: 14px; border-bottom: 1px solid #f0f0f0; }
    tr:hover { background: #fafafa; }
    .color-swatch { width: 12px; height: 12px; border-radius: 3px; display: inline-block; vertical-align: middle; margin-right: 8px; }
    
    .progress-bar-bg { width: 100%; background: #f0f0f0; height: 8px; border-radius: 4px; overflow: hidden; margin-top: 4px; }
    .progress-bar-fill { height: 100%; background: var(--primary); border-radius: 4px; transition: width 0.4s ease; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header-card">
      <div class="header-title">
        <h1>CVAT Real-Time Class Analytics</h1>
        <p id="targetScope">Loading target data...</p>
      </div>
      <div class="actions-group">
        <div id="connStatus" class="status-badge connecting">
          <span class="dot pulse"></span>
          <span id="connText">Connecting...</span>
        </div>
        <button class="btn" id="simulateBtn" onclick="triggerSimulation()">
          ⚡ Simulate Annotation Update
        </button>
        <button class="btn btn-secondary" onclick="fetchRESTData()">
          🔄 Refresh
        </button>
      </div>
    </div>

    <!-- KPI Grid -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-title">Total Dataset Images</div>
        <div class="kpi-value" id="kpiTotalImages">0</div>
        <div class="kpi-sub">Total frames in dataset</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Annotated Images</div>
        <div class="kpi-value" style="color: var(--success);" id="kpiAnnotatedImages">0</div>
        <div class="kpi-sub" id="kpiCompletion">0% coverage</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Unannotated Images</div>
        <div class="kpi-value" style="color: var(--warning);" id="kpiUnannotatedImages">0</div>
        <div class="kpi-sub">Awaiting annotations</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-title">Total Annotations</div>
        <div class="kpi-value" style="color: var(--primary);" id="kpiTotalAnnotations">0</div>
        <div class="kpi-sub" id="kpiActiveClasses">0 active classes</div>
      </div>
    </div>

    <!-- Charts Grid -->
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-header">
          <h3>Class-Wise Distinct Image Counts</h3>
          <span style="font-size: 12px; color: var(--text-muted);">Unique frames containing each class</span>
        </div>
        <div class="chart-container">
          <canvas id="barChart"></canvas>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <h3>Class Distribution Share</h3>
          <span style="font-size: 12px; color: var(--text-muted);">Proportion by unique images</span>
        </div>
        <div class="chart-container">
          <canvas id="doughnutChart"></canvas>
        </div>
      </div>
    </div>

    <!-- Table Breakdown -->
    <div class="table-card">
      <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 4px;">Class-Wise Detailed Telemetry</h3>
      <table id="classesTable">
        <thead>
          <tr>
            <th>Class Label</th>
            <th>Type</th>
            <th>Distinct Images</th>
            <th>Total Annotations</th>
            <th>Dataset Coverage (%)</th>
          </tr>
        </thead>
        <tbody id="classesTbody">
          <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading telemetry data...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <script>
    let barChartInstance = null;
    let doughnutChartInstance = null;
    let socket = null;

    function renderCharts(data) {
      const classes = data.classes || [];
      const labels = classes.map(c => c.label_name);
      const imageCounts = classes.map(c => c.image_count);
      const annotationCounts = classes.map(c => c.annotation_count);
      const colors = classes.map(c => c.color || '#1890ff');

      // Update KPI
      document.getElementById('targetScope').innerText = `${data.target.task_name} (Task #${data.target.task_id}) • Updated: ${new Date().toLocaleTimeString()}`;
      document.getElementById('kpiTotalImages').innerText = data.summary.total_images;
      document.getElementById('kpiAnnotatedImages').innerText = data.summary.annotated_images;
      document.getElementById('kpiCompletion').innerText = `${data.summary.completion_rate}% coverage`;
      document.getElementById('kpiUnannotatedImages').innerText = data.summary.unannotated_images;
      document.getElementById('kpiTotalAnnotations').innerText = data.summary.total_annotations;
      document.getElementById('kpiActiveClasses').innerText = `${data.summary.active_classes} / ${data.summary.total_classes} classes active`;

      // Update Bar Chart
      if (barChartInstance) barChartInstance.destroy();
      const ctxBar = document.getElementById('barChart').getContext('2d');
      barChartInstance = new Chart(ctxBar, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Distinct Images with Class',
              data: imageCounts,
              backgroundColor: colors.map(c => c + 'cc'),
              borderColor: colors,
              borderWidth: 1.5,
              borderRadius: 6
            },
            {
              label: 'Total Object Annotations',
              data: annotationCounts,
              backgroundColor: 'rgba(120, 144, 156, 0.35)',
              borderColor: 'rgba(120, 144, 156, 0.8)',
              borderWidth: 1,
              borderRadius: 6
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 400 },
          scales: {
            y: { beginAtZero: true, ticks: { stepSize: 1, precision: 0 } }
          }
        }
      });

      // Update Doughnut Chart
      if (doughnutChartInstance) doughnutChartInstance.destroy();
      const ctxDoughnut = document.getElementById('doughnutChart').getContext('2d');
      doughnutChartInstance = new Chart(ctxDoughnut, {
        type: 'doughnut',
        data: {
          labels: labels,
          datasets: [{
            data: imageCounts,
            backgroundColor: colors,
            borderWidth: 2,
            borderColor: '#ffffff'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '65%',
          animation: { duration: 400 }
        }
      });

      // Update Table
      const tbody = document.getElementById('classesTbody');
      tbody.innerHTML = classes.map(c => `
        <tr>
          <td>
            <span class="color-swatch" style="background-color: ${c.color}"></span>
            <strong>${c.label_name}</strong>
          </td>
          <td><span style="background: #f0f0f0; padding: 3px 8px; border-radius: 4px; font-size: 12px;">${c.type}</span></td>
          <td><strong style="color: var(--primary);">${c.image_count}</strong></td>
          <td>${c.annotation_count}</td>
          <td style="width: 180px;">
            <div>${c.percentage_of_total_images}%</div>
            <div class="progress-bar-bg">
              <div class="progress-bar-fill" style="width: ${c.percentage_of_total_images}%; background-color: ${c.color}"></div>
            </div>
          </td>
        </tr>
      `).join('');
    }

    async function fetchRESTData() {
      try {
        const res = await fetch('/api/test/analytics/class-counts/?task_id=1');
        const data = await res.json();
        renderCharts(data);
      } catch (err) {
        console.error('REST fetch error:', err);
      }
    }

    async function triggerSimulation() {
      const btn = document.getElementById('simulateBtn');
      btn.innerText = '⚡ Triggering...';
      btn.disabled = true;
      try {
        await fetch('/api/test/analytics/simulate-update/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: 1 })
        });
      } finally {
        btn.innerText = '⚡ Simulate Annotation Update';
        btn.disabled = false;
      }
    }

    function initWebSocket() {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${proto}//${window.location.host}/ws/test/analytics/?task_id=1`;
      
      const badge = document.getElementById('connStatus');
      const text = document.getElementById('connText');

      socket = new WebSocket(url);

      socket.onopen = () => {
        badge.className = 'status-badge connected';
        text.innerText = 'Live WebSocket';
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event === 'INITIAL_DATA' || msg.event === 'CLASS_COUNTS_UPDATED') {
            renderCharts(msg.data);
          }
        } catch (e) {
          console.error(e);
        }
      };

      socket.onclose = () => {
        badge.className = 'status-badge reconnecting';
        text.innerText = 'Reconnecting...';
        setTimeout(initWebSocket, 2500);
      };
    }

    // Initialize
    fetchRESTData();
    initWebSocket();
  </script>
</body>
</html>
"""


async def handle_http_or_ws(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        header_bytes = await reader.readuntil(b"\r\n\r\n")
    except Exception:
        writer.close()
        return

    lines = header_bytes.decode("utf-8", errors="replace").split("\r\n")
    if not lines:
        writer.close()
        return

    req_line = lines[0].split(" ")
    if len(req_line) < 2:
        writer.close()
        return

    method, path = req_line[0], req_line[1]
    headers = {}
    for line in lines[1:]:
        if ": " in line:
            k, v = line.split(": ", 1)
            headers[k.lower()] = v

    # Check for WebSocket Upgrade
    if headers.get("upgrade", "").lower() == "websocket":
        key = headers.get("sec-websocket-key", "")
        accept_raw = key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept_key = base64.b64encode(hashlib.sha1(accept_raw.encode("utf-8")).digest()).decode("utf-8")

        resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
        )
        writer.write(resp.encode("utf-8"))
        await writer.drain()

        # Send initial data
        initial_data = calculate_class_wise_analytics()
        init_frame = make_websocket_frame(json.dumps({"event": "INITIAL_DATA", "data": initial_data}))
        writer.write(init_frame)
        await writer.drain()

        ws_clients.add(writer)

        try:
            while True:
                # Read frames or keep alive
                chunk = await reader.read(2)
                if not chunk:
                    break
                b1, b2 = chunk[0], chunk[1]
                opcode = b1 & 0x0F
                if opcode == 0x08:  # close frame
                    break
                masked = (b2 & 0x80) != 0
                pay_len = b2 & 0x7F
                if pay_len == 126:
                    ext = await reader.read(2)
                    pay_len = struct.unpack(">H", ext)[0]
                elif pay_len == 127:
                    ext = await reader.read(8)
                    pay_len = struct.unpack(">Q", ext)[0]
                mask = await reader.read(4) if masked else b""
                data = await reader.read(pay_len)
                if opcode == 0x09:  # ping
                    pong_frame = bytearray([0x8A, 0])
                    writer.write(pong_frame)
                    await writer.drain()
        except Exception:
            pass
        finally:
            ws_clients.discard(writer)
            writer.close()
            return

    # Normal HTTP requests
    parsed = urlparse(path)
    req_path = parsed.path

    if req_path == "/" or req_path == "/analytics":
        body = DASHBOARD_HTML.encode("utf-8")
        headers_resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers_resp.encode("utf-8") + body)
        await writer.drain()
        writer.close()
        return

    if req_path.startswith("/api/test/analytics/class-counts"):
        data = calculate_class_wise_analytics()
        body = json.dumps(data).encode("utf-8")
        headers_resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers_resp.encode("utf-8") + body)
        await writer.drain()
        writer.close()
        return

    if req_path.startswith("/api/test/analytics/simulate-update") and method == "POST":
        frame_num, label_name = add_random_annotation()
        updated = calculate_class_wise_analytics()
        # Broadcast to all open WebSocket connections
        asyncio.create_task(broadcast_ws({"event": "CLASS_COUNTS_UPDATED", "data": updated}))
        resp_payload = {
            "status": "broadcast_sent",
            "simulated_action": f"Added annotation for '{label_name}' on frame #{frame_num}",
            "connected_clients": len(ws_clients),
        }
        body = json.dumps(resp_payload).encode("utf-8")
        headers_resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers_resp.encode("utf-8") + body)
        await writer.drain()
        writer.close()
        return

    # Fallback 404
    body = b'{"error": "Not Found"}'
    headers_resp = (
        "HTTP/1.1 404 Not Found\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    )
    writer.write(headers_resp.encode("utf-8") + body)
    await writer.drain()
    writer.close()


async def main():
    server = await asyncio.start_server(handle_http_or_ws, HOST, PORT)
    print("=" * 70)
    print("🚀 CVAT Real-Time Analytics Standalone Server Running!")
    print(f"🔗 Dashboard & UI:   http://{HOST}:{PORT}/")
    print(f"📡 REST API:          http://{HOST}:{PORT}/api/test/analytics/class-counts/?task_id=1")
    print(f"⚡ Live WebSocket:    ws://{HOST}:{PORT}/ws/test/analytics/?task_id=1")
    print("=" * 70)
    print("Press Ctrl+C to stop the server.")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped.")
