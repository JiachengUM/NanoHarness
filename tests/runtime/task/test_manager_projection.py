from aicore.events.task import (
    TaskCancelledEvent,
    TaskCreatedEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
import pytest

from aicore.runtime.task import (
    TaskManager,
    TaskProjection,
    TaskRun,
    TaskRunBase,
    TaskStatus,
)


def test_task_projection_and_run_share_base_model() -> None:
    assert issubclass(TaskProjection, TaskRunBase)
    assert issubclass(TaskRun, TaskRunBase)

    # TaskProjection 与 TaskRunBase 共享相同的字段名集合（TaskProjection 收紧了类型但未增删字段）
    assert set(TaskProjection.model_fields) == set(TaskRunBase.model_fields)

    # TaskRun 的额外字段不会泄漏到 TaskProjection
    run_only_fields = set(TaskRun.model_fields) - set(TaskRunBase.model_fields)
    projection_fields = set(TaskProjection.model_fields)
    assert run_only_fields.isdisjoint(projection_fields)


def test_apply_created_then_start_preserves_projection() -> None:
    manager = TaskManager()

    created = manager.apply_created(
        TaskCreatedEvent(
            task_id="weather-1",
            name="weather_search",
            arguments={"city": "香港"},
        )
    )
    started = manager.apply_event(TaskStartEvent(task_id="weather-1"))

    assert created.applied is True
    assert started.applied is True

    projection = manager.get_projection("weather-1")
    assert projection is not None
    assert projection.task_id == "weather-1"
    assert projection.tool_name == "weather_search"
    assert projection.arguments == {"city": "香港"}
    assert projection.status == TaskStatus.RUNNING


def test_apply_start_then_created_enriches_placeholder_projection() -> None:
    manager = TaskManager()

    started = manager.apply_event(TaskStartEvent(task_id="weather-1"))
    created = manager.apply_created(
        TaskCreatedEvent(
            task_id="weather-1",
            name="weather_search",
            arguments={"city": "上海"},
        )
    )

    run = manager.get_task("weather-1")
    projection = manager.get_projection("weather-1")
    active_projection = manager.get_active_task_projections()
    assert run is not None
    assert projection is not None
    assert started.applied is True
    assert created.applied is True
    assert created.current_status == TaskStatus.RUNNING
    assert run.status == TaskStatus.RUNNING
    assert run.task_def_id == "weather_search"
    assert run.tool_name == "weather_search"
    assert run.arguments == {"city": "上海"}
    assert projection.tool_name == "weather_search"
    assert projection.arguments == {"city": "上海"}
    assert projection.status == TaskStatus.RUNNING
    assert active_projection == [projection]


def test_manager_does_not_expose_cancel_mutation_api() -> None:
    manager = TaskManager()

    assert not hasattr(manager, "mark_cancel_requested")


def test_cancelled_event_removes_task_from_active_projection() -> None:
    manager = TaskManager()
    manager.apply_created(
        TaskCreatedEvent(
            task_id="poi-1",
            name="poi_search",
            arguments={"city": "上海", "type": "酒店"},
        )
    )
    manager.apply_event(TaskStartEvent(task_id="poi-1"))

    result = manager.apply_event(TaskCancelledEvent(task_id="poi-1", reason="user cancel"))

    assert result.applied is True
    assert result.current_status == TaskStatus.CANCELLED
    assert manager.get_active_task_projections() == []


def test_late_success_after_cancelled_event_is_rejected() -> None:
    manager = TaskManager()
    manager.apply_created(
        TaskCreatedEvent(task_id="music-1", name="music_search", arguments={"artist": "张学友"})
    )
    manager.apply_event(TaskStartEvent(task_id="music-1"))
    manager.apply_event(TaskCancelledEvent(task_id="music-1", reason="cancelled"))

    result = manager.apply_event(TaskSuccessEvent(task_id="music-1", result="late result"))

    run = manager.get_task("music-1")
    assert run is not None
    assert result.applied is False
    assert run.status == TaskStatus.CANCELLED
    assert run.result is None


def test_cancelled_terminal_state_is_sticky_against_late_success() -> None:
    manager = TaskManager()
    manager.apply_created(
        TaskCreatedEvent(task_id="weather-1", name="weather_search", arguments={"city": "香港"})
    )
    manager.apply_event(TaskStartEvent(task_id="weather-1"))
    cancelled = manager.apply_event(TaskCancelledEvent(task_id="weather-1", reason="cancelled"))
    late_success = manager.apply_event(TaskSuccessEvent(task_id="weather-1", result="late"))

    run = manager.get_task("weather-1")
    assert run is not None
    assert cancelled.applied is True
    assert late_success.applied is False
    assert run.status == TaskStatus.CANCELLED
    assert run.result is None


def test_success_terminal_state_rejects_late_cancelled_event() -> None:
    manager = TaskManager()
    manager.apply_created(
        TaskCreatedEvent(task_id="weather-1", name="weather_search", arguments={"city": "香港"})
    )
    manager.apply_event(TaskStartEvent(task_id="weather-1"))
    success = manager.apply_event(TaskSuccessEvent(task_id="weather-1", result="sunny"))
    cancelled = manager.apply_event(TaskCancelledEvent(task_id="weather-1", reason="late cancel"))

    run = manager.get_task("weather-1")
    assert run is not None
    assert success.applied is True
    assert cancelled.applied is False
    assert run.status == TaskStatus.SUCCESS
    assert run.result == "sunny"


def test_duplicate_created_event_is_rejected_without_mutating_projection() -> None:
    manager = TaskManager()
    first = manager.apply_created(
        TaskCreatedEvent(task_id="weather-1", name="weather_search", arguments={"city": "香港"})
    )
    duplicate = manager.apply_created(
        TaskCreatedEvent(task_id="weather-1", name="poi_search", arguments={"city": "上海"})
    )

    projection = manager.get_projection("weather-1")
    assert projection is not None
    assert first.applied is True
    assert duplicate.applied is False
    assert projection.tool_name == "weather_search"
    assert projection.arguments == {"city": "香港"}


def test_handle_event_ignores_late_success_after_cancelled() -> None:
    manager = TaskManager()
    manager.apply_created(
        TaskCreatedEvent(task_id="weather-1", name="weather_search", arguments={"city": "香港"})
    )
    manager.apply_event(TaskStartEvent(task_id="weather-1"))
    manager.apply_event(TaskCancelledEvent(task_id="weather-1", reason="cancelled"))
    manager.handle_event(TaskSuccessEvent(task_id="weather-1", result="late cancelled"))

    run = manager.get_task("weather-1")
    assert run is not None
    assert run.status == TaskStatus.CANCELLED
    assert run.result is None


def test_handle_event_still_raises_for_missing_task_progress() -> None:
    manager = TaskManager()

    with pytest.raises(AssertionError):
        manager.handle_event(TaskProgressEvent(task_id="missing-1", progress="late"))
