# HB Automation

IPETRONIK `.iad` 파일을 CSV/Excel로 변환하고, 선택 채널의 지정 구간 평균값을 Excel로 출력하는 도구입니다.

## 실행

```powershell
python main.py
```

인자를 주면 CLI 변환기로도 동작합니다.

```powershell
python main.py "D:\Archive\HB_automation\sample.iad"
```

## 버전관리

- 현재 버전은 `VERSION` 파일에서 관리합니다.
- 변경 이력은 `CHANGELOG.md`에 기록합니다.
- 큰 원본 데이터와 변환 산출물은 Git에 넣지 않습니다.

권장 릴리스 흐름:

```powershell
git status
git add .
git commit -m "Release v0.1.0 baseline"
git tag v0.1.0
```
