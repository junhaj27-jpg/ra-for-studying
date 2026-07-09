from datetime import timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from common.project_selection import resolve_current_project
from common.signals import ensure_initial_reference_data
from common.models import YesNoChoices
from common.pagination import paginate
from files.services import (
    SEARCH_FIELD_CHOICES,
    apply_file_filters,
    build_project_file_rows,
    get_file_type_choices,
)

from .models import Document, DocumentApproval
from .services import (
    ARCHITECTURE_DOCUMENT_CODE,
    DERIVED_DOCUMENT_CODES,
    FILE_INPUT_DOCUMENT_CODES,
    GENERATION_JOB_KIND_AUTO_APPLY,
    GENERATION_JOB_KIND_INITIAL,
    INTERFACE_REFERENCE_DOCUMENT_CODE,
    PROGRESS_COMPLETED,
    PROGRESS_FAILED,
    PROGRESS_PENDING,
    PROGRESS_PROCESSING,
    _debug_generation_log,
    acquire_document_lock,
    add_generation_itf_references,
    apply_approval_filters,
    approve_request,
    begin_generation_regeneration,
    build_approval_data_view,
    build_approval_queryset,
    build_approval_rows,
    build_approval_review_view,
    build_document_detail_url,
    build_document_rows,
    build_editor_config,
    build_generation_redirect_url,
    build_history_preview_api_url,
    can_access_initial_generation,
    can_request_approval,
    cancel_approval_request,
    clear_generation_draft_document,
    clear_doc_job_snapshot,
    clear_generation_state,
    confirm_document,
    create_project_net,
    create_approval_request,
    download_remote_content,
    extract_text_from_docx,
    find_generation_job,
    find_doc_job_snapshot,
    get_actor,
    get_approval_status_choices,
    get_current_generation_code,
    get_doc_job_poll_interval_seconds,
    get_detail_by_sn,
    get_document_detail_bytes,
    get_generation_job,
    get_generation_job_kind,
    get_document_label,
    get_document_history_queryset,
    get_document_title,
    get_document_type_choices,
    get_document_view_state,
    get_generation_draft_document,
    get_generation_progress_rows,
    get_generation_selected_files,
    get_generation_state,
    get_generation_itf_references,
    get_generation_prerequisite_error,
    is_same_docx_revision,
    get_latest_generation_job,
    get_latest_detail,
    get_latest_approval_review_job,
    get_latest_pending_approval,
    get_onlyoffice_document_server_url,
    get_project_files,
    get_project_nets,
    get_running_auto_apply_job,
    get_running_generation_job,
    get_running_history_job,
    get_running_initial_job,
    has_document_version,
    has_active_generation_session,
    is_generation_complete,
    is_latest_detail_for_document,
    is_latest_document_for_type,
    is_project_manager,
    is_project_participant,
    is_working_document,
    latest_confirmed_document,
    mark_generation_confirmed,
    parse_callback_payload,
    reject_request,
    remove_generation_itf_reference,
    release_document_lock,
    request_force_save,
    request_fastapi_approval_review,
    resolve_document_code,
    restore_revision,
    save_generation_state,
    save_doc_job_snapshot,
    save_revision,
    set_generation_document_from_job,
    set_generation_draft_document,
    update_generation_selected_files,
    validate_document_content_token,
    wait_for_new_revision,
    start_auto_apply_job,
    start_initial_generation_job,
)

GENERATION_JOB_WALLCLOCK_TIME_ZONE = ZoneInfo("Asia/Seoul")
GENERATION_JOB_FUTURE_SKEW_THRESHOLD = timedelta(hours=1)
APPROVAL_REQUEST_MAX_LENGTH = DocumentApproval._meta.get_field("request_content").max_length


def _get_document_or_404(project, document_sn):
    queryset = Document.objects.select_related(
        "project",
        "document_type",
        "created_by",
        "updated_by",
        "possession_user",
    )
    if project is not None:
        queryset = queryset.filter(project=project)
    return get_object_or_404(queryset, sn=document_sn)


def _get_document_by_sn_or_404(document_sn):
    return get_object_or_404(
        Document.objects.select_related(
            "project",
            "document_type",
            "created_by",
            "updated_by",
            "possession_user",
        ),
        sn=document_sn,
    )


def _ensure_document_access(project, actor, document):
    if project is None or document.project_id != project.sn:
        raise Http404
    if not is_project_participant(project, actor):
        raise Http404


def _collect_prefixed_filters(request, prefix):
    return {
        "file_type": request.GET.get(f"{prefix}file_type", "all"),
        "field": request.GET.get(f"{prefix}field", "all"),
        "q": request.GET.get(f"{prefix}q", "").strip(),
    }


def _document_detail_redirect(document, **query):
    base_url = reverse("doc_detail", args=[document.sn])
    if not query:
        return base_url
    return f"{base_url}?{urlencode(query)}"


def _approval_detail_redirect(approval, **query):
    base_url = reverse("doc_approval_detail", args=[approval.approval_sn])
    if not query:
        return base_url
    return f"{base_url}?{urlencode(query)}"


def _is_ajax_request(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _legacy_detail_error_message():
    return "This document revision is missing docs_path. Ask an administrator to migrate legacy rows."


def _build_history_help_text(can_generate):
    if can_generate:
        return '"RA 문서 생성" 버튼을 눌러 초안을 생성한 뒤 정합성 검토 요청을 진행해 주세요.'
    return "RA 문서 생성은 프로젝트에 할당된 담당자만 진행할 수 있으며, 버전 이력에는 검토 완료된 RA 문서만 표시됩니다."


def _build_generation_step_guide(document_code):
    guides = {
        "DOC_SRS": {
            "title": "요구사항정의서 생성",
            "description": "의료기기 개발 자료, 제품 개요, 회의록 또는 규제 근거 문서를 선택해 주세요.",
            "help": "선택한 문서를 기반으로 사용 목적, 대상 사용자, 사용 환경, 기능/비기능 요구사항, 규제 요구사항을 추출합니다.",
        },
        "DOC_ITF": {
            "title": "위험관리표 생성",
            "description": "위험관리표 작성을 위해 위해요인, 사용 오류, 화면 흐름 또는 설계 참고 이미지를 업로드해 주세요.",
            "help": "요구사항정의서를 기준으로 위해요인, 위해상황, 위험통제 방법, 검증항목을 연결합니다.",
        },
        "DOC_ARCH": {
            "title": "소프트웨어 요구사항 명세서 생성",
            "description": "SaMD 개발문서 작성을 위해 시스템 구성요소, 외부 연계, 데이터 흐름, 보안 요구사항을 입력해 주세요.",
            "help": "기존 아키텍처 입력 구조를 유지하면서 SRS에 필요한 기능, 인터페이스, 데이터, 예외 처리 요구사항을 정리합니다.",
        },
        "DOC_ERD": {
            "title": "추적성 매트릭스 생성",
            "description": "요구사항, 위험요소, 시험 케이스, 검증 결과 간 연결 관계를 도출합니다.",
            "help": "요구사항정의서 저장본을 기준으로 RA 추적성 매트릭스 초안을 생성합니다.",
        },
        "DOC_DB": {
            "title": "변경관리 기록 생성",
            "description": "변경관리 기록 작성을 위해 확정된 요구사항과 추적성 매트릭스를 기준으로 영향 분석 항목을 구성합니다.",
            "help": "변경 사유, 영향받는 요구사항, 위험 항목, 재검증 필요 여부, 인허가 영향 검토 항목을 정리합니다.",
        },
        "DOC_TS": {
            "title": "통합시험 시나리오 생성",
            "description": "요구사항과 위험통제 항목을 기준으로 검증 및 밸리데이션 시험 시나리오를 구성합니다.",
            "help": "요구사항정의서와 위험관리표 저장본이 필요하며, 시험 ID를 추적성 매트릭스와 연결합니다.",
        },
    }
    return guides.get(
        document_code,
        {
            "title": f"{get_document_label(document_code)} 생성",
            "description": f"{get_document_label(document_code)} 생성을 위한 입력 정보를 확인해 주세요.",
            "help": "현재 RA 문서 생성 단계와 입력 조건을 확인한 뒤 생성을 진행할 수 있습니다.",
        },
    )

def _find_generation_progress_row(progress_rows, document_code):
    for row in progress_rows:
        if row.get("code") == document_code:
            return row
    return None


def _format_elapsed_seconds(total_seconds):
    try:
        normalized = max(int(total_seconds or 0), 0)
    except (TypeError, ValueError):
        normalized = 0
    hours = normalized // 3600
    minutes = (normalized % 3600) // 60
    seconds = normalized % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _is_generation_resume_request(request):
    return request.GET.get("resume") == "1"


def _clear_failed_generation_drafts(current_project, state):
    if current_project is None:
        return False
    draft_documents = dict(state.get("draft_documents", {}) or {})
    changed = False
    for document_code, document_sn in draft_documents.items():
        draft = (
            Document.objects.filter(
                project=current_project,
                document_type_id=document_code,
                sn=document_sn,
            )
            .only("sn", "progress_status_id")
            .first()
        )
        latest_job = get_latest_generation_job(
            current_project,
            document_code,
            job_kind=GENERATION_JOB_KIND_INITIAL,
        )
        draft_failed = draft is not None and draft.progress_status_id == PROGRESS_FAILED
        job_failed = latest_job is not None and latest_job.job_status_id == PROGRESS_FAILED
        if draft_failed or job_failed:
            clear_generation_draft_document(state, document_code)
            changed = True
    return changed


def _get_generation_context(request, current_project, actor, document_code, state=None):
    state = state or get_generation_state(request.session, current_project)
    if _clear_failed_generation_drafts(current_project, state):
        save_generation_state(request.session, state)
    selected_files = get_generation_selected_files(current_project, state)
    current_code = get_current_generation_code(state, current_project, preferred_code=document_code)
    current_draft = get_generation_draft_document(current_project, state, current_code)
    if current_draft is not None and current_draft.progress_status_id == PROGRESS_FAILED:
        clear_generation_draft_document(state, current_code)
        save_generation_state(request.session, state)
        current_draft = None

    if request.GET.get("auto_start") == "1" and current_code and current_draft is None:
        prerequisite_error = get_generation_prerequisite_error(current_project, state, current_code)
        if prerequisite_error is None:
            job_result = start_initial_generation_job(current_project, actor, state, document_code=current_code)
            save_generation_state(request.session, state)
            if job_result["status"] in {"started", "running"} and job_result["document"] is not None:
                messages.success(request, f"{get_document_label(current_code)} ?앹꽦???붿껌?덉뒿?덈떎.")
                return None, redirect(build_generation_redirect_url(document_code=current_code, play=True, resume=True))

    current_code = get_current_generation_code(state, current_project, preferred_code=document_code)
    current_draft = get_generation_draft_document(current_project, state, current_code)

    progress_rows = get_generation_progress_rows(state, current_project)
    return {
        "state": state,
        "selected_files": selected_files,
        "current_code": current_code,
        "current_label": get_document_label(current_code) if current_code else "",
        "current_draft": current_draft,
        "progress_rows": progress_rows,
        "is_complete": is_generation_complete(state),
        "completed_documents": [
            Document.objects.filter(sn=document_sn).select_related("document_type").first()
            for document_sn in state.get("confirmed_documents", {}).values()
        ],
        "requested_document_code": document_code,
    }, None


def _build_architecture_form_data(request=None):
    source = request.POST if request is not None else {}
    return {
        "name": source.get("name", "").strip(),
        "purpose": source.get("purpose", "").strip(),
        "middleware_stack": source.get("middleware_stack", "").strip(),
        "firewall_settings": source.get("firewall_settings", "").strip(),
        "auth_method": source.get("auth_method", "").strip(),
        "expected_concurrent_users": source.get("expected_concurrent_users", "").strip(),
        "cloud_yn": YesNoChoices.YES if source.get("cloud_yn") == YesNoChoices.YES else YesNoChoices.NO,
        "hardware_spec": source.get("hardware_spec", "").strip(),
        "remarks": source.get("remarks", "").strip(),
    }


def _build_generation_redirect(document_code, *, resume=True, play=False, auto_start=False, modal=None, arch_form=False):
    base_url = build_generation_redirect_url(
        document_code=document_code,
        play=play,
        auto_start=auto_start,
        resume=resume,
    )
    extra_query = []
    if modal:
        extra_query.append(("modal", modal))
    if arch_form:
        extra_query.append(("arch_form", "1"))
    if not extra_query:
        return base_url
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode(extra_query)}"


def _build_job_title(job_kind, document_code):
    label = get_document_label(document_code)
    if job_kind == "auto_apply":
        return f"{label} ?뚯쓽 ?댁슜 ?먮룞 ?곸슜"
    return f"{label} ?앹꽦"


def _build_history_list_url(document_code, **query):
    query_items = []
    if document_code:
        query_items.append(("docs_cd", document_code))
    for key, value in query.items():
        if value not in (None, ""):
            query_items.append((key, str(value)))
    base_url = reverse("doc_history_list")
    return f"{base_url}?{urlencode(query_items)}" if query_items else base_url


def _build_job_status_url(job_kind, document_code, job_id=None, tracking_document_sn=None):
    query_items = [("job_kind", job_kind), ("docs_cd", document_code)]
    if job_id:
        query_items.append(("job_id", str(job_id)))
    if tracking_document_sn:
        query_items.append(("tracking_document_sn", str(tracking_document_sn)))
    return f"{reverse('doc_job_status')}?{urlencode(query_items)}"


def _get_job_timing(job):
    if job is None:
        return "", 0
    reference_dt = getattr(job, "started_at", None)
    if reference_dt is None and getattr(job, "job_status_id", "") != PROGRESS_PROCESSING:
        reference_dt = getattr(job, "requested_at", None)
    if reference_dt is None:
        return "", 0
    if (
        timezone.is_aware(reference_dt)
        and reference_dt.utcoffset() == timedelta(0)
        and reference_dt - timezone.now() > GENERATION_JOB_FUTURE_SKEW_THRESHOLD
    ):
        # GenerationJob timestamps in the live DB are stored as Seoul wall-clock values.
        # When Django attaches UTC to that naive value, elapsed time clamps to 0 forever.
        reference_dt = timezone.make_aware(
            reference_dt.replace(tzinfo=None),
            GENERATION_JOB_WALLCLOCK_TIME_ZONE,
        )
    started_at = timezone.localtime(reference_dt)
    elapsed_seconds = max(int((timezone.now() - reference_dt).total_seconds()), 0)
    return started_at.isoformat(), elapsed_seconds


def _build_job_response(
    job_kind,
    document_code,
    message,
    *,
    status,
    job_id="",
    request_id="",
    tracking_document_sn=None,
    redirect_url="",
    job_status_code="",
    job_status_label="",
    document_sn=None,
    error_cd="",
    error_msg="",
):
    return {
        "status": status,
        "message": message,
        "title": _build_job_title(job_kind, document_code),
        "docs_cd": document_code,
        "job_kind": job_kind,
        "job_id": job_id,
        "request_id": request_id,
        "tracking_document_sn": tracking_document_sn,
        "poll_url": _build_job_status_url(job_kind, document_code, job_id=job_id, tracking_document_sn=tracking_document_sn),
        "poll_interval_ms": get_doc_job_poll_interval_seconds() * 1000,
        "redirect_url": redirect_url,
        "started_at": "",
        "elapsed_seconds": 0,
        "job_status_code": job_status_code,
        "job_status_label": job_status_label,
        "document_sn": document_sn,
        "error_cd": error_cd,
        "error_msg": error_msg,
    }


def _build_generation_job_response(job_kind, document_code, message, job, *, status, redirect_url=""):
    started_at, elapsed_seconds = _get_job_timing(job)
    tracking_document_sn = getattr(job, "document_id", None)
    job_status_code = getattr(job, "job_status_id", "") or getattr(job, "job_status_code", "") or ""
    if not job_status_code:
        raw_status = getattr(job, "status", "") or status
        if raw_status in {"started", "accepted", "queued", "pending"}:
            job_status_code = PROGRESS_PENDING
        elif raw_status == "running":
            job_status_code = PROGRESS_PROCESSING
        elif raw_status == "failed":
            job_status_code = PROGRESS_FAILED
        elif raw_status == "completed":
            job_status_code = PROGRESS_COMPLETED
    job_status_label = getattr(getattr(job, "job_status", None), "name", "") or getattr(job, "job_status_label", "") or job_status_code
    payload = _build_job_response(
        job_kind,
        document_code,
        message,
        status=status,
        job_id=getattr(job, "job_id", "") or "",
        request_id=getattr(job, "request_id", "") or "",
        tracking_document_sn=tracking_document_sn,
        redirect_url=redirect_url,
        job_status_code=job_status_code,
        job_status_label=job_status_label,
        document_sn=tracking_document_sn,
        error_cd=getattr(job, "error_code", "") or "",
        error_msg=getattr(job, "error_message", "") or "",
    )
    payload["started_at"] = started_at
    payload["elapsed_seconds"] = elapsed_seconds
    return payload


def _serialize_job_status(request, current_project, document_code, job_kind, job_id=None, tracking_document_sn=None):
    if job_kind == GENERATION_JOB_KIND_INITIAL:
        generation_state = get_generation_state(request.session, current_project)
        job = find_generation_job(
            current_project,
            document_code,
            job_kind=job_kind,
            job_id=job_id,
            tracking_document_sn=tracking_document_sn,
        )
        if job is None:
            clear_generation_draft_document(generation_state, document_code)
            save_generation_state(request.session, generation_state)
            return _build_job_response(job_kind, document_code, "吏꾪뻾 以묒씤 ?앹꽦 ?묒뾽???놁뒿?덈떎.", status="idle")
        if job.job_status_id == PROGRESS_FAILED:
            clear_generation_draft_document(generation_state, document_code)
            save_generation_state(request.session, generation_state)
            return _build_generation_job_response(
                job_kind,
                document_code,
                "臾몄꽌 ?앹꽦???ㅽ뙣?덉뒿?덈떎. ?ㅼ떆 ?쒕룄??二쇱꽭??",
                job,
                status="failed",
            )
        if job.document is not None:
            set_generation_document_from_job(generation_state, job.document)
            save_generation_state(request.session, generation_state)
    else:
        job = find_generation_job(
            current_project,
            document_code,
            job_kind=job_kind,
            job_id=job_id,
            tracking_document_sn=tracking_document_sn,
        )
        if job is None:
            return _build_job_response(job_kind, document_code, "吏꾪뻾 以묒씤 ?먮룞 ?곸슜 ?묒뾽???놁뒿?덈떎.", status="idle")
        if job.job_status_id == PROGRESS_FAILED:
            return _build_generation_job_response(
                job_kind,
                document_code,
                "?뚯쓽 ?댁슜 ?먮룞 ?곸슜???ㅽ뙣?덉뒿?덈떎. ?ㅼ떆 ?쒕룄??二쇱꽭??",
                job,
                status="failed",
            )

    if job.job_status_id == PROGRESS_PENDING:
        pending_message = (
            "臾몄꽌 ?앹꽦 ?湲?以묒엯?덈떎."
            if job_kind == GENERATION_JOB_KIND_INITIAL
            else "?뚯쓽 ?댁슜 ?먮룞 ?곸슜 ?湲?以묒엯?덈떎."
        )
        return _build_generation_job_response(
            job_kind,
            document_code,
            pending_message,
            job,
            status="running",
        )

    if job.job_status_id == PROGRESS_PROCESSING:
        processing_message = (
            "臾몄꽌瑜??앹꽦 以묒엯?덈떎."
            if job_kind == GENERATION_JOB_KIND_INITIAL
            else "?뚯쓽 ?댁슜???먮룞 ?곸슜 以묒엯?덈떎."
        )
        return _build_generation_job_response(
            job_kind,
            document_code,
            processing_message,
            job,
            status="running",
        )

    if job.job_status_id == PROGRESS_COMPLETED:
        redirect_url = reverse("doc_detail", args=[job.document_id]) if job.document_id else ""
        return _build_generation_job_response(
            job_kind,
            document_code,
            "臾몄꽌媛 以鍮꾨릺?덉뒿?덈떎.",
            job,
            status="completed",
            redirect_url=redirect_url,
        )

    return _build_generation_job_response(
        job_kind,
        document_code,
        "?묒뾽 ?곹깭瑜??뺤씤?????놁뒿?덈떎.",
        job,
        status="idle",
    )


def _build_active_job_context(job_payload):
    if not job_payload or job_payload.get("status") != "running":
        return None
    badge = _build_job_badge(job_payload.get("job_status_code", ""), job_payload.get("job_status_label", ""))
    return {
        "status": job_payload["status"],
        "message": job_payload["message"],
        "title": job_payload["title"],
        "job_id": job_payload.get("job_id", ""),
        "poll_url": job_payload["poll_url"],
        "poll_interval_ms": job_payload["poll_interval_ms"],
        "tracking_document_sn": job_payload["tracking_document_sn"],
        "job_kind": job_payload["job_kind"],
        "docs_cd": job_payload["docs_cd"],
        "started_at": job_payload.get("started_at", ""),
        "elapsed_seconds": job_payload.get("elapsed_seconds", 0),
        "elapsed_display": _format_elapsed_seconds(job_payload.get("elapsed_seconds", 0)),
        "job_status_code": job_payload.get("job_status_code", ""),
        "job_status_label": badge["status_label"],
        "status_badge_class": badge["status_badge_class"],
    }


def _get_document_active_job(request, current_project, document):
    initial_job = get_running_initial_job(
        current_project,
        document.document_type_id,
        tracking_document_sn=document.sn,
    )
    if initial_job is not None:
        return _build_active_job_context(
            _serialize_job_status(
                request,
                current_project,
                document.document_type_id,
                GENERATION_JOB_KIND_INITIAL,
                job_id=initial_job.job_id,
                tracking_document_sn=document.sn,
            )
        )

    running_job = get_running_auto_apply_job(
        current_project,
        document.document_type_id,
        tracking_document_sn=document.sn,
    )
    if running_job is not None:
        return _build_active_job_context(
            _serialize_job_status(
                request,
                current_project,
                document.document_type_id,
                GENERATION_JOB_KIND_AUTO_APPLY,
                job_id=running_job.job_id,
                tracking_document_sn=document.sn,
            )
        )
    return None


def _get_running_document_auto_apply_job(current_project, document):
    if current_project is None or document is None:
        return None
    return get_running_auto_apply_job(
        current_project,
        document.document_type_id,
        tracking_document_sn=document.sn,
    )


def _is_auto_apply_blocking_document_changes(current_project, document):
    return _get_running_document_auto_apply_job(current_project, document) is not None


def _build_job_badge(job_status_code, job_status_label):
    status_map = {
        PROGRESS_PENDING: "inline-flex whitespace-nowrap rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800",
        PROGRESS_PROCESSING: "inline-flex whitespace-nowrap rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-800",
        PROGRESS_FAILED: "inline-flex whitespace-nowrap rounded-full bg-rose-100 px-3 py-1 text-xs font-semibold text-rose-800",
        PROGRESS_COMPLETED: "inline-flex whitespace-nowrap rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800",
    }
    return {
        "status_label": job_status_label or "상태 정보",
        "status_badge_class": status_map.get(
            job_status_code,
            "inline-flex whitespace-nowrap rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700",
        ),
    }


def _decorate_history_document_row(document_row):
    badge = _build_job_badge("", "확정 완료")
    document_row["status_label"] = badge["status_label"]
    document_row["status_badge_class"] = badge["status_badge_class"]
    document_row["row_kind"] = "document"
    document_row["action_label"] = "미리보기"
    return document_row


def _build_history_job_row(document_code, job):
    document = getattr(job, "document", None)
    job_status_label = getattr(getattr(job, "job_status", None), "name", "") or job.job_status_id
    badge = _build_job_badge(job.job_status_id, job_status_label)
    detail_url = ""
    action_label = "상태 확인"
    download_url = ""
    if job.job_status_id in {PROGRESS_PENDING, PROGRESS_PROCESSING}:
        detail_url = _build_history_list_url(document_code, job_modal="waiting", job_sn=job.sn)
    elif job.job_status_id == PROGRESS_FAILED:
        if job.document_id:
            detail_url = f'{reverse("doc_detail", args=[job.document_id])}?{urlencode({"from": "history", "modal": "generation-failed", "job_sn": job.sn})}'
            action_label = "?ㅻ쪟 蹂닿린"
        else:
            detail_url = _build_history_list_url(document_code, job_modal="waiting", job_sn=job.sn)
    elif job.document_id:
        detail_url = f'{reverse("doc_detail", args=[job.document_id])}?{urlencode({"from": "history"})}'
        action_label = "誘몃━蹂닿린"
        download_url = f'{reverse("doc_content", args=[job.document_id])}?download=1'

    creator_name = getattr(getattr(document, "created_by", None), "name", "-") if document is not None else "-"
    version = getattr(document, "version", "") if document is not None else ""
    return {
        "sn": f"job-{job.sn}",
        "type_name": get_document_label(document_code),
        "creator_name": creator_name or "-",
        "version": version or "-",
        "modification_content": getattr(job, "error_message", "") or getattr(job, "request_id", "") or getattr(job, "job_id", ""),
        "created_at": getattr(job, "requested_at", None),
        "detail_url": detail_url,
        "download_url": download_url,
        "status_label": badge["status_label"],
        "status_badge_class": badge["status_badge_class"],
        "row_kind": "job",
        "action_label": action_label,
        "job_sn": job.sn,
        "job_id": job.job_id,
        "job_status_code": job.job_status_id,
    }


def _build_history_rows(current_project, document_code, documents):
    document_rows = [_decorate_history_document_row(row) for row in build_document_rows(documents)]
    if not document_code:
        return document_rows, None

    latest_job = get_latest_generation_job(current_project, document_code)
    if latest_job is None:
        return document_rows, None

    matching_document_row = next((row for row in document_rows if row.get("sn") == latest_job.document_id), None)
    should_prepend_job_row = latest_job.job_status_id != PROGRESS_COMPLETED or matching_document_row is None
    if should_prepend_job_row:
        document_rows.insert(0, _build_history_job_row(document_code, latest_job))
    return document_rows, latest_job


def _resolve_generation_job_modal(project, job_sn, *, allowed_statuses=None):
    if not job_sn:
        return None
    job = get_generation_job(project, job_sn=job_sn)
    if job is None:
        return None
    if allowed_statuses and job.job_status_id not in allowed_statuses:
        return None
    return job


def _can_show_auto_apply(document, actor, current_project, latest_detail):
    if current_project is None or actor is None or document is None or latest_detail is None:
        return False
    return (
        document.project_id == current_project.sn
        and document.possession_user_id == actor.sn
        and is_latest_document_for_type(document)
        and is_latest_detail_for_document(document, latest_detail)
    )


def _create_project_net_from_request(request, current_project, actor):
    form_data = _build_architecture_form_data(request)
    if current_project is None:
        messages.error(request, "?꾩옱 ?좏깮???꾨줈?앺듃媛 ?놁뒿?덈떎.")
        return False, form_data
    if not form_data["name"]:
        messages.error(request, "援ъ꽦?붿냼紐낆쓣 ?낅젰??二쇱꽭??")
        return False, form_data

    expected_concurrent_users = None
    if form_data["expected_concurrent_users"]:
        try:
            expected_concurrent_users = int(form_data["expected_concurrent_users"])
        except ValueError:
            messages.error(request, "?덉긽 ?숈떆 ?묒냽???섎뒗 ?レ옄濡??낅젰??二쇱꽭??")
            return False, form_data

    create_project_net(
        project=current_project,
        actor=actor,
        name=form_data["name"],
        purpose=form_data["purpose"],
        middleware_stack=form_data["middleware_stack"],
        firewall_settings=form_data["firewall_settings"],
        auth_method=form_data["auth_method"],
        expected_concurrent_users=expected_concurrent_users,
        cloud_yn=form_data["cloud_yn"],
        hardware_spec=form_data["hardware_spec"],
        remarks=form_data["remarks"],
    )
    messages.success(request, "소프트웨어 구성요소를 추가했습니다.")
    return True, _build_architecture_form_data()


@login_required(login_url="home")
def document_history_list(request):
    ensure_initial_reference_data()
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    raw_document_code = request.GET.get("docs_cd") or "all"
    document_code = None if raw_document_code in ("", "all") else resolve_document_code(raw_document_code)
    selected_document_code = document_code or "all"
    selected_document_label = get_document_label(document_code) if document_code else "전체 RA 문서"
    page_title = get_document_label(document_code) if document_code else "RA 문서 버전 이력"
    generation_state = get_generation_state(request.session, current_project)

    documents = get_document_history_queryset(current_project, document_code)

    documents_page, pagination_context = paginate(request, documents)
    document_rows, latest_job = _build_history_rows(current_project, document_code, documents_page.object_list)
    can_generate = can_access_initial_generation(current_project, actor, generation_state)
    active_job = None
    if document_code:
        active_job_kind, active_job = get_running_history_job(current_project, document_code)
        if active_job is not None:
            active_job = _build_active_job_context(
                _serialize_job_status(
                    request,
                    current_project,
                    document_code,
                    active_job_kind,
                    job_id=active_job.job_id,
                    tracking_document_sn=active_job.document_id,
                )
            )
    wait_modal_job = None
    if request.GET.get("job_modal") == "waiting":
        wait_modal_job = _resolve_generation_job_modal(
            current_project,
            request.GET.get("job_sn"),
            allowed_statuses={PROGRESS_PENDING, PROGRESS_PROCESSING},
        )
    context = {
        "active_menu": "doc_history",
        "title": page_title,
        "current_project": current_project,
        "documents": document_rows,
        **pagination_context,
        "has_documents": bool(document_rows),
        "selected_document_code": selected_document_code,
        "selected_document_label": selected_document_label,
        "document_type_choices": get_document_type_choices(include_all=True),
        "can_generate": can_generate,
        "generation_help_text": _build_history_help_text(can_generate),
        "active_job": active_job,
        "latest_job": latest_job,
        "open_generation_wait_modal": wait_modal_job is not None,
        "wait_modal_job": wait_modal_job,
    }
    return render(request, "docs/doc_history_list.html", context)


@login_required(login_url="home")
def document_generate(request):
    ensure_initial_reference_data()
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document_code = resolve_document_code(request.GET.get("docs_cd") or request.POST.get("docs_cd"))
    generation_state = get_generation_state(request.session, current_project)
    architecture_form = _build_architecture_form_data()
    open_arch_form = request.GET.get("arch_form") == "1"

    if not is_project_participant(current_project, actor):
        messages.error(request, "?꾩옱 ?꾨줈?앺듃???좊떦??援ъ꽦?먮쭔 ?곗텧臾??앹꽦??吏꾪뻾?????덉뒿?덈떎.")
        return redirect(f"{reverse('doc_history_list')}?docs_cd={document_code}")

    if request.method == "GET" and request.GET.get("apply_selection") == "1":
        state = get_generation_state(request.session, current_project)
        update_generation_selected_files(state, request.GET.getlist("selected_files"))
        save_generation_state(request.session, state)
        return redirect(_build_generation_redirect(document_code, resume=True))

    if request.method == "POST":
        state = get_generation_state(request.session, current_project)
        action = request.POST.get("action")
        current_code = get_current_generation_code(state, current_project, preferred_code=document_code)

        if action == "reset_generation":
            target_code = resolve_document_code(request.POST.get("docs_cd") or document_code or current_code)
            begin_generation_regeneration(request.session, current_project, target_code)
            messages.success(request, f"{get_document_label(target_code)} ?ъ깮?깆쓣 ?쒖옉?????덈룄濡??대떦 ?④퀎遺??吏꾪뻾 ?곹깭瑜?珥덇린?뷀뻽?듬땲??")
            return redirect(build_generation_redirect_url(document_code=target_code, resume=True))

        if action == "upload_itf_reference":
            if current_code != INTERFACE_REFERENCE_DOCUMENT_CODE:
                messages.error(request, "?꾩옱 ?④퀎?먯꽌???대?吏 李멸퀬?먮즺瑜??낅줈?쒗븷 ???놁뒿?덈떎.")
                return redirect(_build_generation_redirect(document_code, resume=True))

            uploaded_files = request.FILES.getlist("itf_references")
            if not uploaded_files:
                messages.error(request, "?낅줈?쒗븷 ?대?吏 ?뚯씪???좏깮??二쇱꽭??")
                return redirect(_build_generation_redirect(document_code, resume=True))

            added_count, errors = add_generation_itf_references(current_project, actor, state, uploaded_files)
            save_generation_state(request.session, state)
            for error in dict.fromkeys(errors):
                messages.error(request, error)
            if added_count:
                messages.success(request, f"李멸퀬 ?대?吏 {added_count}嫄댁쓣 ?낅줈?쒗뻽?듬땲??")
            return redirect(_build_generation_redirect(document_code, resume=True))

        if action == "remove_itf_reference":
            removed = remove_generation_itf_reference(state, request.POST.get("reference_token", ""))
            save_generation_state(request.session, state)
            if removed:
                messages.success(request, "李멸퀬 ?대?吏瑜??쒓굅?덉뒿?덈떎.")
            else:
                messages.error(request, "?쒓굅??李멸퀬 ?대?吏瑜?李얠? 紐삵뻽?듬땲??")
            return redirect(_build_generation_redirect(document_code, resume=True))

        if action == "delete_project_net":
            if current_code != ARCHITECTURE_DOCUMENT_CODE:
                messages.error(request, "?꾩옱 ?④퀎?먯꽌???꾪궎?띿쿂 援ъ꽦?붿냼瑜???젣?????놁뒿?덈떎.")
                return redirect(_build_generation_redirect(document_code, resume=True))
            if current_project is None:
                messages.error(request, "?꾩옱 ?좏깮???꾨줈?앺듃媛 ?놁뒿?덈떎.")
                return redirect(_build_generation_redirect(document_code, resume=True))
            project_net = get_object_or_404(current_project.nets.all(), sn=request.POST.get("project_net_sn"))
            project_net.delete()
            messages.success(request, "소프트웨어 구성요소를 삭제했습니다.")
            return redirect(_build_generation_redirect(document_code, resume=True))

        if action == "add_project_net":
            if current_code != ARCHITECTURE_DOCUMENT_CODE:
                messages.error(request, "?꾩옱 ?④퀎?먯꽌???꾪궎?띿쿂 援ъ꽦?붿냼瑜?異붽??????놁뒿?덈떎.")
                return redirect(_build_generation_redirect(document_code, resume=True))
            created, architecture_form = _create_project_net_from_request(request, current_project, actor)
            open_arch_form = not created
            if created:
                return redirect(_build_generation_redirect(document_code, resume=True))

        if action == "start_current":
            _debug_generation_log(
                "document_generate_start_current_enter",
                request_path=request.path,
                method=request.method,
                is_ajax=_is_ajax_request(request),
                project_sn=getattr(current_project, "sn", None),
                actor_sn=getattr(actor, "sn", None),
                requested_document_code=document_code,
                current_code=current_code,
                posted_selected_file_ids=request.POST.getlist("selected_files"),
                session_selected_file_ids=list(state.get("selected_file_ids", []) or []),
            )
            if current_code not in {INTERFACE_REFERENCE_DOCUMENT_CODE, ARCHITECTURE_DOCUMENT_CODE}:
                update_generation_selected_files(
                    state,
                    request.POST.getlist("selected_files") or state.get("selected_file_ids", []),
                )

            if not current_code:
                prerequisite_error = get_generation_prerequisite_error(current_project, state, document_code)
                message = prerequisite_error or "?좏뻾 ?곗텧臾쇱쓣 癒쇱? 以鍮꾪빐 二쇱꽭??"
                if _is_ajax_request(request):
                    return JsonResponse({"message": message}, status=400)
                messages.error(request, message)
                return redirect(_build_generation_redirect(document_code, resume=True))

            prerequisite_error = get_generation_prerequisite_error(current_project, state, current_code)
            if prerequisite_error:
                _debug_generation_log(
                    "document_generate_start_current_prerequisite_error",
                    current_code=current_code,
                    error=prerequisite_error,
                )
                if _is_ajax_request(request):
                    return JsonResponse({"message": prerequisite_error}, status=400)
                messages.error(request, prerequisite_error)
                if current_code not in {INTERFACE_REFERENCE_DOCUMENT_CODE, ARCHITECTURE_DOCUMENT_CODE}:
                    return redirect(_build_generation_redirect(document_code, resume=True, modal="files"))
                return redirect(_build_generation_redirect(document_code, resume=True, arch_form=current_code == ARCHITECTURE_DOCUMENT_CODE))

            job_result = start_initial_generation_job(current_project, actor, state, document_code=current_code)
            job_result_record = job_result.get("job")
            _debug_generation_log(
                "document_generate_start_current_job_result",
                current_code=current_code,
                job_status=job_result.get("status"),
                job_id=getattr(job_result_record, "job_id", None),
                document_sn=getattr(job_result.get("document"), "sn", None),
                message=job_result.get("message"),
            )
            save_generation_state(request.session, state)
            job_record = job_result.get("job")
            draft_document = job_result.get("document")
            if job_result["status"] == "error" or job_record is None:
                if _is_ajax_request(request):
                    return JsonResponse({"message": job_result["message"]}, status=502)
                messages.error(request, job_result["message"])
                return redirect(build_generation_redirect_url(document_code=document_code, resume=True))
            job_payload = _build_generation_job_response(
                GENERATION_JOB_KIND_INITIAL,
                current_code,
                job_result["message"],
                job_record,
                status=job_result["status"],
            )
            save_doc_job_snapshot(request.session, job_payload)
            if _is_ajax_request(request):
                return JsonResponse(job_payload)
            if job_result["status"] == "started":
                messages.success(request, f"{get_document_label(current_code)} ?앹꽦???붿껌?덉뒿?덈떎.")
            else:
                messages.info(request, job_result["message"])
            return redirect(_build_generation_redirect(current_code, play=True, resume=True))

        if action != "add_project_net":
            return redirect(_build_generation_redirect(document_code, resume=True))

    generation_context, redirect_response = _get_generation_context(
        request,
        current_project,
        actor,
        document_code,
        state=generation_state,
    )
    if redirect_response is not None:
        return redirect_response

    available_files = get_project_files(current_project, allowed_types=("FILE_RFP", "FILE_MEETING"))
    available_files, file_type, search_field, query = apply_file_filters(request.GET, available_files)
    current_step_code = generation_context["current_code"]
    selected_document_code = generation_context["requested_document_code"]
    selected_is_current_step = bool(current_step_code and selected_document_code == current_step_code)
    selected_step_guide = _build_generation_step_guide(selected_document_code)
    selected_progress_row = _find_generation_progress_row(generation_context["progress_rows"], selected_document_code)
    itf_references = get_generation_itf_references(generation_context["state"])
    architecture_networks = get_project_nets(current_project)
    active_generation_job = None
    can_start_current_generation = False
    can_reset_generation = bool(
        selected_progress_row
        and selected_progress_row.get("status") in {"confirmed", "review"}
    )
    start_button_label = f"{generation_context['current_label']} ?앹꽦" if generation_context["current_label"] else "?곗텧臾??앹꽦"

    if selected_is_current_step and current_step_code == INTERFACE_REFERENCE_DOCUMENT_CODE:
        can_start_current_generation = bool(itf_references and current_step_code and not generation_context["current_draft"])
        start_button_label = "?ъ슜???명꽣?섏씠???ㅺ퀎???앹꽦"
    elif selected_is_current_step and current_step_code == ARCHITECTURE_DOCUMENT_CODE:
        can_start_current_generation = bool(architecture_networks and current_step_code and not generation_context["current_draft"])
        start_button_label = "?꾪궎?띿쿂 ?ㅺ퀎???앹꽦"
    elif selected_is_current_step and current_step_code in FILE_INPUT_DOCUMENT_CODES:
        can_start_current_generation = bool(
            generation_context["selected_files"] and current_step_code and not generation_context["current_draft"]
        )
    elif selected_is_current_step and current_step_code in DERIVED_DOCUMENT_CODES:
        can_start_current_generation = bool(current_step_code and not generation_context["current_draft"])

    if current_step_code:
        running_job = get_running_initial_job(
            current_project,
            current_step_code,
            tracking_document_sn=getattr(generation_context["current_draft"], "sn", None),
        )
        tracking_document_sn = getattr(generation_context["current_draft"], "sn", None)
        active_generation_job = _build_active_job_context(
            _serialize_job_status(
                request,
                current_project,
                current_step_code,
                GENERATION_JOB_KIND_INITIAL,
                job_id=getattr(running_job, "job_id", None),
                tracking_document_sn=tracking_document_sn,
            )
        )

    context = {
        "active_menu": "doc_history",
        "title": "?곗텧臾??앹꽦",
        "current_project": current_project,
        "selected_document_code": selected_document_code,
        "selected_document_label": get_document_label(selected_document_code),
        "selected_step_guide": selected_step_guide,
        "selected_progress_row": selected_progress_row,
        "selected_is_current_step": selected_is_current_step,
        "documents": build_project_file_rows(available_files),
        "file_type": file_type,
        "search_field": search_field,
        "query": query,
        "file_type_choices": get_file_type_choices(),
        "search_field_choices": SEARCH_FIELD_CHOICES,
        "selected_file_ids": generation_context["state"].get("selected_file_ids", []),
        "selected_files": generation_context["selected_files"],
        "current_document_code": generation_context["current_code"],
        "current_document_label": generation_context["current_label"],
        "current_step_code": current_step_code,
        "current_draft": generation_context["current_draft"],
        "progress_rows": generation_context["progress_rows"],
        "open_file_modal": request.GET.get("modal") == "files",
        "current_check_url": reverse("doc_detail", args=[generation_context["current_draft"].sn]) if generation_context["current_draft"] else "",
        "is_complete": generation_context["is_complete"],
        "completed_documents": [document for document in generation_context["completed_documents"] if document is not None],
        "has_selected_files": bool(generation_context["selected_files"]),
        "itf_references": itf_references,
        "architecture_networks": architecture_networks,
        "architecture_form": architecture_form,
        "open_arch_form": open_arch_form,
        "show_file_selector": selected_is_current_step and current_step_code in FILE_INPUT_DOCUMENT_CODES,
        "show_itf_upload": selected_is_current_step and current_step_code == INTERFACE_REFERENCE_DOCUMENT_CODE,
        "show_architecture_inputs": selected_is_current_step and current_step_code == ARCHITECTURE_DOCUMENT_CODE,
        "can_start_current_generation": can_start_current_generation,
        "can_reset_generation": can_reset_generation,
        "start_button_label": start_button_label,
        "has_active_generation_session": has_active_generation_session(generation_context["state"]),
        "active_job": active_generation_job,
    }
    return render(request, "docs/doc_generate.html", context)


@login_required(login_url="home")
def document_job_status(request):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    if current_project is None or not is_project_participant(current_project, actor):
        return JsonResponse({"message": "?꾩옱 ?꾨줈?앺듃???묎렐?????놁뒿?덈떎."}, status=404)

    document_code = resolve_document_code(request.GET.get("docs_cd"))
    job_kind = (request.GET.get("job_kind") or "").strip()
    job_id = (request.GET.get("job_id") or "").strip() or None
    tracking_document_sn = request.GET.get("tracking_document_sn") or None
    if job_kind not in {GENERATION_JOB_KIND_INITIAL, GENERATION_JOB_KIND_AUTO_APPLY}:
        return JsonResponse({"message": "吏?먰븯吏 ?딅뒗 ?묒뾽 ?좏삎?낅땲??"}, status=400)

    payload = _serialize_job_status(
        request,
        current_project,
        document_code,
        job_kind,
        job_id=job_id,
        tracking_document_sn=tracking_document_sn,
    )
    if payload.get("status") == "idle":
        snapshot = find_doc_job_snapshot(
            request.session,
            job_kind,
            document_code,
            job_id=job_id,
            tracking_document_sn=tracking_document_sn,
        )
        if snapshot is not None:
            return JsonResponse(snapshot)
    if payload.get("status") in {"completed", "failed", "idle"}:
        clear_doc_job_snapshot(
            request.session,
            job_id=payload.get("job_id") or job_id,
            job_kind=job_kind,
            document_code=document_code,
            tracking_document_sn=tracking_document_sn,
        )
    return JsonResponse(payload)


@login_required(login_url="home")
def document_detail(request, document_sn):
    ensure_initial_reference_data()
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)

    preferred_mode = "edit" if request.GET.get("mode") == "edit" else "view"
    state, pending_approval = get_document_view_state(document, actor, preferred_mode=preferred_mode)
    latest_detail = get_latest_detail(document)
    try:
        latest_text = extract_text_from_docx(get_document_detail_bytes(latest_detail))
    except ValueError:
        messages.error(request, _legacy_detail_error_message())
        return redirect(f"{reverse('doc_history_list')}?docs_cd={document.document_type_id}")

    preview_detail_sn = request.GET.get("preview_detail")
    preview_detail = get_detail_by_sn(document, preview_detail_sn) if preview_detail_sn else None
    is_history_view = request.GET.get("from") == "history" and not is_working_document(document)
    if preview_detail:
        try:
            preview_text = extract_text_from_docx(get_document_detail_bytes(preview_detail))
        except ValueError:
            messages.error(request, _legacy_detail_error_message())
            return redirect(reverse("doc_detail", args=[document.sn]))
    else:
        preview_text = latest_text

    meeting_files = get_project_files(current_project, allowed_types=("FILE_MEETING",))
    meeting_filter_params = _collect_prefixed_filters(request, "meeting_")
    meeting_files, meeting_file_type, meeting_search_field, meeting_query = apply_file_filters(
        meeting_filter_params,
        meeting_files,
        default_file_type="all",
        allowed_file_types=("FILE_MEETING",),
    )

    if state == "edit":
        revisions = (
            document.details.filter(is_deleted="N")
            .select_related("created_by")
            .order_by("-created_at", "-sn")
        )
        revision_rows = [
            {
                "sn": detail.sn,
                "title": f"?곸꽭 ?대젰 #{detail.sn}",
                "subtitle": "?꾩옱 臾몄꽌??????대젰",
                "created_at": detail.created_at,
                "creator_name": getattr(detail.created_by, "name", "-") or "-",
                "preview_url": build_history_preview_api_url(document, detail.sn),
                "restore_url": reverse("doc_restore_revision", args=[document.sn, detail.sn]),
                "can_restore": True,
            }
            for detail in revisions
        ]
        history_scope_label = "?꾩옱 ?섏젙 以묒씤 臾몄꽌??????대젰???뺤씤?섍퀬 ?먰븯???곸꽭 踰꾩쟾?쇰줈 蹂듭썝?????덉뒿?덈떎."
    else:
        document_revisions = (
            Document.objects.filter(
                project=current_project,
                document_type_id=document.document_type_id,
            )
            .exclude(version="0.0")
            .select_related("created_by")
            .order_by("-created_at", "-sn")
        )
        revision_rows = []
        for revision_document in document_revisions:
            revision_detail = (
                revision_document.details.filter(is_deleted="N")
                .order_by("created_at", "sn")
                .first()
            )
            revision_rows.append(
                {
                    "sn": revision_document.sn,
                    "title": f"臾몄꽌 #{revision_document.sn}",
                    "subtitle": f"踰꾩쟾 {revision_document.version or '-'}",
                    "created_at": revision_document.created_at,
                    "creator_name": getattr(revision_document.created_by, "name", "-") or "-",
                    "preview_url": (
                        build_history_preview_api_url(revision_document, revision_detail.sn)
                        if revision_detail is not None
                        else ""
                    ),
                    "restore_url": "",
                    "can_restore": False,
                    "detail_url": reverse("doc_detail", args=[revision_document.sn]),
                    "is_current": revision_document.sn == document.sn,
                }
            )
        history_scope_label = "媛숈? ?곗텧臾?醫낅쪟??臾몄꽌 踰꾩쟾 ?대젰???뺤씤?????덉뒿?덈떎."
    can_view_revision_history = True

    generation_state = get_generation_state(request.session, current_project)
    current_generation_code = get_current_generation_code(generation_state, current_project, preferred_code=document.document_type_id)
    is_generation_draft = (
        is_working_document(document)
        and generation_state.get("draft_documents", {}).get(document.document_type_id) == document.sn
    )
    generation_return_url = (
        build_generation_redirect_url(document_code=current_generation_code, resume=True)
        if generation_state.get("selected_file_ids")
        else ""
    )
    active_job = _get_document_active_job(request, current_project, document)
    document_change_blocked_by_job = _is_auto_apply_blocking_document_changes(current_project, document)
    failed_generation_job = None
    if request.GET.get("modal") == "generation-failed":
        failed_generation_job = _resolve_generation_job_modal(
            current_project,
            request.GET.get("job_sn"),
            allowed_statuses={PROGRESS_FAILED},
        )
        if failed_generation_job is not None and failed_generation_job.document_id != document.sn:
            failed_generation_job = None
    latest_confirmed = latest_confirmed_document(current_project, document.document_type_id)
    is_latest_confirmed = latest_confirmed is not None and latest_confirmed.sn == document.sn
    can_lock_for_edit = (
        (not document_change_blocked_by_job)
        and (not is_history_view)
        and state == "view"
        and pending_approval is None
        and (is_working_document(document) or is_latest_confirmed)
    )
    can_cancel_approval = pending_approval is not None and pending_approval.created_by_id == actor.sn
    can_auto_apply = (
        (not document_change_blocked_by_job)
        and (not is_history_view)
        and _can_show_auto_apply(document, actor, current_project, latest_detail)
    )
    can_request_document_approval = (
        (not document_change_blocked_by_job)
        and state == "edit"
        and document.possession_user_id == actor.sn
        and can_request_approval(document, actor, pending_approval=pending_approval)
    )

    context = {
        "active_menu": "doc_history",
        "title": get_document_label(document.document_type_id),
        "current_project": current_project,
        "document": document,
        "document_state": state,
        "pending_approval": pending_approval,
        "latest_detail": latest_detail,
        "latest_text": latest_text,
        "preview_detail": preview_detail,
        "preview_text": preview_text,
        "revision_rows": revision_rows,
        "history_scope_label": history_scope_label,
        "can_view_revision_history": can_view_revision_history,
        "can_confirm": (not is_history_view)
        and state == "view"
        and pending_approval is None
        and is_generation_draft
        and (is_project_manager(current_project, actor) or document.created_by_id == actor.sn),
        "can_edit": can_lock_for_edit,
        "can_cancel_approval": can_cancel_approval,
        "can_request_approval": can_request_document_approval,
        "can_auto_apply": can_auto_apply,
        "locked_by_name": getattr(document.possession_user, "name", ""),
        "meeting_documents": build_project_file_rows(meeting_files),
        "meeting_file_type": meeting_file_type,
        "meeting_search_field": meeting_search_field,
        "meeting_query": meeting_query,
        "meeting_file_type_choices": get_file_type_choices(allowed_codes=("FILE_MEETING",)),
        "search_field_choices": SEARCH_FIELD_CHOICES,
        "open_history_modal": preview_detail is not None or request.GET.get("modal") == "history",
        "open_meeting_modal": request.GET.get("modal") == "meeting-files",
        "open_approval_request_modal": request.GET.get("modal") == "approval-request",
        "approval_request_max_length": APPROVAL_REQUEST_MAX_LENGTH,
        "open_generation_failed_modal": failed_generation_job is not None,
        "failed_generation_job": failed_generation_job,
        "onlyoffice_enabled": bool(settings.ONLYOFFICE_DOCUMENT_SERVER_URL),
        "onlyoffice_document_server_url": get_onlyoffice_document_server_url(request, browser=True),
        "download_url": f"{reverse('doc_content', args=[document.sn])}?download=1",
        "editor_config_url": reverse("doc_editor_config", args=[document.sn]),
        "selected_document_code": document.document_type_id,
        "is_generation_draft": is_generation_draft,
        "generation_return_url": generation_return_url,
        "active_job": active_job,
        "document_change_blocked_by_job": document_change_blocked_by_job,
    }
    return render(request, "docs/doc_detail.html", context)


@login_required(login_url="home")
def document_lock(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    if request.method != "POST":
        return redirect(reverse("doc_detail", args=[document.sn]))

    pending_approval = get_latest_pending_approval(document)
    if pending_approval is not None:
        messages.error(request, "?뱀씤 ?붿껌 泥섎━ 以묒씤 ?곗텧臾쇱? ?섏젙?????놁뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))

    if acquire_document_lock(document, actor):
        messages.success(request, "臾몄꽌 ?섏젙 沅뚰븳???뺣낫?덉뒿?덈떎.")
    else:
        messages.error(request, "?ㅻⅨ ?ъ슜?먭? ?섏젙以묒엯?덈떎.")
    return redirect(build_document_detail_url(document, mode="edit"))


@login_required(login_url="home")
def document_save(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    is_ajax = _is_ajax_request(request)
    if request.method != "POST":
        if is_ajax:
            return JsonResponse({"message": "?섎せ???붿껌?낅땲??"}, status=405)
        return redirect(reverse("doc_detail", args=[document.sn]))
    if document.possession_user_id != actor.sn:
        if is_ajax:
            return JsonResponse({"message": "臾몄꽌瑜??먯쑀???ъ슜?먮쭔 ??ν븷 ???덉뒿?덈떎."}, status=403)
        messages.error(request, "臾몄꽌瑜??먯쑀???ъ슜?먮쭔 ??ν븷 ???덉뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))
    if _is_auto_apply_blocking_document_changes(current_project, document):
        message = "?뚯쓽 ?댁슜 ?먮룞 ?곸슜???꾨즺?????ㅼ떆 ?쒕룄??二쇱꽭??"
        if is_ajax:
            return JsonResponse({"message": message}, status=409)
        messages.error(request, message)
        return redirect(build_document_detail_url(document, mode="edit"))

    latest_detail = get_latest_detail(document)
    text_content = request.POST.get("content_text", "").strip()
    saved_detail = latest_detail
    if not text_content and latest_detail is not None:
        try:
            get_document_detail_bytes(latest_detail)
        except ValueError:
            message = _legacy_detail_error_message()
            if is_ajax:
                return JsonResponse({"message": message}, status=409)
            messages.error(request, message)
            return redirect(build_document_detail_url(document, mode="edit"))
    if text_content:
        saved_detail = save_revision(document, actor, text_content=text_content, modification_content="수정 저장")
    elif settings.ONLYOFFICE_DOCUMENT_SERVER_URL:
        baseline_value = request.POST.get("baseline_detail_sn", "").strip()
        baseline_detail_sn = getattr(latest_detail, "sn", None)
        if baseline_value:
            try:
                baseline_detail_sn = int(baseline_value)
            except ValueError:
                baseline_detail_sn = getattr(latest_detail, "sn", None)
        baseline_detail = get_detail_by_sn(document, baseline_detail_sn) or latest_detail
        try:
            force_save_result = request_force_save(
                document,
                latest_detail=baseline_detail,
                userdata=f"doc-save-{document.sn}-{actor.sn}",
                request=request,
            )
        except Exception:
            message = "OnlyOffice ????붿껌???꾩넚?섏? 紐삵뻽?듬땲?? ?섍꼍 ?ㅼ젙???뺤씤??二쇱꽭??"
            if is_ajax:
                return JsonResponse({"message": message}, status=502)
            messages.error(request, message)
            return redirect(build_document_detail_url(document, mode="edit"))

        force_save_error = force_save_result.get("error")
        if force_save_error == 0:
            saved_detail = wait_for_new_revision(document, baseline_detail_sn=baseline_detail_sn)
            if saved_detail is None or getattr(saved_detail, "sn", None) == baseline_detail_sn:
                message = "OnlyOffice ???寃곌낵瑜??꾩쭅 諛쏆? 紐삵뻽?듬땲?? ?좎떆 ???ㅼ떆 ?쒕룄??二쇱꽭??"
                if is_ajax:
                    return JsonResponse({"message": message}, status=409)
                messages.error(request, message)
                return redirect(build_document_detail_url(document, mode="edit"))
        elif force_save_error == 4:
            saved_detail = latest_detail
        else:
            error_messages = {
                1: "?꾩옱 ?몄쭛 以묒씤 臾몄꽌瑜?李얠? 紐삵뻽?듬땲??",
                2: "OnlyOffice callback URL ?ㅼ젙???щ컮瑜댁? ?딆뒿?덈떎.",
                3: "OnlyOffice ?대? ?ㅻ쪟濡???ν븯吏 紐삵뻽?듬땲??",
                5: "OnlyOffice ???紐낅졊 ?뺤떇???щ컮瑜댁? ?딆뒿?덈떎.",
                6: "OnlyOffice ?좏겙 寃利앹뿉 ?ㅽ뙣?덉뒿?덈떎.",
            }
            message = error_messages.get(force_save_error, "OnlyOffice ????붿껌 泥섎━???ㅽ뙣?덉뒿?덈떎.")
            if is_ajax:
                return JsonResponse({"message": message}, status=502)
            messages.error(request, message)
            return redirect(build_document_detail_url(document, mode="edit"))
    detail_url = build_document_detail_url(document, mode="edit")
    if is_ajax:
        return JsonResponse(
            {
                "message": "臾몄꽌 ?섏젙 ?댁슜????ν뻽?듬땲??",
                "redirect_url": detail_url,
                "latest_detail_sn": getattr(saved_detail, "sn", None),
            }
        )
    messages.success(request, "臾몄꽌 ?섏젙 ?댁슜????ν뻽?듬땲??")
    return redirect(detail_url)


@login_required(login_url="home")
def document_cancel_edit(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    if request.method == "POST" and document.possession_user_id == actor.sn:
        release_document_lock(document, actor)
        messages.info(request, "臾몄꽌 ?몄쭛??醫낅즺?덉뒿?덈떎.")
    return redirect(reverse("doc_detail", args=[document.sn]))


@login_required(login_url="home")
def document_confirm(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    if request.method != "POST":
        return redirect(reverse("doc_detail", args=[document.sn]))
    if not (is_project_manager(current_project, actor) or document.created_by_id == actor.sn):
        messages.error(request, "臾몄꽌瑜??뺤젙??沅뚰븳???놁뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))

    try:
        saved_document, _ = confirm_document(document, actor)
    except ValueError:
        messages.error(request, _legacy_detail_error_message())
        return redirect(reverse("doc_detail", args=[document.sn]))
    generation_state = get_generation_state(request.session, current_project)
    if generation_state.get("draft_documents", {}).get(document.document_type_id) == document.sn:
        mark_generation_confirmed(generation_state, document, saved_document)
        save_generation_state(request.session, generation_state)
        if is_generation_complete(generation_state):
            messages.success(request, "紐⑤뱺 ?곗텧臾?珥덉븞????ν뻽?듬땲?? ?꾩슂???곗텧臾쇱? ?뱀씤?붿껌??吏꾪뻾??二쇱꽭??")
            return redirect(build_generation_redirect_url(document_code=saved_document.document_type_id, resume=True))

        messages.success(request, f"{get_document_label(document.document_type_id)} ??μ쓣 ?꾨즺?덉뒿?덈떎.")
        return redirect(_build_generation_redirect(None, auto_start=True, resume=True))

    messages.success(request, "?곗텧臾쇱쓣 ??ν뻽?듬땲??")
    return redirect(reverse("doc_detail", args=[saved_document.sn]))


@login_required(login_url="home")
def document_restore_revision(request, document_sn, detail_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    if request.method != "POST":
        return redirect(reverse("doc_detail", args=[document.sn]))
    if document.possession_user_id != actor.sn:
        messages.error(request, "臾몄꽌瑜??먯쑀???ъ슜?먮쭔 蹂듭썝?????덉뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))

    source_detail = get_detail_by_sn(document, detail_sn)
    if source_detail is None:
        messages.error(request, "蹂듭썝???대젰??李얠쓣 ???놁뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))

    try:
        restore_revision(document, actor, source_detail)
    except ValueError:
        messages.error(request, _legacy_detail_error_message())
        return redirect(reverse("doc_detail", args=[document.sn]))
    messages.success(request, "?좏깮??踰꾩쟾?쇰줈 蹂듭썝?덉뒿?덈떎.")
    return redirect(reverse("doc_detail", args=[document.sn]))


@login_required(login_url="home")
def document_auto_apply(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    latest_detail = get_latest_detail(document)
    if request.method != "POST":
        return redirect(reverse("doc_detail", args=[document.sn]))
    if document.possession_user_id != actor.sn:
        if _is_ajax_request(request):
            return JsonResponse({"message": "臾몄꽌瑜??먯쑀???ъ슜?먮쭔 ?뚯쓽 ?댁슜??諛섏쁺?????덉뒿?덈떎."}, status=403)
        messages.error(request, "臾몄꽌瑜??먯쑀???ъ슜?먮쭔 ?뚯쓽 ?댁슜??諛섏쁺?????덉뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))
    if not _can_show_auto_apply(document, actor, current_project, latest_detail):
        if _is_ajax_request(request):
            return JsonResponse({"message": "理쒖떊 ?곗텧臾쇱쓽 理쒖떊 ?댁슜?먯꽌留??뚯쓽 ?댁슜???먮룞 ?곸슜?????덉뒿?덈떎."}, status=403)
        messages.error(request, "理쒖떊 ?곗텧臾쇱쓽 理쒖떊 ?댁슜?먯꽌留??뚯쓽 ?댁슜???먮룞 ?곸슜?????덉뒿?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))

    selected_file_ids = request.POST.getlist("selected_files")
    selected_files = list(
        get_project_files(current_project, file_ids=selected_file_ids, allowed_types=("FILE_MEETING",))
    )
    if not selected_files:
        if _is_ajax_request(request):
            return JsonResponse({"message": "?뚯쓽濡??뚯씪???섎굹 ?댁긽 ?좏깮??二쇱꽭??"}, status=400)
        messages.error(request, "?뚯쓽濡??뚯씪???섎굹 ?댁긽 ?좏깮??二쇱꽭??")
        return redirect(_document_detail_redirect(document, modal="meeting-files"))

    job_result = start_auto_apply_job(current_project, document.document_type_id, selected_files)
    if job_result["status"] == "error" or job_result.get("job") is None:
        if _is_ajax_request(request):
            return JsonResponse({"message": job_result["message"]}, status=502)
        messages.error(request, job_result["message"])
        return redirect(_document_detail_redirect(document, modal="meeting-files"))
    job_payload = _build_generation_job_response(
        GENERATION_JOB_KIND_AUTO_APPLY,
        document.document_type_id,
        job_result["message"],
        job_result["job"],
        status=job_result["status"],
    )
    save_doc_job_snapshot(request.session, job_payload)

    if _is_ajax_request(request):
        return JsonResponse(job_payload)

    if job_result["status"] == "started":
        messages.success(request, "?뚯쓽 ?댁슜 ?먮룞 ?곸슜???붿껌?덉뒿?덈떎.")
    else:
        messages.info(request, job_result["message"])
    return redirect(reverse("doc_detail", args=[document.sn]))


@login_required(login_url="home")
def document_request_approval(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)
    if request.method != "POST":
        return redirect(reverse("doc_detail", args=[document.sn]))
    _, pending_approval = get_document_view_state(document, actor, preferred_mode="view")

    if document.possession_user_id and document.possession_user_id != actor.sn:
        messages.error(request, "?ㅻⅨ ?ъ슜?먭? ?섏젙以묒엯?덈떎. ?뱀씤?붿껌? ?섏젙 ????ν븳 ??媛?ν빀?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))
    if document.possession_user_id != actor.sn:
        messages.error(request, "?뱀씤?붿껌? ?섏젙紐⑤뱶?먯꽌留?媛?ν빀?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))
    if _is_auto_apply_blocking_document_changes(current_project, document):
        messages.error(request, "?뚯쓽 ?댁슜 ?먮룞 ?곸슜???꾨즺?????뱀씤?붿껌??吏꾪뻾??二쇱꽭??")
        return redirect(build_document_detail_url(document, mode="edit"))

    if not can_request_approval(
        document,
        actor,
        pending_approval=pending_approval,
    ):
        if pending_approval is not None:
            messages.error(request, "?대? ?뱀씤 ?붿껌???곗텧臾쇱엯?덈떎.")
        else:
            messages.error(request, "?뱀씤?붿껌? ?섏젙 ????ν븳 ??媛?ν빀?덈떎.")
        return redirect(reverse("doc_detail", args=[document.sn]))

    request_content = request.POST.get("request_content", "").strip()
    if not request_content:
        messages.error(request, "?뱀씤 ?붿껌 ?댁슜???낅젰??二쇱꽭??")
        return redirect(_document_detail_redirect(document, modal="approval-request"))
    if len(request_content) > APPROVAL_REQUEST_MAX_LENGTH:
        messages.error(
            request,
            f"?뱀씤 ?붿껌 ?댁슜? {APPROVAL_REQUEST_MAX_LENGTH}???댄븯濡??낅젰??二쇱꽭??",
        )
        return redirect(_document_detail_redirect(document, modal="approval-request"))

    approval = create_approval_request(document, actor, request_content)
    try:
        request_fastapi_approval_review(approval.approval_sn)
    except Exception:
        messages.warning(
            request,
            "?뱀씤 ?붿껌? ?깅줉?덉?留??먮룞 寃???붿껌???꾩넚?섏? 紐삵뻽?듬땲?? 愿由ъ옄?먭쾶 臾몄쓽??二쇱꽭??",
        )
    else:
        messages.success(request, "?꾨줈?앺듃 愿由ъ옄?먭쾶 ?뱀씤 ?붿껌???꾩넚?덉뒿?덈떎.")
    return redirect(reverse("doc_detail", args=[document.sn]))


@login_required(login_url="home")
def document_history_preview(request, document_sn, detail_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)

    detail = get_detail_by_sn(document, detail_sn)
    if detail is None:
        return JsonResponse({"message": "Preview revision was not found."}, status=404)
    if settings.ONLYOFFICE_DOCUMENT_SERVER_URL:
        return JsonResponse(
            {
                "editor_config": build_editor_config(request, document, actor, "view", detail=detail),
                "creator_name": getattr(detail.created_by, "name", "-") or "-",
                "created_at": detail.created_at.strftime("%Y-%m-%d %H:%M"),
            }
        )

    try:
        preview_text = extract_text_from_docx(get_document_detail_bytes(detail)) or "Document content is empty."
    except ValueError:
        return JsonResponse({"message": _legacy_detail_error_message()}, status=409)

    return JsonResponse(
        {
            "preview_text": preview_text,
            "creator_name": getattr(detail.created_by, "name", "-") or "-",
            "created_at": detail.created_at.strftime("%Y-%m-%d %H:%M"),
        }
    )


def document_content(request, document_sn):
    token = request.GET.get("token", "").strip()
    document = _get_document_by_sn_or_404(document_sn)
    detail_sn = request.GET.get("detail_sn")
    detail = get_detail_by_sn(document, detail_sn) if detail_sn else None
    if not validate_document_content_token(document, token, detail_sn=detail_sn):
        current_project, _ = resolve_current_project(request)
        actor = get_actor(request)
        _ensure_document_access(current_project, actor, document)
    if detail_sn and detail is None:
        raise Http404

    latest_detail = detail or get_latest_detail(document)
    try:
        content = get_document_detail_bytes(latest_detail)
    except ValueError:
        return HttpResponse(_legacy_detail_error_message(), status=409, content_type="text/plain; charset=utf-8")
    response = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    disposition = "attachment" if request.GET.get("download") == "1" else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{get_document_title(document)}"'
    return response


@login_required(login_url="home")
def document_editor_config(request, document_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    document = _get_document_or_404(current_project, document_sn)
    _ensure_document_access(current_project, actor, document)

    state, _ = get_document_view_state(document, actor, preferred_mode=request.GET.get("mode"))
    mode = "edit" if state == "edit" else "view"
    return JsonResponse(build_editor_config(request, document, actor, mode))


@csrf_exempt
def document_callback(request, document_sn):
    document = _get_document_by_sn_or_404(document_sn)
    if request.method != "POST":
        return JsonResponse({"error": 0})

    payload = parse_callback_payload(request)
    status = payload.get("status")
    if status in {2, 6}:
        baseline_detail = None
        baseline_detail_sn = request.GET.get("baseline_detail_sn")
        if baseline_detail_sn:
            baseline_detail = get_detail_by_sn(document, baseline_detail_sn)
        if baseline_detail is None:
            baseline_detail = get_latest_detail(document)

        content_bytes = None
        if payload.get("url"):
            try:
                content_bytes = download_remote_content(payload["url"])
            except Exception:
                content_bytes = None
        if content_bytes:
            baseline_bytes = get_document_detail_bytes(baseline_detail) if baseline_detail is not None else b""
            if not baseline_bytes or not is_same_docx_revision(content_bytes, baseline_bytes):
                save_revision(
                    document,
                    document.updated_by or document.created_by,
                    content_bytes=content_bytes,
                    modification_content="OnlyOffice 저장",
                )
    return JsonResponse({"error": 0})


@login_required(login_url="home")
def document_cancel_approval(request, approval_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    approval = get_object_or_404(
        DocumentApproval.objects.select_related("detail__document__project", "created_by", "approval_status"),
        approval_sn=approval_sn,
    )
    document = approval.detail.document
    _ensure_document_access(current_project, actor, document)
    if request.method == "POST" and approval.created_by_id == actor.sn and approval.approval_status_id == "APRV_REQ":
        cancel_approval_request(approval)
        messages.success(request, "?뱀씤 ?붿껌??痍⑥냼?덉뒿?덈떎.")
    return redirect(reverse("doc_detail", args=[document.sn]))


@login_required(login_url="home")
def approval_list(request):
    ensure_initial_reference_data()
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)

    approvals = DocumentApproval.objects.none()
    document_code = "all"
    approval_status = "all"
    requester_query = ""
    include_requester = current_project is not None and is_project_manager(current_project, actor)

    if current_project is not None and is_project_participant(current_project, actor):
        approvals = build_approval_queryset(current_project, actor)
        approvals, document_code, approval_status, requester_query = apply_approval_filters(
            request.GET,
            approvals,
            include_requester=include_requester,
        )

    approvals_page, pagination_context = paginate(request, approvals)

    context = {
        "active_menu": "approvals",
        "title": "?곗텧臾??뱀씤?붿껌",
        "current_project": current_project,
        "documents": build_approval_rows(approvals_page.object_list),
        **pagination_context,
        "document_type_choices": get_document_type_choices(include_all=True),
        "approval_status_choices": get_approval_status_choices(include_all=True),
        "selected_document_code": document_code,
        "selected_status": approval_status,
        "requester_query": requester_query,
        "include_requester_search": include_requester,
        "is_manager": include_requester,
    }
    return render(request, "docs/approval_list.html", context)


@login_required(login_url="home")
def approval_detail(request, approval_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    approval = get_object_or_404(
        DocumentApproval.objects.select_related(
            "detail__document__project",
            "detail__document__document_type",
            "detail__document__created_by",
            "detail__document__possession_user",
            "approval_status",
            "created_by",
        ),
        approval_sn=approval_sn,
    )
    document = approval.detail.document
    _ensure_document_access(current_project, actor, document)

    is_manager = is_project_manager(current_project, actor)
    if not is_manager and approval.created_by_id != actor.sn:
        raise Http404

    review_job = get_latest_approval_review_job(approval)
    review_status = (getattr(review_job, "status_code", "") or "").upper()
    review_succeeded = review_status == "SUCCEEDED"
    review_failed = review_status in {"FAILED", "ERROR", "CANCELLED"}
    context = {
        "active_menu": "approvals",
        "title": "?곗텧臾??뱀씤 ?곸꽭",
        "current_project": current_project,
        "approval": approval,
        "document": document,
        "is_manager": is_manager,
        "review_job": review_job,
        "before_data_view": build_approval_data_view(review_job.before_data) if review_succeeded else None,
        "after_data_view": build_approval_data_view(review_job.after_data) if review_succeeded else None,
        "review_view": (
            build_approval_review_view(
                review_job.result,
                before_data=review_job.before_data,
                after_data=review_job.after_data,
            )
            if review_succeeded
            else None
        ),
        "review_status": review_status,
        "review_succeeded": review_succeeded,
        "review_failed": review_failed,
        "review_poll_interval_ms": get_doc_job_poll_interval_seconds() * 1000,
        "requester_name": getattr(approval.created_by, "name", "-") or "-",
        "can_take_action": is_manager and approval.approval_status_id == "APRV_REQ" and review_succeeded,
        "open_approve_modal": request.GET.get("modal") == "approve",
        "open_reject_modal": request.GET.get("modal") == "reject",
    }
    return render(request, "docs/approval_detail.html", context)


@login_required(login_url="home")
def approval_approve(request, approval_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    approval = get_object_or_404(
        DocumentApproval.objects.select_related("detail__document__project"),
        approval_sn=approval_sn,
    )
    document = approval.detail.document
    _ensure_document_access(current_project, actor, document)
    if request.method != "POST" or not is_project_manager(current_project, actor):
        return redirect(reverse("doc_approval_detail", args=[approval.approval_sn]))
    if approval.approval_status_id != "APRV_REQ":
        messages.error(request, "泥섎━?????녿뒗 ?뱀씤 ?붿껌 ?곹깭?낅땲??")
        return redirect(reverse("doc_approval_detail", args=[approval.approval_sn]))

    new_version = request.POST.get("new_version", "").strip()
    if not new_version:
        messages.error(request, "??踰꾩쟾紐낆쓣 ?낅젰??二쇱꽭??")
        return redirect(_approval_detail_redirect(approval, modal="approve"))
    if has_document_version(document.project, document.document_type_id, new_version):
        messages.error(request, "?숈씪???곗텧臾?醫낅쪟??媛숈? 踰꾩쟾???대? 議댁옱?⑸땲?? ??踰꾩쟾紐낆쓣 ?ㅼ떆 ?낅젰??二쇱꽭??")
        return redirect(_approval_detail_redirect(approval, modal="approve"))

    modification_content = request.POST.get("modification_content", "").strip()

    try:
        approved_document, _ = approve_request(approval, actor, new_version, modification_content=modification_content)
    except ValueError:
        messages.error(request, _legacy_detail_error_message())
        return redirect(reverse("doc_approval_detail", args=[approval.approval_sn]))
    messages.success(request, "?뱀씤 ?붿껌??諛섏쁺?섍퀬 ??踰꾩쟾???앹꽦?덉뒿?덈떎.")
    return redirect(reverse("doc_detail", args=[approved_document.sn]))


@login_required(login_url="home")
def approval_reject(request, approval_sn):
    current_project, _ = resolve_current_project(request)
    actor = get_actor(request)
    approval = get_object_or_404(
        DocumentApproval.objects.select_related("detail__document__project"),
        approval_sn=approval_sn,
    )
    document = approval.detail.document
    _ensure_document_access(current_project, actor, document)
    if request.method != "POST" or not is_project_manager(current_project, actor):
        return redirect(reverse("doc_approval_detail", args=[approval.approval_sn]))
    if approval.approval_status_id != "APRV_REQ":
        messages.error(request, "泥섎━?????녿뒗 ?뱀씤 ?붿껌 ?곹깭?낅땲??")
        return redirect(reverse("doc_approval_detail", args=[approval.approval_sn]))

    reason = request.POST.get("rejection_reason", "").strip()
    if not reason:
        messages.error(request, "諛섎젮 ?ъ쑀瑜??낅젰??二쇱꽭??")
        return redirect(_approval_detail_redirect(approval, modal="reject"))

    reject_request(approval, actor, reason)
    messages.success(request, "?뱀씤 ?붿껌??諛섎젮?덉뒿?덈떎.")
    return redirect(reverse("doc_approval_detail", args=[approval.approval_sn]))



