# 🖥️ RenderTracker Architecture

이 문서는 RenderTracker 애플리케이션의 3단계 디렉토리 구조(MVC 패턴 지향)를 설명합니다. AI 에이전트나 새로운 개발자가 앱 구조를 빠르게 파악하고 유지보수할 수 있도록 돕기 위해 작성되었습니다.

## 📁 폴더별 역할 (Directory Structure)

```text
RenderTracker/
│
├── RenderTarget.py        # 🌟 현행 유지 (메인 진입점 및 시스템 트레이 등)
├── architecture.md        # 본 문서
│
├── ui/                    # 1️⃣ 화면 그리기 및 스타일 담당 (View)
│   ├── interface.py       # UI 위젯, 레이아웃 빌더 및 앱 상태 강제 갱신 헬퍼
│   └── styles.py          # CSS 스타일 시트 및 색상/수치 관련 상수 모음
│
├── core/                  # 2️⃣ 핵심 비즈니스 로직 담당 (Model & Logic)
│   ├── engine.py          # 기존의 processor/core 로직. 렌더 상태 전이, 모니터링 폴링 루프 등
│   └── messenger.py       # 디스코드 등 외부 알림 및 웹훅 관련 메서드 집합
│
└── utils/                 # 3️⃣ 공통 유틸리티 및 설정 관리
    ├── path_manager.py    # 파일/폴더 절대경로 추적 (os.path.dirname 연쇄 등)
    ├── config_manager.py  # JSON 환경설정 및 locale 텍스트 로딩 구조 관리
    └── constants.py       # 타임아웃, 업데이트 주기(Polling Interval) 등 전역 매직넘버
```

## 🔄 주요 특징 분석

1. **`RenderTarget.py` 최상단 유지**
   - 사용자 혹은 다른 스크립트가 실행을 지시할 때 제일 윗단에서 접근할 수 있는 `Entry Point(메인 컨트롤러)`입니다.
   - 트레이 아이콘 등을 통제하며, 그 외 `폴링(Polling)` 제어나 UI 조작 등은 각각 `core(engine)`와 `ui(interface)`에 위임합니다.

2. **의존성 규칙**
   - **`ui/`** 는 가급적 화면 표시에 필요한 데이터만 전달받으며, 직접 데이터를 조작하지 않습니다.
   - **`core/`** 는 화면 위젯(`QLabel` 등)을 import 하지 않으며, 오직 데이터(`dict`, `str`, `bool` 등)만을 분석하고 반환합니다.
   - **`utils/`** 는 위 어느 쪽에서도 쉽게 불러들일 수 있는 독립 모듈로 운영됩니다.

---
🚨 **유의 사항 (AI 에이전트용)** 🚨
만약 새로운 로직을 구축하거나 기존 로직을 수정할 경우:
- 파일 임포트 경로는 `from core import engine`, `from ui import interface` 처럼 폴더 경로를 포함하여 선언합니다.
- `utils/path_manager.py`의 `BASE_DIR`는 현재 폴더 깊이에 맞게 두 단계의 상위(`os.path.dirname(os.path.dirname(...))`)를 가리키도록 설정되어 있습니다. 경로 버그가 의심될 때 이를 확인하세요.
