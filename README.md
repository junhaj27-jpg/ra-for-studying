# AIDLC: AI-DLC 기반 의료기기 RA 문서 자동화 플랫폼

AIDLC는 기존 ALPLED 프로젝트 구조를 기반으로 의료기기 개발자가 RA(Regulatory Affairs) 문서를 작성할 때 필요한 요구사항, 위험관리, 검증문서, 시험 시나리오, 변경관리 기록, 추적성 매트릭스를 생성·검토하는 포트폴리오용 문서 자동화 플랫폼입니다.

> 본 프로젝트는 의료 진단 또는 치료 목적의 소프트웨어가 아니라, 의료기기 개발 및 RA 문서 작성 과정을 보조하기 위한 포트폴리오용 문서 자동화 플랫폼입니다.

AIDLC는 진단, 처방, 치료 결정, 의료 판단을 수행하지 않습니다. 제품 설명, 요구사항, 시험 자료, 변경 이력, 규제 근거 문서를 바탕으로 RA 문서 초안을 작성하고 문서 간 정합성을 검토하는 보조 도구를 목표로 합니다.

---

## Repository Structure

| 경로 | 역할 |
| --- | --- |
| `ALPLED-CORE/` | FastAPI, RAG, Agent, workflow 기반 RA 문서 생성·검토 백엔드 |
| `ALPLED-WEB/` | Django 기반 AIDLC 웹 콘솔, 프로젝트 업로드, RA 문서 생성, 승인/검토 UI |
| `FT/` | 요구사항 정규화 및 RA 문서 구조화 모델 파인튜닝 실험 영역 |
| `docs/` | RA 문서 유형과 플랫폼 설명 자료 |
| `config/` | 메뉴/화면 라벨 정의 예시 |
| `samples/` | 의료기기 예시 프로젝트 JSON 샘플 |

---

## Platform Scope

| 구분 | 내용 |
| --- | --- |
| 수행하는 일 | RA 문서 작성 보조, 개발문서 구조화, 검증자료 매핑, 정합성 검토 |
| 수행하지 않는 일 | 진단, 처방, 치료, 임상적 의사결정, 의료 판단 |
| 대상 사용자 | 의료기기 개발자, RA 담당자, QA 담당자, SaMD 프로젝트 관리자 |
| 목적 | 인허가 준비 문서의 누락과 불일치를 줄이고 문서 작성 흐름을 표준화 |

---

## Main Menu

AIDLC WEB 화면은 다음 메뉴 구조를 기준으로 정리했습니다.

- Dashboard
- Project Upload
- RA Document Generator
- Risk Management
- Traceability Matrix
- Test Scenario
- Validation Report
- Admin

---

## RA Document Types

기존 ALPLED 문서 코드와 라우팅은 유지하면서 화면 라벨과 의미를 RA 문서 체계로 재정의했습니다.

| 기존 코드 | RA 문서명 | 목적 |
| --- | --- | --- |
| `DOC_SRS` | 요구사항정의서 | 사용 목적, 사용자, 기능/비기능, 규제 요구사항 정의 |
| `DOC_ITF` | 위험관리표 | 위해요인, 위해상황, 위험통제, 검증항목 연결 |
| `DOC_ARCH` | 소프트웨어 요구사항 명세서 | SaMD 개발문서 보조를 위한 SRS 작성 |
| `DOC_ERD` | 추적성 매트릭스 | 요구사항, 위험, 시험, 검증 결과 연결 |
| `DOC_DB` | 변경관리 기록 | 변경 영향, 재검증 필요 여부, 인허가 영향 기록 |
| `DOC_TS` | 통합시험 시나리오 | 요구사항과 위험통제 기반 시험 절차 생성 |

---

## RA Functions

- 요구사항과 시험 시나리오 자동 매핑
- 위험요소와 검증항목 연결
- 누락 문서 체크
- 문서 간 불일치 검출
- 근거 기반 RAG 문서 생성
- 규제 문서 템플릿 기반 출력
- 승인 요청 문서의 의미적 정합성 검토

---

## Sample Device Topics

샘플 데이터와 화면 문구는 다음 예시를 기준으로 구성했습니다.

- 심박수 기반 운동강도 측정기
- MRI 3D 시각화 연구용 소프트웨어
- 의료기관 문서 자동화 시스템

---

## Verification

이번 리팩토링에서 수정한 주요 Python 파일은 문법 검사를 통과했습니다.

```powershell
python -m py_compile ALPLED-WEB/common/signals.py ALPLED-WEB/docs/views.py ALPLED-WEB/docs/services.py
```

Django 전체 `manage.py check`는 현재 실행 환경에 Django 패키지가 설치되어 있지 않아 별도 가상환경 구성 후 확인이 필요합니다.

---

## Next Steps

- 실제 RA 문서 템플릿을 Word/PDF 출력 형식으로 고도화
- 위험관리표 위험도 계산 로직 구현
- 문서 간 불일치 검출 규칙 엔진 추가
- RAG 근거 문장 출처 표시 강화
- Validation Report 화면에 요구사항-위험-시험 누락 항목 시각화
- 의료기기 예시 데이터를 실제 데모 프로젝트로 seed 처리
