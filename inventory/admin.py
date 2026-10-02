from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import PERMS, StockItem, StockMovement, UniformType


# ---- users and groups, styled like the rest of the admin -------------------
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


# ---- inventory --------------------------------------------------------------
@admin.register(UniformType)
class UniformTypeAdmin(ModelAdmin):
    search_fields = ["name"]


class MovementInline(TabularInline):
    """Read-only history on the item page. Record new movements from the dashboard."""
    model = StockMovement
    extra = 0
    fields = ["date", "movement_type", "quantity", "issued_to", "note", "recorded_by"]
    readonly_fields = fields
    ordering = ["-date", "-id"]
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockItem)
class StockItemAdmin(ModelAdmin):
    list_display = ["uniform_type", "size", "balance", "reorder_level", "stock_status"]
    list_filter = ["uniform_type", "size"]
    search_fields = ["uniform_type__name"]
    inlines = [MovementInline]

    @display(description="Status", label={"OUT": "danger", "LOW": "warning", "OK": "success"})
    def stock_status(self, obj):
        return obj.status


@admin.register(StockMovement)
class StockMovementAdmin(ModelAdmin):
    list_display = ["date", "item", "movement_type", "quantity", "issued_to", "recorded_by"]
    list_filter = ["movement_type", "date", "item__uniform_type"]
    search_fields = ["issued_to", "note"]
    date_hierarchy = "date"
    fields = ["item", "movement_type", "quantity", "date", "issued_to", "note", "recorded_by", "created_at"]
    readonly_fields = ["recorded_by", "created_at"]

    def get_form(self, request, obj=None, **kwargs):
        Form = super().get_form(request, obj, **kwargs)

        class PermissionedForm(Form):
            def clean(form):
                data = super().clean()
                perm = PERMS.get(data.get("movement_type"))
                if perm and not request.user.has_perm(perm):
                    raise ValidationError("You do not have permission to record this kind of movement.")
                return data

        return PermissionedForm

    def save_model(self, request, obj, form, change):
        if not change:
            obj.recorded_by = request.user
        super().save_model(request, obj, form, change)
