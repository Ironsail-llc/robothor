#!/usr/bin/env python3
"""One-time seed script: populate contact_identifiers with GitHub/JIRA mappings for the dev team.

Usage: venv/bin/python scripts/seed_dev_team_identities.py
"""

from __future__ import annotations

import os
import uuid

import psycopg2

DB_NAME = "robothor_memory"
TENANT_ID = os.environ.get("ROBOTHOR_DEFAULT_TENANT", "default")


def get_conn():
    return psycopg2.connect(dbname=DB_NAME)


def find_person(conn, first_name: str, last_name: str = "") -> str | None:
    """Find a CRM person by name, return their UUID or None."""
    with conn.cursor() as cur:
        if last_name:
            cur.execute(
                "SELECT id::text FROM crm_people WHERE first_name ILIKE %s AND last_name ILIKE %s AND deleted_at IS NULL LIMIT 1",
                (first_name, last_name),
            )
        else:
            cur.execute(
                "SELECT id::text FROM crm_people WHERE first_name ILIKE %s AND deleted_at IS NULL LIMIT 1",
                (first_name,),
            )
        row = cur.fetchone()
        return row[0] if row else None


def create_person(conn, first_name: str, last_name: str, email: str = "") -> str:
    """Create a new CRM person and return their UUID."""
    person_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crm_people (id, first_name, last_name, email, tenant_id, created_at, updated_at)
            VALUES (%s::uuid, %s, %s, %s, %s, now(), now())
            """,
            (person_id, first_name, last_name, email or None, TENANT_ID),
        )
    return person_id


def link_identity(conn, person_id: str, channel: str, identifier: str, display_name: str = ""):
    """Link a channel identity to a CRM person (upsert)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contact_identifiers (tenant_id, channel, identifier, display_name, person_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::uuid, now(), now())
            ON CONFLICT (tenant_id, channel, identifier)
            DO UPDATE SET person_id = EXCLUDED.person_id, display_name = EXCLUDED.display_name, updated_at = now()
            """,
            (TENANT_ID, channel, identifier, display_name or None, person_id),
        )


def main():
    conn = get_conn()

    # ── Known team members already in CRM ──
    existing = {
        # (first_name, last_name): {github: ..., jira_display: ...}
        ("Adan", "Cruz"): {"github": "adan-ironsail", "jira": "Adan France Cruz"},
        ("Danylo", "Boiko"): {"github": "danylo-ironsail", "jira": "Danylo Boiko"},
        ("Farhan", "Sheikh"): {"jira": "Farhan Sheikh"},  # GitHub handle unknown
        ("Philip", "D'Agostino"): {"github": "Ironsail-Philip", "jira": "Philip DAgostino"},
        ("Elguja", "Nemsadze"): {"github": "JexPY", "jira": "Elguja"},
        ("Nadjib", "Boumekhiet"): {"jira": "nadjib"},
        ("Illia", "Tutko"): {"jira": "Illia"},
        ("Rochelle", "Blaza"): {"jira": "Rochelle Blaza"},
        ("Gregory", "Popov"): {"github": "hryhorii-popov", "jira": "Gregory Popov"},
    }

    # ── Team members to create ──
    to_create = {
        # (first_name, last_name): {github: ..., jira_display: ...}
        ("Jhon Ray", "Angcon"): {"github": "jhonray23", "jira": "Jhon Ray Angcon"},
        ("Lorenz", "Lauraya"): {
            "github": "llauraya-ironsail",
            "jira": "Lorenz Alfred Jose Linco Lauraya",
        },
        ("Muhammad Usama", "Butt"): {"github": "muhmmad-ironsail", "jira": "Muhammad Usama Butt"},
    }

    # ── GitHub-only handles (real name unknown) ──
    github_only = {
        "slivas": "slivas",
        "2tko": "2tko",
        "shahbaz-ironsail": "shahbaz-ironsail",
    }

    linked = 0
    created = 0

    # Process existing CRM people
    for (first, last), identities in existing.items():
        person_id = find_person(conn, first, last)
        if not person_id:
            # Try first name only for single-name entries
            person_id = find_person(conn, first)
        if not person_id:
            print(f"  WARNING: {first} {last} not found in CRM — skipping")
            continue

        for channel_type, handle in identities.items():
            channel = "github" if channel_type == "github" else "jira_display_name"
            link_identity(conn, person_id, channel, handle, f"{first} {last}")
            linked += 1
            print(f"  Linked {first} {last} → {channel}:{handle}")

    # Create missing people and link
    for (first, last), identities in to_create.items():
        person_id = find_person(conn, first, last)
        if not person_id:
            person_id = create_person(conn, first, last)
            created += 1
            print(f"  Created {first} {last} ({person_id[:8]}...)")

        for channel_type, handle in identities.items():
            channel = "github" if channel_type == "github" else "jira_display_name"
            link_identity(conn, person_id, channel, handle, f"{first} {last}")
            linked += 1
            print(f"  Linked {first} {last} → {channel}:{handle}")

    # GitHub-only handles (create placeholder people)
    for handle, display in github_only.items():
        person_id = find_person(conn, handle)
        if not person_id:
            person_id = create_person(conn, handle, "", "")
            created += 1
            print(f"  Created placeholder for GitHub handle: {handle} ({person_id[:8]}...)")

        link_identity(conn, person_id, "github", handle, display)
        linked += 1
        print(f"  Linked {handle} → github:{handle}")

    conn.commit()
    conn.close()

    print(f"\nDone: {created} people created, {linked} identities linked")


if __name__ == "__main__":
    main()
