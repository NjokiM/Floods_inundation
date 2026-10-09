from django.core.management.base import BaseCommand

from sim.handlib.bake import SiteBaker
from sim.sitedata import site_nairobi, site_tana


class Command(BaseCommand):
    help = "Bake every site (Nairobi + Tana)."

    def handle(self, *args, **opts):
        for mod in (site_nairobi, site_tana):
            SiteBaker(mod).run()
        self.stdout.write(self.style.SUCCESS("bake_all done"))
