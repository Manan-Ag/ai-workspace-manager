"""Replace the initial recruiter-themed tutorial with a neutral workshop example.

Revision ID: 20260905_0004
Revises: 20260905_0003
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260905_0004"
down_revision: Union[str, None] = "20260905_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_PROJECT_DESCRIPTION = (
    "A guided example showing how one conversation can grow into focused branches."
)
NEW_PROJECT_DESCRIPTION = (
    "A practical example showing how one plan can grow into focused branches."
)
OLD_CONTEXT = (
    "The user is planning a small AI workspace launch and wants to focus the "
    "conversation on a concise recruiter-facing demonstration."
)
NEW_CONTEXT = (
    "The user is planning a weekend photography workshop and wants to focus "
    "this path on confidence and pacing for complete beginners."
)

MESSAGE_REPLACEMENTS = [
    (
        "I’m preparing a launch plan for a small AI research workspace. What should I prioritize?",
        "I’m organizing a weekend photography workshop for complete beginners. What should I prioritize?",
    ),
    (
        "Start with three priorities:\n\n"
        "1. **A clear first-use experience** so a visitor understands the product quickly.\n"
        "2. **One memorable capability**—branching an answer into a focused line of thought.\n"
        "3. **A reliable demo path** with a realistic conversation already available.\n\n"
        "Keep the launch small, observe where visitors hesitate, and improve that path first.",
        "Start with three priorities:\n\n"
        "1. **One clear outcome**—everyone should leave able to control exposure and composition.\n"
        "2. **Plenty of guided practice** with short exercises and immediate feedback.\n"
        "3. **Reliable logistics** including loaner cameras, charging, and an indoor backup location.\n\n"
        "Keep the group small, use plain language, and spend more time shooting than presenting.",
    ),
    (
        "Turn those priorities into a simple one-week plan.",
        "Turn those priorities into a simple one-week preparation plan.",
    ),
    (
        "### One-week launch plan\n\n"
        "- **Days 1–2:** Polish onboarding and the sample workspace.\n"
        "- **Days 3–4:** Test branching, search, and chat recovery.\n"
        "- **Day 5:** Invite a few reviewers and watch where they get stuck.\n"
        "- **Days 6–7:** Fix the clearest problems and publish the recruiter link.",
        "### One-week preparation plan\n\n"
        "- **Days 1–2:** Confirm the venue, class size, and available equipment.\n"
        "- **Days 3–4:** Build three short exercises on exposure, focus, and composition.\n"
        "- **Day 5:** Run the agenda with a friend who is new to photography.\n"
        "- **Days 6–7:** Simplify confusing sections, charge equipment, and send attendees a checklist.",
    ),
    (
        "Focus only on what a recruiter should see in the first two minutes.",
        "Focus only on keeping complete beginners confident during the first hour.",
    ),
    (
        "For a two-minute recruiter review, show this sequence:\n\n"
        "1. Enter with one click as a guest.\n"
        "2. Open this sample chat and scan the main trunk.\n"
        "3. Select the **Recruiter demo path** branch to see context become focused.\n"
        "4. Start a new branch from any answer to demonstrate the core interaction.",
        "For a calm, beginner-friendly first hour:\n\n"
        "1. Start with camera handling and one reassuring auto-mode photo.\n"
        "2. Introduce only aperture and shutter speed using a paired exercise.\n"
        "3. Let everyone compare photos and describe one thing they like.\n"
        "4. End with a short composition walk that creates an early success.",
    ),
]


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE projects
            SET name = 'Photography workshop', description = :new_description
            WHERE name = 'Welcome demo' AND description = :old_description
            """
        ),
        {
            "new_description": NEW_PROJECT_DESCRIPTION,
            "old_description": OLD_PROJECT_DESCRIPTION,
        },
    )
    connection.execute(
        sa.text(
            """
            UPDATE conversations
            SET title = 'Planning a beginner photography workshop'
            WHERE title = 'Planning a focused product launch'
            """
        )
    )
    branch_update = sa.text(
        """
        UPDATE conversation_branches
        SET name = 'Beginner-friendly first hour',
            context_summary = :new_context,
            retained_topics = :retained_topics,
            omitted_topics = :omitted_topics
        WHERE name = 'Recruiter demo path' AND context_summary = :old_context
        """
    ).bindparams(
        sa.bindparam("retained_topics", type_=sa.JSON()),
        sa.bindparam("omitted_topics", type_=sa.JSON()),
    )
    connection.execute(
        branch_update,
        {
            "new_context": NEW_CONTEXT,
            "old_context": OLD_CONTEXT,
            "retained_topics": [
                "beginner confidence",
                "guided practice",
                "first-hour pacing",
            ],
            "omitted_topics": [
                "venue logistics",
                "broader one-week preparation",
            ],
        },
    )
    for old_content, new_content in MESSAGE_REPLACEMENTS:
        connection.execute(
            sa.text(
                "UPDATE messages SET content = :new_content WHERE content = :old_content"
            ),
            {"new_content": new_content, "old_content": old_content},
        )


def downgrade() -> None:
    raise RuntimeError("The refreshed tutorial content is intentionally forward-only.")
