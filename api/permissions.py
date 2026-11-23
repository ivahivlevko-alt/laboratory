from rest_framework import permissions
class IsOwner(permissions.BasePermission):
    message = "Ця заявка належить іншому користувачу."
    def has_object_permission(self, request, view, obj):
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.owner_id == request.user.pk
        )