# AIDLC-RA 고도화 기능 명세

이 문서는 사용자가 요청한 RA 포트폴리오 고도화 항목을 실제 저장소에서 어떤 파일과 로직으로 반영했는지 설명합니다.

> 본 프로젝트는 의료 진단 또는 치료 목적의 소프트웨어가 아니라, 의료기기 개발 및 RA 문서 작성 과정을 보조하기 위한 포트폴리오용 문서 자동화 플랫폼입니다.

## 구현 위치

| 항목 | 구현 파일 | 설명 |
| --- | --- | --- |
| 실제 RA 문서 Word/PDF 템플릿 출력 고도화 | `config/ra-output-templates.json`, `docs.ra_automation.build_word_pdf_export_manifest` | DOCX/PDF 출력용 문서 패키지 manifest와 필수 섹션 정의 |
| ISO 14971 기반 위험도 계산 로직 | `ALPLED-WEB/docs/ra_automation.py` | 발생가능성, 심각도 기반 초기/잔여 위험도 계산 |
| IEC 62304 스타일 소프트웨어 요구사항 추적성 강화 | `build_iec62304_traceability` | 요구사항, 위험, 시험 연결과 커버리지 산출 |
| 검증 및 밸리데이션 계획서 자동 생성 규칙 | `generate_vv_plan` | 요구사항, 위험, 시험 기반 V&V 계획 초안 생성 |
| 문서 간 불일치 검출 규칙 엔진 | `detect_document_inconsistencies` | 시험 누락, 위험 ID 누락, 비의료적 고지 누락 검출 |
| RAG 근거 문장 출처 표시 강화 | `package_rag_citations` | 출처 ID, 문서명, 섹션, 페이지, 사용 목적 정규화 |
| 변경관리 영향 분석 자동화 | `analyze_change_impact` | 변경 ID 기준 영향 문서와 재검증 필요 여부 산출 |
| Validation Report 연결 그래프 시각화 | `build_traceability_graph`, `approval_detail.html` | 요구사항-위험-시험 노드/엣지 데이터와 화면 블록 추가 |
| 의료기기 예시 프로젝트 seed 데이터 | `samples/ra-seed-projects.json` | 심박수, MRI, 문서 자동화, 병동 알림, QMS 예시 추가 |
| 사용자별 RA 프로젝트 포트폴리오 리포트 출력 | `render_portfolio_report` | 사용자별 프로젝트 요약 Markdown 리포트 생성 |

## 설계 원칙

- 실제 인허가 승인 여부를 판단하지 않습니다.
- 의료 진단, 처방, 치료 판단 기능을 포함하지 않습니다.
- 규제 자문이 아니라 RA 문서 작성 보조와 정합성 검토 지원에 초점을 둡니다.
- 기존 Django 라우팅과 문서 생성 구조를 깨지 않도록 순수 Python 서비스 모듈로 분리했습니다.
- 향후 실제 Word/PDF 렌더러 또는 RAG 파이프라인과 연결할 수 있도록 manifest와 정규화된 결과 객체를 반환합니다.

## Validation Report 그래프 데이터 예시

```json
{
  "nodes": [
    {"id": "REQ-HR-001", "type": "requirement"},
    {"id": "RISK-HR-001", "type": "risk"},
    {"id": "TEST-HR-001", "type": "test"}
  ],
  "edges": [
    {"from": "REQ-HR-001", "to": "RISK-HR-001", "label": "controls"},
    {"from": "REQ-HR-001", "to": "TEST-HR-001", "label": "verified by"}
  ]
}
```

## 향후 실제 구현 확장

- DOCX 렌더링 엔진 연결
- PDF 변환 파이프라인 연결
- RAG 검색 결과와 citation 자동 주입
- 위험도 매트릭스 기관별 커스터마이징
- 규칙 엔진을 JSON/YAML 기반으로 분리
- Validation Report 그래프를 동적 JavaScript 시각화로 확장

## 사용 시 주의사항

- 본 기능은 RA 문서 작성 보조와 포트폴리오 시연을 위한 로직입니다.
- ISO 14971 위험도 계산 결과는 실제 제조사의 위험허용 기준표, 위험관리계획서, 품질절차를 대체하지 않습니다.
- IEC 62304 추적성 커버리지는 요구사항-시험 연결 여부를 확인하는 보조 지표이며, 소프트웨어 안전등급 결정이나 적합성 판단을 대신하지 않습니다.
- V&V 계획서 초안은 시험 범위와 합격 기준을 정리하기 위한 출발점이며, 실제 시험 프로토콜은 제품 특성, 표준, 시험환경, 품질절차에 맞게 별도 승인해야 합니다.
- RAG citation은 근거 후보를 표시하는 기능입니다. 사용자는 원문, 버전, 작성일, 적용 범위를 직접 확인해야 합니다.
- 변경관리 영향 분석은 영향 가능성이 있는 문서를 추천할 뿐이며, 최종 재검증 필요 여부는 RA/QA/개발 책임자가 결정해야 합니다.
- 환자정보, 개인정보, 영업비밀, 승인되지 않은 임상자료는 샘플 프로젝트나 RAG 근거로 사용하지 않아야 합니다.
- 출력된 Word/PDF 문서는 포트폴리오용 예시이며 실제 제출 전 문서번호, 서명, 승인 이력, 개정 이력, 회사 양식 반영이 필요합니다.
