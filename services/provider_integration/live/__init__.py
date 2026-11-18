"""Live connectors to the FloBrain backend (T5).

These modules replace the test-only fakes with the real ContextVerifier and
CredentialReader agreed in the P-1 interface proposal and the backend response
of 2026-11-15. They are imported only by the route layer (``api/provider_routes.py``);
the core modules never import them. Nothing here reads the environment: settings
arrive as an explicit mapping.
"""
