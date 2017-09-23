#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import importlib

from django.apps import apps


def get_seo_views(metadata_class):
    return get_view_names(metadata_class._meta.seo_views)


def get_view_names(seo_views):
    print('eeve')
    output = []
    for name in seo_views:
        try:
            app = apps.get_app_config(name).models_module
        except:
            output.append(name)
        else:
            app_name = app.__name__.split(".")[:-1]
            app_name.append("urls")
            try:
                urls = importlib.import_module(".".join(app_name)).urlpatterns
            except (ImportError, AttributeError):
                output.append(name)
            else:
                for url in urls:
                    if getattr(url, 'name', None):
                        indefer = url.name 
                        try:
                            output.append([indefer, url.callback.view_class.SEO_NAME])
                        except AttributeError as e:
                            output.append(indefer)
    return output
