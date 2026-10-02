from django.middleware.csrf import CsrfViewMiddleware


class AllowAllOriginsCsrfMiddleware(CsrfViewMiddleware):
    """DEVELOPMENT ONLY: accept form posts from any origin (the CSRF token is still required)."""

    def _origin_verified(self, request):
        return True
