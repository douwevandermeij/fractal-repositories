from django.db import models  # type: ignore


class TestSubModel(models.Model):
    id = models.CharField(max_length=32, primary_key=True)
    name = models.CharField(max_length=32, default="test")
    item_id = models.CharField(max_length=32, default="")

    class Meta:
        app_label = "django"


class TestModel(models.Model):
    id = models.CharField(max_length=32, primary_key=True)
    name = models.CharField(max_length=32, default="test")
    description = models.CharField(max_length=32, default="")
    items = models.ForeignKey(TestSubModel, on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = "django"
