from django.http import JsonResponse, HttpResponseForbidden


__all__ = ['header_auth_middleware']


HEADER = "HTTP_X_RH_IDENTITY"


def header_auth_middleware(get_response):
    def middleware(request):
        auth_data = request.META.get(HEADER)
        if not auth_data:
            return JsonResponse({}, status=HttpResponseForbidden.status_code)

        return get_response(request)
    return middleware
