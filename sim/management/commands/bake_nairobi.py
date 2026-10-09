from django.core.management.base import BaseCommand

from sim.handlib.bake import SiteBaker
from sim.sitedata import site_nairobi


class Command(BaseCommand):
    help = "Bake the Nairobi site data (DEM + HAND + assets) into static/data."

    def handle(self, *args, **opts):
        SiteBaker(site_nairobi).run()
        self.stdout.write(self.style.SUCCESS("bake_nairobi done"))
