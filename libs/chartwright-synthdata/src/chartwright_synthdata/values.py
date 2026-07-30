"""Deterministic synthetic value generation.

All values are fabricated from small pools + seeded randomness. Nothing here is or resembles
real patient data. NPIs are generated to pass the Luhn check (so CP16's validator can be
tested against them); member IDs follow common payer-format shapes.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

_FIRST = ["Alex", "Jordan", "Sam", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Drew"]
_LAST = [
    "Rivera",
    "Chen",
    "Okafor",
    "Nguyen",
    "Haddad",
    "Kowalski",
    "Iyer",
    "Sato",
    "Alvarez",
    "Novak",
]
_PAYERS = [
    "Acme Health Plan",
    "BlueSky Insurance",
    "Meridian Care",
    "Northstar Health",
    "Cascade Mutual",
]
_FACILITIES = [
    "Riverside Imaging Center",
    "Lakeview Orthopedics",
    "Summit Medical Group",
    "Prairie Diagnostics",
]
_SPECIALTIES = ["Orthopedics", "Cardiology", "Neurology", "Oncology", "Radiology"]

# (ICD-10, CPT, description) triples that plausibly co-occur — synthetic pairings only.
_CLINICAL_COMBOS = [
    ("M54.16", "72148", "MRI lumbar spine without contrast"),
    ("M17.11", "27447", "Total knee arthroplasty, right"),
    ("I25.10", "93458", "Cardiac catheterization, left heart"),
    ("G43.909", "70551", "MRI brain without contrast"),
    ("M75.100", "73221", "MRI upper extremity joint"),
]


def _luhn_check_digit(payload: str) -> int:
    """Compute the NPI check digit (Luhn over '80840' + 9-digit payload)."""
    digits = [int(c) for c in "80840" + payload]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def make_npi(rng: random.Random) -> str:
    """A 10-digit NPI that passes the standard checksum. Synthetic, not assigned to anyone."""
    payload = "".join(str(rng.randint(0, 9)) for _ in range(9))
    return payload + str(_luhn_check_digit(payload))


@dataclass(frozen=True)
class SyntheticValues:
    """One document's worth of fabricated field values (the ground truth)."""

    member_id: str
    member_name: str
    member_dob: str  # as printed, MM/DD/YYYY
    payer_name: str
    plan_id: str
    ordering_provider_name: str
    ordering_provider_npi: str
    servicing_facility: str
    diagnosis_code: str
    procedure_code: str
    procedure_description: str
    date_of_service: str  # as printed, MM/DD/YYYY
    urgency: str
    contact_phone: str


def make_values(rng: random.Random) -> SyntheticValues:
    """Generate one deterministic, internally-consistent set of synthetic values."""
    icd10, cpt, desc = rng.choice(_CLINICAL_COMBOS)
    dob = date(1950, 1, 1) + timedelta(days=rng.randint(0, 20000))
    dos = date(2026, 1, 1) + timedelta(days=rng.randint(30, 300))
    provider = f"Dr. {rng.choice(_FIRST)} {rng.choice(_LAST)}, MD"
    return SyntheticValues(
        member_id=f"{rng.choice('ABCDEFXYZ')}{rng.randint(10_000_000, 99_999_999)}",
        member_name=f"{rng.choice(_FIRST)} {rng.choice(_LAST)}",
        member_dob=dob.strftime("%m/%d/%Y"),
        payer_name=rng.choice(_PAYERS),
        plan_id=f"GRP-{rng.randint(10000, 99999)}",
        ordering_provider_name=provider,
        ordering_provider_npi=make_npi(rng),
        servicing_facility=rng.choice(_FACILITIES),
        diagnosis_code=icd10,
        procedure_code=cpt,
        procedure_description=desc,
        date_of_service=dos.strftime("%m/%d/%Y"),
        urgency=rng.choice(["Standard", "Standard", "Standard", "Urgent"]),
        contact_phone=f"(555) {rng.randint(200, 999)}-{rng.randint(1000, 9999)}",
    )
