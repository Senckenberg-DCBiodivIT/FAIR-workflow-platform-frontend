from django.core.management.base import BaseCommand
from cwr_frontend.api.models import CustomAPIKey, ApiKeyIdentity


class Command(BaseCommand):
    help = "Create an API key linked to an ORCID identity"

    def add_arguments(self, parser):
        parser.add_argument("--orcid", required=True, help="ORCID identifier (format XXXX-XXXX-XXXX-XXXX)")
        parser.add_argument("--name", required=True, help="Person name for the identity")
        parser.add_argument(
            "--key-name",
            default=None,
            help="Name for the API key (defaults to 'key-for-<ORCID>')",
        )

    def handle(self, *args, **options):
        orcid = options["orcid"]
        person_name = options["name"]
        key_name = options["key_name"] or f"key-for-{orcid}"

        identity, created = ApiKeyIdentity.objects.get_or_create(
            orcid=orcid, defaults={"name": person_name}
        )

        api_key_obj, raw_key = CustomAPIKey.objects.create_key(
            name=key_name, identity=identity
        )

        self.stdout.write(self.style.SUCCESS("API key created."))
        self.stdout.write("Save this API key securely (raw value shown only once):")
        self.stdout.write(raw_key)