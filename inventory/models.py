from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

IN, OUT, RETURN, LOSS = "IN", "OUT", "RETURN", "LOSS"
ADD_TYPES = (IN, RETURN)      # these put pieces on the shelf
REMOVE_TYPES = (OUT, LOSS)    # these take pieces off the shelf

# permission needed to record each kind of movement
PERMS = {
    IN: "inventory.can_receive_stock",
    OUT: "inventory.can_issue_stock",
    RETURN: "inventory.can_return_stock",
    LOSS: "inventory.can_writeoff_stock",
}


class UniformType(models.Model):
    name = models.CharField(max_length=100, unique=True)  # e.g. Shirt, Trousers, Jacket

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockItem(models.Model):
    SIZES = [
        ("XS", "XS"), ("S", "S"), ("M", "M"), ("L", "L"),
        ("XL", "XL"), ("XXL", "XXL"), ("XXXL", "XXXL"),
    ]

    uniform_type = models.ForeignKey(UniformType, on_delete=models.PROTECT)
    size = models.CharField(max_length=10, choices=SIZES)
    reorder_level = models.PositiveIntegerField(
        default=5, help_text="Shown as LOW when the balance is at or below this number."
    )

    class Meta:
        unique_together = ("uniform_type", "size")
        ordering = ["uniform_type__name", "size"]

    @property
    def balance(self):
        totals = dict(
            self.movements.values_list("movement_type").annotate(total=Sum("quantity"))
        )
        return sum(totals.get(t, 0) for t in ADD_TYPES) - sum(totals.get(t, 0) for t in REMOVE_TYPES)

    @property
    def status(self):
        b = self.balance
        return "OUT" if b <= 0 else "LOW" if b <= self.reorder_level else "OK"

    def __str__(self):
        return f"{self.uniform_type} - {self.size}"


class StockMovement(models.Model):
    IN, OUT, RETURN, LOSS = IN, OUT, RETURN, LOSS
    TYPES = [(IN, "Received"), (OUT, "Issued"), (RETURN, "Returned"), (LOSS, "Written off")]

    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=10, choices=TYPES)
    quantity = models.PositiveIntegerField()
    date = models.DateField(default=timezone.localdate)
    issued_to = models.CharField(
        "person", max_length=150, blank=True,
        help_text="Who it was issued to / who returned it.",
    )
    note = models.CharField(
        max_length=255, blank=True,
        help_text="Delivery note, reason for write-off, condition of returned items...",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.SET_NULL, related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-date", "-id"]
        permissions = [
            ("can_receive_stock", "Can receive stock"),
            ("can_issue_stock", "Can issue stock"),
            ("can_return_stock", "Can record returned stock"),
            ("can_writeoff_stock", "Can write off lost or damaged stock"),
        ]

    # ---- helpers ---------------------------------------------------------
    @property
    def adds(self):
        return self.movement_type in ADD_TYPES

    @property
    def signed_quantity(self):
        return self.quantity if self.adds else -self.quantity

    @classmethod
    def held_by(cls, item, person, exclude_pk=None):
        """Pieces of `item` that `person` was issued and has not yet returned."""
        qs = cls.objects.filter(item=item, issued_to__iexact=person)
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        totals = dict(qs.values_list("movement_type").annotate(t=Sum("quantity")))
        return totals.get(OUT, 0) - totals.get(RETURN, 0)

    # ---- validation ------------------------------------------------------
    def clean(self):
        if not (self.item_id and self.quantity):
            return
        self.issued_to = (self.issued_to or "").strip()

        if self.movement_type in (OUT, RETURN) and not self.issued_to:
            verb = "issued to" if self.movement_type == OUT else "returned by"
            raise ValidationError(f"Enter who the stock was {verb}.")
        if self.movement_type == LOSS and not self.note.strip():
            raise ValidationError("Enter a reason for the write-off in the note.")

        if self.movement_type in REMOVE_TYPES:
            available = self.item.balance
            if self.pk:  # editing: take the old entry's effect out first
                old = StockMovement.objects.filter(pk=self.pk).first()
                if old and old.item_id == self.item_id:
                    available -= old.signed_quantity
            if self.quantity > available:
                raise ValidationError(f"Only {available} in stock.")

        if self.movement_type == RETURN:
            held = self.held_by(self.item, self.issued_to, exclude_pk=self.pk)
            if self.quantity > held:
                raise ValidationError(
                    f"{self.issued_to} only has {held} of this item still to return."
                )

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} x {self.item} on {self.date}"
