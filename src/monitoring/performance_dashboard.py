#!/usr/bin/env python3
"""
Performance Dashboard and Reporting System

Real-time dashboard for monitoring SLA performance and generating executive
reports on system health and customer impact.

FEATURES:
- Real-time SLA metrics visualization
- Performance trend analysis
- Customer impact assessment
- Executive summary reports
- Alert management interface
- Production deployment status
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import asdict
import statistics
import numpy as np
from pathlib import Path

# Web framework imports
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

# Plotting and visualization
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd

# Import the SLA monitoring system
from .sla_monitor import SLAMonitor, SLAMonitoringAPI

logger = logging.getLogger(__name__)

class PerformanceDashboard:
    """Performance monitoring dashboard"""
    
    def __init__(self, sla_monitor: SLAMonitor):
        self.sla_monitor = sla_monitor
        self.monitoring_api = SLAMonitoringAPI(sla_monitor)
        
        # FastAPI app
        self.app = FastAPI(
            title="AI Agency Platform - SLA Performance Dashboard",
            description="Real-time monitoring of system performance and SLA compliance",
            version="1.0.0"
        )
        
        # WebSocket connections for real-time updates
        self.websocket_connections: List[WebSocket] = []
        
        # Setup templates and static files
        self.templates = Jinja2Templates(directory="templates")
        
        # Setup routes
        self._setup_routes()
        
        # Dashboard update task
        self.dashboard_update_task = None
        self.is_running = False
    
    def _setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard_home(request: Request):
            """Main dashboard page"""
            status = await self.monitoring_api.get_status()
            return self.templates.TemplateResponse(
                "dashboard.html", 
                {
                    "request": request,
                    "status": status,
                    "page_title": "SLA Performance Dashboard"
                }
            )
        
        @self.app.get("/api/status")
        async def get_status():
            """Get current SLA status"""
            return await self.monitoring_api.get_status()
        
        @self.app.get("/api/report/{hours}")
        async def get_report(hours: int = 24):
            """Get performance report"""
            return await self.monitoring_api.get_report(hours)
        
        @self.app.get("/api/metric/{metric_name}/history/{hours}")
        async def get_metric_history(metric_name: str, hours: int = 24):
            """Get metric historical data"""
            return await self.monitoring_api.get_metric_history(metric_name, hours)
        
        @self.app.get("/api/charts/sla-compliance")
        async def get_sla_compliance_chart():
            """Get SLA compliance chart data"""
            return await self._generate_sla_compliance_chart()
        
        @self.app.get("/api/charts/performance-trends")
        async def get_performance_trends_chart():
            """Get performance trends chart data"""
            return await self._generate_performance_trends_chart()
        
        @self.app.get("/api/charts/customer-impact")
        async def get_customer_impact_chart():
            """Get customer impact assessment chart"""
            return await self._generate_customer_impact_chart()
        
        @self.app.get("/reports/executive")
        async def executive_report():
            """Generate executive summary report"""
            return await self._generate_executive_report()
        
        @self.app.get("/reports/technical/{hours}")
        async def technical_report(hours: int = 24):
            """Generate detailed technical report"""
            return await self._generate_technical_report(hours)
        
        @self.app.get("/production-readiness")
        async def production_readiness_status():
            """Get production readiness assessment"""
            return await self._assess_production_readiness()
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates"""
            await websocket.accept()
            self.websocket_connections.append(websocket)
            
            try:
                while True:
                    await websocket.receive_text()  # Keep connection alive
            except WebSocketDisconnect:
                self.websocket_connections.remove(websocket)
    
    async def start_dashboard(self, host: str = "0.0.0.0", port: int = 8080):
        """Start the dashboard server"""
        logger.info(f"🎯 Starting performance dashboard at http://{host}:{port}")
        
        self.is_running = True
        
        # Start real-time update task
        self.dashboard_update_task = asyncio.create_task(self._real_time_update_loop())
        
        # Start FastAPI server
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    
    async def stop_dashboard(self):
        """Stop the dashboard server"""
        logger.info("🔄 Stopping performance dashboard...")
        self.is_running = False
        
        if self.dashboard_update_task:
            self.dashboard_update_task.cancel()
        
        logger.info("✅ Performance dashboard stopped")
    
    async def _real_time_update_loop(self):
        """Send real-time updates to connected WebSocket clients"""
        try:
            while self.is_running:
                if self.websocket_connections:
                    # Get current status
                    status = await self.monitoring_api.get_status()
                    
                    # Send to all connected clients
                    disconnected = []
                    for websocket in self.websocket_connections:
                        try:
                            await websocket.send_json(status)
                        except Exception:
                            disconnected.append(websocket)
                    
                    # Remove disconnected clients
                    for ws in disconnected:
                        if ws in self.websocket_connections:
                            self.websocket_connections.remove(ws)
                
                # Update every 10 seconds
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            logger.info("Real-time update loop cancelled")
        except Exception as e:
            logger.error(f"❌ Real-time update loop failed: {e}")
    
    async def _generate_sla_compliance_chart(self) -> Dict[str, Any]:
        """Generate SLA compliance chart data"""
        try:
            status = await self.monitoring_api.get_status()
            
            # Prepare data for chart
            metrics = []
            current_values = []
            target_values = []
            statuses = []
            colors = []
            
            color_map = {
                'OK': 'green',
                'WARNING': 'orange', 
                'CRITICAL': 'red',
                'UNKNOWN': 'gray'
            }
            
            for metric_name, metric_data in status['metrics'].items():
                metrics.append(metric_name.replace('_', ' ').title())
                current_values.append(metric_data['current_value'] or 0)
                target_values.append(metric_data['target_value'])
                statuses.append(metric_data['status'])
                colors.append(color_map.get(metric_data['status'], 'gray'))
            
            # Create compliance chart
            fig = go.Figure(data=[
                go.Bar(
                    name='Current Performance',
                    x=metrics,
                    y=current_values,
                    marker_color=colors,
                    text=statuses,
                    textposition='auto'
                ),
                go.Scatter(
                    name='SLA Target',
                    x=metrics,
                    y=target_values,
                    mode='markers',
                    marker=dict(
                        color='blue',
                        size=10,
                        symbol='diamond'
                    )
                )
            ])
            
            fig.update_layout(
                title='SLA Compliance Status',
                xaxis_title='Metrics',
                yaxis_title='Performance Value',
                barmode='group',
                height=500
            )
            
            return {
                'chart_data': fig.to_dict(),
                'overall_compliance': status['overall_compliance'],
                'active_alerts': status['alerts']['active']
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to generate SLA compliance chart: {e}")
            return {'error': str(e)}
    
    async def _generate_performance_trends_chart(self) -> Dict[str, Any]:
        """Generate performance trends chart"""
        try:
            # Get historical data for key metrics
            key_metrics = [
                'voice_response_time',
                'whatsapp_processing_time',
                'cross_system_handoff_time',
                'system_wide_concurrent_users'
            ]
            
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=[m.replace('_', ' ').title() for m in key_metrics]
            )
            
            for i, metric_name in enumerate(key_metrics):
                row = (i // 2) + 1
                col = (i % 2) + 1
                
                # Get metric history
                history = await self.monitoring_api.get_metric_history(metric_name, hours=24)
                
                if 'samples' in history and history['samples']:
                    timestamps = [s['timestamp'] for s in history['samples']]
                    values = [s['value'] for s in history['samples']]
                    
                    fig.add_trace(
                        go.Scatter(
                            x=timestamps,
                            y=values,
                            mode='lines+markers',
                            name=metric_name.replace('_', ' ').title(),
                            line=dict(width=2)
                        ),
                        row=row, col=col
                    )
                    
                    # Add SLA target line
                    target_value = history['target_value']
                    fig.add_hline(
                        y=target_value,
                        line_dash="dash",
                        line_color="red",
                        row=row, col=col
                    )
            
            fig.update_layout(
                title='Performance Trends (Last 24 Hours)',
                height=800,
                showlegend=False
            )
            
            return {'chart_data': fig.to_dict()}
            
        except Exception as e:
            logger.error(f"❌ Failed to generate performance trends chart: {e}")
            return {'error': str(e)}
    
    async def _generate_customer_impact_chart(self) -> Dict[str, Any]:
        """Generate customer impact assessment chart"""
        try:
            status = await self.monitoring_api.get_status()
            
            # Calculate customer impact scores
            impact_scores = {}
            impact_categories = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
            
            for metric_name, metric_data in status['metrics'].items():
                if metric_data['status'] != 'OK':
                    # Map metrics to customer impact levels
                    if metric_name in ['voice_response_time', 'whatsapp_processing_time']:
                        impact_level = 'HIGH' if metric_data['status'] == 'CRITICAL' else 'MEDIUM'
                    elif metric_name in ['system_wide_concurrent_users', 'system_availability']:
                        impact_level = 'CRITICAL' if metric_data['status'] == 'CRITICAL' else 'HIGH'
                    else:
                        impact_level = 'MEDIUM' if metric_data['status'] == 'CRITICAL' else 'LOW'
                    
                    impact_categories[impact_level] += 1
            
            # Create impact assessment chart
            fig = go.Figure(data=[
                go.Pie(
                    labels=list(impact_categories.keys()),
                    values=list(impact_categories.values()),
                    marker_colors=['lightgreen', 'yellow', 'orange', 'red']
                )
            ])
            
            fig.update_layout(
                title='Customer Impact Assessment',
                height=400
            )
            
            return {
                'chart_data': fig.to_dict(),
                'impact_summary': impact_categories
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to generate customer impact chart: {e}")
            return {'error': str(e)}
    
    async def _generate_executive_report(self) -> Dict[str, Any]:
        """Generate executive summary report"""
        try:
            status = await self.monitoring_api.get_status()
            report_24h = await self.monitoring_api.get_report(hours=24)
            
            # Calculate key metrics for executives
            overall_health = "HEALTHY" if status['overall_compliance'] >= 95 else \
                           "AT_RISK" if status['overall_compliance'] >= 85 else "CRITICAL"
            
            customer_impact = "MINIMAL" if status['alerts']['critical'] == 0 else \
                            "MODERATE" if status['alerts']['critical'] <= 2 else "SEVERE"
            
            # Production readiness assessment
            production_ready = await self._assess_production_readiness()
            
            executive_report = {
                'report_date': datetime.now().isoformat(),
                'executive_summary': {
                    'overall_health': overall_health,
                    'sla_compliance': f"{status['overall_compliance']:.1f}%",
                    'customer_impact': customer_impact,
                    'production_readiness': production_ready['status'],
                    'active_critical_issues': status['alerts']['critical']
                },
                'key_metrics': {
                    'voice_system_performance': self._get_metric_status(status, 'voice_response_time'),
                    'whatsapp_system_performance': self._get_metric_status(status, 'whatsapp_processing_time'),
                    'system_capacity': self._get_metric_status(status, 'system_wide_concurrent_users'),
                    'system_availability': self._get_metric_status(status, 'system_availability')
                },
                'business_impact': {
                    'customer_acquisition_status': 'HEALTHY' if status['alerts']['critical'] == 0 else 'IMPACTED',
                    'revenue_at_risk': 'LOW' if status['overall_compliance'] >= 90 else 'MEDIUM',
                    'customer_satisfaction_risk': customer_impact
                },
                'recommendations': self._generate_executive_recommendations(status, production_ready),
                'next_review': (datetime.now() + timedelta(hours=24)).isoformat()
            }
            
            return executive_report
            
        except Exception as e:
            logger.error(f"❌ Failed to generate executive report: {e}")
            return {'error': str(e)}
    
    async def _generate_technical_report(self, hours: int) -> Dict[str, Any]:
        """Generate detailed technical report"""
        try:
            report = await self.monitoring_api.get_report(hours)
            status = await self.monitoring_api.get_status()
            
            technical_report = {
                'report_period': f'Last {hours} hours',
                'generated_at': datetime.now().isoformat(),
                'system_performance': {
                    'sla_compliance_summary': report['sla_compliance_summary'],
                    'current_status': status['metrics'],
                    'performance_trends': self._analyze_performance_trends(report)
                },
                'infrastructure_health': {
                    'memory_usage': status['metrics']['memory_usage'],
                    'database_performance': status['metrics']['database_query_time'],
                    'system_availability': status['metrics']['system_availability']
                },
                'integration_performance': {
                    'voice_integration': {
                        'response_time': status['metrics']['voice_response_time'],
                        'concurrent_capacity': status['metrics']['voice_concurrent_sessions'],
                        'bilingual_performance': status['metrics']['bilingual_switching_overhead']
                    },
                    'whatsapp_integration': {
                        'processing_time': status['metrics']['whatsapp_processing_time'],
                        'throughput': status['metrics']['whatsapp_throughput'],
                        'media_processing': status['metrics']['media_processing_time']
                    },
                    'cross_integration': {
                        'handoff_time': status['metrics']['cross_system_handoff_time'],
                        'end_to_end_journey': status['metrics']['end_to_end_journey_time']
                    }
                },
                'alert_analysis': report['alert_summary'],
                'optimization_recommendations': self._generate_technical_recommendations(status, report)
            }
            
            return technical_report
            
        except Exception as e:
            logger.error(f"❌ Failed to generate technical report: {e}")
            return {'error': str(e)}
    
    async def _assess_production_readiness(self) -> Dict[str, Any]:
        """Assess production readiness based on current performance"""
        try:
            status = await self.monitoring_api.get_status()
            
            # Critical SLA requirements for production readiness
            critical_requirements = [
                ('voice_response_time', 'Voice Response Time'),
                ('system_wide_concurrent_users', 'System Capacity'),
                ('system_availability', 'System Availability')
            ]
            
            failed_requirements = []
            warning_requirements = []
            
            for metric_key, metric_name in critical_requirements:
                metric_status = status['metrics'][metric_key]['status']
                if metric_status == 'CRITICAL':
                    failed_requirements.append(metric_name)
                elif metric_status == 'WARNING':
                    warning_requirements.append(metric_name)
            
            # Determine overall readiness status
            if failed_requirements:
                readiness_status = 'NOT_READY'
                readiness_message = f"Critical failures: {', '.join(failed_requirements)}"
            elif len(warning_requirements) > 2:
                readiness_status = 'AT_RISK'
                readiness_message = f"Multiple warnings: {', '.join(warning_requirements)}"
            elif warning_requirements:
                readiness_status = 'READY_WITH_MONITORING'
                readiness_message = f"Ready with monitoring: {', '.join(warning_requirements)}"
            else:
                readiness_status = 'READY'
                readiness_message = "All critical SLA requirements met"
            
            return {
                'status': readiness_status,
                'message': readiness_message,
                'overall_compliance': status['overall_compliance'],
                'critical_failures': failed_requirements,
                'warnings': warning_requirements,
                'assessment_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to assess production readiness: {e}")
            return {'error': str(e)}
    
    def _get_metric_status(self, status: Dict[str, Any], metric_name: str) -> Dict[str, Any]:
        """Get formatted metric status for reports"""
        metric = status['metrics'][metric_name]
        return {
            'current_value': metric['current_value'],
            'target_value': metric['target_value'],
            'unit': metric['unit'],
            'status': metric['status'],
            'trend': metric['trend']
        }
    
    def _analyze_performance_trends(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance trends from report data"""
        trends = {}
        
        for metric_name, metric_data in report['sla_compliance_summary'].items():
            if metric_data['samples'] > 5:  # Need enough data for trend analysis
                # Simple trend analysis based on average vs target
                avg_performance = metric_data['average']
                target_value = self.sla_monitor.sla_metrics[metric_name].target_value
                
                # Calculate performance ratio
                if metric_name in ['voice_concurrent_sessions', 'whatsapp_throughput', 'system_wide_concurrent_users']:
                    # Higher is better
                    performance_ratio = avg_performance / target_value
                else:
                    # Lower is better
                    performance_ratio = target_value / avg_performance
                
                if performance_ratio >= 1.0:
                    trend_status = 'EXCEEDING_TARGET'
                elif performance_ratio >= 0.9:
                    trend_status = 'MEETING_TARGET'
                elif performance_ratio >= 0.8:
                    trend_status = 'APPROACHING_LIMIT'
                else:
                    trend_status = 'BELOW_TARGET'
                
                trends[metric_name] = {
                    'status': trend_status,
                    'performance_ratio': performance_ratio,
                    'average_value': avg_performance
                }
        
        return trends
    
    def _generate_executive_recommendations(self, status: Dict[str, Any], production_readiness: Dict[str, Any]) -> List[str]:
        """Generate executive recommendations"""
        recommendations = []
        
        if production_readiness['status'] == 'NOT_READY':
            recommendations.append("🚨 CRITICAL: Address failed SLA requirements before production deployment")
        
        if status['alerts']['critical'] > 0:
            recommendations.append("🔥 Immediate action required: Resolve critical performance issues")
        
        if status['overall_compliance'] < 90:
            recommendations.append("⚠️ Consider infrastructure scaling to improve SLA compliance")
        
        if status['alerts']['warning'] > 3:
            recommendations.append("📊 Monitor system closely - multiple warning conditions present")
        
        if not recommendations:
            recommendations.append("✅ System performing well - maintain current monitoring")
        
        return recommendations
    
    def _generate_technical_recommendations(self, status: Dict[str, Any], report: Dict[str, Any]) -> List[str]:
        """Generate technical optimization recommendations"""
        recommendations = []
        
        # Voice system recommendations
        voice_response = status['metrics']['voice_response_time']
        if voice_response['status'] != 'OK':
            recommendations.append(f"Optimize voice response time - currently {voice_response['current_value']:.2f}s")
        
        # WhatsApp system recommendations
        whatsapp_processing = status['metrics']['whatsapp_processing_time']
        if whatsapp_processing['status'] != 'OK':
            recommendations.append(f"Optimize WhatsApp processing - currently {whatsapp_processing['current_value']:.2f}s")
        
        # Infrastructure recommendations
        memory_usage = status['metrics']['memory_usage']
        if memory_usage['current_value'] and memory_usage['current_value'] > 3000:  # 3GB
            recommendations.append("Consider memory optimization - usage approaching limits")
        
        # Database recommendations
        db_performance = status['metrics']['database_query_time']
        if db_performance['status'] != 'OK':
            recommendations.append("Optimize database queries - performance degraded")
        
        # Capacity recommendations
        concurrent_users = status['metrics']['system_wide_concurrent_users']
        if concurrent_users['current_value'] and concurrent_users['current_value'] > 400:
            recommendations.append("Plan capacity scaling - approaching concurrent user limits")
        
        return recommendations


# HTML template for dashboard (would be in templates/dashboard.html in production)
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{page_title}}</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        // Real-time WebSocket connection
        const ws = new WebSocket('ws://localhost:8080/ws');
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };
        
        function updateDashboard(data) {
            // Update overall compliance
            document.getElementById('overall-compliance').textContent = data.overall_compliance.toFixed(1) + '%';
            
            // Update alerts
            document.getElementById('active-alerts').textContent = data.alerts.active;
            document.getElementById('critical-alerts').textContent = data.alerts.critical;
            document.getElementById('warning-alerts').textContent = data.alerts.warning;
            
            // Update metrics table
            updateMetricsTable(data.metrics);
        }
        
        function updateMetricsTable(metrics) {
            const tbody = document.getElementById('metrics-tbody');
            tbody.innerHTML = '';
            
            for (const [name, metric] of Object.entries(metrics)) {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td class="px-4 py-2">${name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</td>
                    <td class="px-4 py-2">${metric.current_value?.toFixed(2) || 'N/A'}</td>
                    <td class="px-4 py-2">${metric.target_value} ${metric.unit}</td>
                    <td class="px-4 py-2">
                        <span class="px-2 py-1 rounded text-sm ${getStatusColor(metric.status)}">
                            ${metric.status}
                        </span>
                    </td>
                    <td class="px-4 py-2">${metric.trend}</td>
                `;
                tbody.appendChild(row);
            }
        }
        
        function getStatusColor(status) {
            switch(status) {
                case 'OK': return 'bg-green-200 text-green-800';
                case 'WARNING': return 'bg-yellow-200 text-yellow-800';
                case 'CRITICAL': return 'bg-red-200 text-red-800';
                default: return 'bg-gray-200 text-gray-800';
            }
        }
        
        // Load charts
        async function loadCharts() {
            // SLA Compliance Chart
            const slaResponse = await fetch('/api/charts/sla-compliance');
            const slaData = await slaResponse.json();
            Plotly.newPlot('sla-chart', slaData.chart_data.data, slaData.chart_data.layout);
            
            // Performance Trends Chart
            const trendsResponse = await fetch('/api/charts/performance-trends');
            const trendsData = await trendsResponse.json();
            Plotly.newPlot('trends-chart', trendsData.chart_data.data, trendsData.chart_data.layout);
        }
        
        // Load charts when page loads
        window.onload = loadCharts;
    </script>
</head>
<body class="bg-gray-100">
    <div class="container mx-auto px-4 py-8">
        <h1 class="text-3xl font-bold mb-8">AI Agency Platform - SLA Performance Dashboard</h1>
        
        <!-- Status Overview -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Overall Compliance</h3>
                <p id="overall-compliance" class="text-3xl font-bold text-blue-600">{{status.overall_compliance|round(1)}}%</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Active Alerts</h3>
                <p id="active-alerts" class="text-3xl font-bold text-yellow-600">{{status.alerts.active}}</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Critical Issues</h3>
                <p id="critical-alerts" class="text-3xl font-bold text-red-600">{{status.alerts.critical}}</p>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h3 class="text-lg font-semibold text-gray-700">Warnings</h3>
                <p id="warning-alerts" class="text-3xl font-bold text-orange-600">{{status.alerts.warning}}</p>
            </div>
        </div>
        
        <!-- SLA Metrics Table -->
        <div class="bg-white rounded-lg shadow mb-8">
            <div class="px-6 py-4 border-b">
                <h2 class="text-xl font-semibold">SLA Metrics</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-2 text-left">Metric</th>
                            <th class="px-4 py-2 text-left">Current</th>
                            <th class="px-4 py-2 text-left">Target</th>
                            <th class="px-4 py-2 text-left">Status</th>
                            <th class="px-4 py-2 text-left">Trend</th>
                        </tr>
                    </thead>
                    <tbody id="metrics-tbody">
                        {% for name, metric in status.metrics.items() %}
                        <tr>
                            <td class="px-4 py-2">{{name.replace('_', ' ').title()}}</td>
                            <td class="px-4 py-2">{{metric.current_value|round(2) if metric.current_value else 'N/A'}}</td>
                            <td class="px-4 py-2">{{metric.target_value}} {{metric.unit}}</td>
                            <td class="px-4 py-2">
                                <span class="px-2 py-1 rounded text-sm 
                                    {% if metric.status == 'OK' %}bg-green-200 text-green-800
                                    {% elif metric.status == 'WARNING' %}bg-yellow-200 text-yellow-800
                                    {% elif metric.status == 'CRITICAL' %}bg-red-200 text-red-800
                                    {% else %}bg-gray-200 text-gray-800{% endif %}">
                                    {{metric.status}}
                                </span>
                            </td>
                            <td class="px-4 py-2">{{metric.trend}}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Charts -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div class="bg-white p-6 rounded-lg shadow">
                <h2 class="text-xl font-semibold mb-4">SLA Compliance Status</h2>
                <div id="sla-chart"></div>
            </div>
            <div class="bg-white p-6 rounded-lg shadow">
                <h2 class="text-xl font-semibold mb-4">Performance Trends</h2>
                <div id="trends-chart"></div>
            </div>
        </div>
        
        <!-- Quick Actions -->
        <div class="mt-8 bg-white p-6 rounded-lg shadow">
            <h2 class="text-xl font-semibold mb-4">Quick Actions</h2>
            <div class="flex flex-wrap gap-4">
                <a href="/reports/executive" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
                    Executive Report
                </a>
                <a href="/reports/technical/24" class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">
                    Technical Report (24h)
                </a>
                <a href="/production-readiness" class="bg-purple-600 text-white px-4 py-2 rounded hover:bg-purple-700">
                    Production Readiness
                </a>
                <button onclick="window.location.reload()" class="bg-gray-600 text-white px-4 py-2 rounded hover:bg-gray-700">
                    Refresh Dashboard
                </button>
            </div>
        </div>
    </div>
</body>
</html>
"""

if __name__ == "__main__":
    async def main():
        """Run performance dashboard"""
        # Create SLA monitor
        sla_monitor = SLAMonitor()
        
        # Start SLA monitoring
        await sla_monitor.start_monitoring()
        
        # Create and start dashboard
        dashboard = PerformanceDashboard(sla_monitor)
        
        try:
            await dashboard.start_dashboard()
        except KeyboardInterrupt:
            logger.info("Shutting down performance dashboard...")
        finally:
            await dashboard.stop_dashboard()
            await sla_monitor.stop_monitoring()
    
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())