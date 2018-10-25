from django.http import JsonResponse, HttpResponseForbidden
from inventory.auth.identity import from_http_header, validate


__all__ = ['header_auth_middleware']


HEADER = "HTTP_X_RH_IDENTITY"


def header_auth_middleware(get_response):
    def middleware(request):
        auth_data = request.META.get(HEADER)
        try:
            identity = from_http_header(auth_data)
            validate(identity)
        except (TypeError, ValueError) as exception:
            return JsonResponse({"error": str(exception)},
                                status=HttpResponseForbidden.status_code)

        return get_response(request)
    return middleware
