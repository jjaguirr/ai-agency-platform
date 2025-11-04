#!/usr/bin/env python3
"""
Attention Span Parameter System for Executive Assistant
Controls how focused the EA is on single tasks vs. multi-tasking
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import json

logger = logging.getLogger(__name__)

class AttentionSpanMode(Enum):
    """Different attention span modes for the EA"""
    LASER_FOCUSED = "laser_focused"      # Single task, maximum depth
    BALANCED = "balanced"                # Multi-task with good context
    MULTI_TASKING = "multi_tasking"      # Handle multiple tasks simultaneously
    BACKGROUND_MONITOR = "background"     # Monitor while doing other work
    SCANNING = "scanning"                # Quick overview, surface level

@dataclass
class AttentionSpanConfig:
    """Configuration for EA attention span behavior"""
    mode: AttentionSpanMode = AttentionSpanMode.BALANCED
    context_window_size: int = 10           # Number of recent messages to remember
    task_switching_threshold: float = 0.7   # When to consider switching tasks (0-1)
    focus_duration_minutes: int = 15        # How long to stay focused on one task
    memory_retention_hours: int = 24        # How long to retain task context
    tool_access_level: str = "standard"     # "minimal", "standard", "extended"
    max_concurrent_tasks: int = 3           # Maximum tasks to handle simultaneously

    def to_dict(self) -> Dict:
        """Convert to dictionary for storage"""
        return {
            "mode": self.mode.value,
            "context_window_size": self.context_window_size,
            "task_switching_threshold": self.task_switching_threshold,
            "focus_duration_minutes": self.focus_duration_minutes,
            "memory_retention_hours": self.memory_retention_hours,
            "tool_access_level": self.tool_access_level,
            "max_concurrent_tasks": self.max_concurrent_tasks
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'AttentionSpanConfig':
        """Create from dictionary"""
        return cls(
            mode=AttentionSpanMode(data.get("mode", "balanced")),
            context_window_size=data.get("context_window_size", 10),
            task_switching_threshold=data.get("task_switching_threshold", 0.7),
            focus_duration_minutes=data.get("focus_duration_minutes", 15),
            memory_retention_hours=data.get("memory_retention_hours", 24),
            tool_access_level=data.get("tool_access_level", "standard"),
            max_concurrent_tasks=data.get("max_concurrent_tasks", 3)
        )

@dataclass
class TaskContext:
    """Context for a specific task the EA is working on"""
    task_id: str
    description: str
    start_time: datetime
    priority: str = "normal"  # "low", "normal", "high", "critical"
    status: str = "active"    # "active", "paused", "completed", "archived"
    messages: List[Dict] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

class AttentionSpanManager:
    """Manages EA attention span and task focus"""

    def __init__(self, customer_id: str, config: Optional[AttentionSpanConfig] = None):
        self.customer_id = customer_id
        self.config = config or AttentionSpanConfig()

        # Task management
        self.current_focus_task: Optional[str] = None
        self.focus_start_time: Optional[datetime] = None
        self.active_tasks: Dict[str, TaskContext] = {}
        self.task_history: List[TaskContext] = []

        # Attention metrics
        self.attention_metrics = {
            "tasks_completed": 0,
            "context_switches": 0,
            "focus_duration_total": 0,
            "last_activity": datetime.now()
        }

        logger.info(f"Attention span manager initialized for {customer_id} with mode: {self.config.mode.value}")

    async def process_message(self, message: str, channel: str) -> Dict:
        """Process message with attention span awareness"""
        current_time = datetime.now()

        # Update activity timestamp
        self.attention_metrics["last_activity"] = current_time

        # Analyze message for task relevance
        task_analysis = await self._analyze_task_relevance(message)

        # Check if we should switch focus
        should_switch = await self._should_switch_focus(task_analysis, current_time)

        if should_switch:
            await self._switch_focus(task_analysis.primary_task, message, channel)

        # Process with current attention span
        result = await self._process_with_current_focus(message, channel, task_analysis)

        # Update attention metrics
        await self._update_attention_metrics(task_analysis)

        return result

    async def _analyze_task_relevance(self, message: str) -> Dict:
        """Analyze message for task relevance and priority"""
        # Simple keyword-based analysis (can be enhanced with AI)
        message_lower = message.lower()

        # Task type detection
        task_keywords = {
            "automation": ["automate", "workflow", "automation", "process"],
            "analysis": ["analyze", "report", "data", "metrics", "performance"],
            "communication": ["email", "message", "contact", "call", "respond"],
            "planning": ["plan", "schedule", "organize", "strategy", "meeting"],
            "research": ["research", "find", "search", "information", "learn"]
        }

        detected_tasks = []
        for task_type, keywords in task_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                detected_tasks.append(task_type)

        # Priority assessment
        priority_keywords = {
            "critical": ["urgent", "asap", "emergency", "critical", "important"],
            "high": ["priority", "soon", "quickly", "rush"],
            "normal": ["when possible", "later", "sometime"]
        }

        priority = "normal"
        for priority_level, keywords in priority_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                priority = priority_level
                break

        return {
            "primary_task": detected_tasks[0] if detected_tasks else "general",
            "detected_tasks": detected_tasks,
            "priority": priority,
            "relevance_score": min(1.0, len(detected_tasks) * 0.3 + (0.5 if priority == "critical" else 0.2)),
            "message_length": len(message),
            "complexity_indicators": len([w for w in message.split() if len(w) > 6])  # Long words indicate complexity
        }

    async def _should_switch_focus(self, task_analysis: Dict, current_time: datetime) -> bool:
        """Determine if EA should switch attention to new task"""
        # Check focus duration
        if (self.focus_start_time and
            (current_time - self.focus_start_time).seconds > self.config.focus_duration_minutes * 60):
            return True

        # Check task relevance threshold
        if task_analysis["relevance_score"] > self.config.task_switching_threshold:
            return True

        # Check if we're at max concurrent tasks
        active_count = len([t for t in self.active_tasks.values() if t.status == "active"])
        if active_count >= self.config.max_concurrent_tasks:
            return True

        return False

    async def _switch_focus(self, new_task: str, message: str, channel: str):
        """Switch attention to new task while preserving context"""
        current_time = datetime.now()

        # Archive current task context if exists
        if self.current_focus_task and self.current_focus_task in self.active_tasks:
            await self._archive_current_task()

        # Create new task context
        task_id = f"task_{current_time.timestamp()}_{hash(new_task) % 10000}"
        new_task_context = TaskContext(
            task_id=task_id,
            description=new_task,
            start_time=current_time,
            priority="normal",
            messages=[{
                "content": message,
                "channel": channel,
                "timestamp": current_time.isoformat()
            }]
        )

        self.active_tasks[task_id] = new_task_context
        self.current_focus_task = task_id
        self.focus_start_time = current_time

        # Update metrics
        self.attention_metrics["context_switches"] += 1

        logger.info(f"🔄 Switched focus to task: {new_task} (ID: {task_id})")

    async def _archive_current_task(self):
        """Archive current task and move to history"""
        if self.current_focus_task and self.current_focus_task in self.active_tasks:
            task = self.active_tasks[self.current_focus_task]
            task.status = "completed"

            # Calculate focus duration
            if self.focus_start_time:
                focus_duration = datetime.now() - self.focus_start_time
                self.attention_metrics["focus_duration_total"] += focus_duration.seconds

            self.task_history.append(task)
            del self.active_tasks[self.current_focus_task]

            # Keep only last 50 tasks in history
            if len(self.task_history) > 50:
                self.task_history = self.task_history[-50:]

    async def _process_with_current_focus(self, message: str, channel: str, task_analysis: Dict) -> Dict:
        """Process message with current attention focus"""
        current_time = datetime.now()

        # Add message to current task context
        if self.current_focus_task and self.current_focus_task in self.active_tasks:
            task = self.active_tasks[self.current_focus_task]
            task.messages.append({
                "content": message,
                "channel": channel,
                "timestamp": current_time.isoformat()
            })

        # Adjust processing based on attention mode
        if self.config.mode == AttentionSpanMode.LASER_FOCUSED:
            # Deep focus processing
            context_messages = await self._get_focused_context()
            max_tokens = 1000
        elif self.config.mode == AttentionSpanMode.MULTI_TASKING:
            # Multi-task processing
            context_messages = await self._get_multi_task_context()
            max_tokens = 500
        else:
            # Balanced processing
            context_messages = await self._get_balanced_context()
            max_tokens = 750

        return {
            "context_messages": context_messages,
            "max_tokens": max_tokens,
            "current_task": self.current_focus_task,
            "attention_mode": self.config.mode.value,
            "task_count": len(self.active_tasks)
        }

    async def _get_focused_context(self) -> List[Dict]:
        """Get context focused on current task"""
        if self.current_focus_task and self.current_focus_task in self.active_tasks:
            task = self.active_tasks[self.current_focus_task]
            return task.messages[-self.config.context_window_size:]
        return []

    async def _get_multi_task_context(self) -> List[Dict]:
        """Get context from multiple active tasks"""
        context_messages = []

        for task in self.active_tasks.values():
            if task.status == "active":
                # Add last 2 messages from each active task
                context_messages.extend(task.messages[-2:])

        # Sort by timestamp and limit
        context_messages.sort(key=lambda x: x.get("timestamp", ""))
        return context_messages[-self.config.context_window_size:]

    async def _get_balanced_context(self) -> List[Dict]:
        """Get balanced context from current task and recent messages"""
        context = []

        # Add current task messages
        if self.current_focus_task and self.current_focus_task in self.active_tasks:
            task = self.active_tasks[self.current_focus_task]
            context.extend(task.messages[-5:])  # Last 5 from current task

        # Add recent messages from other tasks
        for task_id, task in self.active_tasks.items():
            if task_id != self.current_focus_task and task.status == "active":
                context.extend(task.messages[-2:])  # Last 2 from other tasks

        # Sort by timestamp and limit
        context.sort(key=lambda x: x.get("timestamp", ""))
        return context[-self.config.context_window_size:]

    async def _update_attention_metrics(self, task_analysis: Dict):
        """Update attention span metrics"""
        # Track task completion
        if task_analysis["primary_task"] != "general":
            # Simple heuristic: if message contains completion keywords, mark task complete
            completion_keywords = ["done", "finished", "complete", "thanks", "perfect"]
            if any(keyword in task_analysis.get("message", "").lower() for keyword in completion_keywords):
                if self.current_focus_task:
                    await self._archive_current_task()
                    self.attention_metrics["tasks_completed"] += 1

    def get_attention_metrics(self) -> Dict:
        """Get current attention span metrics"""
        return {
            **self.attention_metrics,
            "current_mode": self.config.mode.value,
            "active_tasks": len(self.active_tasks),
            "current_focus_task": self.current_focus_task,
            "focus_duration_minutes": (
                (datetime.now() - self.focus_start_time).seconds / 60
                if self.focus_start_time else 0
            )
        }

    def update_config(self, new_config: AttentionSpanConfig):
        """Update attention span configuration"""
        self.config = new_config
        logger.info(f"Attention span config updated to mode: {new_config.mode.value}")

# Factory function for easy creation
def create_attention_manager(customer_id: str, mode: str = "balanced") -> AttentionSpanManager:
    """Create attention span manager with specified mode"""
    config = AttentionSpanConfig(mode=AttentionSpanMode(mode))
    return AttentionSpanManager(customer_id, config)

# Example usage and testing
async def test_attention_span_system():
    """Test the attention span system"""
    print("🧠 === Testing Attention Span System ===\n")

    # Create attention manager
    manager = create_attention_manager("test-customer", "balanced")

    # Test different modes
    modes_to_test = [
        AttentionSpanMode.LASER_FOCUSED,
        AttentionSpanMode.MULTI_TASKING,
        AttentionSpanMode.BACKGROUND_MONITOR
    ]

    for mode in modes_to_test:
        print(f"🔄 Testing mode: {mode.value}")

        # Update config
        config = AttentionSpanConfig(mode=mode)
        manager.update_config(config)

        # Process some messages
        test_messages = [
            "I need help automating my social media posts",
            "Can you also help me with email management?",
            "What about customer support automation?"
        ]

        for msg in test_messages:
            result = await manager.process_message(msg, "whatsapp")
            print(f"  Message: {msg[:50]}...")
            print(f"  Current task: {result['current_task']}")
            print(f"  Task count: {result['task_count']}")

        # Show metrics
        metrics = manager.get_attention_metrics()
        print(f"  Metrics: {metrics['context_switches']} switches, {metrics['tasks_completed']} completed\n")

    print("✅ Attention span system test completed!")

if __name__ == "__main__":
    asyncio.run(test_attention_span_system())