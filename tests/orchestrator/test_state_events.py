"""
Days 14-15: State Management & Event Bus Tests

Tests for StateManager and EventBus integration.
"""

import pytest
from pathlib import Path
import json
import threading
import time

from src.orchestrator.state import StateManager
from src.orchestrator.events import EventBus, EventTypes


class TestStateManager:
    """Tests for StateManager"""

    def test_init_creates_empty_state(self, tmp_path):
        """Should initialize with empty state"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        assert manager._state["tasks"] == {}
        assert manager._state["dependencies"] == {}
        assert manager._state["completed"] == set()
        assert manager._state["blockers"] == []

    def test_register_task(self, tmp_path):
        """Should register a new task"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task(
            task_id="task-001",
            agent_id="agent-001",
            phase="PLAN",
            dependencies=["task-000"]
        )

        assert "task-001" in manager._state["tasks"]
        assert manager._state["tasks"]["task-001"]["agent_id"] == "agent-001"
        assert manager._state["tasks"]["task-001"]["phase"] == "PLAN"
        assert manager._state["dependencies"]["task-001"] == ["task-000"]

    def test_register_task_without_dependencies(self, tmp_path):
        """Should register task without dependencies"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task(
            task_id="task-001",
            agent_id="agent-001",
            phase="PLAN",
            dependencies=None
        )

        assert "task-001" in manager._state["tasks"]
        assert "task-001" not in manager._state["dependencies"]

    def test_update_phase(self, tmp_path):
        """Should update task phase"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN")
        manager.update_phase("task-001", "TDD")

        assert manager._state["tasks"]["task-001"]["phase"] == "TDD"
        assert len(manager._state["tasks"]["task-001"]["transitions"]) == 1
        assert manager._state["tasks"]["task-001"]["transitions"][0]["phase"] == "TDD"

    def test_mark_completed(self, tmp_path):
        """Should mark task as completed"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN")
        manager.mark_completed("task-001")

        assert "task-001" in manager._state["completed"]
        assert "completed_at" in manager._state["tasks"]["task-001"]

    def test_add_blocker(self, tmp_path):
        """Should add blocker for task"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN")
        manager.add_blocker("task-001", "Missing API key")

        assert len(manager._state["blockers"]) == 1
        assert manager._state["blockers"][0]["task_id"] == "task-001"
        assert manager._state["blockers"][0]["blocker"] == "Missing API key"

    def test_get_snapshot(self, tmp_path):
        """Should get state snapshot for task"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        # Register tasks with dependencies
        manager.register_task("task-001", "agent-001", "PLAN", dependencies=["task-000"])
        manager.register_task("task-000", "agent-000", "PLAN")
        manager.mark_completed("task-000")
        manager.add_blocker("task-001", "Waiting for approval")

        snapshot = manager.get_snapshot("task-001")

        assert snapshot["task_dependencies"] == ["task-000"]
        assert snapshot["completed_tasks"] == ["task-000"]
        assert snapshot["current_phase"] == "PLAN"
        assert snapshot["blockers"] == ["Waiting for approval"]

    def test_get_all_tasks(self, tmp_path):
        """Should get all tasks"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN")
        manager.register_task("task-002", "agent-002", "TDD")

        tasks = manager.get_all_tasks()

        assert len(tasks) == 2
        assert "task-001" in tasks
        assert "task-002" in tasks

    def test_is_task_unblocked_all_complete(self, tmp_path):
        """Should return true when all dependencies complete"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN", dependencies=["task-000"])
        manager.mark_completed("task-000")

        assert manager.is_task_unblocked("task-001") is True

    def test_is_task_unblocked_incomplete(self, tmp_path):
        """Should return false when dependencies incomplete"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN", dependencies=["task-000"])

        assert manager.is_task_unblocked("task-001") is False

    def test_is_task_unblocked_no_dependencies(self, tmp_path):
        """Should return true when no dependencies"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        manager.register_task("task-001", "agent-001", "PLAN")

        assert manager.is_task_unblocked("task-001") is True

    def test_state_persistence(self, tmp_path):
        """Should persist state to file"""
        state_file = tmp_path / "state.json"
        manager1 = StateManager(state_file)

        manager1.register_task("task-001", "agent-001", "PLAN")
        manager1.mark_completed("task-001")

        # Create new manager instance (loads from file)
        manager2 = StateManager(state_file)

        assert "task-001" in manager2._state["tasks"]
        assert "task-001" in manager2._state["completed"]

    def test_thread_safety(self, tmp_path):
        """Should be thread-safe"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)

        # Register 100 tasks from 10 threads
        def register_tasks(start_id):
            for i in range(10):
                task_id = f"task-{start_id + i}"
                manager.register_task(task_id, f"agent-{start_id}", "PLAN")

        threads = []
        for i in range(10):
            t = threading.Thread(target=register_tasks, args=(i * 10,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have 100 tasks
        assert len(manager._state["tasks"]) == 100


class TestEventBus:
    """Tests for EventBus"""

    def test_init_empty(self):
        """Should initialize with no subscribers"""
        bus = EventBus()

        assert bus._subscribers == {}
        assert bus._event_history == []

    def test_subscribe(self):
        """Should subscribe to event type"""
        bus = EventBus()
        handler_called = []

        def handler(event):
            handler_called.append(event)

        bus.subscribe("test.event", handler)

        assert "test.event" in bus._subscribers
        assert handler in bus._subscribers["test.event"]

    def test_publish_notifies_subscribers(self):
        """Should notify all subscribers"""
        bus = EventBus()
        events_received = []

        def handler1(event):
            events_received.append(("handler1", event))

        def handler2(event):
            events_received.append(("handler2", event))

        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)

        bus.publish("test.event", {"data": "value"})

        assert len(events_received) == 2
        assert events_received[0][0] == "handler1"
        assert events_received[1][0] == "handler2"
        assert events_received[0][1]["data"]["data"] == "value"

    def test_publish_stores_in_history(self):
        """Should store events in history"""
        bus = EventBus()

        bus.publish("test.event", {"data": "value1"})
        bus.publish("test.event", {"data": "value2"})

        assert len(bus._event_history) == 2
        assert bus._event_history[0]["type"] == "test.event"
        assert bus._event_history[0]["data"]["data"] == "value1"
        assert bus._event_history[1]["data"]["data"] == "value2"

    def test_publish_includes_timestamp(self):
        """Should include timestamp in events"""
        bus = EventBus()

        bus.publish("test.event", {"data": "value"})

        assert "timestamp" in bus._event_history[0]

    def test_publish_continues_on_handler_error(self):
        """Should continue publishing even if handler fails"""
        bus = EventBus()
        handler2_called = []

        def handler1(event):
            raise Exception("Handler error")

        def handler2(event):
            handler2_called.append(event)

        bus.subscribe("test.event", handler1)
        bus.subscribe("test.event", handler2)

        bus.publish("test.event", {"data": "value"})

        # Handler2 should still be called
        assert len(handler2_called) == 1

    def test_get_history_all(self):
        """Should get all history"""
        bus = EventBus()

        bus.publish("event1", {"data": "1"})
        bus.publish("event2", {"data": "2"})
        bus.publish("event3", {"data": "3"})

        history = bus.get_history()

        assert len(history) == 3
        # Most recent first
        assert history[0]["type"] == "event3"
        assert history[1]["type"] == "event2"
        assert history[2]["type"] == "event1"

    def test_get_history_filtered_by_type(self):
        """Should filter history by event type"""
        bus = EventBus()

        bus.publish("event.a", {"data": "1"})
        bus.publish("event.b", {"data": "2"})
        bus.publish("event.a", {"data": "3"})

        history = bus.get_history(event_type="event.a")

        assert len(history) == 2
        assert history[0]["type"] == "event.a"
        assert history[1]["type"] == "event.a"

    def test_get_history_limited(self):
        """Should limit history size"""
        bus = EventBus()

        for i in range(20):
            bus.publish("test.event", {"data": str(i)})

        history = bus.get_history(limit=5)

        assert len(history) == 5
        # Most recent 5
        assert history[0]["data"]["data"] == "19"
        assert history[4]["data"]["data"] == "15"

    def test_clear_history(self):
        """Should clear event history"""
        bus = EventBus()

        bus.publish("test.event", {"data": "value"})
        bus.clear_history()

        assert len(bus._event_history) == 0

    def test_thread_safety(self):
        """Should be thread-safe"""
        bus = EventBus()
        events_received = []

        def handler(event):
            events_received.append(event)

        bus.subscribe("test.event", handler)

        # Publish 100 events from 10 threads
        def publish_events(start_id):
            for i in range(10):
                bus.publish("test.event", {"id": start_id + i})

        threads = []
        for i in range(10):
            t = threading.Thread(target=publish_events, args=(i * 10,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have 100 events
        assert len(bus._event_history) == 100
        assert len(events_received) == 100


class TestEventTypes:
    """Tests for EventTypes constants"""

    def test_event_types_defined(self):
        """Should have all required event types"""
        assert EventTypes.TASK_CLAIMED == "task.claimed"
        assert EventTypes.TASK_TRANSITIONED == "task.transitioned"
        assert EventTypes.TASK_COMPLETED == "task.completed"
        assert EventTypes.TOOL_EXECUTED == "tool.executed"
        assert EventTypes.GATE_BLOCKED == "gate.blocked"
        assert EventTypes.GATE_PASSED == "gate.passed"


class TestStateEventIntegration:
    """Tests for StateManager and EventBus integration"""

    def test_task_lifecycle_with_events(self, tmp_path):
        """Should track task lifecycle through state and events"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)
        bus = EventBus()

        # Track events
        events_received = []

        def event_handler(event):
            events_received.append(event)

        bus.subscribe(EventTypes.TASK_CLAIMED, event_handler)
        bus.subscribe(EventTypes.TASK_TRANSITIONED, event_handler)
        bus.subscribe(EventTypes.TASK_COMPLETED, event_handler)

        # 1. Claim task
        manager.register_task("task-001", "agent-001", "PLAN")
        bus.publish(EventTypes.TASK_CLAIMED, {
            "task_id": "task-001",
            "agent_id": "agent-001",
            "phase": "PLAN"
        })

        # 2. Transition phase
        manager.update_phase("task-001", "TDD")
        bus.publish(EventTypes.TASK_TRANSITIONED, {
            "task_id": "task-001",
            "from_phase": "PLAN",
            "to_phase": "TDD"
        })

        # 3. Complete task
        manager.mark_completed("task-001")
        bus.publish(EventTypes.TASK_COMPLETED, {
            "task_id": "task-001"
        })

        # Verify state
        assert manager._state["tasks"]["task-001"]["phase"] == "TDD"
        assert "task-001" in manager._state["completed"]

        # Verify events
        assert len(events_received) == 3
        assert events_received[0]["type"] == EventTypes.TASK_CLAIMED
        assert events_received[1]["type"] == EventTypes.TASK_TRANSITIONED
        assert events_received[2]["type"] == EventTypes.TASK_COMPLETED

    def test_multi_agent_coordination(self, tmp_path):
        """Should coordinate multiple agents through state and events"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)
        bus = EventBus()

        # Track completion events
        completions = []

        def completion_handler(event):
            completions.append(event["data"]["task_id"])

        bus.subscribe(EventTypes.TASK_COMPLETED, completion_handler)

        # Agent 1: task-001 (no dependencies)
        manager.register_task("task-001", "agent-001", "PLAN")
        manager.mark_completed("task-001")
        bus.publish(EventTypes.TASK_COMPLETED, {"task_id": "task-001"})

        # Agent 2: task-002 (depends on task-001)
        manager.register_task("task-002", "agent-002", "PLAN", dependencies=["task-001"])

        # task-002 should be unblocked now
        assert manager.is_task_unblocked("task-002") is True

        manager.mark_completed("task-002")
        bus.publish(EventTypes.TASK_COMPLETED, {"task_id": "task-002"})

        # Verify coordination
        assert completions == ["task-001", "task-002"]
        assert "task-001" in manager._state["completed"]
        assert "task-002" in manager._state["completed"]

    def test_gate_blocking_workflow(self, tmp_path):
        """Should track gate blocking through state and events"""
        state_file = tmp_path / "state.json"
        manager = StateManager(state_file)
        bus = EventBus()

        # Track gate events
        gate_events = []

        def gate_handler(event):
            gate_events.append(event)

        bus.subscribe(EventTypes.GATE_BLOCKED, gate_handler)
        bus.subscribe(EventTypes.GATE_PASSED, gate_handler)

        # Register task
        manager.register_task("task-001", "agent-001", "PLAN")

        # Gate blocked
        manager.add_blocker("task-001", "Missing required artifact")
        bus.publish(EventTypes.GATE_BLOCKED, {
            "task_id": "task-001",
            "gate_id": "plan_approval",
            "blockers": ["Missing required artifact"]
        })

        # Verify blocker in state
        snapshot = manager.get_snapshot("task-001")
        assert "Missing required artifact" in snapshot["blockers"]

        # Gate passed (after fixing)
        bus.publish(EventTypes.GATE_PASSED, {
            "task_id": "task-001",
            "gate_id": "plan_approval"
        })

        # Verify events
        assert len(gate_events) == 2
        assert gate_events[0]["type"] == EventTypes.GATE_BLOCKED
        assert gate_events[1]["type"] == EventTypes.GATE_PASSED
