import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("price", models.DecimalField(
                    decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(0)],
                )),
                ("stock", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ("sku",),
                "constraints": [models.CheckConstraint(
                    condition=models.Q(price__gte=0), name="product_nonnegative_price",
                )],
            },
        ),
    ]
