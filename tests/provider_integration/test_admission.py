"""T2.2 admission tests: exact-version scoped reads, lifecycle ordering, isolation.

Reader-level portions of TC-02, TC-03, TC-05, TC-06 and TC-13 using the
test-only fakes. Orchestrator re-checks and provider call counts are T2.3.
"""

import asyncio
import os
import pathlib
import traceback
import unittest
from datetime import timedelta
from unittest import mock

import services.provider_integration as production
from services.provider_integration import (
    Binding,
    ContextKind,
    CredentialSource,
    CredentialState,
    ErrorCode,
    Operation,
    ProviderIntegrationError,
    Target,
    ValidationResult,
    ValidationStatus,
    VerifiedContext,
    new_request_id,
)

from fakes import FakeClock, FakeContextVerifier, FakeCredentialStore, PauseGate, network_guard_patchers

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "services" / "provider_integration"
FAKES_PATH = pathlib.Path(__file__).resolve().parent / "fakes.py"

GEN = Target(Operation.GENERATE_TEXT, "gpt-4o-mini")
TRANSCRIBE = Target(Operation.TRANSCRIBE_AUDIO, "gpt-4o-mini-transcribe")
BOTH = frozenset({GEN, TRANSCRIBE})

KEY_A1 = "test-provider-key-scope-a-v1"
KEY_A2 = "test-provider-key-scope-a-v2"
KEY_A3 = "test-provider-key-scope-a-v3"
KEY_B1 = "test-provider-key-scope-b-v1"
ENV_CANARY = "test-provider-key-environment-canary"

_patches = []


def setUpModule():
    for patcher in network_guard_patchers():
        patcher.start()
        _patches.append(patcher)


def tearDownModule():
    while _patches:
        _patches.pop().stop()


def make_binding(**overrides):
    values = dict(
        scope_id="scope-A",
        credential_ref="credential-A",
        credential_version="v1",
        credential_source=CredentialSource.CUSTOMER,
        provider="openai",
    )
    values.update(overrides)
    return Binding(**values)


def make_context(clock, *, kind=ContextKind.INVOKE, targets=frozenset({GEN}), lifetime=300, **binding_overrides):
    return VerifiedContext(
        binding=make_binding(**binding_overrides),
        request_id=new_request_id(),
        kind=kind,
        allowed_targets=targets,
        expires_at=clock.now() + timedelta(seconds=lifetime),
    )


def make_store(clock):
    store = FakeCredentialStore(clock)
    store.add_record("scope-A", "credential-A", "v1", key=KEY_A1, targets=BOTH, active=True)
    store.add_record("scope-B", "credential-B", "v1", key=KEY_B1, targets=BOTH, active=True)
    return store


async def admit_once(store, context, targets=frozenset({GEN})):
    async with store.admit(context, targets) as lease:
        return lease


class AdmissionTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.store = make_store(self.clock)

    async def assertDenied(self, code, context, targets=frozenset({GEN}), store=None):
        store = store or self.store
        before = store.admissions_total
        in_flight_before = store.in_flight
        with self.assertRaises(ProviderIntegrationError) as caught:
            async with store.admit(context, targets):
                self.fail("admission should have been denied")
        self.assertIs(caught.exception.code, code)
        self.assertEqual(store.in_flight, in_flight_before)
        self.assertEqual(store.admissions_total, before)
        rendered = "".join(traceback.format_exception(caught.exception)) + repr(caught.exception)
        for key in (KEY_A1, KEY_A2, KEY_A3, KEY_B1):
            self.assertNotIn(key, rendered)


class DenialMatrixTests(AdmissionTestCase):
    async def test_denial_matrix(self):
        """TC-02 (reader): change each binding/target/kind field separately."""
        lease = await admit_once(self.store, make_context(self.clock))
        self.assertEqual(lease.binding.credential_version, "v1")
        self.assertEqual(lease.secret.reveal_for_session(), KEY_A1)

        self.store.add_record("scope-A", "credential-C", "v1", key=KEY_A3, targets=frozenset({GEN}), active=True)
        cases = [
            ("scope", dict(scope_id="scope-B"), ErrorCode.CREDENTIAL_UNAVAILABLE),
            ("scope case", dict(scope_id="SCOPE-A"), ErrorCode.CREDENTIAL_UNAVAILABLE),
            ("credential", dict(credential_ref="credential-B"), ErrorCode.CREDENTIAL_UNAVAILABLE),
            ("version", dict(credential_version="v9"), ErrorCode.CREDENTIAL_UNAVAILABLE),
            ("source", dict(credential_source=CredentialSource.PLATFORM), ErrorCode.ACCESS_DENIED),
            ("provider", dict(provider="other-provider"), ErrorCode.ACCESS_DENIED),
        ]
        for name, overrides, code in cases:
            with self.subTest(field=name):
                await self.assertDenied(code, make_context(self.clock, **overrides))

        with self.subTest(case="target not in context"):
            await self.assertDenied(ErrorCode.ACCESS_DENIED, make_context(self.clock), frozenset({TRANSCRIBE}))
        with self.subTest(case="target not permitted for credential"):
            context = make_context(self.clock, credential_ref="credential-C", targets=BOTH)
            await self.assertDenied(ErrorCode.CAPABILITY_DENIED, context, frozenset({TRANSCRIBE}))
        with self.subTest(case="empty or malformed targets"):
            await self.assertDenied(ErrorCode.ACCESS_DENIED, make_context(self.clock), frozenset())
            await self.assertDenied(ErrorCode.ACCESS_DENIED, make_context(self.clock), {GEN})
        with self.subTest(case="expired context"):
            expired = make_context(self.clock, lifetime=0)
            await self.assertDenied(ErrorCode.ACCESS_DENIED, expired)
            later = make_context(self.clock, lifetime=10)
            self.clock.advance(10)
            await self.assertDenied(ErrorCode.ACCESS_DENIED, later)
        with self.subTest(case="not a verified context"):
            await self.assertDenied(ErrorCode.ACCESS_DENIED, make_binding())

    async def test_verifier_denial_matrix(self):
        """TC-02 (verifier fake): only registered, fresh, exactly matching evidence passes."""
        verifier = FakeContextVerifier(self.clock)
        context = make_context(self.clock, targets=BOTH)
        verifier.register("evidence-1", context)
        verified = await verifier.verify("evidence-1", make_binding(), ContextKind.INVOKE, frozenset({GEN}))
        self.assertIs(verified, context)

        denials = [
            ("unknown evidence", ("evidence-2", make_binding(), ContextKind.INVOKE, frozenset({GEN}))),
            ("unhashable evidence", (["evidence-1"], make_binding(), ContextKind.INVOKE, frozenset({GEN}))),
            ("kind", ("evidence-1", make_binding(), ContextKind.VALIDATE, frozenset({GEN}))),
            ("targets", ("evidence-1", make_binding(), ContextKind.INVOKE, frozenset({Target(Operation.GENERATE_TEXT, "gpt-4o")}))),
            ("empty targets", ("evidence-1", make_binding(), ContextKind.INVOKE, frozenset())),
            ("not a binding", ("evidence-1", "scope-A", ContextKind.INVOKE, frozenset({GEN}))),
        ]
        for field_name, value in (
            ("scope_id", "scope-B"),
            ("credential_ref", "credential-B"),
            ("credential_version", "v2"),
            ("credential_source", CredentialSource.PLATFORM),
            ("provider", "other-provider"),
        ):
            denials.append((field_name, ("evidence-1", make_binding(**{field_name: value}), ContextKind.INVOKE, frozenset({GEN}))))
        for name, args in denials:
            with self.subTest(case=name), self.assertRaises(ProviderIntegrationError) as caught:
                await verifier.verify(*args)
            self.assertIs(caught.exception.code, ErrorCode.ACCESS_DENIED)

        verifier.revoke("evidence-1")
        with self.assertRaises(ProviderIntegrationError):
            await verifier.verify("evidence-1", make_binding(), ContextKind.INVOKE, frozenset({GEN}))
        verifier.register("evidence-3", make_context(self.clock, lifetime=5))
        self.clock.advance(5)
        with self.assertRaises(ProviderIntegrationError):
            await verifier.verify("evidence-3", make_binding(), ContextKind.INVOKE, frozenset({GEN}))
        self.assertEqual(verifier.calls, len(denials) + 3)

    async def test_unverified_request_never_reaches_reader(self):
        """TC-02: a verifier denial means zero reader calls."""
        verifier = FakeContextVerifier(self.clock)
        with self.assertRaises(ProviderIntegrationError):
            context = await verifier.verify("unregistered", make_binding(), ContextKind.INVOKE, frozenset({GEN}))
            async with self.store.admit(context, frozenset({GEN})):
                pass
        self.assertEqual(self.store.admit_calls, 0)


class StateAndLifecycleTests(AdmissionTestCase):
    async def test_state_matrix(self):
        """TC-06: only active (invoke) or active/pending (validate) states are admitted."""
        self.store.add_record("scope-S", "credential-active", "v1", key=KEY_A1, targets=BOTH, active=True)
        for state in (CredentialState.PENDING, CredentialState.DISABLED, CredentialState.DELETED, CredentialState.EXPIRED):
            self.store.add_record("scope-S", f"credential-{state.value}", "v1", key=KEY_A1, state=state, targets=BOTH)
        expected = {
            CredentialState.ACTIVE: (True, True),
            CredentialState.PENDING: (False, True),
            CredentialState.DISABLED: (False, False),
            CredentialState.DELETED: (False, False),
            CredentialState.EXPIRED: (False, False),
        }
        for state, (invoke_ok, validate_ok) in expected.items():
            for kind, allowed in ((ContextKind.INVOKE, invoke_ok), (ContextKind.VALIDATE, validate_ok)):
                context = make_context(self.clock, kind=kind, scope_id="scope-S", credential_ref=f"credential-{state.value}")
                with self.subTest(state=state.value, kind=kind.value):
                    if allowed:
                        lease = await admit_once(self.store, context)
                        self.assertIs(lease.state, state)
                    else:
                        await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, context)

    async def test_unknown_state_and_real_looking_keys_refused(self):
        with self.assertRaises(TypeError):
            self.store.add_record("scope-S", "credential-x", "v1", key=KEY_A1, state="active", targets=BOTH)  # type: ignore[arg-type]
        for key in ("sk-live-0123456789abcdef", "", "TEST-PROVIDER-KEY-upper"):
            with self.subTest(key=key[:8]), self.assertRaises(ValueError) as caught:
                self.store.add_record("scope-S", "credential-y", "v1", key=key, targets=BOTH)
            self.assertNotIn("0123456789abcdef", str(caught.exception))

    async def test_admission_change_order(self):
        """TC-06: admitted-before-disable may finish; admitted-after is denied (both orders)."""
        context = make_context(self.clock)

        # Sequential: a lease admitted before disable keeps its snapshot.
        async with self.store.admit(context, frozenset({GEN})) as lease:
            await self.store.disable("scope-A", "credential-A", "v1")
            self.assertIs(lease.state, CredentialState.ACTIVE)
            self.assertEqual(lease.secret.reveal_for_session(), KEY_A1)
        await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock))

    async def test_concurrent_admit_before_disable(self):
        """TC-06: an admission holding the lock wins; the queued disable applies afterwards."""
        gate = PauseGate()
        self.store.admit_gate = gate
        finish = asyncio.Event()
        leases = []

        async def hold():
            async with self.store.admit(make_context(self.clock), frozenset({GEN})) as lease:
                leases.append(lease)
                await finish.wait()

        holder = asyncio.create_task(hold())
        await gate.entered.wait()
        self.store.admit_gate = None
        disabler = asyncio.create_task(self.store.disable("scope-A", "credential-A", "v1"))
        for _ in range(5):
            await asyncio.sleep(0)  # yield only; ordering is fixed by the gate, not by timing
        self.assertFalse(disabler.done(), "disable must wait for the in-progress admission")
        self.assertTrue(self.store.locked)

        gate.release.set()
        await disabler
        self.assertEqual(len(leases), 1)
        self.assertIs(leases[0].state, CredentialState.ACTIVE)
        await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock))
        finish.set()
        await holder
        self.assertEqual(self.store.in_flight, 0)

    async def test_concurrent_disable_before_admit(self):
        """TC-06: a lifecycle change holding the lock wins; the queued admission is denied."""
        gate = PauseGate()
        self.store.lifecycle_gate = gate
        disabler = asyncio.create_task(self.store.disable("scope-A", "credential-A", "v1"))
        await gate.entered.wait()
        self.store.lifecycle_gate = None

        async def try_admit():
            async with self.store.admit(make_context(self.clock), frozenset({GEN})):
                pass

        admitter = asyncio.create_task(try_admit())
        for _ in range(5):
            await asyncio.sleep(0)
        self.assertFalse(admitter.done(), "admission must wait for the in-progress lifecycle change")
        gate.release.set()
        await disabler
        with self.assertRaises(ProviderIntegrationError) as caught:
            await admitter
        self.assertIs(caught.exception.code, ErrorCode.CREDENTIAL_UNAVAILABLE)
        self.assertEqual(self.store.admissions_total, 0)

    async def test_rotation_denies_old_version(self):
        """C3: after rotation an old-version request is denied, never upgraded."""
        await self.store.add_pending("scope-A", "credential-A", "v2", key=KEY_A2, targets=BOTH)
        await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock, credential_version="v2"))

        async with self.store.admit(make_context(self.clock), frozenset({GEN})) as held_v1:
            await self.store.rotate("scope-A", "credential-A", "v2")
            self.assertEqual(held_v1.binding.credential_version, "v1")
            self.assertEqual(held_v1.secret.reveal_for_session(), KEY_A1)

        self.assertEqual(self.store.active_version("scope-A", "credential-A"), "v2")
        for kind in (ContextKind.INVOKE, ContextKind.VALIDATE):
            with self.subTest(kind=kind.value):
                await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock, kind=kind))
        lease_v2 = await admit_once(self.store, make_context(self.clock, credential_version="v2"))
        self.assertEqual(lease_v2.binding.credential_version, "v2")
        self.assertEqual(lease_v2.secret.reveal_for_session(), KEY_A2)
        with self.assertRaises(ValueError):
            await self.store.rotate("scope-A", "credential-A", "v9")

    async def test_replacement_and_stale_result(self):
        """TC-05 (reader/backend): pending validates as itself; stale results are refused."""
        await self.store.add_pending("scope-A", "credential-A", "v2", key=KEY_A2, targets=BOTH)
        validate_v2 = make_context(self.clock, kind=ContextKind.VALIDATE, credential_version="v2")

        async with self.store.admit(validate_v2, frozenset({GEN})) as lease:
            self.assertEqual(lease.binding.credential_version, "v2")
            self.assertIs(lease.state, CredentialState.PENDING)
            self.assertEqual(lease.secret.reveal_for_session(), KEY_A2)
            self.assertEqual(self.store.active_version("scope-A", "credential-A"), "v1")
            invoke_v1 = await admit_once(self.store, make_context(self.clock))
            self.assertEqual(invoke_v1.secret.reveal_for_session(), KEY_A1)
            fresh = self.make_result(lease.binding, ValidationStatus.VALID)
        self.assertTrue(self.store.backend_accepts(fresh))

        failed = self.make_result(make_binding(credential_version="v2"), ValidationStatus.INDETERMINATE, ErrorCode.PROVIDER_TIMEOUT)
        self.assertEqual(failed.binding.credential_version, "v2")
        self.assertEqual(self.store.active_version("scope-A", "credential-A"), "v1")
        await admit_once(self.store, make_context(self.clock))

        async with self.store.admit(validate_v2, frozenset({GEN})) as lease:
            await self.store.add_pending("scope-A", "credential-A", "v3", key=KEY_A3, targets=BOTH)
            await self.store.delete("scope-A", "credential-A", "v2")
            stale = self.make_result(lease.binding, ValidationStatus.VALID)
        self.assertEqual(stale.binding.credential_version, "v2")
        self.assertFalse(self.store.backend_accepts(stale))
        self.assertEqual(self.store.active_version("scope-A", "credential-A"), "v1")
        self.assertFalse(self.store.backend_accepts(make_binding()))  # not a ValidationResult

    def make_result(self, binding, status, reason=None):
        return ValidationResult(
            request_id=new_request_id(), binding=binding, target=GEN,
            checked_at=self.clock.now(), status=status, reason_code=reason,
        )

    async def test_production_module_has_no_lifecycle_actions(self):
        """TC-05: activation and lifecycle changes exist only in the test fake."""
        forbidden = {"activate", "rotate", "disable", "delete", "set_active", "add_pending", "backend_accepts"}
        for name in production.__all__:
            item = getattr(production, name)
            with self.subTest(export=name):
                self.assertFalse(forbidden & set(dir(item)) - set(dir(object)) - {"__class__"})
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                for word in sorted(forbidden):
                    self.assertNotIn(f"def {word}", source)
                self.assertNotIn("fakes", source)


class IsolationAndOutageTests(AdmissionTestCase):
    async def test_two_scopes_concurrent_isolation(self):
        """TC-03 (reader): overlapping admissions each receive only their own key."""
        barrier = asyncio.Barrier(2)
        seen = {}
        overlap = []

        async def use(scope_id, credential_ref):
            context = make_context(self.clock, scope_id=scope_id, credential_ref=credential_ref)
            async with self.store.admit(context, frozenset({GEN})) as lease:
                await barrier.wait()  # both leases are held at this point
                overlap.append(self.store.in_flight)
                seen[scope_id] = lease
                await barrier.wait()  # neither releases until both have observed

        await asyncio.gather(use("scope-A", "credential-A"), use("scope-B", "credential-B"))
        self.assertEqual(overlap, [2, 2])
        self.assertEqual(seen["scope-A"].secret.reveal_for_session(), KEY_A1)
        self.assertEqual(seen["scope-B"].secret.reveal_for_session(), KEY_B1)
        self.assertIsNot(seen["scope-A"].secret, seen["scope-B"].secret)
        self.assertNotEqual(seen["scope-A"].admission_id, seen["scope-B"].admission_id)
        self.assertEqual(self.store.in_flight, 0)

        again = await admit_once(self.store, make_context(self.clock))
        self.assertIsNot(again.secret, seen["scope-A"].secret)
        self.assertNotEqual(again.secret, seen["scope-A"].secret)

    async def test_outage_and_no_fallback(self):
        """TC-13 (reader): outage or missing record fails closed; no environment key."""
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": ENV_CANARY}):
            self.store.outage = True
            await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock))
            self.store.outage = False
            await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock, credential_ref="credential-missing"))
            empty = FakeCredentialStore(self.clock)
            await self.assertDenied(ErrorCode.CREDENTIAL_UNAVAILABLE, make_context(self.clock), store=empty)
        source = FAKES_PATH.read_text(encoding="utf-8")
        for token in ("os.environ", "getenv", "OPENAI_API_KEY", "dotenv"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    async def test_lease_released_on_every_exit(self):
        context = make_context(self.clock)
        async with self.store.admit(context, frozenset({GEN})):
            self.assertEqual(self.store.in_flight, 1)
        self.assertEqual(self.store.in_flight, 0)

        with self.assertRaises(RuntimeError):
            async with self.store.admit(context, frozenset({GEN})):
                raise RuntimeError("synthetic failure")
        self.assertEqual(self.store.in_flight, 0)

        entered = asyncio.Event()

        async def hold_forever():
            async with self.store.admit(context, frozenset({GEN})):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(hold_forever())
        await entered.wait()
        self.assertEqual(self.store.in_flight, 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.store.in_flight, 0)

    async def test_cancel_while_waiting_records_no_admission(self):
        self.store.lifecycle_gate = PauseGate()
        gate = self.store.lifecycle_gate
        disabler = asyncio.create_task(self.store.disable("scope-B", "credential-B", "v1"))
        await gate.entered.wait()

        async def try_admit():
            async with self.store.admit(make_context(self.clock), frozenset({GEN})):
                pass

        waiting = asyncio.create_task(try_admit())
        for _ in range(5):
            await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
        gate.release.set()
        await disabler
        self.assertEqual(self.store.admissions_total, 0)
        self.assertEqual(self.store.in_flight, 0)
        self.assertFalse(self.store.locked)


if __name__ == "__main__":
    unittest.main()
