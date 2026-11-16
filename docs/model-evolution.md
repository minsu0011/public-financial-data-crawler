# 수집 모드 설계

| 모드 | 역할 |
| --- | --- |
| `discover` | 다운로드 전 링크와 대상 확인 |
| `recommended` | 연구 우선순위에 따른 원천 수집 |
| `maximum` | 원문·raw 자료를 포함한 광범위 수집 |

수집 우선순위는 MIDAS, Form 3/4/5, 재무·주석, FTD, FINRA short volume, EDGAR logs, Form D, 13F 순서의 자료 수요를 반영합니다. 한 원천의 실패는 개별 로그로 남기고 다른 원천의 수집과 구분합니다.

[실행법](../README.md) · [수집 결과 확인](validation.md)
