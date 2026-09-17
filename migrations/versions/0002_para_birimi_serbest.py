"""Para birimi listesi koddan çıkarıldı (karar 2026-09-17).

``etki.para_birimi`` artık izinli değer listesiyle değil, yalnız "boş değil"
kısıtıyla denetlenir: hangi para birimlerinin var olduğu belgelerde ve nesne
özelliklerinde yaşar, kodda değil.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    with op.batch_alter_table("etki", recreate="always") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("ck_etki_para_birimi_izinli"), type_="check"
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_etki_para_birimi_bos_degil"), "length(para_birimi) > 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("etki", recreate="always") as batch_op:
        batch_op.drop_constraint(
            batch_op.f("ck_etki_para_birimi_bos_degil"), type_="check"
        )
        batch_op.create_check_constraint(
            batch_op.f("ck_etki_para_birimi_izinli"), "para_birimi IN ('TRY')"
        )
