from collections import defaultdict
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from .models import ADD_TYPES, IN, LOSS, OUT, RETURN, StockMovement
from .services import SIZE_ORDER, holdings, items_with_balance

PERIODS = (7, 30, 90)    # period buttons shown on the dashboard
DEFAULT_PERIOD = 30


def _pct(value, biggest, minimum=3):
    """Bar width/height in whole percent; tiny non-zero values stay visible."""
    if value <= 0 or biggest <= 0:
        return 0
    return max(round(value / biggest * 100), minimum)


def _level(item):
    if item is None:
        return "none"
    if item.total <= 0:
        return "out"
    if item.total <= item.reorder_level:
        return "low"
    return "ok"


def dashboard_callback(request, context):
    # ---- period (?days=7 / 30 / 90) ---------------------------------------
    try:
        days = int(request.GET.get("days", DEFAULT_PERIOD))
    except (TypeError, ValueError):
        days = DEFAULT_PERIOD
    if days not in PERIODS:
        days = DEFAULT_PERIOD

    today = timezone.localdate()
    since = today - timedelta(days=days - 1)

    # ---- current balance of every type/size --------------------------------
    items = items_with_balance()
    total_stock = sum(i.total for i in items)
    out_of_stock = [i for i in items if i.total <= 0]
    low_stock = sorted((i for i in items if 0 < i.total <= i.reorder_level), key=lambda i: i.total)
    attention = sorted(out_of_stock, key=str) + low_stock

    # ---- stock by type / by size --------------------------------------------
    by_type, by_size = defaultdict(int), defaultdict(int)
    for i in items:
        by_type[i.uniform_type.name] += i.total
        by_size[i.size] += i.total
    biggest = max(by_type.values(), default=0)
    type_rows = [{"name": n, "total": t, "pct": _pct(t, biggest)} for n, t in sorted(by_type.items())]
    biggest = max(by_size.values(), default=0)
    size_rows = [
        {"name": s, "total": by_size[s], "pct": _pct(by_size[s], biggest)}
        for s in SIZE_ORDER if s in by_size
    ]

    # ---- type x size grid ---------------------------------------------------
    sizes_present = [s for s in SIZE_ORDER if s in by_size]
    grid = defaultdict(dict)
    for i in items:
        grid[i.uniform_type.name][i.size] = i
    matrix_rows = []
    for name in sorted(grid):
        cells = []
        for s in sizes_present:
            it = grid[name].get(s)
            cells.append({
                "value": it.total if it else None,
                "level": _level(it),
                "id": it.id if it else None,
            })
        matrix_rows.append({"name": name, "cells": cells, "total": by_type[name]})

    # ---- movements per day (chart) and period totals -------------------------
    daily = defaultdict(lambda: {"in": 0, "out": 0})
    kinds = defaultdict(int)
    for m in (
        StockMovement.objects.filter(date__gte=since, date__lte=today)
        .order_by()
        .values("date", "movement_type")
        .annotate(t=Sum("quantity"))
    ):
        daily[m["date"]]["in" if m["movement_type"] in ADD_TYPES else "out"] += m["t"]
        kinds[m["movement_type"]] += m["t"]

    series = []
    for n in range(days):
        d = since + timedelta(days=n)
        series.append({"date": d, "in": daily[d]["in"], "out": daily[d]["out"]})
    peak = max((max(s["in"], s["out"]) for s in series), default=0)
    for s in series:
        s["in_pct"] = _pct(s["in"], peak)
        s["out_pct"] = _pct(s["out"], peak)
    axis = [series[0]["date"], series[len(series) // 2]["date"], series[-1]["date"]]

    # ---- fastest moving (issued) ---------------------------------------------
    fastest = list(
        StockMovement.objects.filter(movement_type=OUT, date__gte=since, date__lte=today)
        .order_by()
        .values("item__uniform_type__name", "item__size")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:6]
    )
    top = fastest[0]["total"] if fastest else 0
    for f in fastest:
        f["pct"] = _pct(f["total"], top)

    # ---- who is holding uniforms right now ------------------------------------
    per_person = defaultdict(int)
    shown = {}
    for h in holdings():
        per_person[h["person"].lower()] += h["qty"]
        shown.setdefault(h["person"].lower(), h["person"])
    holders = sorted(
        ({"person": shown[k], "total": v} for k, v in per_person.items()),
        key=lambda h: -h["total"],
    )
    top = holders[0]["total"] if holders else 0
    for h in holders:
        h["pct"] = _pct(h["total"], top)

    people, seen = [], set()
    for name in (
        StockMovement.objects.exclude(issued_to="").order_by("issued_to")
        .values_list("issued_to", flat=True).distinct()
    ):
        if name.lower() not in seen:
            seen.add(name.lower())
            people.append(name)

    added, issued = kinds[IN], kinds[OUT]
    returned, written_off = kinds[RETURN], kinds[LOSS]

    context.update(
        {
            "days": days,
            "periods": PERIODS,
            "total_stock": total_stock,
            "item_count": len(items),
            "added": added,
            "issued": issued,
            "returned": returned,
            "written_off": written_off,
            "net": added + returned - issued - written_off,
            "low_count": len(low_stock),
            "out_count": len(out_of_stock),
            "attention": attention,
            "stock_options": sorted(
                items,
                key=lambda i: (i.uniform_type.name, SIZE_ORDER.index(i.size) if i.size in SIZE_ORDER else 99),
            ),
            "type_rows": type_rows,
            "size_rows": size_rows,
            "sizes_present": sizes_present,
            "matrix_rows": matrix_rows,
            "series": series,
            "axis": axis,
            "peak": peak,
            "fastest": fastest,
            "holders": holders[:6],
            "holder_count": len(holders),
            "people": people,
            "latest_movements": StockMovement.objects.select_related("item__uniform_type")[:8],
        }
    )
    return context
