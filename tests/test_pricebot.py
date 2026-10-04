import json
import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from pricebot import __main__ as cli
from pricebot import checker, config, state
from pricebot.config import COUPANG_DISCLOSURE, Config, Product, Settings
from pricebot.sources import Offer, SourceError, coupang, elevenst, select_offer, webpage

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 4, 9, 17, tzinfo=checker.KST)


def product(**kw):
    base = dict(id="p1", name="에어팟", target_price=250000, source="11st", query="에어팟")
    base.update(kw)
    return Product(**base)


def offer(price, **kw):
    base = dict(title="에어팟 프로 2", price=price, url="https://www.11st.co.kr/products/1",
                product_code="1", mall="11번가")
    base.update(kw)
    return Offer(**base)


class SelectOfferTest(unittest.TestCase):
    offers = [
        offer(9900, title="에어팟 프로 케이스", product_code="10"),
        offer(260000, title="에어팟 프로 2 정품", product_code="20"),
        offer(240000, title="에어팟 프로 2 리퍼", product_code="30"),
        offer(255000, title="Apple 에어팟 프로 2", product_code="40"),
    ]

    def test_filters_accessories_and_takes_cheapest(self):
        p = product(include=["프로"], exclude=["케이스", "리퍼"])
        self.assertEqual(select_offer(p, self.offers).product_code, "40")

    def test_pinned_code_wins(self):
        p = product(product_code="20")
        self.assertEqual(select_offer(p, self.offers).price, 260000)

    def test_pinned_code_missing_raises(self):
        with self.assertRaises(SourceError):
            select_offer(product(product_code="999"), self.offers)

    def test_no_match_raises(self):
        with self.assertRaises(SourceError):
            select_offer(product(include=["버즈"]), self.offers)


class AlertLogicTest(unittest.TestCase):
    def run_once(self, st, price, p=None):
        p = p or product()
        cfg = Config(Settings(), [p])
        outs = checker.run(cfg, st, now=NOW, fetch=lambda _: offer(price))
        for o in outs:
            checker.mark_sent(st, o)
        return outs[0]

    def test_alert_dedup_and_rearm(self):
        st = {}
        self.assertIsNone(self.run_once(st, 260000).alert_price)   # 목표가 위
        self.assertEqual(self.run_once(st, 249000).alert_price, 249000)  # 첫 도달
        self.assertIsNone(self.run_once(st, 249000).alert_price)   # 같은 가격 → 조용
        self.assertIsNone(self.run_once(st, 249500).alert_price)   # 소폭 반등 → 조용
        self.assertEqual(self.run_once(st, 240000).alert_price, 240000)  # 더 하락 → 알림
        self.assertIsNone(self.run_once(st, 270000).alert_price)   # 목표가 위로 복귀 → 재무장
        self.assertIsNone(st["p1"]["last_alert_price"])
        self.assertEqual(self.run_once(st, 245000).alert_price, 245000)  # 다시 도달 → 알림
        self.assertEqual(st["p1"]["lowest_price"], 240000)

    def test_unsent_alert_is_retried(self):
        st = {}
        cfg = Config(Settings(), [product()])
        checker.run(cfg, st, now=NOW, fetch=lambda _: offer(200000))  # mark_sent 안 함 = 전송 실패
        out = checker.run(cfg, st, now=NOW, fetch=lambda _: offer(200000))[0]
        self.assertEqual(out.alert_price, 200000)

    def test_history_only_records_changes(self):
        st = {}
        for price in (260000, 260000, 255000):
            self.run_once(st, price)
        self.assertEqual([h[1] for h in st["p1"]["history"]], [260000, 255000])

    def test_error_warning_once_at_streak(self):
        st = {}
        cfg = Config(Settings(), [product()])

        def boom(_):
            raise SourceError("결과 없음")

        counts = [len(checker.run(cfg, st, now=NOW, fetch=boom)[0].messages) for _ in range(5)]
        self.assertEqual(counts, [0, 0, 1, 0, 0])
        self.run_once(st, 260000)
        self.assertEqual(st["p1"]["error_streak"], 0)

    def test_unexpected_exception_does_not_stop_others(self):
        cfg = Config(Settings(), [product(id="a"), product(id="b")])

        def fetch(p):
            if p.id == "a":
                raise KeyError("x")
            return offer(1)

        outs = checker.run(cfg, {}, now=NOW, fetch=fetch)
        self.assertTrue(outs[0].error)
        self.assertEqual(outs[1].alert_price, 1)

    def test_disabled_products_skipped(self):
        cfg = Config(Settings(), [product(enabled=False)])
        self.assertEqual(checker.run(cfg, {}, now=NOW, fetch=lambda _: offer(1)), [])


class MessageTest(unittest.TestCase):
    def test_plain_link_has_no_disclosure(self):
        msg = checker.format_alert(product(), offer(240000), {}, "DISCLOSE")
        self.assertIn("240,000원", msg)
        self.assertNotIn("DISCLOSE", msg)

    def test_affiliate_link_gets_disclosure(self):
        p = product(affiliate_url="https://partner.example/abc?x=1&y=2")
        msg = checker.format_alert(p, offer(240000), {}, "DISCLOSE")
        self.assertIn("DISCLOSE", msg)
        self.assertIn("x=1&amp;y=2", msg)

    def test_coupang_link_uses_coupang_phrase(self):
        o = offer(240000, affiliate_url="https://link.coupang.com/a/xyz")
        msg = checker.format_alert(product(), o, {}, "DISCLOSE")
        self.assertIn(COUPANG_DISCLOSURE, msg)

    def test_title_is_escaped(self):
        msg = checker.format_alert(product(name="<b>x</b>"), offer(1, title="a & b"), {}, "")
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", msg)
        self.assertIn("a &amp; b", msg)

    def test_new_low_mentioned(self):
        msg = checker.format_alert(product(), offer(240000), {"lowest_price": 250000}, "")
        self.assertIn("최저가 갱신", msg)


class ElevenstParseTest(unittest.TestCase):
    XML = """<?xml version="1.0" encoding="EUC-KR"?>
<ProductSearchResponse><Products><TotalCount>2</TotalCount>
<Product><ProductCode>111</ProductCode><ProductName><![CDATA[<b>에어팟</b> 프로 2]]></ProductName>
<ProductPrice>289,000</ProductPrice><SalePrice>259000</SalePrice><Seller>애플공식</Seller>
<DetailPageUrl><![CDATA[https://www.11st.co.kr/products/111]]></DetailPageUrl></Product>
<Product><ProductCode>222</ProductCode><ProductName>케이스</ProductName>
<ProductPrice>9900</ProductPrice></Product>
</Products></ProductSearchResponse>"""

    def test_parse(self):
        offers = elevenst.parse(self.XML)
        self.assertEqual(len(offers), 2)
        self.assertEqual((offers[0].title, offers[0].price, offers[0].mall), ("에어팟 프로 2", 259000, "애플공식"))
        self.assertEqual(offers[1].url, "https://www.11st.co.kr/products/222")

    def test_error_response(self):
        xml = ('<?xml version="1.0" encoding="EUC-KR"?><ErrorResponse><ErrorCode>003</ErrorCode>'
               "<ErrorMessage>tMall.unregisteredKey</ErrorMessage>"
               "<ErrorDetail>등록되지 않은 OpenAPI Key입니다.</ErrorDetail></ErrorResponse>")
        with self.assertRaisesRegex(SourceError, "등록되지 않은"):
            elevenst.parse(xml)

    def test_search_retries_cp949_on_empty(self):
        empty = '<?xml version="1.0" encoding="EUC-KR"?><ProductSearchResponse><Products/></ProductSearchResponse>'
        responses = [empty.encode("cp949"), self.XML.encode("cp949")]
        urls = []

        def fake_request(url, **_):
            urls.append(url)
            return responses.pop(0), "text/xml;charset=EUC-KR"

        with mock.patch.dict(os.environ, {"ELEVENST_API_KEY": "k"}), \
                mock.patch("pricebot.http.request", fake_request):
            offers = elevenst.search("에어팟")
        self.assertEqual(len(offers), 2)
        self.assertIn("%EC%97%90", urls[0])  # UTF-8 '에'
        self.assertIn("%BF%A1", urls[1])     # CP949 '에'


class WebpageTest(unittest.TestCase):
    def test_jsonld_graph_and_aggregate(self):
        page = """<html><title>샵</title><script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
         {"@type":["Product"],"name":"블렌더","offers":{"@type":"AggregateOffer","lowPrice":"89000","highPrice":"99000"}}]}
        </script></html>"""
        self.assertEqual(webpage.extract(page), ("블렌더", 89000))

    def test_jsonld_offer_list(self):
        page = """<script type="application/ld+json">{"@type":"Product","name":"A",
        "offers":[{"@type":"Offer","price":"120,000"},{"@type":"Offer","price":110000}]}</script>"""
        self.assertEqual(webpage.extract(page)[1], 110000)

    def test_meta_fallback(self):
        page = '<title>X</title><meta property="product:price:amount" content="45000">'
        self.assertEqual(webpage.extract(page), ("X", 45000))

    def test_regex(self):
        page = '<div>"salePrice": 77000</div>'
        self.assertEqual(webpage.extract(page, r'"salePrice":\s*(\d+)')[1], 77000)

    def test_nothing_found(self):
        with self.assertRaises(SourceError):
            webpage.extract("<html></html>")


class CoupangTest(unittest.TestCase):
    def test_authorization_format(self):
        t = time.strptime("2026-10-04 00:17:00", "%Y-%m-%d %H:%M:%S")
        h = coupang.authorization("GET", "/p", "keyword=a&limit=1", "AK", "SK", now=t)
        self.assertTrue(h.startswith("CEA algorithm=HmacSHA256, access-key=AK, signed-date=261004T001700Z, signature="))
        import hashlib, hmac
        expected = hmac.new(b"SK", b"261004T001700ZGET/pkeyword=a&limit=1", hashlib.sha256).hexdigest()
        self.assertTrue(h.endswith(expected))

    def test_search_parses_response(self):
        resp = {"rCode": "0", "data": {"productData": [
            {"productId": 7, "productName": "원두 1kg", "productPrice": 21900,
             "productUrl": "https://link.coupang.com/re/x", "isRocket": True}]}}
        with mock.patch.dict(os.environ, {"COUPANG_ACCESS_KEY": "a", "COUPANG_SECRET_KEY": "s"}), \
                mock.patch("pricebot.http.get_json", return_value=resp):
            [o] = coupang.search("원두")
        self.assertEqual((o.product_code, o.price, o.affiliate_url), ("7", 21900, "https://link.coupang.com/re/x"))

    def test_missing_keys(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(SourceError):
            coupang.search("x")


class ConfigAndCliTest(unittest.TestCase):
    def test_bundled_products_toml_loads(self):
        cfg = config.load(ROOT / "products.toml")
        self.assertGreaterEqual(len(cfg.products), 5)

    def test_unknown_field_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[[products]]\nid="a"\nname="a"\ntarget_price=1\nsource="11st"\ntarget=2\n')
        with self.assertRaisesRegex(config.ConfigError, "target"):
            config.load(f.name)

    def test_check_without_telegram_keeps_alert_pending(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = Path(d, "p.toml")
            cfg_path.write_text('[[products]]\nid="a"\nname="A"\ntarget_price=100\nsource="11st"\nquery="a"\n')
            st_path = Path(d, "s.json")
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch("pricebot.checker.get_offer", return_value=offer(90)), \
                    mock.patch("builtins.print"):
                rc = cli.main(["--config", str(cfg_path), "--state", str(st_path), "check"])
            self.assertEqual(rc, 0)
            saved = json.loads(st_path.read_text())
            self.assertEqual(saved["a"]["last_price"], 90)
            self.assertIsNone(saved["a"].get("last_alert_price"))

    def test_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "x", "s.json")
            state.save(p, {"a": {"name": "한글"}})
            self.assertEqual(state.load(p), {"a": {"name": "한글"}})
            self.assertIn("한글", p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
