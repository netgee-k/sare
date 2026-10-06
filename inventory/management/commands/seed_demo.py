import random
import shutil
from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from inventory.models import IN, LOSS, OUT, RETURN, StockItem, StockMovement, UniformType

# type: (sizes, reorder level, how fast it moves)
CATALOG = {
    "Shirt":    (["S", "M", "L", "XL", "XXL"], 8, 1.0),
    "Trousers": (["S", "M", "L", "XL", "XXL"], 8, 0.9),
    "Skirt":    (["XS", "S", "M", "L"], 6, 0.6),
    "Blazer":   (["S", "M", "L", "XL"], 5, 0.5),
    "Jumper":   (["S", "M", "L", "XL"], 6, 0.7),
    "Tie":      (["M"], 10, 1.4),          # one size, stored as M
}
SIZE_WEIGHT = {"XS": .4, "S": 1.0, "M": 2.0, "L": 1.8, "XL": 1.0, "XXL": .5}

PEOPLE = [
    "Wanjiru Kamau", "Brian Otieno", "Amina Hassan", "Kevin Mwangi", "Grace Akinyi", "David Kiptoo",
    "Faith Njeri", "Peter Ochieng", "Mercy Wambui", "Samuel Kariuki", "Lucy Achieng", "John Maina",
    "Esther Chebet", "Ali Yusuf", "Diana Atieno", "Joseph Mutua", "Nancy Wangari", "Daniel Omondi",
    "Sharon Cherono", "Collins Kimani", "Ruth Naliaka", "Victor Barasa",
]
DEMO_PREFIX = "Demo "   # added to type names when loading into the REAL database
DEMO_TAG = "[demo] "    # added to every movement note in the REAL database
LOSS_NOTES = ["Torn beyond repair", "Lost by wearer", "Stained, unusable", "Damaged in laundry", "Wrong size, discarded"]


class Command(BaseCommand):
    help = "Fill the DEMO database with realistic uniform stock and history."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=120, help="How many days of history (default 120)")
        parser.add_argument("--seed", type=int, default=7, help="Change for a different random data set")
        parser.add_argument("--users", action="store_true", help="Also create demo logins (demo database only)")
        parser.add_argument("--wipe", action="store_true", help="Delete existing inventory data first (demo database only)")
        parser.add_argument("--force", action="store_true", help="Allow adding to a database that already has stock")
        parser.add_argument("--real", action="store_true", help="Confirm loading demo data into your REAL database")
        parser.add_argument("--remove", action="store_true", help="Remove all demo data that was loaded into the real database")

    # ------------------------------------------------------------------
    def handle(self, *args, **o):
        dbname = str(settings.DATABASES["default"]["NAME"])
        is_demo = "demo" in dbname.lower()

        # ---- remove demo data from the real database ----------------------
        if o["remove"]:
            items = StockItem.objects.filter(uniform_type__name__startswith=DEMO_PREFIX)
            moves = StockMovement.objects.filter(item__in=items).count()
            n_items = items.count()
            if n_items:
                self.backup()
            items.delete()  # their movements go with them
            UniformType.objects.filter(name__startswith=DEMO_PREFIX).delete()
            self.stdout.write(self.style.SUCCESS(f"Removed {n_items} demo items and {moves} demo movements."))
            return

        if (o["wipe"] or o["users"]) and not is_demo:
            raise CommandError(
                f"Refusing: --wipe/--users only work on the demo database, and this is {dbname}.\n"
                "Run with SARE_DEMO=1 to use db_demo.sqlite3."
            )

        real = not is_demo
        if real:
            if not o["real"]:
                raise CommandError(
                    f"This is your REAL database ({dbname}).\n"
                    "Add --real to confirm. Demo items are labelled 'Demo ...', a backup is taken first,\n"
                    "and `python manage.py seed_demo --remove` deletes them again."
                )
            if UniformType.objects.filter(name__startswith=DEMO_PREFIX).exists() and not o["force"]:
                raise CommandError("Demo data is already loaded. Run `seed_demo --remove` first to reload it.")
            prefix, tag, recorder = DEMO_PREFIX, DEMO_TAG, None
            backup = self.backup()
            if backup:
                self.stdout.write(f"Backup saved: {backup}")
        else:
            prefix, tag = "", ""
            recorder = get_user_model().objects.filter(is_superuser=True).first()
            if o["wipe"]:
                StockMovement.objects.all().delete()
                StockItem.objects.all().delete()
                UniformType.objects.all().delete()
                self.stdout.write("Cleared existing inventory data.")
            if StockItem.objects.exists() and not o["force"]:
                raise CommandError(
                    f"{dbname} already has stock items, so I did not add anything.\n"
                    "Pass --force to add anyway, or --wipe to start the demo database over."
                )

        rng = random.Random(o["seed"])
        today = timezone.localdate()
        start = today - timedelta(days=o["days"])

        # ---- items --------------------------------------------------------
        items = []
        for type_name, (sizes, reorder, speed) in CATALOG.items():
            utype, _ = UniformType.objects.get_or_create(name=prefix + type_name)
            for size in sizes:
                item, _ = StockItem.objects.get_or_create(
                    uniform_type=utype, size=size, defaults={"reorder_level": reorder}
                )
                items.append((item, speed * SIZE_WEIGHT[size]))

        # ---- history ------------------------------------------------------
        rows, final = [], {}
        for item, weight in items:
            events = self.make_events(rng, start, today, weight)
            moves, balance = self.simulate(events)
            final[item.id] = balance
            rows.append((item, moves))

        # make the dashboard interesting: one item out of stock, a few low
        picks = rng.sample([r for r in rows if final[r[0].id] > 12], k=min(4, len(rows)))
        for n, (item, moves) in enumerate(picks):
            target = 0 if n == 0 else rng.randint(1, max(1, item.reorder_level - 1))
            take = final[item.id] - target
            if take > 0:
                moves.append((today - timedelta(days=rng.randint(0, 2)), OUT, take,
                              rng.choice(PEOPLE), "Bulk issue"))
                final[item.id] = target

        # ---- save, oldest first so ids follow history ---------------------
        flat = []
        for item, moves in rows:
            for d, t, q, person, note in moves:
                flat.append((d, 0 if t == IN else 1, item.id, t, q, person, note))
        flat.sort(key=lambda x: (x[0], x[1], x[2]))
        by_id = {i.id: i for i, _ in rows}
        StockMovement.objects.bulk_create([
            StockMovement(
                item=by_id[iid], movement_type=t, quantity=q, date=d, issued_to=person, note=(tag + note).strip(),
                recorded_by=recorder,
                created_at=timezone.make_aware(datetime.combine(d, time(rng.randint(8, 16), rng.randint(0, 59)))),
            )
            for d, _, iid, t, q, person, note in flat
        ])

        if o["users"]:
            self.make_users()

        count = StockMovement.objects.count()
        low = sum(1 for i, _ in rows if 0 < final[i.id] <= i.reorder_level)
        out = sum(1 for i, _ in rows if final[i.id] <= 0)
        self.stdout.write(self.style.SUCCESS(
            f"Demo data ready: {len(items)} items, {count} movements over {o['days']} days "
            f"({low} low, {out} out of stock)."
        ))

    # ------------------------------------------------------------------
    def backup(self):
        """Copy the SQLite file next to itself before touching real data."""
        db = settings.DATABASES["default"]
        src = Path(str(db["NAME"]))
        if "sqlite" in db["ENGINE"] and src.exists():
            dst = src.with_name(f"{src.name}.bak-{timezone.now():%Y%m%d-%H%M%S}")
            shutil.copy2(src, dst)
            return dst
        return None

    def make_events(self, rng, start, today, weight):
        span = (today - start).days
        ev = [(start + timedelta(days=rng.randint(0, 5)), IN, rng.randint(55, 110), "", "Opening stock")]
        for _ in range(rng.randint(1, 2)):
            d = start + timedelta(days=rng.randint(int(span * .3), int(span * .8)))
            ev.append((d, IN, rng.randint(30, 80), "", f"Delivery note DN-{rng.randint(1000, 9999)}"))
        for _ in range(max(3, round(weight * rng.uniform(7, 12)))):
            d = start + timedelta(days=rng.randint(8, span))
            ev.append((d, OUT, rng.choice([1, 1, 1, 2, 2, 3]), rng.choice(PEOPLE), ""))
        for _ in range(rng.randint(0, 2)):
            d = start + timedelta(days=rng.randint(15, span))
            ev.append((d, LOSS, rng.choice([1, 1, 2]), "", rng.choice(LOSS_NOTES)))
        return ev

    def simulate(self, events):
        """Replay events in date order, dropping any that stock levels would not allow."""
        def run(evts):
            bal, held, kept = 0, defaultdict(int), []
            for d, t, q, p, note in sorted(evts, key=lambda e: (e[0], 0 if e[1] == IN else 1)):
                if t == IN:
                    bal += q
                elif t in (OUT, LOSS):
                    if bal < q:
                        continue
                    bal -= q
                    if t == OUT:
                        held[p] += q
                elif t == RETURN:
                    if held[p] < q:
                        continue
                    held[p] -= q
                    bal += q
                kept.append((d, t, q, p, note))
            return kept, bal

        kept, _ = run(events)
        # ~1 in 4 issues comes back a few days later (pieces returned in good order)
        rng = random.Random(len(events) * 31 + sum(e[2] for e in events))
        today = max(e[0] for e in events)
        returns = []
        for d, t, q, p, note in kept:
            if t == OUT and rng.random() < 0.25 and d + timedelta(days=4) <= today:
                returns.append((d + timedelta(days=rng.randint(4, 40)), RETURN, 1, p, "Returned, good condition"))
        returns = [r for r in returns if r[0] <= today]
        return run(kept + returns)

    def make_users(self):
        User = get_user_model()
        call_command("setup_roles", verbosity=0)
        from django.contrib.auth.models import Group
        accounts = [("demo", None, True), ("demo_manager", "Store Manager", False), ("demo_clerk", "Issuing Clerk", False)]
        for username, group, superuser in accounts:
            user, created = User.objects.get_or_create(username=username, defaults={"is_staff": True, "is_superuser": superuser})
            user.is_staff, user.is_superuser = True, superuser
            user.set_password("demo12345")
            user.save()
            if group:
                user.groups.set([Group.objects.get(name=group)])
        self.stdout.write("Demo logins (password demo12345): demo (admin), demo_manager, demo_clerk")
