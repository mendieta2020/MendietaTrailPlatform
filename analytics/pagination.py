from rest_framework.pagination import PageNumberPagination


class OptionalPageNumberPagination(PageNumberPagination):
    """
    Paginación "opt-in".

    - Si el cliente NO envía `page` ni `page_size`: no pagina (legacy list response).
    - Si envía `page` o `page_size`: pagina y devuelve el envelope estándar de DRF.
    """

    page_query_param = "page"
    page_size_query_param = "page_size"

    # Default usado SOLO cuando el cliente opta por paginación (ej: envía `page=1`).
    page_size = 20

    # Límite defensivo para evitar payloads masivos.
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        qp = getattr(request, "query_params", {}) or {}
        if self.page_query_param not in qp and self.page_size_query_param not in qp:
            return None
        return super().paginate_queryset(queryset, request, view=view)


class CoachPlanningPagination(PageNumberPagination):
    page_query_param = "page"
    page_size_query_param = "page_size"
    page_size = 50
    max_page_size = 200
