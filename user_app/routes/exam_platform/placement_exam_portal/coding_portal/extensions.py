"""Extension handles for the coding portal.

The standalone compiler created its own limiter/CSRF/CORS singletons. Inside
this app those already exist and are bound to the running application, so the
portal reuses them - two limiters would each keep separate counters and
neither would enforce the intended rate.
"""
from extensions import limiter  # noqa: F401  (re-exported for the portal's routes)
