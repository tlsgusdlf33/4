# pricebot — 가격 하락 알림 봇 (개인용 → 제휴 수익화)

갖고 싶은 상품과 목표가를 `products.toml`에 적어 두면, GitHub Actions가 하루 4번 가격을 확인하고
목표가 이하로 떨어졌을 때 텔레그램으로 알려 줍니다. 서버가 필요 없고 비용은 0원입니다.

- Python 3.11+ 표준 라이브러리만 사용 (설치할 패키지 없음)
- 가격 출처: **11번가 Open API** / **쿠팡 파트너스 API** / **상품 페이지(JSON-LD)**. 출처는 상품마다 고를 수 있음
- 같은 하락 구간에서는 한 번만 알림. 더 떨어지면 다시 알리고, 목표가 위로 올라갔다 다시 내려오면 또 알림
- 제휴 링크가 붙은 알림에는 대가성 문구가 **자동으로** 들어감
- 3회 연속 가격 확인에 실패하면 텔레그램으로 한 번 경고

## ⚠️ 원래 계획에서 바뀐 점: 네이버 쇼핑 검색 API 종료

처음 아이디어는 "네이버 쇼핑 API로 가격 확인"이었지만, 네이버 검색 API의 **쇼핑 검색은
2026-07-31에 종료됐고 대체 API도 없습니다** (기존 키도 쓸 수 없음). API HUB로 옮겨 간
Shopping Insight는 클릭 추이만 주고 가격·상품 URL은 주지 않습니다.
그래서 가격 출처를 바꿔 끼울 수 있는 구조로 만들고, 바로 쓸 수 있는 무료 출처로 11번가 Open API를 넣었습니다.

## 가입 조건 정리 (2026-10 기준)

| 서비스 | 용도 | 조건 / 제한 |
|---|---|---|
| 텔레그램 봇 | 알림 발송 | 무료. @BotFather에서 즉시 발급 |
| 11번가 Open API | 가격 확인 (지금 바로) | 무료. [OPENAPI CENTER](https://openapi.11st.co.kr)에서 회원가입 후 키 발급. 키당 서비스별 **하루 5,000회** |
| 쿠팡 파트너스 (링크) | 제휴 수수료 | 가입 즉시 대시보드에서 링크 생성 가능. 단 **정산은 최종 승인 후** |
| 쿠팡 파트너스 API | 쿠팡 가격 확인 + 자동 제휴 링크 | **최종 승인 후에만 키 발급**. 최종 승인은 **누적 판매금액 15만 원 이상**이 되면 심사. 검색 API **시간당 10회** |
| 네이버 쇼핑 검색 API | — | **2026-07-31 종료** (대체 없음) |

즉 순서는 이렇습니다.

1. **지금**: 11번가 키 + 텔레그램으로 개인용 봇 운영
2. **쿠팡 파트너스 가입**: 대시보드에서 상품 링크를 직접 만들어 `affiliate_url`에 넣기
   (쿠팡 링크는 쿠팡 가격 기준이어야 하므로, 이 경우 그 상품의 가격 출처도 쿠팡과 맞아야 함. 아래 주의 참고)
3. **누적 15만 원 달성 → 최종 승인**: API 키를 받아 `source = "coupang"`으로 전환하면 가격 확인과 제휴 링크가 자동

## 설치 (10분)

### 1. 텔레그램 봇 만들기
1. 텔레그램에서 `@BotFather` → `/newbot` → 토큰을 받습니다.
2. 만든 봇에게 아무 메시지나 보냅니다.
3. chat_id를 확인합니다.
   ```bash
   TELEGRAM_BOT_TOKEN=123:abc python -m pricebot chat-id
   ```

### 2. 11번가 Open API 키
[OPENAPI CENTER](https://openapi.11st.co.kr)에 가입한 뒤 서비스를 등록하고 32자리 키를 받습니다.

### 3. 상품 등록
`products.toml`의 예시 5개를 내가 사려던 상품으로 바꿉니다. 정확하게 추적하려면 상품코드를 고정하세요.
```bash
ELEVENST_API_KEY=... python -m pricebot search 11st "에어팟 프로 2세대 USB-C"
#    259,000원  code=1234567890    Apple 에어팟 프로 2세대 USB-C ...  [애플공식]
#      9,900원  code=2222222222    에어팟 프로 케이스 ...
```
→ `product_code = "1234567890"`. 코드를 고정하지 않으면 `include`/`exclude` 조건에 맞는 결과 중 최저가를 추적합니다.
케이스·필름 같은 액세서리를 거르려면 `exclude`를 꼭 채우세요.

### 4. 로컬에서 확인
```bash
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... ELEVENST_API_KEY=...
python -m pricebot test-alert        # 텔레그램 연결 테스트
python -m pricebot check --dry-run   # 전송·저장 없이 결과만 보기
python -m pricebot check             # 실제 실행 (알림 + state/prices.json 저장)
python -m pricebot status            # 저장된 현재가/최저가 보기
```

### 5. GitHub Actions로 자동 실행
저장소 **Settings → Secrets and variables → Actions**에 아래 값을 등록합니다.

| Secret | 필수 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ |
| `TELEGRAM_CHAT_ID` | ✅ |
| `ELEVENST_API_KEY` | 11번가 출처를 쓸 때 |
| `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` | 쿠팡 최종 승인 후 |

`.github/workflows/price-check.yml`이 KST 09:17 / 13:17 / 17:17 / 21:17에 실행되고, 결과 상태를
`state/prices.json`으로 커밋합니다. **Actions 탭 → price-check → Run workflow**로 바로 돌려 볼 수 있습니다.

- 위시리스트가 공개되는 게 싫다면 저장소를 **private**으로 두세요 (실행 1회 1분 미만 → 월 무료 한도 안).
- 공개 저장소에서는 60일 동안 활동이 없으면 예약 실행이 꺼집니다. 이 봇은 가격이 바뀔 때마다 상태를 커밋하지만, 꺼졌다면 Actions 탭에서 다시 켜면 됩니다.

## 가격 출처별 설정

```toml
[[products]]
id = "airpods-pro2"         # 상태 저장 키
name = "에어팟 프로 2"
target_price = 250000
source = "11st"             # "11st" | "coupang" | "webpage"
query = "에어팟 프로 2세대"   # 11st / coupang
include = ["에어팟", "프로"]
exclude = ["케이스", "필름", "중고", "리퍼"]
product_code = ""           # search 명령으로 찾은 코드
url = ""                    # webpage: 상품 페이지 주소
price_regex = ""            # webpage: JSON-LD/메타태그가 없을 때 (\d+) 그룹 1개
affiliate_url = ""          # 직접 만든 제휴 링크
enabled = true
```

- **webpage** 출처는 `robots.txt`가 막은 페이지는 읽지 않습니다. 쿠팡·네이버처럼 자동 수집을 약관으로
  금지하거나 봇을 차단하는 사이트에는 쓰지 마세요. 브랜드 공식몰처럼 JSON-LD(`schema.org/Product`)를 제공하는 곳에 적합합니다.
- **affiliate_url**에는 *가격을 확인한 바로 그 상품·그 몰*의 링크만 넣으세요. 11번가 가격으로 알리고
  쿠팡 링크를 달면 사용자가 보는 가격이 달라져 신뢰를 잃고, 표시광고 문제도 생길 수 있습니다.

## 제휴 고지 (필수)

제휴 링크가 들어간 알림에는 문구가 자동으로 붙습니다.

- 쿠팡 링크: `이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.`
- 그 외 제휴 링크: `products.toml`의 `[settings].disclosure`

지인에게 봇을 공유할 때도 이 문구는 지우지 마세요 (공정위 추천·보증 심사지침, 쿠팡 파트너스 운영정책).

## 다음 단계 (사용자 늘리기)

지금은 한 사람(한 chat_id)용입니다. 지인이 쓰기 시작하면:
1. 텔레그램 **채널**을 만들어 봇을 관리자로 넣고, 채널 chat_id(`-100...`)를 `TELEGRAM_CHAT_ID`로 → 여러 명이 같은 알림을 받음
2. 사용자별 위시리스트가 필요해지면 텔레그램 명령(`/add`, `/list`)과 DB(예: Cloudflare Workers + D1)로 확장

## 개발

```bash
python -m unittest -v
```

구조:
```
pricebot/
  __main__.py      CLI (check, search, status, chat-id, test-alert, deeplink)
  checker.py       알림 판단·메시지·상태 갱신
  config.py        products.toml 로더, 고지 문구
  notify.py        텔레그램
  sources/         11st, coupang, webpage + 상품 선택(select_offer)
state/prices.json  가격 기록 (Actions가 커밋)
```
