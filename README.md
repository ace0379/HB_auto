# HB Automation

IPETRONIK `.iad` 파일을 CSV/Excel로 변환하고, 선택 채널의 지정 구간 평균값을 Excel로 출력하는 도구입니다.

## 실행

GUI 실행:

```powershell
python main.py
```

CLI 변환:

```powershell
python main.py "D:\Archive\HB_automation\sample.iad"
```

## 주요 기능

- `.iad` 파일에서 `.cha`, `.ird` 추출
- UTF-16 IRD XML 파싱
- 채널명, 단위, 샘플링 정보, 변환식 추출
- 선택 채널 시계열 그래프 표시
- 마우스 휠 줌, 드래그 이동, 더블클릭 평균 구간 지정
- 평균값 및 평균값 - Ambient temperature 계산
- Preview 팝업 확인
- Excel/CSV Export

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
