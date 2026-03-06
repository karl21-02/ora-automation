from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import Organization, OrganizationAgent
from .schemas import (
    OrganizationCreate,
    OrganizationDetail,
    OrganizationList,
    OrganizationRead,
    OrganizationUpdate,
    OrgAgentCreate,
    OrgAgentRead,
    OrgAgentUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orgs", tags=["organizations"])


def _get_org(db: Session, org_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")
    return org


def _get_agent(db: Session, org_id: str, agent_id: str) -> OrganizationAgent:
    agent = (
        db.query(OrganizationAgent)
        .filter(OrganizationAgent.org_id == org_id, OrganizationAgent.id == agent_id)
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


# ── Organization CRUD ─────────────────────────────────────────────


@router.get("", response_model=OrganizationList)
def list_orgs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> OrganizationList:
    orgs = db.query(Organization).order_by(Organization.name).limit(limit).all()
    return OrganizationList(
        items=[OrganizationRead.model_validate(o) for o in orgs],
        total=len(orgs),
    )


@router.post("", response_model=OrganizationDetail, status_code=201)
def create_org(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
) -> OrganizationDetail:
    existing = db.query(Organization).filter(Organization.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="organization name already exists")
    org = Organization(
        id=uuid4().hex[:36],
        name=payload.name,
        description=payload.description,
        is_preset=False,
        teams=payload.teams,
        flat_mode_agents=payload.flat_mode_agents,
        agent_final_weights=payload.agent_final_weights,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrganizationDetail.model_validate({**OrganizationRead.model_validate(org).model_dump(), "agents": []})


@router.get("/{org_id}", response_model=OrganizationDetail)
def get_org(org_id: str, db: Session = Depends(get_db)) -> OrganizationDetail:
    org = _get_org(db, org_id)
    agents = (
        db.query(OrganizationAgent)
        .filter(OrganizationAgent.org_id == org_id)
        .order_by(OrganizationAgent.sort_order, OrganizationAgent.agent_id)
        .all()
    )
    return OrganizationDetail(
        **OrganizationRead.model_validate(org).model_dump(),
        agents=[OrgAgentRead.model_validate(a) for a in agents],
    )


@router.patch("/{org_id}", response_model=OrganizationRead)
def update_org(
    org_id: str,
    payload: OrganizationUpdate,
    db: Session = Depends(get_db),
) -> OrganizationRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        dup = db.query(Organization).filter(Organization.name == update_data["name"], Organization.id != org_id).first()
        if dup:
            raise HTTPException(status_code=409, detail="organization name already exists")
    for key, value in update_data.items():
        setattr(org, key, value)
    db.commit()
    db.refresh(org)
    return OrganizationRead.model_validate(org)


@router.delete("/{org_id}", status_code=204)
def delete_org(org_id: str, db: Session = Depends(get_db)) -> None:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be deleted")
    db.delete(org)
    db.commit()


@router.post("/{org_id}/clone", response_model=OrganizationDetail, status_code=201)
def clone_org(
    org_id: str,
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
) -> OrganizationDetail:
    source = _get_org(db, org_id)
    existing = db.query(Organization).filter(Organization.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="organization name already exists")

    new_org = Organization(
        id=uuid4().hex[:36],
        name=payload.name,
        description=payload.description or source.description,
        is_preset=False,
        teams=payload.teams or source.teams,
        flat_mode_agents=payload.flat_mode_agents or source.flat_mode_agents,
        agent_final_weights=payload.agent_final_weights or source.agent_final_weights,
    )
    db.add(new_org)
    db.flush()

    source_agents = (
        db.query(OrganizationAgent)
        .filter(OrganizationAgent.org_id == org_id)
        .order_by(OrganizationAgent.sort_order)
        .all()
    )
    new_agents = []
    for sa in source_agents:
        na = OrganizationAgent(
            id=uuid4().hex[:36],
            org_id=new_org.id,
            agent_id=sa.agent_id,
            display_name=sa.display_name,
            display_name_ko=sa.display_name_ko,
            role=sa.role,
            tier=sa.tier,
            domain=sa.domain,
            team=sa.team,
            personality=sa.personality,
            behavioral_directives=sa.behavioral_directives,
            constraints=sa.constraints,
            decision_focus=sa.decision_focus,
            weights=sa.weights,
            trust_map=sa.trust_map,
            system_prompt_template=sa.system_prompt_template,
            enabled=sa.enabled,
            sort_order=sa.sort_order,
        )
        db.add(na)
        new_agents.append(na)

    db.commit()
    db.refresh(new_org)
    for na in new_agents:
        db.refresh(na)

    return OrganizationDetail(
        **OrganizationRead.model_validate(new_org).model_dump(),
        agents=[OrgAgentRead.model_validate(a) for a in new_agents],
    )


# ── Agent CRUD ────────────────────────────────────────────────────


@router.post("/{org_id}/agents", response_model=OrgAgentRead, status_code=201)
def create_agent(
    org_id: str,
    payload: OrgAgentCreate,
    db: Session = Depends(get_db),
) -> OrgAgentRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    existing = (
        db.query(OrganizationAgent)
        .filter(OrganizationAgent.org_id == org_id, OrganizationAgent.agent_id == payload.agent_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="agent_id already exists in this organization")
    agent = OrganizationAgent(
        id=uuid4().hex[:36],
        org_id=org_id,
        **payload.model_dump(),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return OrgAgentRead.model_validate(agent)


@router.patch("/{org_id}/agents/{agent_id}", response_model=OrgAgentRead)
def update_agent(
    org_id: str,
    agent_id: str,
    payload: OrgAgentUpdate,
    db: Session = Depends(get_db),
) -> OrgAgentRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    agent = _get_agent(db, org_id, agent_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, key, value)
    db.commit()
    db.refresh(agent)
    return OrgAgentRead.model_validate(agent)


@router.delete("/{org_id}/agents/{agent_id}", status_code=204)
def delete_agent(
    org_id: str,
    agent_id: str,
    db: Session = Depends(get_db),
) -> None:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    agent = _get_agent(db, org_id, agent_id)
    db.delete(agent)
    db.commit()
