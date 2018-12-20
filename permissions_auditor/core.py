from collections import namedtuple

from django.conf import ImproperlyConfigured, settings
from django.contrib.admindocs.views import simplify_regex
from django.urls.resolvers import RegexPattern, RoutePattern, URLPattern, URLResolver
from django.utils.module_loading import import_string

from . import defaults


def get_setting(name):
    return getattr(settings, name, getattr(defaults, name))


class ViewParser:

    def __init__(self):
        self.load_processors()

    def load_processors(self):
        self._processors = []

        for processor_path in get_setting('PERMISSIONS_AUDITOR_PROCESSORS'):

            try:
                processor = import_string(processor_path)
                self._processors.append(processor())
            except (ImportError, TypeError):
                raise ImproperlyConfigured(
                    '{} is not a valid permissions processor.'.format(processor_path)
                )

    def parse(self, view):
        """
        Process a view.

        Returns a tuple containing:
        permissions (list), login_required (boolean), docstrings (str)
        """
        permissions = []
        login_required = False
        docstrings = []

        for processor in self._processors:
            if processor.can_process(view):
                permissions.extend(processor.get_permission_required(view))
                login_required = processor.get_login_required(view) or login_required
                docstrings.append(processor.get_docstring(view))

        return permissions, login_required, '\n'.join(list(set(filter(None, docstrings))))


def get_all_views(urlpatterns=None, base_url=''):
    """
    Get all views in the specified urlpatterns.

    If urlpatterns is not specified, uses the `PERMISSIONS_AUDITOR_ROOT_URLCONF`
    setting, which by default is the value of `ROOT_URLCONF` in your project settings.

    Returns a list of namedtuples containing:
    module, name, url, permissions, login_required, docstring
    """
    if urlpatterns is None:
        root_urlconf = __import__(get_setting('PERMISSIONS_AUDITOR_ROOT_URLCONF'))
        urlpatterns = root_urlconf.urls.urlpatterns

    views = []
    result_tuple = namedtuple('View', [
        'module', 'name', 'url', 'permissions', 'login_required', 'docstring'
    ])

    parser = ViewParser()

    for pattern in urlpatterns:
        if isinstance(pattern, RoutePattern) or isinstance(pattern, URLResolver):

            # TODO: Namespace filtering
            # pattern.namespace

            # Recursively fetch patterns
            views.extend(get_all_views(pattern.url_patterns, base_url + str(pattern.pattern)))

        elif isinstance(pattern, URLPattern) or isinstance(pattern, RegexPattern):
            view = pattern.callback

            # If this is a CBV, use the actual class instead of the as_view() classmethod.
            view = getattr(view, 'view_class', view)

            # TODO: view name / module filtering
            # view.__module__ view.__name__

            permissions, login_required, docstring = parser.parse(view)

            views.append(result_tuple._make([
                view.__module__,
                view.__name__,
                simplify_regex(base_url + str(pattern.pattern)),
                permissions,
                login_required,
                docstring
            ]))

    return views
