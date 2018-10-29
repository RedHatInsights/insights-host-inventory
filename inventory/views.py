from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.response import Response
from inventory.models import Host
from inventory.serializers import HostSerializer


class HostViewSet(viewsets.ModelViewSet):
    serializer_class = HostSerializer
    queryset = Host.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cf = serializer.validated_data["canonical_facts"]
            found_host = Host.objects.get(
                Q(canonical_facts__contained_by=cf) | Q(canonical_facts__contains=cf),
                account=serializer.validated_data["account"],
            )

            print(found_host)

            found_host.canonical_facts.update(cf)
            found_host.facts.update(serializer.validated_data.get("facts", {}))

            found_host.save()
            headers = self.get_success_headers(serializer.validated_data)
            return Response(
                serializer.validated_data, status=status.HTTP_200_OK, headers=headers
            )

        except Exception as e:
            print(f"Couldn't find the canonical facts, creating: {e}")
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.validated_data)
            return Response(
                serializer.validated_data,
                status=status.HTTP_201_CREATED,
                headers=headers,
            )
