from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate
from django.dispatch import receiver


SEED_CODES = [
    ("DOC_SRS", "요구사항정의서", "의료기기 개발 자료에서 제품 목적, 사용자, 기능/비기능 요구사항을 구조화한 RA 기준 문서"),
    ("DOC_ITF", "위험관리표", "위해요인, 위해상황, 위험통제, 검증항목을 연결하는 ISO 14971 관점 문서"),
    ("DOC_ARCH", "소프트웨어 요구사항 명세서", "SaMD 개발문서 보조를 위한 SRS 및 시스템 구성요소 정의 문서"),
    ("DOC_ERD", "추적성 매트릭스", "요구사항, 위험, 시험, 검증 결과, 변경 이력을 연결하는 추적성 문서"),
    ("DOC_DB", "변경관리 기록", "요구사항, 알고리즘, 데이터, UI, 라벨 변경의 RA 영향과 재검증 필요성을 기록하는 문서"),
    ("DOC_TS", "통합시험 시나리오", "요구사항과 위험통제 항목을 기준으로 생성하는 검증 시험 시나리오"),
    ("FILE_MEETING", "회의록", "RA 검토 회의, 설계 검토, 변경 검토 회의록"),
    ("FILE_RFP", "의료기기 개발 자료", "제품 개요, 사용 목적, 요구사항, 시험 자료, 변경 이력 등 RA 문서 생성 근거 자료"),
    (
        "FILE_REQ_DOC_JSON",
        "RA 요구사항 JSON",
        "요구사항정의서 화면과 별도로 관리되는 RA 요구사항 구조화 JSON",
    ),
    ("PRGRS_PENDING", "생성 대기", "RA 문서 생성 작업 대기 상태"),
    ("PRGRS_PROCESSING", "생성 중", "RA 문서 생성 및 정합성 검토 진행 상태"),
    ("PRGRS_COMPLETED", "생성 완료", "RA 문서 초안 생성 완료 상태"),
    ("PRGRS_FAILED", "생성 실패", "RA 문서 생성 작업 실패 상태"),
    ("ROLE_MEMBER", "담당자", "프로젝트 RA 문서 작성 담당 권한"),
    ("ROLE_MANAGER", "관리자", "프로젝트 RA 문서 검토 및 승인 권한"),
    ("APRV_REQ", "검토 대기", "RA 문서 정합성 검토 요청 상태"),
    ("APRV_COM", "검토 완료", "RA 문서 정합성 검토 완료 상태"),
    ("APRV_RJT", "보완 요청", "RA 문서 보완 요청 상태"),
]


def _ensure_admin_user():
    try:
        User = get_user_model()
        admin = User.objects.filter(user_id="admin").first()
        if admin is None:
            next_sn = (User.objects.order_by("-sn").values_list("sn", flat=True).first() or 0) + 1
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tbl_user (
                        user_sn,
                        user_id,
                        user_pswd,
                        user_nm,
                        dept_nm,
                        jbgd_nm,
                        sys_mngr_yn,
                        tmpr_pswd_yn,
                        use_yn,
                        crt_dt,
                        creatr_sn,
                        mdfcn_dt,
                        mdfr_sn
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP, %s
                    )
                    """,
                    [
                        next_sn,
                        "admin",
                        make_password("abc1234"),
                        "관리자",
                        "RA 문서 자동화",
                        "시스템 관리자",
                        "Y",
                        "N",
                        "Y",
                        next_sn,
                        next_sn,
                    ],
                )
            admin = User.objects.get(sn=next_sn)

        update_fields = []
        if admin.sys_mngr_yn != "Y":
            admin.sys_mngr_yn = "Y"
            update_fields.append("sys_mngr_yn")
        if admin.use_yn != "Y":
            admin.use_yn = "Y"
            update_fields.append("use_yn")
        if admin.created_by_id is None:
            admin.created_by = admin
            update_fields.append("created_by")
        if admin.updated_by_id is None:
            admin.updated_by = admin
            update_fields.append("updated_by")
        if update_fields:
            admin.save(update_fields=update_fields)
        return admin
    except Exception:
        return None


def ensure_initial_reference_data():
    try:
        existing_tables = set(connection.introspection.table_names())
    except Exception:
        return

    if not {"tbl_user", "tbl_code"}.issubset(existing_tables):
        return

    Code = django_apps.get_model("common", "Code")
    admin = _ensure_admin_user()
    if admin is None:
        return

    try:
        for code, name, remarks in SEED_CODES:
            Code.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "remarks": remarks,
                    "created_by": admin,
                    "updated_by": admin,
                },
            )
    except Exception:
        return


@receiver(post_migrate, dispatch_uid="common.seed_initial_reference_data")
def seed_initial_reference_data(sender, app_config, **kwargs):
    if app_config.label != "common":
        return
    ensure_initial_reference_data()


@receiver(connection_created, dispatch_uid="common.sqlite_memory_journal")
def configure_sqlite_connection(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=MEMORY;")
        cursor.execute("PRAGMA synchronous=OFF;")
        cursor.execute("PRAGMA temp_store=MEMORY;")
