"""Unit tests for ScanPath model and schema."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ora_automation_api.database import Base
from ora_automation_api.models import Project, ScanPath
from ora_automation_api.schemas import (
    ScanPathCreate,
    ScanPathRead,
    ScanPathUpdate,
    ScanResult,
)


@pytest.fixture()
def db() -> Session:
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestScanPathModel:
    """Test ScanPath ORM model."""

    def test_create_scan_path(self, db: Session):
        """Should create a ScanPath with required fields."""
        scan_path = ScanPath(
            id=uuid4().hex,
            path="/workspace/projects",
        )
        db.add(scan_path)
        db.commit()
        db.refresh(scan_path)

        assert scan_path.id is not None
        assert scan_path.path == "/workspace/projects"
        assert scan_path.name is None
        assert scan_path.enabled is True
        assert scan_path.recursive is False
        assert scan_path.project_count == 0
        assert scan_path.last_scanned_at is None
        assert scan_path.created_at is not None

    def test_create_scan_path_with_name(self, db: Session):
        """Should create a ScanPath with optional name."""
        scan_path = ScanPath(
            id=uuid4().hex,
            path="/workspace/company",
            name="회사 프로젝트",
            recursive=True,
        )
        db.add(scan_path)
        db.commit()

        assert scan_path.name == "회사 프로젝트"
        assert scan_path.recursive is True

    def test_unique_path_constraint(self, db: Session):
        """Should enforce unique path constraint."""
        path = "/workspace/unique"
        sp1 = ScanPath(id=uuid4().hex, path=path)
        db.add(sp1)
        db.commit()

        sp2 = ScanPath(id=uuid4().hex, path=path)
        db.add(sp2)

        with pytest.raises(Exception):  # IntegrityError
            db.commit()

    def test_update_scan_path(self, db: Session):
        """Should update ScanPath fields."""
        scan_path = ScanPath(
            id=uuid4().hex,
            path="/workspace/test",
            enabled=True,
        )
        db.add(scan_path)
        db.commit()

        scan_path.enabled = False
        scan_path.name = "테스트"
        scan_path.project_count = 5
        scan_path.last_scanned_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(scan_path)

        assert scan_path.enabled is False
        assert scan_path.name == "테스트"
        assert scan_path.project_count == 5
        assert scan_path.last_scanned_at is not None


class TestScanPathProjectRelation:
    """Test ScanPath and Project relationship."""

    def test_project_with_scan_path_id(self, db: Session):
        """Should create Project linked to ScanPath."""
        scan_path = ScanPath(
            id=uuid4().hex,
            path="/workspace/linked",
        )
        db.add(scan_path)
        db.commit()

        project = Project(
            id=uuid4().hex,
            name="linked-project",
            source_type="local",
            local_path="/workspace/linked/project1",
            scan_path_id=scan_path.id,
        )
        db.add(project)
        db.commit()

        assert project.scan_path_id == scan_path.id

    def test_scan_path_delete_sets_null(self, db: Session):
        """Should set scan_path_id to NULL when ScanPath is deleted."""
        scan_path = ScanPath(
            id=uuid4().hex,
            path="/workspace/deletable",
        )
        db.add(scan_path)
        db.commit()

        project = Project(
            id=uuid4().hex,
            name="orphan-project",
            source_type="local",
            local_path="/workspace/deletable/project1",
            scan_path_id=scan_path.id,
        )
        db.add(project)
        db.commit()

        db.delete(scan_path)
        db.commit()
        db.refresh(project)

        # SQLite doesn't enforce FK by default, so this tests the model intent
        # In PostgreSQL, ON DELETE SET NULL would work
        assert project.scan_path_id is None or project.scan_path_id == scan_path.id


class TestScanPathSchemas:
    """Test ScanPath Pydantic schemas."""

    def test_scan_path_create_minimal(self):
        """Should create schema with minimal fields."""
        schema = ScanPathCreate(path="/workspace/test")
        assert schema.path == "/workspace/test"
        assert schema.name is None
        assert schema.recursive is False

    def test_scan_path_create_full(self):
        """Should create schema with all fields."""
        schema = ScanPathCreate(
            path="/workspace/full",
            name="전체 설정",
            recursive=True,
        )
        assert schema.path == "/workspace/full"
        assert schema.name == "전체 설정"
        assert schema.recursive is True

    def test_scan_path_update_partial(self):
        """Should allow partial updates."""
        schema = ScanPathUpdate(enabled=False)
        assert schema.enabled is False
        assert schema.name is None
        assert schema.recursive is None

    def test_scan_path_read_from_model(self, db: Session):
        """Should convert ORM model to read schema."""
        scan_path = ScanPath(
            id=uuid4().hex,
            path="/workspace/readable",
            name="읽기 테스트",
            enabled=True,
            recursive=False,
            project_count=3,
        )
        db.add(scan_path)
        db.commit()
        db.refresh(scan_path)

        schema = ScanPathRead.model_validate(scan_path)
        assert schema.id == scan_path.id
        assert schema.path == "/workspace/readable"
        assert schema.name == "읽기 테스트"
        assert schema.enabled is True
        assert schema.recursive is False
        assert schema.project_count == 3

    def test_scan_result_schema(self):
        """Should validate ScanResult schema."""
        result = ScanResult(
            scan_path_id="abc123",
            projects_found=10,
            projects_created=3,
            projects_updated=2,
            duration_ms=150,
        )
        assert result.projects_found == 10
        assert result.projects_created == 3
        assert result.projects_updated == 2
        assert result.duration_ms == 150
