from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import get_db
from .models import Organization, OrganizationAgent, OrganizationChapter, OrganizationSilo
from .org_templates import get_template
from .schemas import (
    OrganizationCreate,
    OrganizationDetail,
    OrganizationList,
    OrganizationRead,
    OrganizationUpdate,
    OrgAgentCreate,
    OrgAgentRead,
    OrgAgentUpdate,
    OrgChapterCreate,
    OrgChapterRead,
    OrgChapterUpdate,
    OrgSiloCreate,
    OrgSiloRead,
    OrgSiloUpdate,
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
        pipeline_params=payload.pipeline_params,
    )
    db.add(org)
    db.flush()

    # Apply template if specified
    template = get_template(payload.template_id)
    new_silos: list[OrganizationSilo] = []
    new_chapters: list[OrganizationChapter] = []
    new_agents: list[OrganizationAgent] = []

    if template and (template.silos or template.chapters or template.agents):
        # Create silos with ID mapping
        silo_name_to_id: dict[str, str] = {}
        for idx, ts in enumerate(template.silos):
            silo_id = uuid4().hex[:36]
            silo_name_to_id[ts.name] = silo_id
            silo = OrganizationSilo(
                id=silo_id,
                org_id=org.id,
                name=ts.name,
                description=ts.description,
                color=ts.color,
                sort_order=idx,
            )
            db.add(silo)
            new_silos.append(silo)

        # Create chapters with ID mapping
        chapter_name_to_id: dict[str, str] = {}
        for idx, tc in enumerate(template.chapters):
            chapter_id = uuid4().hex[:36]
            chapter_name_to_id[tc.name] = chapter_id
            chapter = OrganizationChapter(
                id=chapter_id,
                org_id=org.id,
                name=tc.name,
                description=tc.description,
                shared_directives=tc.shared_directives,
                shared_constraints=[],
                shared_decision_focus=[],
                chapter_prompt="",
                color=tc.color,
                icon=tc.icon,
                sort_order=idx,
            )
            db.add(chapter)
            new_chapters.append(chapter)

        db.flush()

        # Create agents with resolved silo_id / chapter_id
        for idx, ta in enumerate(template.agents):
            agent = OrganizationAgent(
                id=uuid4().hex[:36],
                org_id=org.id,
                agent_id=ta.agent_id,
                silo_id=silo_name_to_id.get(ta.silo) if ta.silo else None,
                chapter_id=chapter_name_to_id.get(ta.chapter) if ta.chapter else None,
                is_clevel=ta.is_clevel,
                weight_score=1.0,
                display_name=ta.display_name,
                display_name_ko=ta.display_name_ko,
                role=ta.role,
                tier=ta.tier,
                domain=None,
                team=ta.team,
                personality={},
                behavioral_directives=[],
                constraints=[],
                decision_focus=[],
                weights=ta.weights,
                trust_map={},
                system_prompt_template="",
                enabled=True,
                sort_order=idx,
            )
            db.add(agent)
            new_agents.append(agent)

    db.commit()
    db.refresh(org)
    for s in new_silos:
        db.refresh(s)
    for c in new_chapters:
        db.refresh(c)
    for a in new_agents:
        db.refresh(a)

    return OrganizationDetail(
        **OrganizationRead.model_validate(org).model_dump(),
        agents=[OrgAgentRead.model_validate(a) for a in new_agents],
        silos=[OrgSiloRead.model_validate(s) for s in new_silos],
        chapters=[OrgChapterRead.model_validate(c) for c in new_chapters],
    )


@router.get("/{org_id}", response_model=OrganizationDetail)
def get_org(org_id: str, db: Session = Depends(get_db)) -> OrganizationDetail:
    org = _get_org(db, org_id)
    agents = (
        db.query(OrganizationAgent)
        .filter(OrganizationAgent.org_id == org_id)
        .order_by(OrganizationAgent.sort_order, OrganizationAgent.agent_id)
        .all()
    )
    silos = (
        db.query(OrganizationSilo)
        .filter(OrganizationSilo.org_id == org_id)
        .order_by(OrganizationSilo.sort_order, OrganizationSilo.name)
        .all()
    )
    chapters = (
        db.query(OrganizationChapter)
        .filter(OrganizationChapter.org_id == org_id)
        .order_by(OrganizationChapter.sort_order, OrganizationChapter.name)
        .all()
    )
    return OrganizationDetail(
        **OrganizationRead.model_validate(org).model_dump(),
        agents=[OrgAgentRead.model_validate(a) for a in agents],
        silos=[OrgSiloRead.model_validate(s) for s in silos],
        chapters=[OrgChapterRead.model_validate(c) for c in chapters],
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
        pipeline_params=payload.pipeline_params or source.pipeline_params,
    )
    db.add(new_org)
    db.flush()

    # Deep copy silos with ID mapping
    silo_id_map: dict[str, str] = {}
    source_silos = (
        db.query(OrganizationSilo)
        .filter(OrganizationSilo.org_id == org_id)
        .order_by(OrganizationSilo.sort_order)
        .all()
    )
    new_silos = []
    for ss in source_silos:
        new_id = uuid4().hex[:36]
        silo_id_map[ss.id] = new_id
        ns = OrganizationSilo(
            id=new_id,
            org_id=new_org.id,
            name=ss.name,
            description=ss.description,
            color=ss.color,
            sort_order=ss.sort_order,
        )
        db.add(ns)
        new_silos.append(ns)

    # Deep copy chapters with ID mapping
    chapter_id_map: dict[str, str] = {}
    source_chapters = (
        db.query(OrganizationChapter)
        .filter(OrganizationChapter.org_id == org_id)
        .order_by(OrganizationChapter.sort_order)
        .all()
    )
    new_chapters = []
    for sc in source_chapters:
        new_id = uuid4().hex[:36]
        chapter_id_map[sc.id] = new_id
        nc = OrganizationChapter(
            id=new_id,
            org_id=new_org.id,
            name=sc.name,
            description=sc.description,
            shared_directives=sc.shared_directives,
            shared_constraints=sc.shared_constraints,
            shared_decision_focus=sc.shared_decision_focus,
            chapter_prompt=sc.chapter_prompt,
            color=sc.color,
            icon=sc.icon,
            sort_order=sc.sort_order,
        )
        db.add(nc)
        new_chapters.append(nc)

    db.flush()

    # Deep copy agents with remapped silo_id / chapter_id
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
            silo_id=silo_id_map.get(sa.silo_id) if sa.silo_id else None,
            chapter_id=chapter_id_map.get(sa.chapter_id) if sa.chapter_id else None,
            is_clevel=sa.is_clevel,
            weight_score=sa.weight_score,
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
    for ns in new_silos:
        db.refresh(ns)
    for nc in new_chapters:
        db.refresh(nc)
    for na in new_agents:
        db.refresh(na)

    return OrganizationDetail(
        **OrganizationRead.model_validate(new_org).model_dump(),
        agents=[OrgAgentRead.model_validate(a) for a in new_agents],
        silos=[OrgSiloRead.model_validate(s) for s in new_silos],
        chapters=[OrgChapterRead.model_validate(c) for c in new_chapters],
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


# ── Silo CRUD ─────────────────────────────────────────────────────


@router.post("/{org_id}/silos", response_model=OrgSiloRead, status_code=201)
def create_silo(
    org_id: str,
    payload: OrgSiloCreate,
    db: Session = Depends(get_db),
) -> OrgSiloRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    existing = (
        db.query(OrganizationSilo)
        .filter(OrganizationSilo.org_id == org_id, OrganizationSilo.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="silo name already exists in this organization")
    silo = OrganizationSilo(
        id=uuid4().hex[:36],
        org_id=org_id,
        **payload.model_dump(),
    )
    db.add(silo)
    db.commit()
    db.refresh(silo)
    return OrgSiloRead.model_validate(silo)


@router.patch("/{org_id}/silos/{silo_id}", response_model=OrgSiloRead)
def update_silo(
    org_id: str,
    silo_id: str,
    payload: OrgSiloUpdate,
    db: Session = Depends(get_db),
) -> OrgSiloRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    silo = (
        db.query(OrganizationSilo)
        .filter(OrganizationSilo.org_id == org_id, OrganizationSilo.id == silo_id)
        .first()
    )
    if not silo:
        raise HTTPException(status_code=404, detail="silo not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        dup = (
            db.query(OrganizationSilo)
            .filter(
                OrganizationSilo.org_id == org_id,
                OrganizationSilo.name == update_data["name"],
                OrganizationSilo.id != silo_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="silo name already exists in this organization")
    for key, value in update_data.items():
        setattr(silo, key, value)
    db.commit()
    db.refresh(silo)
    return OrgSiloRead.model_validate(silo)


@router.delete("/{org_id}/silos/{silo_id}", status_code=204)
def delete_silo(
    org_id: str,
    silo_id: str,
    db: Session = Depends(get_db),
) -> None:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    silo = (
        db.query(OrganizationSilo)
        .filter(OrganizationSilo.org_id == org_id, OrganizationSilo.id == silo_id)
        .first()
    )
    if not silo:
        raise HTTPException(status_code=404, detail="silo not found")
    db.delete(silo)
    db.commit()


# ── Chapter CRUD ──────────────────────────────────────────────────


@router.post("/{org_id}/chapters", response_model=OrgChapterRead, status_code=201)
def create_chapter(
    org_id: str,
    payload: OrgChapterCreate,
    db: Session = Depends(get_db),
) -> OrgChapterRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    existing = (
        db.query(OrganizationChapter)
        .filter(OrganizationChapter.org_id == org_id, OrganizationChapter.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="chapter name already exists in this organization")
    chapter = OrganizationChapter(
        id=uuid4().hex[:36],
        org_id=org_id,
        **payload.model_dump(),
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return OrgChapterRead.model_validate(chapter)


@router.patch("/{org_id}/chapters/{chapter_id}", response_model=OrgChapterRead)
def update_chapter(
    org_id: str,
    chapter_id: str,
    payload: OrgChapterUpdate,
    db: Session = Depends(get_db),
) -> OrgChapterRead:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    chapter = (
        db.query(OrganizationChapter)
        .filter(OrganizationChapter.org_id == org_id, OrganizationChapter.id == chapter_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    update_data = payload.model_dump(exclude_unset=True)
    if "name" in update_data:
        dup = (
            db.query(OrganizationChapter)
            .filter(
                OrganizationChapter.org_id == org_id,
                OrganizationChapter.name == update_data["name"],
                OrganizationChapter.id != chapter_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="chapter name already exists in this organization")
    for key, value in update_data.items():
        setattr(chapter, key, value)
    db.commit()
    db.refresh(chapter)
    return OrgChapterRead.model_validate(chapter)


@router.delete("/{org_id}/chapters/{chapter_id}", status_code=204)
def delete_chapter(
    org_id: str,
    chapter_id: str,
    db: Session = Depends(get_db),
) -> None:
    org = _get_org(db, org_id)
    if org.is_preset:
        raise HTTPException(status_code=403, detail="preset organizations cannot be modified")
    chapter = (
        db.query(OrganizationChapter)
        .filter(OrganizationChapter.org_id == org_id, OrganizationChapter.id == chapter_id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="chapter not found")
    db.delete(chapter)
    db.commit()
