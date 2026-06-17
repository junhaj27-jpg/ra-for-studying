# Brain MRI 3D Longitudinal Analysis Web Service

## 1. 프로젝트 개요

**Brain MRI 3D Longitudinal Analysis Web Service**는 동일 환자의 Brain MRI 데이터를 기반으로 병변 또는 종양 의심 영역의 부피 변화를 추적하고, 2D 슬라이스 뷰어와 3D 모델 뷰어를 통해 시각적으로 확인할 수 있는 웹 기반 MRI 분석 프로토타입이다.

본 프로젝트는 의료진의 진단을 대체하는 시스템이 아니라, Brain MRI 분석 결과를 정량화하고 장기 변화 추세를 확인할 수 있도록 돕는 **진단 보조용 연구 및 포트폴리오 프로토타입**이다.

주요 처리 흐름은 다음과 같다.

```txt
MRI 데이터 업로드
→ 비식별화 및 메타데이터 관리
→ MRI 전처리
→ Segmentation Mask 생성
→ 병변 부피 계산
→ 3D 모델 생성
→ 장기/단기 변화 추적
→ PDF 분석 보고서 생성
```

---

## 2. 개발 배경

Brain MRI는 장기간 추적 관찰이 필요한 질환에서 중요한 의료영상 데이터이다. 특히 병변 또는 종양 의심 영역의 크기 변화는 치료 반응, 상태 변화, 재발 가능성 등을 확인하는 데 중요한 참고 자료가 될 수 있다.

본 프로젝트는 서로 다른 병원과 촬영 장비에서 생성된 MRI 데이터를 하나의 환자 기준으로 통합 관리하고, 병원 및 장비 차이를 고려하여 촬영 시점별 병변 부피 변화와 시계열 추적 결과를 제공하는 것을 목표로 한다.

서로 다른 병원에서 촬영된 MRI 데이터는 다음과 같은 차이가 발생할 수 있다.

```txt
밝기 차이
해상도 차이
슬라이스 간격 차이
촬영 방향 차이
장비별 영상 품질 차이
조영 여부 차이
```

따라서 본 시스템은 MRI 데이터를 비교 가능한 형태로 정렬하고, 병변 또는 종양 의심 영역의 부피 변화를 정량적으로 확인할 수 있도록 설계한다.

---

## 3. 데이터 구성

본 프로젝트의 데이터는 실제 환자번호를 사용하지 않고, 비식별 환자 코드 `P001`을 기준으로 관리한다.

| 구분         | 설명                                        |
| ---------- | ----------------------------------------- |
| 환자 코드      | P001                                      |
| 이대목동병원 데이터 | 병변 또는 종양 의심 영역이 가장 크게 관찰된 단기 집중 촬영 구간     |
| 서울대병원 데이터  | 항암제 치료 이후 최근까지 이어지는 장기 추적 데이터             |
| MRI 규모     | MRI 1세트당 약 895개 슬라이스                      |
| 전체 데이터     | 약 12개 MRI 세트 기준                           |
| 데이터 성격     | 3D 모델링 및 병변 부피 추적이 가능한 고해상도 Brain MRI 데이터 |

데이터 해석 기준은 다음과 같다.

```txt
EUMC 데이터:
- 병변 최대 관찰 구간
- 단기 집중 촬영 데이터
- 초기 또는 고위험 변화 구간으로 활용

SNUH 데이터:
- 항암제 이후 장기 추적 데이터
- 최근 follow-up 데이터
- 병변 부피 감소 흐름 확인
```

---

## 4. 분석 관점

본 프로젝트에서는 MRI 상에서 관찰되는 영역을 단순히 “종양”으로 단정하지 않는다.

대신 다음을 포함하는 표현으로 정의한다.

```txt
병변 또는 종양 의심 영역
치료 이후 잔존 병변
괴사 흔적
부종
잔존 종양 가능성
영상상 변화 영역
```

따라서 본 시스템은 최종 진단을 수행하지 않고, 촬영 시점별 부피 변화와 영상상 변화 추세를 정량화하여 의료진 판단을 보조하는 것을 목표로 한다.

---

## 5. 주요 기능

### 5.1 MRI 데이터 관리

* 비식별 환자 코드 기반 MRI 데이터 관리
* 병원 코드, 촬영 시점, 장비 정보 등록
* MRI 파일 세트 업로드
* MRI 데이터 목록 조회
* 분석 상태 확인
* 원본 파일 및 분석 결과 파일 관리

### 5.2 MRI 파일 업로드

* DICOM 파일 업로드
* NIfTI 파일 업로드
* ZIP 압축 파일 업로드
* 파일 형식 검증
* 대용량 MRI 파일 관리
* 업로드 진행 상태 표시
* 업로드 실패 시 오류 메시지 제공

### 5.3 MRI 전처리

* DICOM / NIfTI 로딩
* ZIP 압축 해제
* 슬라이스 순서 정렬
* intensity 정규화
* 병원 및 장비 차이에 따른 해상도 보정
* spacing resampling
* 3D volume 구성
* 웹 표시용 PNG 슬라이스 변환

### 5.4 AI 기반 MRI 분석

* Brain MRI 내 병변 또는 종양 의심 영역 분석
* segmentation mask 생성
* 원본 MRI와 mask overlay 표시
* 병변 부피 계산
* 분석 상태 관리

### 5.5 병변 부피 계산

segmentation mask의 voxel 개수를 기반으로 병변 부피를 계산한다.

```txt
voxel_count = mask에서 1로 표시된 voxel 개수
voxel_volume_mm3 = spacing_z × spacing_y × spacing_x
volume_mm3 = voxel_count × voxel_volume_mm3
volume_cm3 = volume_mm3 / 1000
```

결과는 `cm³` 단위로 표시한다.

### 5.6 3D 모델링

병변 부피를 숫자로만 표시하지 않고, 실제 3D 형태로 확인할 수 있도록 한다.

처리 흐름은 다음과 같다.

```txt
Segmentation Mask
→ Marching Cubes
→ 3D Mesh 생성
→ OBJ 또는 GLB 저장
→ Three.js 기반 웹 3D 뷰어 표시
```

3D 뷰어 기능은 다음과 같다.

* 병변 3D 모델 조회
* 회전
* 확대
* 축소
* 병변 부피 표시
* 촬영 시점별 모델 비교

### 5.7 장기 및 단기 추적 분석

* 동일 환자 코드 기준 MRI 촬영 이력 조회
* 이대목동병원 단기 집중 촬영 데이터 확인
* 서울대병원 장기 추적 데이터 확인
* 최대 병변 시점 자동 탐지
* 최근 촬영 시점 자동 탐지
* 촬영 시점별 부피 변화량 계산
* 촬영 시점별 부피 변화율 계산
* 항암제 이후 감소 추세 분석

### 5.8 분석 보고서

* MRI 분석 결과 PDF 보고서 생성
* 환자 코드 표시
* 촬영 시점 표시
* 병원 코드 표시
* 병변 부피 표시
* 변화량 및 변화율 표시
* 원본 이미지, mask 이미지, overlay 이미지 포함
* 진단 보조용 안내 문구 포함

---

## 6. 서비스 화면 구성

본 서비스는 약 20개 화면으로 구성한다.

| Page | Page Title    | Screen ID       | 설명                         |
| ---: | ------------- | --------------- | -------------------------- |
|    1 | 로그인           | U-LOGIN         | 사용자 로그인 화면                 |
|    2 | 프로젝트 선택       | U-PROJ-SEL      | MRI 분석 프로젝트 선택 화면          |
|    3 | 프로젝트 설명       | U-PROJ-DESC     | 서비스 개요 및 분석 목적 안내 화면       |
|    4 | 환자 MRI 데이터 관리 | U-MRI-PAT-LIST  | 환자 코드별 MRI 데이터 목록 화면       |
|    5 | MRI 촬영 이력 관리  | U-MRI-HIS       | 촬영 시점 및 병원별 이력 조회 화면       |
|    6 | MRI 파일 등록     | U-MRI-UP        | MRI 파일 세트 업로드 화면           |
|    7 | MRI 파일 선택 완료  | U-MRI-UP-SEL    | 선택된 MRI 파일 목록 확인 화면        |
|    8 | MRI 업로드 진행    | U-MRI-UP-ING    | 대용량 MRI 업로드 진행 화면          |
|    9 | MRI 전처리 설정    | U-MRI-PRE-SET   | 정규화, 해상도 보정, 슬라이스 정렬 설정 화면 |
|   10 | MRI 전처리 진행    | U-MRI-PRE-ING   | MRI 전처리 상태 확인 화면           |
|   11 | MRI 분석 실행     | U-MRI-ANA-REQ   | 분석 대상 MRI 선택 및 분석 요청 화면    |
|   12 | MRI 분석 진행 현황  | U-MRI-ANA-ING   | AI 분석 진행 상태 확인 화면          |
|   13 | MRI 슬라이스 뷰어   | U-MRI-SLICE     | 895개 슬라이스 조회 화면            |
|   14 | MRI 분석 결과 상세  | U-MRI-RST-DET   | 원본, mask, overlay 확인 화면    |
|   15 | 병변 부피 분석      | U-MRI-VOL       | 병변 부피 계산 결과 화면             |
|   16 | 3D 모델 뷰어      | U-MRI-3D        | 병변 또는 뇌 영역 3D 모델 확인 화면     |
|   17 | 장기 추적 분석      | U-MRI-LONG-TRK  | 서울대 장기 추적 MRI 변화 분석 화면     |
|   18 | 단기 집중 분석      | U-MRI-SHORT-TRK | 이대목동병원 단기 집중 촬영 변화 분석 화면   |
|   19 | 병원·장비 비교 분석   | U-MRI-HOSP-CMP  | 병원 및 장비 차이 보정 결과 화면        |
|   20 | MRI 분석 보고서    | U-MRI-REPORT    | PDF 분석 보고서 다운로드 화면         |

---

## 7. 주요 요구사항

### 7.1 MRI 데이터 관리 요구사항

| 요구사항 ID     | 요구사항명     | 내용                                          |
| ----------- | --------- | ------------------------------------------- |
| REQ-MRI-001 | MRI 목록 조회 | 사용자는 프로젝트에 등록된 MRI 데이터 목록을 조회할 수 있어야 한다.    |
| REQ-MRI-002 | MRI 파일 등록 | 사용자는 MRI 분석을 위한 파일 세트를 업로드할 수 있어야 한다.       |
| REQ-MRI-003 | MRI 파일 검증 | 시스템은 업로드 파일의 형식, 용량, 개수를 검증해야 한다.           |
| REQ-MRI-004 | 환자 코드 관리  | 시스템은 환자 이름이나 실제 환자번호 대신 비식별 환자 코드를 사용해야 한다. |
| REQ-MRI-005 | 촬영 정보 관리  | 시스템은 촬영 시점, 병원 코드, 장비 정보를 저장해야 한다.          |
| REQ-MRI-006 | 촬영 이력 조회  | 사용자는 환자 코드 기준으로 촬영 이력을 조회할 수 있어야 한다.        |

### 7.2 분석 요구사항

| 요구사항 ID     | 요구사항명    | 내용                                         |
| ----------- | -------- | ------------------------------------------ |
| REQ-ANA-001 | 분석 실행    | 사용자는 업로드된 MRI 데이터를 선택하여 분석을 실행할 수 있어야 한다.  |
| REQ-ANA-002 | 전처리 수행   | 시스템은 MRI 정규화, 해상도 보정, 슬라이스 정렬을 수행해야 한다.    |
| REQ-ANA-003 | 병변 영역 분석 | 시스템은 MRI 내 병변 또는 종양 의심 영역을 분석해야 한다.        |
| REQ-ANA-004 | Mask 생성  | 시스템은 분석 결과를 segmentation mask 형태로 저장해야 한다. |
| REQ-ANA-005 | 부피 계산    | 시스템은 병변 영역의 부피를 cm³ 단위로 계산해야 한다.           |
| REQ-ANA-006 | 분석 상태 표시 | 시스템은 대기, 전처리 중, 분석 중, 완료, 실패 상태를 표시해야 한다.  |

### 7.3 3D 및 추적 분석 요구사항

| 요구사항 ID     | 요구사항명       | 내용                                                          |
| ----------- | ----------- | ----------------------------------------------------------- |
| REQ-TRK-001 | 통합 추적 분석    | 시스템은 이대목동병원 단기 집중 MRI와 서울대병원 장기 추적 MRI를 동일 환자 기준으로 비교해야 한다. |
| REQ-TRK-002 | 최대 병변 시점 탐지 | 시스템은 병변 또는 종양 의심 영역이 가장 크게 관찰된 시점을 자동 탐지해야 한다.              |
| REQ-TRK-003 | 최근 시점 탐지    | 시스템은 가장 최근 추적 MRI 시점을 자동 탐지해야 한다.                           |
| REQ-TRK-004 | 변화량 계산      | 시스템은 이전 촬영 시점 대비 병변 부피 변화량을 계산해야 한다.                        |
| REQ-TRK-005 | 변화율 계산      | 시스템은 이전 촬영 시점 대비 병변 부피 변화율을 계산해야 한다.                        |
| REQ-TRK-006 | 3D 모델 생성    | 시스템은 segmentation mask를 기반으로 3D 모델을 생성해야 한다.                |
| REQ-TRK-007 | 3D 모델 조회    | 사용자는 웹에서 3D 모델을 회전, 확대, 축소하여 확인할 수 있어야 한다.                  |

---

## 8. 기술 스택

| 영역               | 기술                                                |
| ---------------- | ------------------------------------------------- |
| Frontend         | HTML, CSS, JavaScript                             |
| 3D Viewer        | Three.js                                          |
| Chart            | Chart.js                                          |
| Backend          | FastAPI                                           |
| Database         | SQLite, PostgreSQL                                |
| MRI Processing   | pydicom, nibabel, SimpleITK                       |
| Image Processing | NumPy, OpenCV, scikit-image                       |
| AI Framework     | PyTorch, MONAI                                    |
| 3D Modeling      | marching cubes, trimesh                           |
| Report           | ReportLab 또는 WeasyPrint                           |
| Deployment       | 로컬 PC, 원격 PC, Render, Hugging Face Spaces, RunPod |

---

## 9. 시스템 구조

```txt
mri-analysis-web-service/
├─ backend/
│  ├─ main.py
│  ├─ database.py
│  ├─ models.py
│  ├─ schemas.py
│  ├─ routers/
│  │  ├─ patients.py
│  │  ├─ mri.py
│  │  ├─ analysis.py
│  │  └─ tracking.py
│  └─ services/
│     ├─ file_service.py
│     ├─ preprocess_service.py
│     ├─ volume_service.py
│     └─ report_service.py
│
├─ ai/
│  ├─ deidentify_dicom.py
│  ├─ check_deidentify.py
│  ├─ preprocess.py
│  ├─ convert_slice.py
│  ├─ segmentation.py
│  ├─ segmentation_dummy.py
│  ├─ volume.py
│  ├─ make_3d_model.py
│  ├─ tracking_summary.py
│  └─ visualize.py
│
├─ frontend/
│  ├─ index.html
│  ├─ upload.html
│  ├─ viewer.html
│  ├─ result.html
│  ├─ 3d.html
│  └─ static/
│     ├─ css/
│     ├─ js/
│     ├─ images/
│     └─ models/
│
├─ media/
│  ├─ uploads/
│  ├─ processed/
│  ├─ slices/
│  ├─ masks/
│  ├─ models/
│  └─ reports/
│
├─ docs/
│  ├─ 요구사항정의서.md
│  ├─ 화면설계서.md
│  ├─ DB설계서.md
│  ├─ 시스템아키텍처.md
│  └─ 테스트시나리오.md
│
├─ metadata.csv
├─ requirements.txt
├─ .gitignore
└─ README.md
```

---

## 10. 데이터베이스 설계 요약

| 테이블              | 설명                               |
| ---------------- | -------------------------------- |
| User             | 사용자 계정 및 권한 정보                   |
| Project          | MRI 분석 프로젝트 정보                   |
| Patient          | 비식별 환자 코드 정보                     |
| MRIStudy         | 촬영 시점, 병원 코드, 장비명 등 MRI 촬영 단위 정보 |
| MRISeries        | MRI 파일 세트 및 슬라이스 정보              |
| AnalysisJob      | MRI 분석 요청 및 진행 상태 정보             |
| AnalysisResult   | 분석 결과, 병변 부피, 신뢰도 정보             |
| SegmentationMask | 병변 mask 파일 정보                    |
| Model3D          | 3D 모델 파일 정보                      |
| Report           | PDF 분석 보고서 정보                    |

추가로 필요한 컬럼은 다음과 같다.

```txt
study_group:
- short_term
- long_term

timepoint_label:
- EUMC_T01
- EUMC_T02
- SNUH_T05
- SNUH_T08

treatment_phase:
- pre_treatment
- during_treatment
- post_treatment
- recent_follow_up

comparison_note:
- 병원/장비 차이로 직접 비교 주의
```

---

## 11. 비식별화 및 보안 기준

본 프로젝트는 의료영상 데이터를 다루기 때문에 익명화 및 비식별화가 필수이다.

### 11.1 기본 원칙

```txt
원본 DICOM 공개 업로드 금지
실제 환자번호 사용 금지
실제 환자명 사용 금지
실제 생년월일 사용 금지
실제 검사번호 사용 금지
실제 촬영일 직접 공개 금지
```

### 11.2 권장 방식

```txt
원본 DICOM
→ 로컬 보관

비식별화 DICOM
→ 내부 분석용

NIfTI 변환본
→ Hugging Face Private Dataset 업로드 가능

분석 결과
→ mask, preview, volume, tracking.csv 형태로 관리
```

### 11.3 제거해야 할 정보

```txt
PatientName
PatientID
PatientBirthDate
PatientSex
PatientAge
PatientAddress
PatientTelephoneNumbers
AccessionNumber
InstitutionName
InstitutionAddress
ReferringPhysicianName
PerformingPhysicianName
OperatorsName
StationName
DeviceSerialNumber
StudyDescription
SeriesDescription
ProtocolName
ImageComments
StudyInstanceUID
SeriesInstanceUID
SOPInstanceUID
FrameOfReferenceUID
Private Tags
```

### 11.4 이미지 내부 확인

DICOM 메타데이터를 제거해도 이미지 픽셀 내부에 환자명, 병원명, 날짜가 박혀 있을 수 있다. 따라서 preview PNG를 생성한 뒤 다음을 확인해야 한다.

```txt
앞쪽 슬라이스 10장 확인
중간 슬라이스 10장 확인
뒤쪽 슬라이스 10장 확인
이미지 모서리 글자 확인
파일명과 폴더명 확인
metadata.csv 확인
```

---

## 12. Hugging Face 활용 방식

Hugging Face에는 원본 MRI를 직접 공개하지 않고, 비식별화된 데이터와 결과 파일만 업로드한다.

### 12.1 권장 저장 방식

```txt
Hugging Face Private Dataset
├─ image.nii.gz
├─ mask.nii.gz
├─ preview_slice.png
├─ overlay.png
├─ result.json
└─ tracking.csv
```

### 12.2 권장 구조

```txt
brain-mri-longitudinal-dataset/
├─ README.md
├─ metadata.csv
├─ patient_P001/
│  ├─ EUMC_T01/
│  │  ├─ image.nii.gz
│  │  ├─ mask.nii.gz
│  │  └─ result.json
│  ├─ EUMC_T02/
│  │  ├─ image.nii.gz
│  │  ├─ mask.nii.gz
│  │  └─ result.json
│  ├─ SNUH_T05/
│  │  ├─ image.nii.gz
│  │  ├─ mask.nii.gz
│  │  └─ result.json
│  └─ SNUH_T08/
│     ├─ image.nii.gz
│     ├─ mask.nii.gz
│     └─ result.json
├─ previews/
│  ├─ P001_EUMC_T01_slice_0450.png
│  └─ P001_SNUH_T08_overlay.png
└─ tracking.csv
```

### 12.3 Space와 Dataset 분리

```txt
Dataset repo:
- 데이터 저장용
- 비식별화 NIfTI
- mask
- result.json
- tracking.csv

Space:
- 웹 데모 실행용
- Gradio 또는 FastAPI 화면
- Dataset에서 필요한 샘플만 다운로드
```

---

## 13. 배포 및 실행 방식

### 13.1 현재 추천 방식

현재 단계에서는 RunPod보다 FastAPI 기반 로컬 또는 원격 PC 실행이 적합하다.

```txt
FastAPI:
- 웹서비스 본체
- 업로드
- DB
- 화면
- 결과 조회
- 슬라이스 뷰어
- 3D 뷰어

RunPod:
- 무거운 GPU 분석
- MONAI segmentation
- 대용량 MRI 추론
- 3D 모델 생성 고도화
```

### 13.2 원격 PC 사용 방식

원격 PC를 직접 조종해서 프로젝트를 실행할 수 있다.

권장 도구:

```txt
Chrome Remote Desktop
RustDesk
AnyDesk
Windows Remote Desktop
Parsec
```

가장 쉬운 방식은 Chrome Remote Desktop이다.

원격 PC에서 FastAPI 실행:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

원격 PC 브라우저에서 접속:

```txt
http://127.0.0.1:8000
```

### 13.3 무료 서버 후보

| 서비스                 | 용도              | 적합도         |
| ------------------- | --------------- | ----------- |
| Render              | FastAPI 웹서비스 배포 | 높음          |
| Hugging Face Spaces | 데모 화면           | 중간          |
| Google Colab        | 전처리/AI 분석 실험    | 높음          |
| Vercel / Netlify    | 프론트엔드 배포        | 중간          |
| RunPod              | GPU 분석          | 고도화 단계에서 사용 |

---

## 14. 개발 단계

### 14.1 1차 MVP

```txt
로그인 기능
프로젝트 선택 기능
환자 코드 기반 MRI 데이터 관리
MRI 파일 업로드
촬영 시점, 병원 코드, 장비명 등록
MRI 목록 조회
분석 상태 표시
```

### 14.2 2차 MVP

```txt
MRI 슬라이스 PNG 변환
웹 기반 MRI 슬라이스 뷰어
촬영 시점별 MRI 이력 조회
병원별 MRI 데이터 구분
분석 결과 목록 화면
```

### 14.3 3차 MVP

```txt
segmentation mask 등록 또는 생성
병변 부피 계산
촬영 시점별 부피 변화 그래프
단기/장기 추적 분석
PDF 보고서 생성
```

### 14.4 4차 MVP

```txt
3D 모델 생성
Three.js 기반 3D 모델 뷰어
병원 및 장비 차이 보정 결과 표시
AI segmentation 모델 연결
```

---

## 15. 자동 추적 분석 로직

사람이 매번 “이대가 먼저인지”, “서울대가 최근인지”, “어디가 가장 큰지”를 직접 작성하지 않도록 코드가 자동으로 계산한다.

### 15.1 metadata.csv 예시

```csv
patient_code,hospital_code,study_label,study_order,study_group,treatment_phase,volume_cm3,file_path
P001,EUMC,EUMC_T01,1,short_term,pre_treatment,42.3,data/P001/EUMC_T01/image.nii.gz
P001,EUMC,EUMC_T02,2,short_term,pre_treatment,40.8,data/P001/EUMC_T02/image.nii.gz
P001,EUMC,EUMC_T03,3,short_term,pre_treatment,43.1,data/P001/EUMC_T03/image.nii.gz
P001,EUMC,EUMC_T04,4,short_term,pre_treatment,41.7,data/P001/EUMC_T04/image.nii.gz
P001,SNUH,SNUH_T05,5,long_term,post_treatment,28.5,data/P001/SNUH_T05/image.nii.gz
P001,SNUH,SNUH_T06,6,long_term,post_treatment,20.2,data/P001/SNUH_T06/image.nii.gz
P001,SNUH,SNUH_T07,7,long_term,post_treatment,13.6,data/P001/SNUH_T07/image.nii.gz
P001,SNUH,SNUH_T08,8,long_term,recent_follow_up,8.4,data/P001/SNUH_T08/image.nii.gz
```

### 15.2 자동 계산 항목

```txt
촬영 순서 정렬
최대 병변 부피 시점 탐지
최근 촬영 시점 탐지
이전 시점 대비 변화량 계산
이전 시점 대비 변화율 계산
최대 시점 대비 최근 감소량 계산
최대 시점 대비 최근 감소율 계산
발표용 설명 문장 자동 생성
그래프용 JSON 생성
```

---

## 16. ALPLED 확장 가능성

본 Brain MRI 프로젝트는 ALPLED의 도메인 확장 예시로 활용할 수 있다.

ALPLED는 특정 산업에 한정된 플랫폼이 아니라, RFP, 회의록, 기획 자료를 기반으로 다양한 도메인의 개발 산출물을 자동 생성할 수 있는 AI-DLC 문서 생성 플랫폼이다.

의료 AI 분야는 다음 문서가 중요하기 때문에 ALPLED 적용 가능성이 높다.

```txt
요구사항 정의서
사용자 인터페이스 설계서
시스템 아키텍처 설계서
엔티티 관계 모형 설계서
데이터베이스 설계서
통합시험 시나리오
검증 문서
보안 문서
RA 문서
```

### 16.1 Brain MRI 도메인 적용 예시

| 산출물           | Brain MRI 도메인 적용 예시                                  |
| ------------- | ---------------------------------------------------- |
| 사용자 요구사항 정의서  | MRI 업로드, 환자별 검사 이력 조회, 병변 부피 계산, 변화율 분석 요구사항 정의      |
| 사용자 인터페이스 설계서 | MRI 슬라이스 뷰어, 환자별 추적 그래프, 3D 모델 뷰어 화면 설계              |
| 아키텍처 설계서      | DICOM/NIfTI 처리 서버, AI 분석 서버, 의료 데이터 저장소, 접근 제어 구조 설계 |
| 엔티티 관계 모형 설계서 | 환자, 검사, MRI 시리즈, 분석 결과, 부피 변화 이력 엔티티 정의              |
| 데이터베이스 설계서    | 환자 검사 이력, 이미지 메타데이터, 분석 결과 테이블 및 컬럼 정의               |
| 통합시험 시나리오     | MRI 업로드, 분석 요청, 부피 결과 확인, 장기 변화율 검증 테스트 케이스 생성       |

---

## 17. 기대 효과

```txt
장기 Brain MRI 데이터의 체계적 관리
서로 다른 병원 및 장비에서 생성된 MRI 데이터 비교 가능성 확보
병변 또는 종양 의심 영역의 부피 정량화
촬영 시점별 변화량 및 변화율 확인
2D 슬라이스와 3D 모델 기반 시각적 분석
항암제 치료 이후 변화 추세 확인
의료진 및 연구자를 위한 진단 보조 자료 제공
포트폴리오용 의료 AI 웹서비스 구현 사례 확보
ALPLED의 의료 AI 도메인 확장 사례로 활용 가능
```

---

## 18. 주의사항

본 프로젝트는 연구 및 포트폴리오 목적의 MRI 분석 웹서비스 프로토타입이다.

본 시스템의 분석 결과는 의료진의 최종 진단을 대체할 수 없으며, 실제 임상 환경에서 사용하기 위해서는 다음 절차가 필요하다.

```txt
추가 임상 검증
전문의 판독 결과와 비교 검증
의료 데이터 보안 심사
DICOM 비식별화 검증
접근 권한 관리
감사 로그
의료기기 인허가 검토
병원 내부망 배포 구조 검토
모델 성능 검증
```

분석 결과 화면과 보고서에는 다음 문구를 포함한다.

```txt
본 분석 결과는 의료진의 진단을 보조하기 위한 참고 자료이며,
최종 진단 및 치료 판단은 의료 전문가가 수행해야 합니다.
```

---

## 19. 실행 명령어

### 19.1 설치

```bash
pip install -r requirements.txt
```

### 19.2 서버 실행

```bash
uvicorn backend.main:app --reload
```

### 19.3 접속

```txt
http://127.0.0.1:8000
```

### 19.4 API 문서

```txt
http://127.0.0.1:8000/docs
```

---

## 20. 최종 요약

본 프로젝트는 동일 환자의 Brain MRI 데이터를 기반으로 병변 또는 종양 의심 영역의 부피 변화를 추적하는 웹 기반 분석 서비스이다.

이대목동병원 데이터는 병변이 크게 관찰된 단기 집중 촬영 구간으로 활용하고, 서울대병원 데이터는 항암제 이후 최근까지 이어지는 장기 추적 데이터로 활용한다.

시스템은 MRI 업로드, 비식별화, 전처리, segmentation mask 생성, 병변 부피 계산, 3D 모델 생성, 장기 추적 그래프, PDF 보고서를 제공한다.

또한 본 프로젝트는 ALPLED의 의료 AI 도메인 확장 사례로 활용할 수 있으며, 의료 분야에서 요구되는 요구사항 정의, 보안 문서, 검증 문서, 테스트 시나리오 자동 생성 가능성을 보여준다.


