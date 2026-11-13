import unittest
from email.message import Message

from check_public_api import check_cors


class CorsPreflightTest(unittest.TestCase):
    origin = 'https://why621-quant-frontend.gallantchip621662.chatgpt.site'

    def headers(self, origin=None, methods='GET, POST, OPTIONS', allowed='Accept, Content-Type, X-Research-Version'):
        headers = Message()
        headers['Access-Control-Allow-Origin'] = origin or self.origin
        headers['Access-Control-Allow-Methods'] = methods
        headers['Access-Control-Allow-Headers'] = allowed
        return headers

    def test_exact_origin_and_research_header_pass(self):
        check_cors(self.headers(), self.origin, True)

    def test_other_origin_or_wildcard_does_not_silently_pass(self):
        for origin in ['https://why621.github.io', '*']:
            with self.assertRaisesRegex(ValueError, 'CORS_ORIGIN_MISSING'):
                check_cors(self.headers(origin), self.origin)

    def test_missing_research_header_is_caught_before_post(self):
        with self.assertRaisesRegex(ValueError, 'CORS_PREFLIGHT_INCOMPLETE'):
            check_cors(self.headers(allowed='Accept,Content-Type'), self.origin, True)

    def test_get_only_does_not_imply_post_is_available(self):
        with self.assertRaisesRegex(ValueError, 'CORS_PREFLIGHT_INCOMPLETE'):
            check_cors(self.headers(methods='GET, OPTIONS'), self.origin, True)


if __name__ == '__main__':
    unittest.main()
