# Public Financial Data Crawler

금융 이벤트 연구에 필요한 공개 원천을 한곳에 내려받는 다운로드 전용 도구다. 사이트별 링크 탐색과 파일 형식, 실패 방식이 달라 같은 데이터를 반복 수집하기 어려워 시작했다. **원천별 수집기를 분리하고 재개·해시·로그를 공통으로 관리**한다. 모델 학습이나 투자 신호 계산은 하지 않는다.

## 구조와 기술

원천 카탈로그 → 링크 탐색 → 모드별 대상 선택 → 다운로드·재시도 → 파일 검증·SHA-256 → 다운로드 트리와 로그

- [download_all.py](download_all.py): 전체 실행과 모드 선택
- [collectors](collectors): SEC·FINRA 등 원천별 수집기
- [metadata](metadata): 175개 공개 원천 카탈로그와 직접 링크 목록

Python과 HTTP 수집 라이브러리, CSV/JSON 메타데이터, Windows batch launcher를 사용한다. 개별 provider의 파서와 공통 다운로드 처리를 분리했다.

## 수집 대상과 우선순위

MIDAS → 실제 Form 3/4/5 → Financial Statements & Notes → FTD → FINRA short volume → EDGAR logs → Form D → 13F 순서의 연구 수요를 반영했다. Regulation A, crowdfunding, N-PORT, SEC bulk 및 다른 공공 데이터 원천도 카탈로그에 포함한다.

카탈로그에 있다는 사실과 다운로드에 성공했다는 사실은 다르다. 오래된 링크·접근 제한·원천별 보유 기간은 실제 로그에서 확인해야 한다. 공개 링크가 있다고 재배포 권리까지 자동으로 생기는 것은 아니다.

## 개발 과정과 선택

1. **원천을 카탈로그로 분리했다.** 코드 수정 없이 수집 후보와 직접 링크의 근거를 추적할 수 있게 했다.
2. **탐색과 다운로드를 나눴다.** discover 모드는 링크만 확인하고, recommended와 maximum은 범위를 다르게 둔다.
3. **개별 사이트 실패를 격리했다.** 한 원천의 403·404가 전체 수집의 종료 조건이 되지 않게 했다.
4. **재실행 비용을 줄였다.** 기존 파일과 부분 다운로드를 확인하고 서버가 지원하는 범위에서 이어받는다.
5. **완료 여부의 근거를 남겼다.** 파일 크기·해시·로그를 기록한다. SHA-256 일치는 전송된 파일의 동일성을 뜻하며 금융 데이터의 의미까지 보증하지 않는다.

## 실행

작은 범위부터 확인하는 경우:

```powershell
python -m pip install -r requirements.txt
python download_all.py --email researcher@example.com --mode discover --output DOWNLOADED_DATA
```

이메일은 SEC 요청 식별용으로 실제 연락 가능한 주소로 바꾼다. 주요 파일은 `--mode recommended`, 광범위 수집은 `--mode maximum`으로 실행한다.

[RUN_DISCOVER_ONLY.bat](RUN_DISCOVER_ONLY.bat), [RUN_RECOMMENDED.bat](RUN_RECOMMENDED.bat), [RUN_MAXIMUM.bat](RUN_MAXIMUM.bat)도 같은 용도의 Windows 진입점이다. maximum의 SEC 원문·FINRA raw 범위는 매우 커질 수 있으므로 출력 디스크 여유를 먼저 확인한다.

## 결과와 한계

결과는 지정한 출력 폴더의 원천별 파일과 다운로드 기록이다. 다운로드 성공 수·실패 사유·재시도 가능 여부로 결과를 판단하며 ML 성능표는 만들지 않는다. rate limit, 변경된 링크, 부분 파일의 서버 지원 여부에 따라 완료 범위가 달라진다.

원천별 데이터 준비는 [data/README.md](data/README.md), 사용 범위는 [ATTRIBUTION.md](ATTRIBUTION.md), 실행 확인 범위는 [테스트 범위](docs/testing-notes.md)에 정리했다. 이 프로젝트는 다운로드 흐름 하나를 중심으로 하므로 별도 Wiki 대신 README와 원천 카탈로그를 읽으면 된다.
