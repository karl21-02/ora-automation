"""Scheduling intent — unit tests for UPCE dialog engine scheduling extension.

Tests: SchedulingSlots merge, build_proposed_plans for scheduling, validate_cron,
validate_interval, build_job_name, create_scheduled_job_from_slots.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ora_automation_api.database import Base
from ora_automation_api.dialog_engine import (
    DialogContext,
    DialogState,
    IntentClassification,
    IntentType,
    SchedulingSlots,
    build_proposed_plans,
    merge_slots,
)
from ora_automation_api.models import ScheduledJob
from ora_automation_api.scheduling_handler import (
    ScheduleValidationError,
    build_job_name,
    create_scheduled_job_from_slots,
    validate_cron,
    validate_interval,
)


# =====================================================================
# 1. SchedulingSlots merge tests
# =====================================================================


class TestSchedulingSlotsMerge:

    def test_merge_basic_scheduling_slots(self):
        ctx = DialogContext(state=DialogState.UNDERSTANDING, intent=IntentType.SCHEDULING)
        classification = IntentClassification(
            intent=IntentType.SCHEDULING,
            next_state=DialogState.SLOT_FILLING,
            scheduling_slots=SchedulingSlots(
                topic="AI 보안 트렌드",
                frequency_type="cron",
                cron_expression="0 9 * * *",
                human_readable="매일 오전 9시",
            ),
        )
        updated = merge_slots(ctx, classification)

        assert updated.accumulated_slots["topic"] == "AI 보안 트렌드"
        assert updated.accumulated_slots["frequency_type"] == "cron"
        assert updated.accumulated_slots["cron_expression"] == "0 9 * * *"
        assert updated.accumulated_slots["human_readable"] == "매일 오전 9시"

    def test_merge_interval_scheduling_slots(self):
        ctx = DialogContext(state=DialogState.UNDERSTANDING, intent=IntentType.SCHEDULING)
        classification = IntentClassification(
            intent=IntentType.SCHEDULING,
            next_state=DialogState.SLOT_FILLING,
            scheduling_slots=SchedulingSlots(
                topic="성능 모니터링",
                frequency_type="interval",
                interval_minutes=360,
                human_readable="6시간마다",
            ),
        )
        updated = merge_slots(ctx, classification)

        assert updated.accumulated_slots["frequency_type"] == "interval"
        assert updated.accumulated_slots["interval_minutes"] == 360

    def test_merge_preserves_existing_scheduling_slots(self):
        ctx = DialogContext(
            state=DialogState.SLOT_FILLING,
            intent=IntentType.SCHEDULING,
            accumulated_slots={"topic": "보안 분석", "frequency_type": "cron"},
            turn_count=1,
        )
        classification = IntentClassification(
            intent=IntentType.SCHEDULING,
            next_state=DialogState.CONFIRMING,
            scheduling_slots=SchedulingSlots(
                cron_expression="0 9 * * *",
                human_readable="매일 오전 9시",
            ),
        )
        updated = merge_slots(ctx, classification)

        # topic preserved from existing
        assert updated.accumulated_slots["topic"] == "보안 분석"
        # new slots added
        assert updated.accumulated_slots["cron_expression"] == "0 9 * * *"
        assert updated.accumulated_slots["human_readable"] == "매일 오전 9시"

    def test_merge_auto_publish_flag(self):
        ctx = DialogContext(state=DialogState.SLOT_FILLING, intent=IntentType.SCHEDULING)
        classification = IntentClassification(
            intent=IntentType.SCHEDULING,
            next_state=DialogState.SLOT_FILLING,
            scheduling_slots=SchedulingSlots(auto_publish=True),
        )
        updated = merge_slots(ctx, classification)
        assert updated.accumulated_slots["auto_publish"] is True


# =====================================================================
# 2. build_proposed_plans for SCHEDULING
# =====================================================================


class TestSchedulingBuildPlans:

    def test_cron_plan(self):
        slots = {
            "topic": "AI 보안 트렌드",
            "frequency_type": "cron",
            "cron_expression": "0 9 * * *",
            "human_readable": "매일 오전 9시",
        }
        plans = build_proposed_plans(slots, IntentType.SCHEDULING)

        assert len(plans) == 1
        assert plans[0]["target"] == "run-cycle"
        assert plans[0]["env"]["FOCUS"] == "AI 보안 트렌드"
        assert plans[0]["schedule_meta"]["frequency_type"] == "cron"
        assert plans[0]["schedule_meta"]["cron_expression"] == "0 9 * * *"
        assert plans[0]["schedule_meta"]["human_readable"] == "매일 오전 9시"

    def test_interval_plan(self):
        slots = {
            "topic": "성능 모니터링",
            "frequency_type": "interval",
            "interval_minutes": 360,
            "human_readable": "6시간마다",
        }
        plans = build_proposed_plans(slots, IntentType.SCHEDULING)

        assert len(plans) == 1
        assert plans[0]["schedule_meta"]["frequency_type"] == "interval"
        assert plans[0]["schedule_meta"]["interval_minutes"] == 360

    def test_multi_project_scheduling(self):
        slots = {
            "topic": "보안 분석",
            "frequency_type": "cron",
            "cron_expression": "0 9 * * 1-5",
            "human_readable": "평일 오전 9시",
            "projects": ["OraAiServer", "OraFrontend"],
        }
        plans = build_proposed_plans(slots, IntentType.SCHEDULING)

        assert len(plans) == 2
        assert plans[0]["label"] == "OraAiServer"
        assert plans[1]["label"] == "OraFrontend"
        # Both share schedule_meta
        assert plans[0]["schedule_meta"]["cron_expression"] == "0 9 * * 1-5"

    def test_custom_target(self):
        slots = {
            "topic": "딥 분석",
            "frequency_type": "cron",
            "cron_expression": "0 0 * * 0",
            "human_readable": "매주 일요일 자정",
            "target": "run-cycle-deep",
        }
        plans = build_proposed_plans(slots, IntentType.SCHEDULING)

        assert plans[0]["target"] == "run-cycle-deep"

    def test_auto_publish_in_meta(self):
        slots = {
            "topic": "보안",
            "frequency_type": "cron",
            "cron_expression": "0 9 * * *",
            "auto_publish": True,
        }
        plans = build_proposed_plans(slots, IntentType.SCHEDULING)
        assert plans[0]["schedule_meta"]["auto_publish"] is True


# =====================================================================
# 3. validate_cron
# =====================================================================


class TestValidateCron:

    def test_valid_cron(self):
        assert validate_cron("0 9 * * *") == "0 9 * * *"

    def test_valid_cron_weekdays(self):
        assert validate_cron("0 8 * * 1-5") == "0 8 * * 1-5"

    def test_invalid_cron(self):
        with pytest.raises(ScheduleValidationError, match="유효하지 않은"):
            validate_cron("invalid cron")

    def test_empty_cron(self):
        with pytest.raises(ScheduleValidationError, match="비어 있습니다"):
            validate_cron("")

    def test_whitespace_cron(self):
        with pytest.raises(ScheduleValidationError, match="비어 있습니다"):
            validate_cron("   ")

    def test_cron_with_whitespace_stripped(self):
        assert validate_cron("  0 9 * * *  ") == "0 9 * * *"


# =====================================================================
# 4. validate_interval
# =====================================================================


class TestValidateInterval:

    def test_valid_interval(self):
        assert validate_interval(60) == 60

    def test_min_boundary(self):
        assert validate_interval(5) == 5

    def test_max_boundary(self):
        assert validate_interval(10080) == 10080

    def test_below_min(self):
        with pytest.raises(ScheduleValidationError, match="최소 5분"):
            validate_interval(3)

    def test_above_max(self):
        with pytest.raises(ScheduleValidationError, match="최대 10080분"):
            validate_interval(20000)


# =====================================================================
# 5. build_job_name
# =====================================================================


class TestBuildJobName:

    def test_basic_name(self):
        name = build_job_name("AI 보안 트렌드", "매일 오전 9시")
        assert name == "AI 보안 트렌드 - 매일 오전 9시"

    def test_special_chars_removed(self):
        name = build_job_name("AI/보안@트렌드!", "매일(9시)")
        assert "/" not in name
        assert "@" not in name
        assert "!" not in name
        assert "(" not in name

    def test_no_human_readable(self):
        name = build_job_name("보안 분석")
        assert name == "보안 분석"

    def test_truncated_to_128(self):
        long_topic = "매우 긴 " * 50
        name = build_job_name(long_topic, "매일")
        assert len(name) <= 128


# =====================================================================
# 6. create_scheduled_job_from_slots
# =====================================================================


class TestCreateScheduledJobFromSlots:

    @pytest.fixture()
    def db(self) -> Session:
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = TestSession()
        yield session
        session.close()
        engine.dispose()

    def test_create_cron_job(self, db: Session):
        slots = {
            "topic": "AI 보안 트렌드",
            "frequency_type": "cron",
            "cron_expression": "0 9 * * *",
            "human_readable": "매일 오전 9시",
        }
        job = create_scheduled_job_from_slots(db, slots)

        assert job.id is not None
        assert job.name == "AI 보안 트렌드 - 매일 오전 9시"
        assert job.cron_expression == "0 9 * * *"
        assert job.interval_minutes is None
        assert job.target == "run-cycle"
        assert job.enabled is True
        assert job.env["FOCUS"] == "AI 보안 트렌드"
        assert job.next_run_at is not None

    def test_create_interval_job(self, db: Session):
        slots = {
            "topic": "성능 모니터링",
            "frequency_type": "interval",
            "interval_minutes": 360,
            "human_readable": "6시간마다",
        }
        job = create_scheduled_job_from_slots(db, slots)

        assert job.interval_minutes == 360
        assert job.cron_expression is None
        assert job.next_run_at is not None

    def test_missing_topic_raises(self, db: Session):
        slots = {
            "frequency_type": "cron",
            "cron_expression": "0 9 * * *",
        }
        with pytest.raises(ScheduleValidationError, match="topic"):
            create_scheduled_job_from_slots(db, slots)

    def test_duplicate_name_raises(self, db: Session):
        slots = {
            "topic": "보안 분석",
            "frequency_type": "cron",
            "cron_expression": "0 9 * * *",
            "human_readable": "매일 오전 9시",
        }
        create_scheduled_job_from_slots(db, slots)
        db.commit()

        with pytest.raises(ScheduleValidationError, match="이미 존재"):
            create_scheduled_job_from_slots(db, slots)

    def test_auto_publish_flag(self, db: Session):
        slots = {
            "topic": "보안 트렌드",
            "frequency_type": "cron",
            "cron_expression": "0 9 * * *",
            "auto_publish": True,
        }
        job = create_scheduled_job_from_slots(db, slots)
        assert job.auto_publish_notion is True

    def test_projects_in_env(self, db: Session):
        slots = {
            "topic": "멀티 프로젝트",
            "frequency_type": "interval",
            "interval_minutes": 120,
            "projects": ["OraAiServer", "OraFrontend"],
        }
        job = create_scheduled_job_from_slots(db, slots)
        assert job.env["PROJECTS"] == "OraAiServer,OraFrontend"

    def test_invalid_frequency_type_raises(self, db: Session):
        slots = {
            "topic": "보안",
            "frequency_type": "weekly",
        }
        with pytest.raises(ScheduleValidationError, match="frequency_type"):
            create_scheduled_job_from_slots(db, slots)

    def test_missing_cron_for_cron_type(self, db: Session):
        slots = {
            "topic": "보안",
            "frequency_type": "cron",
        }
        with pytest.raises(ScheduleValidationError, match="cron_expression"):
            create_scheduled_job_from_slots(db, slots)

    def test_missing_interval_for_interval_type(self, db: Session):
        slots = {
            "topic": "보안",
            "frequency_type": "interval",
        }
        with pytest.raises(ScheduleValidationError, match="interval_minutes"):
            create_scheduled_job_from_slots(db, slots)
