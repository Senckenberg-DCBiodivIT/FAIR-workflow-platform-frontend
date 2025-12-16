from django.db import migrations

def forward_copy_orcid(apps, schema_editor):
    ApiKeyIdentity = apps.get_model("api", "ApiKeyIdentity")
    for obj in ApiKeyIdentity.objects.all():
        if obj.orcid:
            obj.id_type = "orcid"
            obj.identifier = obj.orcid
            obj.save(update_fields=["id_type", "identifier"])

def reverse_copy_orcid(apps, schema_editor):
    ApiKeyIdentity = apps.get_model("api", "ApiKeyIdentity")
    for obj in ApiKeyIdentity.objects.all():
        if obj.id_type == "orcid":
            obj.orcid = obj.identifier
            obj.save(update_fields=["orcid"])

class Migration(migrations.Migration):

    dependencies = [
        ("api", "0003_apikeyidentity_id_type_apikeyidentity_identifier_and_more"),
    ]

    operations = [
        migrations.RunPython(forward_copy_orcid, reverse_copy_orcid),
    ]
