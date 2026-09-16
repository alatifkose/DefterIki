"""İlk şema: Aşama 4 dikey diliminin on beş tablosu (Tam Plan bölüm 5; tek defter).

Alembic autogenerate ile defteriki.sema.METADATA'dan üretildi, sonra donduruldu;
bu dosya değişmez, şema değişimi yeni migration ile yapılır. belge → okuma dış
anahtarı döngü kırmak için use_alter taşır, SQLite'ta satır içi yazılır.
Nesne durumlarına ONAY_BEKLIYOR 4.4 kararıyla eklendi (henüz gerçek veri yokken).

Sürüm: 0001
Önceki: yok
Oluşturma: 2026-09-16 22:51:31.737877
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "arsiv_dosya",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("boyut", sa.Integer(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("goreli_yol", sa.Text(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "boyut >= 0", name=op.f("ck_arsiv_dosya_boyut_negatif_degil")
        ),
        sa.CheckConstraint(
            "length(sha256) = 64", name=op.f("ck_arsiv_dosya_sha256_64_hex")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arsiv_dosya")),
        sa.UniqueConstraint("goreli_yol", name=op.f("uq_arsiv_dosya_goreli_yol")),
        sa.UniqueConstraint("sha256", name=op.f("uq_arsiv_dosya_sha256")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "islem_anahtari",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("arac_adi", sa.Text(), nullable=False),
        sa.Column("anahtar", sa.Text(), nullable=False),
        sa.Column("istek_ozeti", sa.Text(), nullable=False),
        sa.Column("sonuc", sa.JSON(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "anahtar <> ''", name=op.f("ck_islem_anahtari_anahtar_bos_degil")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_islem_anahtari")),
        sa.UniqueConstraint(
            "arac_adi", "anahtar", name=op.f("uq_islem_anahtari_arac_adi_anahtar")
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "nesne",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("seviye", sa.Integer(), nullable=False),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.Column("surum", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "durum IN ('ONAY_BEKLIYOR', 'AKTIF', 'ENGELLI', 'PASIF', 'SILINDI')",  # noqa: E501
            name=op.f("ck_nesne_durum_izinli"),
        ),
        sa.CheckConstraint("seviye >= 0", name=op.f("ck_nesne_seviye_negatif_degil")),
        sa.CheckConstraint("surum >= 1", name=op.f("ck_nesne_surum_pozitif")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nesne")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("nesne", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nesne_seviye_id"), ["seviye", "id"], unique=False
        )

    op.create_table(
        "onay_talep",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tur", sa.Text(), nullable=False),
        sa.Column("hedef_id", sa.Integer(), nullable=False),
        sa.Column("hedef_surumu", sa.Integer(), nullable=False),
        sa.Column("icerik", sa.JSON(), nullable=False),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.Column("karar", sa.JSON(), nullable=True),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.Column("cozum_zamani", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "durum IN ('BEKLIYOR', 'ONAYLANDI', 'REDDEDILDI')",
            name=op.f("ck_onay_talep_durum_izinli"),
        ),
        sa.CheckConstraint(
            "tur IN ('NESNE_ACILISI')", name=op.f("ck_onay_talep_tur_izinli")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_onay_talep")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("onay_talep", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_onay_talep_durum_id"), ["durum", "id"], unique=False
        )

    op.create_table(
        "belge",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dosya_id", sa.Integer(), nullable=False),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.Column("etkin_okuma_id", sa.Integer(), nullable=True),
        sa.Column("surum", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "durum IN ('ARSIVLENDI', 'OKUNUYOR', 'KARAR_BEKLIYOR', 'HAZIR', 'KAYITLI', 'GECERSIZ', 'YERINE_GECILDI')",  # noqa: E501
            name=op.f("ck_belge_durum_izinli"),
        ),
        sa.CheckConstraint("surum >= 1", name=op.f("ck_belge_surum_pozitif")),
        sa.ForeignKeyConstraint(
            ["dosya_id"], ["arsiv_dosya.id"], name=op.f("fk_belge_dosya_id_arsiv_dosya")
        ),
        sa.ForeignKeyConstraint(
            ["etkin_okuma_id"],
            ["okuma.id"],
            name=op.f("fk_belge_etkin_okuma_id_okuma"),
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_belge")),
        sa.UniqueConstraint("dosya_id", name=op.f("uq_belge_dosya_id")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "denetim_olay",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("islem_id", sa.Integer(), nullable=True),
        sa.Column("aktor", sa.Text(), nullable=False),
        sa.Column("eylem", sa.Text(), nullable=False),
        sa.Column("hedef", sa.Text(), nullable=False),
        sa.Column("gerekce", sa.Text(), nullable=True),
        sa.Column("onceki_durum", sa.Text(), nullable=True),
        sa.Column("sonraki_durum", sa.Text(), nullable=True),
        sa.Column("zaman", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["islem_id"],
            ["islem_anahtari.id"],
            name=op.f("fk_denetim_olay_islem_id_islem_anahtari"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_denetim_olay")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "kayit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("asil_nesne_id", sa.Integer(), nullable=False),
        sa.Column("islem_tarihi", sa.Date(), nullable=False),
        sa.Column("valor_tarihi", sa.Date(), nullable=True),
        sa.Column("aciklama", sa.Text(), nullable=True),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "durum IN ('AKTIF', 'GECERSIZ')", name=op.f("ck_kayit_durum_izinli")
        ),
        sa.ForeignKeyConstraint(
            ["asil_nesne_id"], ["nesne.id"], name=op.f("fk_kayit_asil_nesne_id_nesne")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kayit")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("kayit", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_kayit_asil_nesne_id_islem_tarihi_id"),
            ["asil_nesne_id", "islem_tarihi", "id"],
            unique=False,
        )

    op.create_table(
        "nesne_baglanti",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alt_id", sa.Integer(), nullable=False),
        sa.Column("ust_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "alt_id <> ust_id", name=op.f("ck_nesne_baglanti_kendine_bagli_degil")
        ),
        sa.ForeignKeyConstraint(
            ["alt_id"], ["nesne.id"], name=op.f("fk_nesne_baglanti_alt_id_nesne")
        ),
        sa.ForeignKeyConstraint(
            ["ust_id"], ["nesne.id"], name=op.f("fk_nesne_baglanti_ust_id_nesne")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nesne_baglanti")),
        sa.UniqueConstraint(
            "alt_id", "ust_id", name=op.f("uq_nesne_baglanti_alt_id_ust_id")
        ),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("nesne_baglanti", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nesne_baglanti_ust_id"), ["ust_id"], unique=False
        )

    op.create_table(
        "nesne_ozellik",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("alan_adi", sa.Text(), nullable=False),
        sa.Column("deger_turu", sa.Text(), nullable=False),
        sa.Column("deger", sa.JSON(), nullable=False),
        sa.Column("eslesme_degeri", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "alan_adi <> ''", name=op.f("ck_nesne_ozellik_alan_adi_bos_degil")
        ),
        sa.CheckConstraint(
            "deger_turu IN ('METIN', 'TAMSAYI', 'ONDALIK', 'TARIH', 'MANTIKSAL', 'JSON')",  # noqa: E501
            name=op.f("ck_nesne_ozellik_deger_turu_izinli"),
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id"], ["nesne.id"], name=op.f("fk_nesne_ozellik_nesne_id_nesne")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nesne_ozellik")),
        sa.UniqueConstraint(
            "nesne_id", "alan_adi", name=op.f("uq_nesne_ozellik_nesne_id_alan_adi")
        ),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("nesne_ozellik", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nesne_ozellik_alan_adi_deger_turu_eslesme_degeri"),
            ["alan_adi", "deger_turu", "eslesme_degeri"],
            unique=False,
        )

    op.create_table(
        "etki",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kayit_id", sa.Integer(), nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("eksen", sa.Text(), nullable=False),
        sa.Column("yon", sa.Text(), nullable=False),
        sa.Column("tutar_kurus", sa.Integer(), nullable=False),
        sa.Column("para_birimi", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "eksen IN ('VARLIK', 'BORC', 'GIDER')", name=op.f("ck_etki_eksen_izinli")
        ),
        sa.CheckConstraint(
            "para_birimi IN ('TRY')", name=op.f("ck_etki_para_birimi_izinli")
        ),
        sa.CheckConstraint(
            "yon IN ('ARTTIR', 'AZALT')", name=op.f("ck_etki_yon_izinli")
        ),
        sa.CheckConstraint(
            "tutar_kurus >= 0", name=op.f("ck_etki_tutar_negatif_degil")
        ),
        sa.ForeignKeyConstraint(
            ["kayit_id"], ["kayit.id"], name=op.f("fk_etki_kayit_id_kayit")
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id"], ["nesne.id"], name=op.f("fk_etki_nesne_id_nesne")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_etki")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("etki", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_etki_nesne_id_eksen_para_birimi_kayit_id"),
            ["nesne_id", "eksen", "para_birimi", "kayit_id"],
            unique=False,
        )

    op.create_table(
        "nesne_sart",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("ozellik_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["nesne_id"], ["nesne.id"], name=op.f("fk_nesne_sart_nesne_id_nesne")
        ),
        sa.ForeignKeyConstraint(
            ["ozellik_id"],
            ["nesne_ozellik.id"],
            name=op.f("fk_nesne_sart_ozellik_id_nesne_ozellik"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nesne_sart")),
        sa.UniqueConstraint(
            "nesne_id", "ozellik_id", name=op.f("uq_nesne_sart_nesne_id_ozellik_id")
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "okuma",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("belge_id", sa.Integer(), nullable=False),
        sa.Column("surum_no", sa.Integer(), nullable=False),
        sa.Column("sema_surumu", sa.Text(), nullable=False),
        sa.Column("icerik", sa.JSON(), nullable=True),
        sa.Column("tamlik", sa.JSON(), nullable=True),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.Column("olusturma_zamani", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "durum IN ('ACIK', 'TAMAMLANDI', 'IPTAL')",
            name=op.f("ck_okuma_durum_izinli"),
        ),
        sa.CheckConstraint("surum_no >= 1", name=op.f("ck_okuma_surum_no_pozitif")),
        sa.ForeignKeyConstraint(
            ["belge_id"], ["belge.id"], name=op.f("fk_okuma_belge_id_belge")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_okuma")),
        sa.UniqueConstraint(
            "belge_id", "surum_no", name=op.f("uq_okuma_belge_id_surum_no")
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "nesne_kaynak",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("nesne_id", sa.Integer(), nullable=False),
        sa.Column("belge_id", sa.Integer(), nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=True),
        sa.Column("konum", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["belge_id"], ["belge.id"], name=op.f("fk_nesne_kaynak_belge_id_belge")
        ),
        sa.ForeignKeyConstraint(
            ["nesne_id"], ["nesne.id"], name=op.f("fk_nesne_kaynak_nesne_id_nesne")
        ),
        sa.ForeignKeyConstraint(
            ["okuma_id"], ["okuma.id"], name=op.f("fk_nesne_kaynak_okuma_id_okuma")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_nesne_kaynak")),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("nesne_kaynak", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_nesne_kaynak_nesne_id"), ["nesne_id"], unique=False
        )

    op.create_table(
        "okuma_satir",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("okuma_id", sa.Integer(), nullable=False),
        sa.Column("satir_anahtari", sa.Text(), nullable=False),
        sa.Column("konum", sa.Integer(), nullable=False),
        sa.Column("ham", sa.JSON(), nullable=False),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.Column("aday_grup_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "durum IN ('YAZILDI', 'KARAR_BEKLIYOR', 'MEVCUDA_BAGLANDI', 'KAPSAM_DISI')",  # noqa: E501
            name=op.f("ck_okuma_satir_durum_izinli"),
        ),
        sa.CheckConstraint(
            "satir_anahtari <> ''", name=op.f("ck_okuma_satir_satir_anahtari_bos_degil")
        ),
        sa.ForeignKeyConstraint(
            ["okuma_id"], ["okuma.id"], name=op.f("fk_okuma_satir_okuma_id_okuma")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_okuma_satir")),
        sa.UniqueConstraint(
            "okuma_id",
            "satir_anahtari",
            name=op.f("uq_okuma_satir_okuma_id_satir_anahtari"),
        ),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "kayit_kaynak",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kayit_id", sa.Integer(), nullable=False),
        sa.Column("okuma_satir_id", sa.Integer(), nullable=False),
        sa.Column("rol", sa.Text(), nullable=False),
        sa.Column("durum", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "durum IN ('AKTIF', 'KALDIRILDI')",
            name=op.f("ck_kayit_kaynak_durum_izinli"),
        ),
        sa.CheckConstraint(
            "rol IN ('ASIL', 'DESTEK')", name=op.f("ck_kayit_kaynak_rol_izinli")
        ),
        sa.ForeignKeyConstraint(
            ["kayit_id"], ["kayit.id"], name=op.f("fk_kayit_kaynak_kayit_id_kayit")
        ),
        sa.ForeignKeyConstraint(
            ["okuma_satir_id"],
            ["okuma_satir.id"],
            name=op.f("fk_kayit_kaynak_okuma_satir_id_okuma_satir"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_kayit_kaynak")),
        sa.UniqueConstraint(
            "kayit_id",
            "okuma_satir_id",
            name=op.f("uq_kayit_kaynak_kayit_id_okuma_satir_id"),
        ),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("kayit_kaynak", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_kayit_kaynak_okuma_satir_id"),
            ["okuma_satir_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("kayit_kaynak", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_kayit_kaynak_okuma_satir_id"))

    op.drop_table("kayit_kaynak")
    op.drop_table("okuma_satir")
    with op.batch_alter_table("nesne_kaynak", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nesne_kaynak_nesne_id"))

    op.drop_table("nesne_kaynak")
    op.drop_table("okuma")
    op.drop_table("nesne_sart")
    with op.batch_alter_table("etki", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_etki_nesne_id_eksen_para_birimi_kayit_id"))

    op.drop_table("etki")
    with op.batch_alter_table("nesne_ozellik", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_nesne_ozellik_alan_adi_deger_turu_eslesme_degeri")
        )

    op.drop_table("nesne_ozellik")
    with op.batch_alter_table("nesne_baglanti", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nesne_baglanti_ust_id"))

    op.drop_table("nesne_baglanti")
    with op.batch_alter_table("kayit", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_kayit_asil_nesne_id_islem_tarihi_id"))

    op.drop_table("kayit")
    op.drop_table("denetim_olay")
    op.drop_table("belge")
    with op.batch_alter_table("onay_talep", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_onay_talep_durum_id"))

    op.drop_table("onay_talep")
    with op.batch_alter_table("nesne", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_nesne_seviye_id"))

    op.drop_table("nesne")
    op.drop_table("islem_anahtari")
    op.drop_table("arsiv_dosya")
