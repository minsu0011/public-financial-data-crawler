# 실행 확인

```powershell
python download_all.py --help
python download_all.py --email researcher@example.com --mode discover --output DOWNLOADED_DATA
```

첫 명령은 인자를, 두 번째는 원천 링크 탐색을 확인합니다. 이메일은 SEC 요청 식별용 주소로 바꿉니다. 실제 파일 수집은 `recommended` 또는 `maximum` 모드에서 수행합니다.

수집 뒤 점검 항목은 [결과 확인](validation.md)에 있습니다.
