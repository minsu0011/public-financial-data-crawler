# 수집 구조

`download_all.py`가 모드·기간·출력 경로를 정하고 `collectors/`의 원천별 탐색기를 실행합니다. 카탈로그에서 대상을 찾은 뒤 다운로드·재시도·이어받기를 수행하고 파일 크기·SHA-256·로그를 남깁니다.

원천 목록은 [metadata](../metadata), 실행 모드는 [README](../README.md)에 있습니다.
