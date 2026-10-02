from django.db.models import Case, F, IntegerField, Sum, When
from django.db.models.functions import Coalesce

from .models import ADD_TYPES, OUT, REMOVE_TYPES, RETURN, StockItem, StockMovement

SIZE_ORDER = [s for s, _ in StockItem.SIZES]


def items_with_balance():
    """Every type/size line with its current balance in `.total` (one query)."""
    return list(
        StockItem.objects.select_related("uniform_type").annotate(
            total=Coalesce(
                Sum(
                    Case(
                        When(movements__movement_type__in=ADD_TYPES, then=F("movements__quantity")),
                        When(movements__movement_type__in=REMOVE_TYPES, then=-F("movements__quantity")),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
                0,
            )
        )
    )


def status(item):
    return "OUT" if item.total <= 0 else "LOW" if item.total <= item.reorder_level else "OK"


def holdings():
    """Who still holds uniforms: issued minus returned, per person and item."""
    net, shown = {}, {}
    qs = (
        StockMovement.objects.filter(movement_type__in=[OUT, RETURN])
        .exclude(issued_to="")
        .order_by()
        .values("issued_to", "item__uniform_type__name", "item__size", "movement_type")
        .annotate(q=Sum("quantity"))
    )
    for r in qs:
        person = r["issued_to"].strip()
        key = (person.lower(), r["item__uniform_type__name"], r["item__size"])
        shown.setdefault(key[0], person)
        net[key] = net.get(key, 0) + (r["q"] if r["movement_type"] == OUT else -r["q"])
    rows = [
        {"person": shown[k[0]], "type": k[1], "size": k[2], "qty": q}
        for k, q in net.items()
        if q > 0
    ]
    rows.sort(
        key=lambda r: (
            r["person"].lower(), r["type"],
            SIZE_ORDER.index(r["size"]) if r["size"] in SIZE_ORDER else 99,
        )
    )
    return rows
