import unittest
from access_probe import access_blocked, PROBES

class AccessContractTests(unittest.TestCase):
    def test_denied(self):
        for status in (401, 403):
            self.assertTrue(access_blocked(status, None))

    def test_allowed_access_login(self):
        for status in (302, 303, 307, 308):
            for url in (
                "https://terrabid.cloudflareaccess.com/cdn-cgi/access/login/hydra",
                "/cdn-cgi/access/login",
            ):
                self.assertTrue(access_blocked(status, url))

    def test_reject_wrong_target_or_success(self):
        for status, url in (
            (200, None), (204, None), (404, None), (500, None),
            (302, None), (302, "https://example.invalid/cdn-cgi/access/login"),
            (302, "http://terrabid.cloudflareaccess.com/cdn-cgi/access/login"),
            (302, "https://terrabid.cloudflareaccess.com.evil.invalid/cdn-cgi/access/login"),
            (302, "https://user@terrabid.cloudflareaccess.com/cdn-cgi/access/login"),
            (302, "https://terrabid.cloudflareaccess.com:8443/cdn-cgi/access/login"),
            (302, "https://terrabid.cloudflareaccess.com/other"),
            (302, "https://terrabid.cloudflareaccess.com/cdn-cgi/access/loginfoo"),
        ):
            self.assertFalse(access_blocked(status, url), (status, url))

    def test_no_paid_mutations(self):
        self.assertEqual([(method,path) for method,path,_ in PROBES if method != "GET"],
                         [("POST","/v1/marketplace/compare")])

if __name__ == "__main__":
    unittest.main()
