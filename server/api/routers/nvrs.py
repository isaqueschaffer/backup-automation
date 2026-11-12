from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import verify_admin_token
from database import get_db
from models import Machine, NVR
from schemas import NVRCreate, NVRUpdate, NVRResponse
from services.crypto_service import encrypt

router = APIRouter(prefix="/api/v1/clients/{machine_id}/nvrs", tags=["nvrs"])


def _get_machine_or_404(machine_id: UUID, db: Session) -> Machine:
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="Client not found")
    return machine


@router.get("", response_model=List[NVRResponse], dependencies=[Depends(verify_admin_token)])
def list_nvrs(machine_id: UUID, db: Session = Depends(get_db)):
    _get_machine_or_404(machine_id, db)
    return db.query(NVR).filter(NVR.machine_id == machine_id).all()


@router.post("", response_model=NVRResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_admin_token)])
def create_nvr(machine_id: UUID, body: NVRCreate, db: Session = Depends(get_db)):
    _get_machine_or_404(machine_id, db)
    nvr = NVR(
        machine_id=machine_id,
        name=body.name,
        ip=body.ip,
        username=body.username,
        password=encrypt(body.password),
    )
    db.add(nvr)
    db.commit()
    db.refresh(nvr)
    return nvr


@router.put("/{nvr_id}", response_model=NVRResponse, dependencies=[Depends(verify_admin_token)])
def update_nvr(machine_id: UUID, nvr_id: UUID, body: NVRUpdate, db: Session = Depends(get_db)):
    nvr = db.query(NVR).filter(NVR.id == nvr_id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR not found")
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "password" and value:
            nvr.password = encrypt(value)
        else:
            setattr(nvr, field, value)
    db.commit()
    db.refresh(nvr)
    return nvr


@router.delete("/{nvr_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_admin_token)])
def delete_nvr(machine_id: UUID, nvr_id: UUID, db: Session = Depends(get_db)):
    nvr = db.query(NVR).filter(NVR.id == nvr_id, NVR.machine_id == machine_id).first()
    if not nvr:
        raise HTTPException(status_code=404, detail="NVR not found")
    db.delete(nvr)
    db.commit()
