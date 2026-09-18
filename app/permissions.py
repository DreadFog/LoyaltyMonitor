from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(view):
    """Limit a view to administrators after login_required has authenticated it."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view