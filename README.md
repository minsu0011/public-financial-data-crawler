# Public Financial Data Crawler

SEC·FINRA 등 공개 금융 원천의 링크를 탐색하고 파일을 수집하는 Python 도구입니다. 원천별 수집기를 분리하고 재시도·이어받기·SHA-256·로그를 공통으로 관리합니다.

## 구성

- [download_all.py](download_all.py): 전체 실행과 수집 모드
- [collectors](collectors): 원천별 링크 탐색과 다운로드
- [metadata](metadata): 공개 원천 카탈로그와 직접 링크 목록

Form 3/4/5, Financial Statements & Notes, FTD, short volume, EDGAR logs, Form D, 13F 등을 다룹니다. 카탈로그 항목의 실제 가용 여부는 수집 로그로 확인합니다.

## 실행

```powershell
python -m pip install -r requirements.txt
python download_all.py --email researcher@example.com --mode discover --output DOWNLOADED_DATA
```

이메일은 SEC 요청 식별용으로 실제 연락 가능한 주소를 사용합니다.

| 모드 | 동작 |
| --- | --- |
| `discover` | 링크 탐색 |
| `recommended` | 우선순위 원천 수집 |
| `maximum` | 광범위 수집; 저장 공간과 실행 시간 확인 필요 |

Windows에서는 `RUN_DISCOVER_ONLY.bat`, `RUN_RECOMMENDED.bat`, `RUN_MAXIMUM.bat`도 사용할 수 있습니다.

수집 결과는 원천별 파일과 다운로드 기록으로 남습니다. 접근 제한, 링크 변경과 서버의 이어받기 지원 여부에 따라 완료 범위가 달라집니다.

[데이터 안내](data/README.md) · [실행 확인 범위](docs/testing-notes.md) · [이용 조건](ATTRIBUTION.md)

[전체 문서 안내](docs/README.md)
