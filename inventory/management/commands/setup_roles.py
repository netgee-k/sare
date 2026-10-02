from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

ROLES = {
    # name: codenames (None = everything in the inventory app)
    "Store Manager": None,
    "Storekeeper": [
        "view_uniformtype", "view_stockitem", "add_stockitem", "view_stockmovement", "add_stockmovement",
        "can_receive_stock", "can_issue_stock", "can_return_stock",
    ],
    "Issuing Clerk": [
        "view_uniformtype", "view_stockitem", "view_stockmovement", "add_stockmovement",
        "can_issue_stock", "can_return_stock",
    ],
    "Viewer": ["view_uniformtype", "view_stockitem", "view_stockmovement"],
}


class Command(BaseCommand):
    help = "Create the standard inventory roles (groups) and their permissions."

    def handle(self, *args, **options):
        inv = Permission.objects.filter(content_type__app_label="inventory")
        for name, codenames in ROLES.items():
            group, _ = Group.objects.get_or_create(name=name)
            perms = inv if codenames is None else inv.filter(codename__in=codenames)
            group.permissions.set(perms)
            self.stdout.write(self.style.SUCCESS(f"{name}: {perms.count()} permissions"))
        self.stdout.write("Now open Admin > Users, tick 'Staff status' and pick a group for each person.")
