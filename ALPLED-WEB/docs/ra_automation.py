"""RA portfolio automation helpers for AIDLC-RA.

The functions in this module intentionally avoid medical diagnosis or treatment
logic. They model documentation support tasks: ISO 14971-style risk scoring,
IEC 62304-style traceability checks, V&V planning, consistency review, RAG
citation packaging, change impact analysis, and portfolio report generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Mapping, Sequence

RiskInput = Mapping[str, Any]
RequirementInput = Mapping[str, Any]
TestInput = Mapping[str, Any]
ChangeInput = Mapping[str, Any]
CitationInput = Mapping[str, Any]

DISCLAIMER = (
    "본 프로젝트는 의료 진단 또는 치료 목적의 소프트웨어가 아니라, "
    "의료기기 개발 및 RA 문서 작성 과정을 보조하기 위한 포트폴리오용 "
    "문서 자동화 플랫폼입니다."
)

RISK_LEVELS = {
    "low": {"label": "Low", "action": "수용 가능. 정기 검토 대상."},
    "medium": {"label": "Medium", "action": "위험통제와 검증 근거 필요."},
    "high": {"label": "High", "action": "위험통제 필수. V&V 시험과 잔여위험 검토 필요."},
    "unacceptable": {"label": "Unacceptable", "action": "설계 변경 또는 추가 통제 전까지 수용 불가."},
}

DOCUMENT_TEMPLATES = {
    "requirements": "요구사항정의서",
    "srs": "소프트웨어 요구사항 명세서",
    "risk": "위험관리표",
    "vv_plan": "검증 및 밸리데이션 계획서",
    "test_scenario": "통합시험 시나리오",
    "change_record": "변경관리 기록",
    "traceability": "추적성 매트릭스",
    "validation_report": "RA 문서 정합성 검토 결과",
}


@dataclass(frozen=True)
class RiskScore:
    probability: int
    severity: int
    score: int
    level: str
    label: str
    action: str


def _as_int(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calculate_iso14971_risk(probability: Any, severity: Any) -> RiskScore:
    """Return a simple ISO 14971-style risk score.

    Probability and severity are normalized to a 1-5 range. The score is not a
    substitute for a manufacturer's approved risk acceptability matrix; it is a
    portfolio helper that demonstrates RA documentation logic.
    """

    p = max(1, min(5, _as_int(probability)))
    s = max(1, min(5, _as_int(severity)))
    score = p * s
    if score >= 20:
        level = "unacceptable"
    elif score >= 12:
        level = "high"
    elif score >= 6:
        level = "medium"
    else:
        level = "low"
    meta = RISK_LEVELS[level]
    return RiskScore(probability=p, severity=s, score=score, level=level, label=meta["label"], action=meta["action"])


def enrich_risk_table(risks: Sequence[RiskInput]) -> List[Dict[str, Any]]:
    """Add initial/residual risk scores and RA review actions to risk rows."""

    enriched: List[Dict[str, Any]] = []
    for risk in risks:
        initial = calculate_iso14971_risk(risk.get("probability", 3), risk.get("severity", 3))
        residual = calculate_iso14971_risk(risk.get("residualProbability", risk.get("probability", 2)), risk.get("residualSeverity", risk.get("severity", 3)))
        row = dict(risk)
        row.update(
            {
                "initialRiskScore": initial.score,
                "initialRiskLevel": initial.label,
                "residualRiskScore": residual.score,
                "residualRiskLevel": residual.label,
                "raAction": residual.action,
                "requiresVerification": bool(risk.get("control")),
            }
        )
        enriched.append(row)
    return enriched


def build_iec62304_traceability(requirements: Sequence[RequirementInput], risks: Sequence[RiskInput], tests: Sequence[TestInput]) -> Dict[str, Any]:
    """Build requirement-risk-test traceability rows and coverage metrics."""

    risk_by_id = {str(item.get("id")): item for item in risks if item.get("id")}
    tests_by_requirement: Dict[str, List[TestInput]] = {}
    for test in tests:
        req_id = str(test.get("mappedRequirement") or test.get("requirementId") or "")
        if req_id:
            tests_by_requirement.setdefault(req_id, []).append(test)

    rows: List[Dict[str, Any]] = []
    missing_tests: List[str] = []
    missing_risks: List[str] = []
    for req in requirements:
        req_id = str(req.get("id", ""))
        risk_id = str(req.get("mappedRisk") or req.get("riskId") or "")
        mapped_tests = tests_by_requirement.get(req_id, [])
        if not mapped_tests:
            missing_tests.append(req_id)
        if risk_id and risk_id not in risk_by_id:
            missing_risks.append(req_id)
        rows.append(
            {
                "requirementId": req_id,
                "requirementType": req.get("type", "functional"),
                "riskId": risk_id or None,
                "riskMapped": bool(risk_id and risk_id in risk_by_id),
                "testIds": [test.get("id") for test in mapped_tests],
                "testMapped": bool(mapped_tests),
                "iec62304Note": "software requirement linked to verification" if mapped_tests else "verification mapping required",
            }
        )

    total = len(requirements)
    covered = total - len(missing_tests)
    coverage = round((covered / total) * 100, 1) if total else 0.0
    return {"rows": rows, "coveragePercent": coverage, "missingTests": missing_tests, "missingRisks": missing_risks}


def generate_vv_plan(requirements: Sequence[RequirementInput], risks: Sequence[RiskInput], tests: Sequence[TestInput]) -> Dict[str, Any]:
    """Create a V&V plan draft from requirements, risks, and test scenarios."""

    trace = build_iec62304_traceability(requirements, risks, tests)
    risk_rows = enrich_risk_table(risks)
    high_risk_ids = [row.get("id") for row in risk_rows if row.get("initialRiskLevel") in {"High", "Unacceptable"}]
    test_map = {test.get("id"): test for test in tests}
    planned_tests = []
    for row in trace["rows"]:
        for test_id in row["testIds"]:
            test = test_map.get(test_id, {})
            planned_tests.append(
                {
                    "testId": test_id,
                    "requirementId": row["requirementId"],
                    "riskId": row["riskId"],
                    "title": test.get("title", "검증 시험"),
                    "acceptanceCriteria": test.get("acceptanceCriteria", "요구사항과 기대 결과가 일치해야 한다."),
                    "evidence": "시험 결과 기록, 화면 캡처, 로그 파일",
                }
            )
    return {
        "documentType": DOCUMENT_TEMPLATES["vv_plan"],
        "scope": "요구사항, 위험통제, 통합시험 시나리오의 검증 커버리지 확인",
        "highRiskItems": high_risk_ids,
        "plannedTests": planned_tests,
        "coveragePercent": trace["coveragePercent"],
        "openItems": trace["missingTests"],
        "disclaimer": DISCLAIMER,
    }


def detect_document_inconsistencies(project: Mapping[str, Any]) -> List[Dict[str, str]]:
    """Detect basic consistency issues across requirements, risks, tests, and claims."""

    issues: List[Dict[str, str]] = []
    requirements = list(project.get("requirements", []))
    risks = list(project.get("risks", []))
    tests = list(project.get("testScenarios", []))
    trace = build_iec62304_traceability(requirements, risks, tests)

    for req_id in trace["missingTests"]:
        issues.append({"severity": "major", "type": "missing_test", "message": f"요구사항 {req_id}에 연결된 시험 시나리오가 없습니다."})
    for req_id in trace["missingRisks"]:
        issues.append({"severity": "major", "type": "missing_risk", "message": f"요구사항 {req_id}의 위험 ID가 위험관리표에 없습니다."})

    risk_ids = {risk.get("id") for risk in risks}
    verified_risk_ids = {test.get("mappedRisk") for test in tests if test.get("mappedRisk")}
    for risk_id in sorted(risk_ids - verified_risk_ids):
        risk = next((item for item in risks if item.get("id") == risk_id), {})
        if risk.get("verificationItem"):
            continue
        issues.append({"severity": "minor", "type": "unverified_risk", "message": f"위험 {risk_id}에 명시적인 검증시험 연결이 부족합니다."})

    combined_text = " ".join(str(value) for value in project.values() if isinstance(value, str))
    prohibited_terms = ["진단", "처방", "치료 계획", "응급상황 판단"]
    if any(term in combined_text for term in prohibited_terms) and not project.get("notMedicalClaim"):
        issues.append({"severity": "critical", "type": "medical_claim_scope", "message": "의료적 주장으로 오해될 수 있는 표현이 있으나 비의료적 범위 고지가 없습니다."})

    return issues


def package_rag_citations(citations: Sequence[CitationInput]) -> List[Dict[str, Any]]:
    """Normalize RAG evidence snippets for source display in RA documents."""

    packaged = []
    for index, citation in enumerate(citations, start=1):
        packaged.append(
            {
                "citationId": f"RAG-{index:03d}",
                "source": citation.get("source", "uploaded evidence"),
                "section": citation.get("section", "general"),
                "page": citation.get("page"),
                "quote": citation.get("quote", ""),
                "usedFor": citation.get("usedFor", "RA document draft"),
            }
        )
    return packaged


def analyze_change_impact(change: ChangeInput, traceability_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Estimate affected RA artifacts when a requirement, risk, test, or UI label changes."""

    affected_ids = set(str(item) for item in change.get("affectedIds", []))
    changed_type = str(change.get("type", "requirement"))
    impacted_docs = {DOCUMENT_TEMPLATES["change_record"], DOCUMENT_TEMPLATES["traceability"]}
    impacted_rows = []

    for row in traceability_rows:
        row_ids = {str(row.get("requirementId")), str(row.get("riskId"))}
        row_ids.update(str(test_id) for test_id in row.get("testIds", []))
        if affected_ids & row_ids:
            impacted_rows.append(dict(row))
            impacted_docs.update([DOCUMENT_TEMPLATES["requirements"], DOCUMENT_TEMPLATES["risk"], DOCUMENT_TEMPLATES["test_scenario"], DOCUMENT_TEMPLATES["vv_plan"]])

    if changed_type in {"ui_label", "intended_use", "claim"}:
        impacted_docs.update([DOCUMENT_TEMPLATES["requirements"], DOCUMENT_TEMPLATES["validation_report"]])

    return {
        "changeId": change.get("id", "CHG-TBD"),
        "impactedDocuments": sorted(impacted_docs),
        "impactedTraceabilityRows": impacted_rows,
        "requiresRevalidation": bool(impacted_rows or changed_type in {"algorithm", "intended_use", "risk_control"}),
        "recommendedAction": "영향 문서 업데이트 후 V&V 재검토" if impacted_rows else "변경관리 기록에 사유와 검토 결과 보관",
    }


def build_traceability_graph(traceability_rows: Sequence[Mapping[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """Create graph nodes/edges for Validation Report visualization."""

    nodes: Dict[str, Dict[str, str]] = {}
    edges: List[Dict[str, str]] = []
    for row in traceability_rows:
        req_id = str(row.get("requirementId") or "")
        risk_id = str(row.get("riskId") or "")
        if req_id:
            nodes[req_id] = {"id": req_id, "label": req_id, "type": "requirement"}
        if risk_id and risk_id != "None":
            nodes[risk_id] = {"id": risk_id, "label": risk_id, "type": "risk"}
            edges.append({"from": req_id, "to": risk_id, "label": "controls"})
        for test_id in row.get("testIds", []):
            test_key = str(test_id)
            nodes[test_key] = {"id": test_key, "label": test_key, "type": "test"}
            edges.append({"from": req_id, "to": test_key, "label": "verified by"})
            if risk_id and risk_id != "None":
                edges.append({"from": risk_id, "to": test_key, "label": "mitigation verified"})
    return {"nodes": list(nodes.values()), "edges": edges}


def build_word_pdf_export_manifest(project: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a document package manifest for Word/PDF template rendering."""

    project_name = project.get("name", "RA Project")
    package_id = project.get("id", "RA-PKG")
    documents = []
    for key, title in DOCUMENT_TEMPLATES.items():
        documents.append(
            {
                "templateKey": key,
                "title": title,
                "wordFileName": f"{package_id}-{key}.docx",
                "pdfFileName": f"{package_id}-{key}.pdf",
                "requiredSections": ["문서 목적", "입력 근거", "본문", "검토 기준", "승인 이력"],
            }
        )
    return {"packageId": package_id, "projectName": project_name, "generatedOn": date.today().isoformat(), "documents": documents, "disclaimer": DISCLAIMER}


def render_portfolio_report(user_name: str, projects: Sequence[Mapping[str, Any]]) -> str:
    """Render a Markdown portfolio report for a user across RA projects."""

    lines = [f"# {user_name} RA 프로젝트 포트폴리오 리포트", "", DISCLAIMER, ""]
    for project in projects:
        requirements = project.get("requirements", [])
        risks = project.get("risks", [])
        tests = project.get("testScenarios", [])
        trace = build_iec62304_traceability(requirements, risks, tests)
        issues = detect_document_inconsistencies(project)
        manifest = build_word_pdf_export_manifest(project)
        lines.extend(
            [
                f"## {project.get('name', 'RA Project')}",
                f"- 프로젝트 ID: {project.get('id', '-')}",
                f"- 사용 목적: {project.get('intendedUse', '-')}",
                f"- 비의료적 범위: {project.get('notMedicalClaim', '-')}",
                f"- 추적성 커버리지: {trace['coveragePercent']}%",
                f"- 정합성 이슈: {len(issues)}건",
                f"- 출력 패키지 문서 수: {len(manifest['documents'])}개",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


__all__ = [
    "DISCLAIMER",
    "DOCUMENT_TEMPLATES",
    "RiskScore",
    "calculate_iso14971_risk",
    "enrich_risk_table",
    "build_iec62304_traceability",
    "generate_vv_plan",
    "detect_document_inconsistencies",
    "package_rag_citations",
    "analyze_change_impact",
    "build_traceability_graph",
    "build_word_pdf_export_manifest",
    "render_portfolio_report",
]
