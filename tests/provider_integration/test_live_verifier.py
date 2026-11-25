"""T5.2: live token checker (JwtContextVerifier and JwksClient).

Offline: synthetic ES256 keys, fake JWKS over httpx.MockTransport.
"""

import base64
import json
import unittest

import httpx
import jwt
from jwt.algorithms import ECAlgorithm

from services.provider_integration import Binding, ContextKind, CredentialSource, ErrorCode, Operation, Target
from services.provider_integration.errors import ProviderIntegrationError
from services.provider_integration.live.config import load_live_settings
from services.provider_integration.live.verifier import JwksClient, JwtContextVerifier, parse_binding_claim

from live_fixtures import (
    AUDIENCE,
    BINDING,
    DROP,
    REF_B,
    SCOPE_B,
    ENV,
    GENERATE,
    NOW,
    SERVICE_SECRET,
    TRANSCRIBE,
    Clock,
    FakeBackend,
    SigningKey,
    settings,
    wall,
)

GEN_TARGET = Target(Operation.GENERATE_TEXT, "gpt-4o-mini")
TR_TARGET = Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")
BOTH = frozenset({GEN_TARGET, TR_TARGET})


def binding(**overrides):
    values = dict(BINDING)
    values.update(overrides)
    return parse_binding_claim(values)  # the same conversion the live code uses (T5.6)


class Rig:
    def __init__(self, keys=None, now=NOW, **setting_overrides):
        self.keys = keys or [SigningKey("key-1")]
        self.backend = FakeBackend(self.keys)
        self.settings = settings(**setting_overrides)
        self.clock = Clock(1000.0)
        self.jwks = JwksClient(self.settings, transport=self.backend.transport(), clock=self.clock)
        self.verifier = JwtContextVerifier(self.settings, jwks=self.jwks, wall_clock=wall(now))


class VerifierTestCase(unittest.IsolatedAsyncioTestCase):
    async def assertDenied(self, rig, token, *, kind=ContextKind.INVOKE, targets=frozenset({GEN_TARGET}), requested=None):
        with self.assertRaises(ProviderIntegrationError) as caught:
            await rig.verifier.verify(token, requested or binding(), kind, targets)
        self.assertIs(caught.exception.code, ErrorCode.ACCESS_DENIED)
        if isinstance(token, str) and token:
            self.assertNotIn(token, repr(caught.exception) + str(caught.exception))


class ValidTokenTests(VerifierTestCase):
    async def test_valid_token_returns_bound_context(self):
        rig = Rig()
        token = rig.keys[0].token(jti="req-123")
        context = await rig.verifier.verify(token, binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        self.assertEqual(context.binding, binding())
        self.assertEqual(context.request_id, "req-123")
        self.assertIs(context.kind, ContextKind.INVOKE)
        self.assertEqual(context.allowed_targets, BOTH)
        self.assertEqual(context.expires_at.timestamp(), NOW + 90)
        self.assertEqual(context.credential_token.reveal_for_session(), token)
        self.assertNotIn(token, repr(context))

    async def test_jwks_call_uses_service_secret_and_exact_url(self):
        rig = Rig()
        await rig.verifier.verify(rig.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        request = rig.backend.jwks_requests()[0]
        self.assertEqual(str(request.url), "https://backend.example.test/internal/jwks/")
        self.assertEqual(request.headers["authorization"], f"Bearer {SERVICE_SECRET}")
        self.assertEqual(request.method, "GET")

    async def test_keys_are_cached(self):
        rig = Rig()
        for _ in range(3):
            await rig.verifier.verify(rig.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        self.assertEqual(rig.jwks.fetches, 1)

    async def test_platform_source_and_validate_kind(self):
        rig = Rig()
        token = rig.keys[0].token(kind="validate", targets=[dict(GENERATE)],
                                  binding=dict(BINDING, credential_source="platform"))
        context = await rig.verifier.verify(token, binding(credential_source="platform"),
                                            ContextKind.VALIDATE, frozenset({GEN_TARGET}))
        self.assertIs(context.binding.credential_source, CredentialSource.PLATFORM)

    async def test_clock_skew_edges(self):
        rig_late = Rig(now=NOW + 90 + 29)  # 29 s after expiry: inside skew
        await rig_late.verifier.verify(rig_late.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        rig_early = Rig(now=NOW - 29)  # 29 s before nbf: inside skew
        await rig_early.verifier.verify(rig_early.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))


class RejectedTokenTests(VerifierTestCase):
    async def test_claim_tampering_is_denied(self):
        cases = {
            "wrong issuer": dict(iss="someone-else"),
            "wrong audience": dict(aud="other-service"),
            "missing jti": dict(jti=DROP),
            "missing exp": dict(exp=DROP),
            "missing iat": dict(iat=DROP),
            "missing nbf": dict(nbf=DROP),
            "bad jti": dict(jti="has space"),
            "lifetime too long": dict(exp=int(NOW) + 91),
            "exp before iat": dict(exp=int(NOW) - 1),
            "boolean exp": dict(exp=True),
            "wrong kind": dict(kind="validate"),
            "unknown kind": dict(kind="admin"),
            "missing binding": dict(binding=DROP),
            "extra binding field": dict(binding=dict(BINDING, role="admin")),
            "binding not object": dict(binding="scope-A"),
            "missing targets": dict(targets=DROP),
            "empty targets": dict(targets=[]),
            "bad target": dict(targets=[{"operation": "delete_everything", "model": "gpt-4o-mini"}]),
            "target extra field": dict(targets=[dict(GENERATE, destination="https://evil.example.test")]),
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                rig = Rig()
                await self.assertDenied(rig, rig.keys[0].token(**overrides))

    async def test_binding_mismatch_is_denied_for_every_field(self):
        for field_name, other in (("scope_id", SCOPE_B), ("credential_ref", REF_B),
                                  ("credential_version", 2), ("credential_source", "platform"),
                                  ("provider", "other-provider")):
            with self.subTest(field=field_name):
                rig = Rig()
                await self.assertDenied(rig, rig.keys[0].token(), requested=binding(**{field_name: other}))

    async def test_requested_targets_must_be_in_token(self):
        rig = Rig()
        token = rig.keys[0].token(targets=[dict(GENERATE)])
        await self.assertDenied(rig, token, targets=frozenset({GEN_TARGET, TR_TARGET}))

    async def test_validate_token_must_name_exactly_one_target(self):
        rig = Rig()
        token = rig.keys[0].token(kind="validate")
        await self.assertDenied(rig, token, kind=ContextKind.VALIDATE, targets=frozenset({GEN_TARGET}))

    async def test_time_window(self):
        for name, now in (("expired beyond skew", NOW + 90 + 30), ("not yet valid beyond skew", NOW - 31)):
            with self.subTest(case=name):
                rig = Rig(now=now)
                await self.assertDenied(rig, rig.keys[0].token())

    async def test_forged_algorithms_and_signatures(self):
        rig = Rig()
        good = rig.keys[0].token()
        header, payload, _ = good.split(".")

        def b64(data):
            return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

        unsigned = b64({"alg": "none", "kid": "key-1", "typ": "JWT"}) + "." + payload + "."
        claims = jwt.decode(good, options={"verify_signature": False})
        hs256 = b64({"alg": "HS256", "kid": "key-1"}) + "." + payload + ".c2lnbmF0dXJl"
        impostor = SigningKey("key-1").token()  # same kid, different private key
        tampered = header + "." + b64(dict(claims, binding=dict(BINDING, scope_id=SCOPE_B))) + "." + good.split(".")[2]
        cases = {"alg none": unsigned, "HS256": hs256, "wrong key, same kid": impostor, "edited payload": tampered,
                 "garbage": "not-a-token", "empty": "", "non-string": 12345, "too long": "a" * 9000}
        for name, token in cases.items():
            with self.subTest(case=name):
                await self.assertDenied(rig, token)

    async def test_replayed_token_is_denied(self):
        rig = Rig()
        token = rig.keys[0].token()
        await rig.verifier.verify(token, binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        await self.assertDenied(rig, token)

    async def test_inspect_does_not_consume_the_token(self):
        rig = Rig()
        token = rig.keys[0].token()
        claims = await rig.verifier.inspect(token)
        self.assertEqual(claims["binding"], BINDING)
        await rig.verifier.verify(token, binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))


class KeyRotationTests(VerifierTestCase):
    async def test_unknown_kid_triggers_one_refetch(self):
        """C-1: a token signed with a newly published key still verifies."""
        old, new = SigningKey("key-1"), SigningKey("key-2")
        rig = Rig(keys=[old])
        await rig.verifier.verify(old.token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        rig.backend.keys = [old, new]
        rig.clock.value += 11  # past the minimum refresh interval
        await rig.verifier.verify(new.token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        self.assertEqual(rig.jwks.fetches, 2)

    async def test_unknown_kid_refetch_is_rate_limited(self):
        rig = Rig()
        await rig.verifier.verify(rig.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        stranger = SigningKey("key-9")
        for _ in range(5):
            await self.assertDenied(rig, stranger.token())
        self.assertEqual(rig.jwks.fetches, 1)

    async def test_bad_jwks_responses_deny(self):
        cases = {
            "500": dict(jwks_status=500),
            "not a key list": dict(jwks_override={"keys": "nope"}),
            "private key published": dict(jwks_override=None, private=True),
            "wrong curve": dict(jwks_override=None, curve="P-384"),
            "redirect": dict(jwks_status=302),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                rig = Rig()
                if "jwks_status" in change:
                    rig.backend.jwks_status = change["jwks_status"]
                if change.get("jwks_override") is not None:
                    rig.backend.jwks_override = change["jwks_override"]
                if change.get("private"):
                    # A real private JWK for the signing key: it would verify if it were accepted.
                    jwk = ECAlgorithm.to_jwk(rig.keys[0].private, as_dict=True)
                    jwk.update({"kid": "key-1", "alg": "ES256"})
                    rig.backend.jwks_override = {"keys": [jwk]}
                if change.get("curve"):
                    jwk = rig.keys[0].jwk()
                    jwk["crv"] = change["curve"]
                    rig.backend.jwks_override = {"keys": [jwk]}
                await self.assertDenied(rig, rig.keys[0].token())

    async def test_backend_unreachable_denies(self):
        rig = Rig()
        rig.backend.raise_error = httpx.ConnectError("refused")
        await self.assertDenied(rig, rig.keys[0].token())


class SettingsTests(unittest.TestCase):
    def test_all_settings_required_and_validated(self):
        self.assertIsNotNone(load_live_settings(ENV))
        bad = {
            "FLOBRAIN_BACKEND_URL": ["http://backend.example.test", "https://backend.example.test/api",
                                     "https://user:pw@backend.example.test", "", None],
            "MULTIMODAL_SERVICE_SECRET": ["short", " " + SERVICE_SECRET, None],
            "CREDENTIAL_JWT_ISSUER": ["", " padded", None],
            "CREDENTIAL_JWT_AUDIENCE": ["", None],
            "PROVIDER_APPROVED_TARGETS": ["", "gpt-4o-mini", "generate_text:bad model", "delete:gpt-4o-mini", None],
        }
        for name, values in bad.items():
            for value in values:
                with self.subTest(setting=name, value=repr(value)[:30]):
                    env = dict(ENV)
                    if value is None:
                        del env[name]
                    else:
                        env[name] = value
                    self.assertIsNone(load_live_settings(env))

    def test_secret_is_redacted(self):
        live = load_live_settings(ENV)
        self.assertNotIn(SERVICE_SECRET, repr(live))
        self.assertEqual(live.token_audience, AUDIENCE)


if __name__ == "__main__":
    unittest.main()


class ReviewFixTests(VerifierTestCase):
    """Independent review findings of 2026-11-18 (fixes 1, 4, 5, 6 and the exception-context note)."""

    async def test_non_finite_and_disordered_time_claims_are_denied(self):
        cases = {
            "iat NaN": dict(iat=float("nan"), exp=int(NOW) + 315_360_000),
            "nbf NaN": dict(nbf=float("nan")),
            "exp infinity": dict(exp=float("inf")),
            "iat negative infinity": dict(iat=float("-inf")),
        }
        for name, overrides in cases.items():
            with self.subTest(case=name):
                rig = Rig()
                await self.assertDenied(rig, rig.keys[0].token(**overrides))
        # nbf after exp, checked at a moment where every other time rule would pass.
        rig = Rig(now=NOW + 80)
        await self.assertDenied(rig, rig.keys[0].token(nbf=int(NOW) + 95))

    async def test_encryption_keys_and_duplicate_kids_are_refused(self):
        rig = Rig()
        jwk = rig.keys[0].jwk()
        jwk["use"] = "enc"
        rig.backend.jwks_override = {"keys": [jwk]}
        await self.assertDenied(rig, rig.keys[0].token())
        rig = Rig()
        # The real key is listed last, so only the duplicate rule can refuse this document.
        rig.backend.jwks_override = {"keys": [SigningKey("key-1").jwk(), rig.keys[0].jwk()]}
        await self.assertDenied(rig, rig.keys[0].token())

    async def test_cached_keys_survive_a_short_outage_but_not_the_hard_limit(self):
        rig = Rig()
        await rig.verifier.verify(rig.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        rig.backend.jwks_status = 503
        rig.clock.value += 301  # cache expired, refresh fails, last good keys still within 10 minutes
        await rig.verifier.verify(rig.keys[0].token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        rig.clock.value += 300  # now 601 s since the last successful fetch
        await self.assertDenied(rig, rig.keys[0].token())

    async def test_key_removed_by_backend_stops_working_after_refresh(self):
        old, new = SigningKey("key-1"), SigningKey("key-2")
        rig = Rig(keys=[old])
        await rig.verifier.verify(old.token(), binding(), ContextKind.INVOKE, frozenset({GEN_TARGET}))
        rig.backend.keys = [new]
        rig.clock.value += 301
        await self.assertDenied(rig, old.token())

    async def test_backend_errors_keep_no_exception_context(self):
        from services.provider_integration.live._http import BackendCallError, call_backend
        backend = FakeBackend([])
        backend.raise_error = httpx.ConnectError("refused")
        with self.assertRaises(BackendCallError) as caught:
            await call_backend(settings(), "GET", "/internal/jwks/", timeout_seconds=1, transport=backend.transport())
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)

    async def test_default_transport_ignores_environment_tls_and_proxy_settings(self):
        from unittest import mock
        from services.provider_integration.live import _http
        captured = {}

        class Stop(Exception):
            pass

        def fake_transport(**kwargs):
            captured.update(kwargs)
            raise Stop()

        with mock.patch.object(_http.httpx, "AsyncHTTPTransport", side_effect=fake_transport):
            with self.assertRaises(Stop):
                await _http.call_backend(settings(), "GET", "/internal/jwks/", timeout_seconds=1)
        self.assertIs(captured.get("trust_env"), False)
        self.assertIs(captured.get("verify"), True)
        self.assertEqual(captured.get("retries"), 0)


class CredentialVersionFormatTests(VerifierTestCase):
    """T5.6: Ofon's confirmed format (C-4) sends credential_version as a whole number."""

    async def test_numeric_versions_are_accepted_and_kept_exact(self):
        for version in (1, 2, 41, 999_999):
            with self.subTest(version=version):
                rig = Rig()
                token = rig.keys[0].token(binding=dict(BINDING, credential_version=version))
                context = await rig.verifier.verify(token, binding(credential_version=version),
                                                    ContextKind.INVOKE, frozenset({GEN_TARGET}))
                self.assertEqual(context.binding.credential_version, str(version))

    async def test_other_version_types_are_refused(self):
        for name, version in (("text", "1"), ("prefixed text", "v1"), ("zero", 0), ("negative", -1),
                              ("boolean", True), ("decimal", 1.0), ("too large", 10 ** 13), ("missing", None)):
            with self.subTest(case=name):
                rig = Rig()
                claim = dict(BINDING, credential_version=version)
                if version is None:
                    del claim["credential_version"]
                await self.assertDenied(rig, rig.keys[0].token(binding=claim))

    async def test_version_mismatch_between_token_and_request_is_denied(self):
        rig = Rig()
        token = rig.keys[0].token(binding=dict(BINDING, credential_version=1))
        await self.assertDenied(rig, token, requested=binding(credential_version=2))

    async def test_platform_key_with_platform_scope(self):
        """C-6: company keys use credential_source 'platform' and scope_id 'platform'."""
        rig = Rig()
        claim = dict(BINDING, scope_id="platform", credential_source="platform")
        context = await rig.verifier.verify(rig.keys[0].token(binding=claim),
                                            binding(scope_id="platform", credential_source="platform"),
                                            ContextKind.INVOKE, frozenset({GEN_TARGET}))
        self.assertEqual((context.binding.scope_id, context.binding.credential_source.value), ("platform", "platform"))


class VersionParsingTests(unittest.TestCase):
    """T5.6: the version rule itself, isolated from any other binding comparison."""

    def test_only_positive_whole_numbers_parse(self):
        self.assertEqual(parse_binding_claim(dict(BINDING, credential_version=1)).credential_version, "1")
        for name, version in (("text", "1"), ("prefixed text", "v1"), ("zero", 0), ("negative", -3),
                              ("boolean", True), ("decimal", 2.0), ("too large", 10 ** 13), ("none", None)):
            with self.subTest(case=name), self.assertRaises(ProviderIntegrationError) as caught:
                parse_binding_claim(dict(BINDING, credential_version=version))
            self.assertIs(caught.exception.code, ErrorCode.ACCESS_DENIED)
