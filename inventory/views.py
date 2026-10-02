from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import reports
from .models import PERMS, StockItem, StockMovement


@staff_member_required
@require_POST
def quick_move(request):
    """Receive / issue / return / write off stock straight from the dashboard."""
    days = request.POST.get("days", "")
    back = reverse("admin:index") + (f"?days={days}" if days in ("7", "30", "90") else "")

    mtype = request.POST.get("movement_type", "")
    if mtype not in PERMS:
        messages.error(request, "Choose what you are recording.")
        return redirect(back)
    if not request.user.has_perm(PERMS[mtype]):
        label = dict(StockMovement.TYPES)[mtype].lower()
        messages.error(request, f"You do not have permission to record '{label}' movements.")
        return redirect(back)

    try:
        item = StockItem.objects.select_related("uniform_type").get(pk=request.POST.get("item"))
        quantity = int(request.POST.get("quantity", ""))
        if quantity < 1:
            raise ValueError
        movement = StockMovement(
            item=item,
            movement_type=mtype,
            quantity=quantity,
            issued_to=request.POST.get("issued_to", "").strip(),
            note=request.POST.get("note", "").strip(),
            recorded_by=request.user,
        )
        movement.full_clean()
        movement.save()
    except (StockItem.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Pick an item and enter a quantity of 1 or more.")
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    else:
        verb = dict(StockMovement.TYPES)[mtype]
        messages.success(request, f"{verb}: {quantity} x {item}. Balance now {item.balance}.")
    return redirect(back)


@staff_member_required
def report(request, kind):
    needed = "inventory.view_stockmovement" if kind == "movements" else "inventory.view_stockitem"
    if not request.user.has_perm(needed):
        raise PermissionDenied

    filters = {}
    if kind == "stock":
        rep = reports.stock_report()
    elif kind == "holdings":
        rep = reports.holdings_report()
    elif kind == "movements":
        d_start, d_end = reports.default_range()
        start = reports.parse_date(request.GET.get("start"), d_start)
        end = reports.parse_date(request.GET.get("end"), d_end)
        mtype = request.GET.get("type", "")
        rep = reports.movement_report(start, end, mtype)
        filters = {"start": start.isoformat(), "end": end.isoformat(), "type": mtype}
    else:
        raise Http404

    fmt = request.GET.get("format")
    if fmt == "xlsx":
        return reports.to_xlsx(rep)
    if fmt == "csv":
        return reports.to_csv(rep)

    query = request.GET.copy()
    query.pop("format", None)
    return render(
        request,
        "inventory/report.html",
        {
            "rep": rep,
            "rows": reports.html_rows(rep),
            "filters": filters,
            "qs": query.urlencode(),
            "type_choices": StockMovement.TYPES,
            "now": timezone.localtime(),
        },
    )


class StaffAuthForm(AuthenticationForm):
    """Only staff accounts may sign in; the message is shown on the landing page."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError(
                "This account has no access to the inventory system. Ask an administrator.",
                code="no_access",
            )


class LandingView(LoginView):
    """Public front page with the sign-in form."""

    template_name = "inventory/landing.html"
    authentication_form = StaffAuthForm
    redirect_authenticated_user = False

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["org_name"] = getattr(settings, "ORG_NAME", "")
        return ctx
