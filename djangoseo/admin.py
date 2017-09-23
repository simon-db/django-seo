# -*- coding: utf-8 -*-
from django import forms
from django.contrib import admin
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet
from django.contrib.contenttypes.admin import GenericStackedInline
from django.contrib.contenttypes.models import ContentType
from django.utils.encoding import smart_str
from django.forms.models import fields_for_model
from django.utils.translation import ugettext_lazy as _
from django.utils.text import capfirst

from djangoseo.utils import get_seo_content_types
from djangoseo.systemviews import get_seo_views


# TODO Use groups as fieldsets


def get_path_admin(use_site=False, use_subdomains=False):
    list_display = ['_path']
    search_fields = ['_path']
    list_filter = []
    if use_site:
        list_display.append('_site')
        list_filter.append('_site')
    if use_subdomains:
        list_display.append('_subdomain')
    return type('PathMetadataAdmin', (admin.ModelAdmin, ), {
        'list_display': tuple(list_display),
        'list_filter': tuple(list_filter),
        'search_fields': tuple(search_fields)
    })


def get_model_instance_admin(use_site=False, use_subdomains=False):
    list_display = ['_content_type', '_object_id', '_path']
    search_fields = ['_path', '_content_type__name']
    list_filter = []
    if use_site:
        list_display.append('_site')
        list_filter.append('_site')
    if use_subdomains:
        list_display.append('_subdomain')
    return type('ModelInstanceMetadataAdmin', (admin.ModelAdmin,), {
        'list_display': tuple(list_display),
        'list_filter': tuple(list_filter),
        'search_fields': tuple(search_fields)
    })


def get_model_admin(use_site=False, use_subdomains=False):
    list_display = ['_content_type']
    search_fields = ['_content_type__name']
    list_filter = []
    if use_site:
        list_display.append('_site')
        list_filter.append('_site')
    if use_subdomains:
        list_display.append('_subdomain')
    return type('ModelMetadataAdmin', (admin.ModelAdmin,), {
        'list_display': tuple(list_display),
        'list_filter': tuple(list_filter),
        'search_fields': tuple(search_fields)
    })


def get_view_admin(use_site=False, use_subdomains=False):
    list_display = ['_view']
    search_fields = ['_view']
    list_filter = []
    if use_site:
        list_display.append('_site')
        list_filter.append('_site')
    if use_subdomains:
        list_display.append('_subdomain')
    return type('ViewMetadataAdmin', (admin.ModelAdmin,), {
        'list_display': tuple(list_display),
        'list_filter': tuple(list_filter),
        'search_fields': tuple(search_fields)
    })


def register_seo_admin(admin_site, metadata_class):
    """ Register the backends specified in Meta.backends with the admin """
    use_sites = metadata_class._meta.use_sites
    use_subdomains = metadata_class._meta.use_subdomains

    path_admin = get_path_admin(use_sites, use_subdomains)
    model_instance_admin = get_model_instance_admin(use_sites, use_subdomains)
    model_admin = get_model_admin(use_sites, use_subdomains)
    view_admin = get_view_admin(use_sites, use_subdomains)

    def get_list_display():
        return tuple(name for name, obj in metadata_class._meta.elements.items()
                     if obj.editable)

    backends = metadata_class._meta.backends

    if 'model' in backends:
        class ModelAdmin(model_admin):
            form = get_model_form(metadata_class)
            list_display = model_admin.list_display + get_list_display()

        _register_admin(admin_site, metadata_class._meta.get_model('model'), ModelAdmin)

    if 'view' in backends:
        class ViewAdmin(view_admin):
            form = get_view_form(metadata_class)
            list_display = view_admin.list_display + get_list_display()

        _register_admin(admin_site, metadata_class._meta.get_model('view'), ViewAdmin)

    if 'path' in backends:
        class PathAdmin(path_admin):
            form = get_path_form(metadata_class)
            list_display = path_admin.list_display + get_list_display()

        _register_admin(admin_site, metadata_class._meta.get_model('path'), PathAdmin)

    if 'modelinstance' in backends:
        class ModelInstanceAdmin(model_instance_admin):
            form = get_modelinstance_form(metadata_class)
            list_display = model_instance_admin.list_display + get_list_display()

        _register_admin(admin_site, metadata_class._meta.get_model('modelinstance'), ModelInstanceAdmin)


def _register_admin(admin_site, model, admin_class):
    """ Register model in the admin, ignoring any previously registered models.
        Alternatively it could be used in the future to replace a previously
        registered model.
    """
    try:
        admin_site.register(model, admin_class)
    except admin.sites.AlreadyRegistered:
        pass


class MetadataFormset(BaseGenericInlineFormSet):
    def _construct_form(self, i, **kwargs):
        """ Override the method to change the form attribute empty_permitted """
        form = super(MetadataFormset, self)._construct_form(i, **kwargs)
        # Monkey patch the form to always force a save.
        # It's unfortunate, but necessary because we always want an instance
        # Affect on performance shouldn't be too great, because ther is only
        # ever one metadata attached
        form.empty_permitted = False
        form.has_changed = lambda: True

        # Set a marker on this object to prevent automatic metadata creation
        # This is seen by the post_save handler, which then skips this instance.
        if self.instance:
            self.instance.__seo_metadata_handled = True

        return form


def get_inline(metadata_class):
    attrs = {
        'max_num': 1,
        'extra': 1,
        'model': metadata_class._meta.get_model('modelinstance'),
        'ct_field': "_content_type",
        'ct_fk_field': "_object_id",
        'formset': MetadataFormset,
    }
    return type('MetadataInline', (GenericStackedInline,), attrs)


def get_model_form(metadata_class):
    model_class = metadata_class._meta.get_model('model')

    # Restrict content type choices to the models set in seo_models
    content_types = get_seo_content_types(metadata_class._meta.seo_models)
    content_type_choices = [(x._get_pk_val(), smart_str(x)) for x in
                            ContentType.objects.filter(id__in=content_types)]

    # Get a list of fields, with _content_type at the start
    important_fields = ['_content_type'] + core_choice_fields(metadata_class)
    _fields = important_fields + list(fields_for_model(model_class,
                                                  exclude=important_fields).keys())

    class ModelMetadataForm(forms.ModelForm):
        _content_type = forms.ChoiceField(label=capfirst(_("model")),
                                          choices=content_type_choices)

        class Meta:
            model = model_class
            fields = _fields

        def clean__content_type(self):
            value = self.cleaned_data['_content_type']
            try:
                return ContentType.objects.get(pk=int(value))
            except (ContentType.DoesNotExist, ValueError):
                raise forms.ValidationError("Invalid ContentType")

    return ModelMetadataForm


def get_modelinstance_form(metadata_class):
    model_class = metadata_class._meta.get_model('modelinstance')

    # Restrict content type choices to the models set in seo_models
    content_types = get_seo_content_types(metadata_class._meta.seo_models)

    # Get a list of fields, with _content_type at the start
    important_fields = ['_content_type'] + ['_object_id'] + core_choice_fields(metadata_class)
    _fields = important_fields + list(fields_for_model(model_class,
                                                  exclude=important_fields).keys())

    class ModelMetadataForm(forms.ModelForm):
        _content_type = forms.ModelChoiceField(
            queryset=ContentType.objects.filter(id__in=content_types),
            empty_label=None,
            label=capfirst(_("model")),
        )

        _object_id = forms.IntegerField(label=capfirst(_("ID")))

        class Meta:
            model = model_class
            fields = _fields

    return ModelMetadataForm


def get_path_form(metadata_class):
    model_class = metadata_class._meta.get_model('path')

    # Get a list of fields, with _view at the start
    important_fields = ['_path'] + core_choice_fields(metadata_class)
    _fields = important_fields + list(fields_for_model(model_class,
                                                  exclude=important_fields).keys())

    class ModelMetadataForm(forms.ModelForm):
        class Meta:
            model = model_class
            fields = _fields

    return ModelMetadataForm


def get_view_form(metadata_class):
    model_class = metadata_class._meta.get_model('view')

    # Restrict content type choices to the models set in seo_models
    view_choices = []
    for item in get_seo_views(metadata_class):
        if isinstance(item, list):
            view_choices.append((item[0], item[1]))
        else:
            view_choices.append((item, " ".join(item.split("_"))))
    
    view_choices.insert(0, ("", "---------"))

    # Get a list of fields, with _view at the start
    important_fields = ['_view'] + core_choice_fields(metadata_class)
    _fields = important_fields + list(fields_for_model(model_class,
                                                  exclude=important_fields).keys())

    class ModelMetadataForm(forms.ModelForm):
        _view = forms.ChoiceField(label=capfirst(_("view")),
                                  choices=view_choices, required=False)

        class Meta:
            model = model_class
            fields = _fields

    return ModelMetadataForm


def core_choice_fields(metadata_class):
    """ If the 'optional' core fields (_site and _language) are required,
        list them here.
    """
    fields = []
    if metadata_class._meta.use_sites:
        fields.append('_site')
    if metadata_class._meta.use_i18n:
        fields.append('_language')
    return fields


def _monkey_inline(model, admin_class_instance, metadata_class, inline_class, admin_site):
    """ Monkey patch the inline onto the given admin_class instance. """
    if model in metadata_class._meta.seo_models:
        # *Not* adding to the class attribute "inlines", as this will affect
        # all instances from this class. Explicitly adding to instance attribute.
        admin_class_instance.__dict__['inlines'] = admin_class_instance.inlines + [inline_class]

        # Because we've missed the registration, we need to perform actions
        # that were done then (on admin class instantiation)
        inline_instance = inline_class(admin_class_instance.model, admin_site)
        if hasattr(admin_class_instance, 'inline_instances'):
            admin_class_instance.inline_instances.append(inline_instance)


def _with_inline(func, admin_site, metadata_class, inline_class):
    """ Decorator for register function that adds an appropriate inline."""

    def register(model_or_iterable, admin_class=None, **options):
        # Call the (bound) function we were given.
        # We have to assume it will be bound to admin_site
        func(model_or_iterable, admin_class, **options)
        _monkey_inline(model_or_iterable, admin_site._registry[model_or_iterable],
                       metadata_class, inline_class, admin_site)

    return register


def auto_register_inlines(admin_site, metadata_class):
    """ This is a questionable function that automatically adds our metadata
        inline to all relevant models in the site.
    """
    inline_class = get_inline(metadata_class)

    for model, admin_class_instance in admin_site._registry.items():
        _monkey_inline(model, admin_class_instance, metadata_class, inline_class, admin_site)

    # Monkey patch the register method to automatically add an inline for this site.
    # _with_inline() is a decorator that wraps the register function with the same injection code
    # used above (_monkey_inline).
    admin_site.register = _with_inline(admin_site.register, admin_site, metadata_class, inline_class)
