    def send(
        self,
        request: Request,
        *,
        stream: bool = False,
        auth: AuthTypes | UseClientDefault | None = USE_CLIENT_DEFAULT,
        follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> Response:
        """
        Send a request.
    
        The request is sent as-is, unmodified.
    
        Typically you'll want to build one with `Client.build_request()`
        so that any client-level configuration is merged into the request,
        but passing an explicit `httpx.Request()` is supported as well.
    
        See also: [Request instances][0]
    
        [0]: /advanced/clients/#request-instances
        """
        if self._state == ClientState.CLOSED:
>           raise RuntimeError("Cannot send a request, as the client has been closed.")
E           RuntimeError: Cannot send a request, as the client has been closed.

.venv/lib/python3.13/site-packages/httpx/_client.py:901: RuntimeError
=========================== short test summary info ============================
FAILED tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_full_lifecycle_spools_all_events
========================= 1 failed, 13 passed in 0.37s =========================