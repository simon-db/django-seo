from django.apps.config import AppConfig

from djangoseo.models import setup


class SeoConfig(AppConfig):
    name = 'djangoseo'
    verbose_name = "SEO настройки"

    def ready(self):
        setup()
