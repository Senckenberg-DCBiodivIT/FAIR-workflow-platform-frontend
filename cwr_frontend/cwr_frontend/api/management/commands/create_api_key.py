from django.core.management.base import BaseCommand
from cwr_frontend.api.models import CustomAPIKey, ApiKeyIdentity

IDENTIFIER_TYPES = ['orcid', 'doi', 'ror']

class Command(BaseCommand):
    help = "Create an API key linked to a persistent identifier"

    def add_arguments(self, parser):
        parser.add_argument('--type', choices=IDENTIFIER_TYPES, required=True,
                            help='Type of identifier (orcid, doi, ror)')
        parser.add_argument("--identifier", required=True, help="The identifier value (e.g., 0000-0002-1825-0097 or 10.3030/101181294)")
        parser.add_argument("--name", required=True, help="Name for the identity")
        parser.add_argument(
            "--key-name",
            default=None,
            help="Optional name for the API key",
        )

    def handle(self, *args, **options):
        id_type = options["type"]
        identifier = options["identifier"]
        name = options["name"]
        key_name = options["key_name"] or f"key-for-{identifier}"

        identity, created = ApiKeyIdentity.objects.get_or_create(
            id_type=id_type,
            identifier = identifier,
            defaults={"name": name}
        )

        identity.full_clean()

        api_key_obj, raw_key = CustomAPIKey.objects.create_key(
            name=key_name, identity=identity
        )

        self.stdout.write(self.style.SUCCESS("API key created."))
        self.stdout.write("Save this API key securely (raw value shown only once):")
        self.stdout.write(raw_key)